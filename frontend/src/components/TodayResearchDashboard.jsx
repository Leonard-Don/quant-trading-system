import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App as AntdApp,
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  BellOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudSyncOutlined,
  ExportOutlined,
  FileTextOutlined,
  FireOutlined,
  ImportOutlined,
  LineChartOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import {
  createResearchJournalEntry,
  getResearchJournalSnapshot,
  updateResearchJournalEntryStatus,
  updateResearchJournalSnapshot,
} from '../services/api';
import { loadRealtimeProfileId } from '../hooks/useRealtimePreferences';
import { buildAppUrl, navigateToAppUrl } from '../utils/researchContext';
import {
  RESEARCH_INBOX_BUCKET_LABELS,
  RESEARCH_INBOX_BUCKET_ORDER,
  TODAY_RESEARCH_PRIORITY_LABELS,
  TODAY_RESEARCH_STATUS_LABELS,
  TODAY_RESEARCH_TYPE_LABELS,
  buildTodayResearchSnapshot,
  collectLocalResearchState,
  deriveResearchActionQueue,
  deriveResearchInboxEntries,
  filterResearchEntries,
  groupResearchInboxEntries,
  mergeResearchEntries,
  normalizeResearchEntry,
  summarizeResearchActionQueue,
  summarizeResearchEntries,
} from '../utils/todayResearch';
import {
  MetricGrid,
  PageHero,
  Panel,
  StatCard,
  StatusPill,
  Surface,
  Toolbar,
} from '../design/components';
import { FadeIn, Stagger } from '../design/motion';

const { Text } = Typography;
const { TextArea } = Input;

const TYPE_ICON = {
  backtest: <BarChartOutlined />,
  realtime_review: <LineChartOutlined />,
  realtime_alert: <BellOutlined />,
  realtime_event: <LineChartOutlined />,
  industry_watch: <FireOutlined />,
  industry_alert: <FireOutlined />,
  manual: <FileTextOutlined />,
  trade_plan: <CheckCircleOutlined />,
};

const TYPE_COLOR = {
  backtest: 'blue',
  realtime_review: 'cyan',
  realtime_alert: 'orange',
  realtime_event: 'geekblue',
  industry_watch: 'purple',
  industry_alert: 'magenta',
  manual: 'default',
  trade_plan: 'green',
};

const PRIORITY_COLOR = {
  high: 'red',
  medium: 'gold',
  low: 'blue',
};

const STATUS_COLOR = {
  open: 'orange',
  watching: 'processing',
  snoozed: 'gold',
  done: 'green',
  dismissed: 'default',
  archived: 'default',
};

const INBOX_BUCKET_COLOR = {
  actionable: 'volcano',
  watch: 'processing',
  snoozed: 'gold',
  read_later: 'default',
  archived: 'default',
};

const EMPTY_JOURNAL = {
  entries: [],
  summary: summarizeResearchEntries([]),
  source_state: {},
  generated_at: null,
  updated_at: null,
};
const EMPTY_ENTRIES = [];

const WORKBENCH_FLOW_STEPS = [
  {
    key: 'collect',
    icon: <FileTextOutlined />,
    title: '线索收件',
    description: '回测、实时行情、行业观察记录统一汇入。',
  },
  {
    key: 'triage',
    icon: <ThunderboltOutlined />,
    title: '排队分层',
    description: '按需处理、继续观察、稍后回看拆成今日行动清单。',
  },
  {
    key: 'return',
    icon: <ClockCircleOutlined />,
    title: '回到上下文',
    description: '处理完线索后，保留标的时间线和完整复盘档案。',
  },
];

const DEFAULT_ENTRY_FILTERS = {
  status: 'all',
  priority: 'all',
  type: 'all',
  keyword: '',
};

const STATUS_FILTER_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '待处理/跟踪', value: 'active' },
  ...Object.entries(TODAY_RESEARCH_STATUS_LABELS).map(([value, label]) => ({ value, label })),
];

const PRIORITY_FILTER_OPTIONS = [
  { label: '全部优先级', value: 'all' },
  ...Object.entries(TODAY_RESEARCH_PRIORITY_LABELS).map(([value, label]) => ({
    value,
    label: `优先级 ${label}`,
  })),
];

const TYPE_FILTER_OPTIONS = [
  { label: '全部类型', value: 'all' },
  ...Object.entries(TODAY_RESEARCH_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

const formatTime = (value) => {
  if (!value) return '未同步';
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return '未同步';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
};

const mergeLocalWithBackend = (localSnapshot, backendEntries = []) => {
  const backendById = new Map(backendEntries.map((entry, index) => [
    entry.id,
    normalizeResearchEntry(entry, index),
  ]));
  const localEntries = mergeResearchEntries(localSnapshot.entries || []);
  const localIds = new Set(localEntries.map((entry) => entry.id));
  const mergedLocal = localEntries.map((entry) => {
    const backendEntry = backendById.get(entry.id);
    if (!backendEntry) {
      return entry;
    }
    return {
      ...entry,
      status: backendEntry.status || entry.status,
      priority: backendEntry.priority || entry.priority,
      note: entry.note || backendEntry.note,
      updated_at: backendEntry.updated_at || entry.updated_at,
      status_updated_at: backendEntry.status_updated_at || entry.status_updated_at,
      lifecycle: Object.keys(backendEntry.lifecycle || {}).length
        ? backendEntry.lifecycle
        : entry.lifecycle,
    };
  });
  const backendOnly = Array.from(backendById.values()).filter((entry) => !localIds.has(entry.id));
  return {
    ...localSnapshot,
    entries: mergeResearchEntries([...mergedLocal, ...backendOnly]),
  };
};

const getMetricValue = (summary, key) => Number(summary?.type_counts?.[key] || 0);

const TodayResearchDashboard = () => {
  const { message: messageApi } = AntdApp.useApp();
  const [journal, setJournal] = useState(EMPTY_JOURNAL);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [backupVisible, setBackupVisible] = useState(false);
  const [backupText, setBackupText] = useState('');
  const [entryFilters, setEntryFilters] = useState(DEFAULT_ENTRY_FILTERS);
  const [form] = Form.useForm();
  const profileId = useMemo(() => loadRealtimeProfileId(), []);

  const summary = journal.summary || summarizeResearchEntries(journal.entries);
  const sourceCounts = journal.source_state?.counts || {};
  const actionQueue = summary.action_queue || [];
  const nextActions = summary.next_actions || [];
  const symbolTimeline = summary.symbol_timeline || [];
  const entries = journal.entries || EMPTY_ENTRIES;
  const inboxOptions = useMemo(() => ({
    now: journal.updated_at || journal.generated_at,
  }), [journal.generated_at, journal.updated_at]);
  const inboxEntries = useMemo(
    () => deriveResearchInboxEntries(entries, inboxOptions),
    [entries, inboxOptions]
  );
  const inboxGroups = useMemo(
    () => groupResearchInboxEntries(entries, inboxOptions),
    [entries, inboxOptions]
  );
  const inboxPreviewEntries = useMemo(
    () => inboxEntries.filter((entry) => entry.inbox_bucket !== 'archived').slice(0, 6),
    [inboxEntries]
  );
  const researchActions = useMemo(() => (
    Array.isArray(summary.research_actions)
      ? summary.research_actions
      : deriveResearchActionQueue(entries, inboxOptions)
  ), [entries, inboxOptions, summary.research_actions]);
  const researchActionCounts = useMemo(() => (
    summary.research_action_counts && typeof summary.research_action_counts === 'object'
      ? { ...summarizeResearchActionQueue([]), ...summary.research_action_counts }
      : summarizeResearchActionQueue(researchActions)
  ), [researchActions, summary.research_action_counts]);
  const visibleResearchActions = useMemo(
    () => researchActions.slice(0, 5),
    [researchActions]
  );
  const activeEntries = useMemo(
    () => entries.filter((entry) => entry.status === 'open' || entry.status === 'watching'),
    [entries]
  );
  const highPriorityActiveCount = useMemo(
    () => activeEntries.filter((entry) => entry.priority === 'high').length,
    [activeEntries]
  );
  const primaryQueueEntry = actionQueue[0] || null;
  const visibleQueueEntries = primaryQueueEntry ? actionQueue.slice(1, 5) : actionQueue.slice(0, 5);
  const hiddenQueueCount = Math.max(actionQueue.length - (primaryQueueEntry ? 1 : 0) - visibleQueueEntries.length, 0);
  const isJournalEmpty = entries.length === 0;
  const filteredEntries = useMemo(
    () => filterResearchEntries(entries, entryFilters),
    [entries, entryFilters]
  );
  const hasActiveEntryFilters = useMemo(() => (
    entryFilters.status !== DEFAULT_ENTRY_FILTERS.status
      || entryFilters.priority !== DEFAULT_ENTRY_FILTERS.priority
      || entryFilters.type !== DEFAULT_ENTRY_FILTERS.type
      || String(entryFilters.keyword || '').trim() !== DEFAULT_ENTRY_FILTERS.keyword
  ), [entryFilters]);

  const syncJournal = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) {
      setSyncing(true);
    }
    setLoading((current) => current && !quiet);
    try {
      const localSnapshot = buildTodayResearchSnapshot(collectLocalResearchState());
      let backendEntries = [];
      try {
        const backendResponse = await getResearchJournalSnapshot(profileId);
        backendEntries = Array.isArray(backendResponse?.data?.entries)
          ? backendResponse.data.entries
          : [];
      } catch (error) {
        backendEntries = [];
      }
      const mergedSnapshot = mergeLocalWithBackend(localSnapshot, backendEntries);
      const response = await updateResearchJournalSnapshot(mergedSnapshot, profileId);
      const nextJournal = response?.data || {
        ...mergedSnapshot,
        summary: summarizeResearchEntries(mergedSnapshot.entries),
      };
      setJournal(nextJournal);
      if (!quiet) {
        messageApi.success('今日研究档案已同步');
      }
    } catch (error) {
      console.error('Failed to sync research journal:', error);
      if (!quiet) {
        messageApi.warning('同步失败，已保留本地汇总视图');
      }
      const fallbackSnapshot = buildTodayResearchSnapshot(collectLocalResearchState());
      setJournal({
        ...fallbackSnapshot,
        summary: summarizeResearchEntries(fallbackSnapshot.entries),
      });
    } finally {
      setLoading(false);
      setSyncing(false);
    }
  }, [messageApi, profileId]);

  useEffect(() => {
    syncJournal({ quiet: true });
  }, [syncJournal]);

  const handleOpenEntry = useCallback((entry) => {
    const action = entry.action || {};
    if (action.view === 'backtest') {
      navigateToAppUrl(buildAppUrl({
        view: 'backtest',
        tab: action.tab || (entry.symbol ? 'history' : 'new'),
        historySymbol: entry.symbol || undefined,
      }));
      return;
    }
    if (action.view === 'realtime') {
      navigateToAppUrl(buildAppUrl({ view: 'realtime' }));
      return;
    }
    if (action.view === 'industry') {
      navigateToAppUrl(buildAppUrl({ view: 'industry' }));
      return;
    }
    navigateToAppUrl(buildAppUrl({ view: 'today' }));
  }, []);

  const handleOpenModule = useCallback((view) => {
    navigateToAppUrl(buildAppUrl({ view }));
  }, []);

  const handleUpdateEntryStatus = useCallback(async (entry, status, options = {}) => {
    try {
      const response = await updateResearchJournalEntryStatus(
        entry.id,
        status,
        profileId,
        options.note
      );
      setJournal(response?.data || journal);
      messageApi.success(options.successMessage || '状态已更新');
    } catch (error) {
      console.error('Failed to update research journal status:', error);
      messageApi.error('状态更新失败');
    }
  }, [journal, messageApi, profileId]);

  const handleMarkDone = useCallback((entry, note = undefined) => {
    handleUpdateEntryStatus(entry, 'done', {
      note,
      successMessage: '已标记为完成',
    });
  }, [handleUpdateEntryStatus]);

  const handleResearchActionLifecycle = useCallback((action, status, note, successMessage) => {
    const entry = entries.find((item) => String(item.id) === String(action.entry_id));
    handleUpdateEntryStatus(entry || { id: action.entry_id }, status, {
      note,
      successMessage,
    });
  }, [entries, handleUpdateEntryStatus]);

  const handleCreateManualEntry = useCallback(async (values) => {
    const createdAt = new Date().toISOString();
    const entry = {
      id: `manual:${Date.now()}`,
      type: 'manual',
      status: 'open',
      priority: values.priority || 'medium',
      title: values.title,
      summary: values.summary,
      note: values.note,
      symbol: values.symbol,
      industry: values.industry,
      source: 'manual_entry',
      source_label: '手动记录',
      created_at: createdAt,
      updated_at: createdAt,
      tags: ['手动记录'],
      action: values.symbol ? { view: 'realtime', symbol: values.symbol, label: '打开实时看盘' } : { view: 'today' },
    };
    try {
      const response = await createResearchJournalEntry(entry, profileId);
      setJournal(response?.data || journal);
      form.resetFields();
      messageApi.success('已加入研究档案');
    } catch (error) {
      console.error('Failed to create research journal entry:', error);
      messageApi.error('新增记录失败');
    }
  }, [form, journal, messageApi, profileId]);

  const handleExportBackup = useCallback(async () => {
    const payload = {
      version: 1,
      profile_id: profileId,
      exported_at: new Date().toISOString(),
      journal,
    };
    const text = JSON.stringify(payload, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      messageApi.success('研究档案备份 JSON 已复制');
    } catch (error) {
      setBackupText(text);
      setBackupVisible(true);
      messageApi.warning('无法写入剪贴板，已打开备份文本');
    }
  }, [journal, messageApi, profileId]);

  const handleImportBackup = useCallback(async () => {
    try {
      const parsed = JSON.parse(backupText);
      const importedJournal = parsed?.journal || parsed;
      const importedEntries = Array.isArray(importedJournal?.entries)
        ? importedJournal.entries
        : [];
      const nextSnapshot = {
        entries: mergeResearchEntries(importedEntries),
        source_state: importedJournal?.source_state || { imported: true },
        generated_at: importedJournal?.generated_at || new Date().toISOString(),
      };
      const response = await updateResearchJournalSnapshot(nextSnapshot, profileId);
      setJournal(response?.data || {
        ...nextSnapshot,
        summary: summarizeResearchEntries(nextSnapshot.entries),
      });
      setBackupVisible(false);
      setBackupText('');
      messageApi.success('研究档案备份已导入');
    } catch (error) {
      messageApi.error('导入失败，请检查 JSON 格式');
    }
  }, [backupText, messageApi, profileId]);

  const handleEntryFilterChange = useCallback((key, value) => {
    setEntryFilters((current) => ({
      ...current,
      [key]: value,
    }));
  }, []);

  const handleEntryKeywordChange = useCallback((event) => {
    handleEntryFilterChange('keyword', event.target.value);
  }, [handleEntryFilterChange]);

  const handleClearEntryFilters = useCallback(() => {
    setEntryFilters({ ...DEFAULT_ENTRY_FILTERS });
  }, []);

  const renderEntry = (entry, options = {}) => {
    const { compact = false } = options;
    return (
      <div
        className={`today-research-entry${compact ? ' today-research-entry--compact' : ''}`}
        key={entry.id}
        data-testid="today-research-entry"
      >
        <div className="today-research-entry__icon">{TYPE_ICON[entry.type] || <FileTextOutlined />}</div>
        <div className="today-research-entry__main">
          <Space wrap size={6}>
            <Tag color={TYPE_COLOR[entry.type]}>{TODAY_RESEARCH_TYPE_LABELS[entry.type]}</Tag>
            <Tag color={STATUS_COLOR[entry.status]}>{TODAY_RESEARCH_STATUS_LABELS[entry.status]}</Tag>
            <Tag color={PRIORITY_COLOR[entry.priority]}>优先级 {TODAY_RESEARCH_PRIORITY_LABELS[entry.priority]}</Tag>
            {entry.symbol ? <Tag>{entry.symbol}</Tag> : null}
            {entry.industry ? <Tag>{entry.industry}</Tag> : null}
          </Space>
          <div className="today-research-entry__title">{entry.title}</div>
          {entry.summary ? <div className="today-research-entry__summary">{entry.summary}</div> : null}
          {!compact && entry.note ? <div className="today-research-entry__note">{entry.note}</div> : null}
          <div className="today-research-entry__meta">
            {entry.source_label || entry.source} · {formatTime(entry.updated_at)}
          </div>
        </div>
        <Space className="today-research-entry__actions" wrap>
          <Button size="small" onClick={() => handleOpenEntry(entry)}>
            {entry.action?.label || '打开'}
          </Button>
          {entry.status !== 'done' && entry.status !== 'archived' ? (
            <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleMarkDone(entry)}>
              完成
            </Button>
          ) : null}
        </Space>
      </div>
    );
  };

  const renderInboxEntry = (entry) => (
    <button
      type="button"
      className="today-research-inbox-item"
      key={entry.id}
      onClick={() => handleOpenEntry(entry)}
    >
      <div className="today-research-inbox-item__top">
        <Tag color={INBOX_BUCKET_COLOR[entry.inbox_bucket]}>
          {RESEARCH_INBOX_BUCKET_LABELS[entry.inbox_bucket]}
        </Tag>
        <Tag color={PRIORITY_COLOR[entry.inbox_priority]}>
          优先级 {TODAY_RESEARCH_PRIORITY_LABELS[entry.inbox_priority]}
        </Tag>
        {entry.inbox_tags.map((tag) => (
          <Tag key={`${entry.id}:${tag}`}>{tag}</Tag>
        ))}
      </div>
      <strong>{entry.title}</strong>
      <span>{entry.inbox_reason} · {entry.source_label || entry.source} · {formatTime(entry.updated_at)}</span>
    </button>
  );

  const renderResearchAction = (action) => {
    const entry = entries.find((item) => String(item.id) === String(action.entry_id));
    const priorityLabel = TODAY_RESEARCH_PRIORITY_LABELS[action.priority] || TODAY_RESEARCH_PRIORITY_LABELS.medium;
    const bucketColor = action.inbox_bucket === 'actionable'
      ? 'volcano'
      : INBOX_BUCKET_COLOR[action.inbox_bucket] || 'processing';
    return (
      <div className="today-research-action-item" key={action.key || action.entry_id}>
        <button
          type="button"
          className="today-research-action-item__open"
          onClick={() => handleOpenEntry(entry || { action: action.action || {}, symbol: action.symbol })}
        >
          <div className="today-research-action-item__top">
            <Tag color={bucketColor}>
              {action.label || '打开上下文'}
            </Tag>
            <Tag color={PRIORITY_COLOR[action.priority]}>优先级 {priorityLabel}</Tag>
            {action.symbol ? <Tag>{action.symbol}</Tag> : null}
            {action.industry ? <Tag>{action.industry}</Tag> : null}
            {(action.tags || []).map((tag) => (
              <Tag key={`${action.key || action.entry_id}:${tag}`}>{tag}</Tag>
            ))}
          </div>
          <strong>{action.entry_title || '研究行动'}</strong>
          <span>{action.description}</span>
        </button>
        <Space className="today-research-action-item__controls" wrap size={6}>
          <Button
            size="small"
            icon={<CheckCircleOutlined />}
            onClick={() => handleResearchActionLifecycle(
              action,
              'done',
              '已从研究行动完成',
              '已标记为完成'
            )}
          >
            完成
          </Button>
          <Button
            size="small"
            icon={<ClockCircleOutlined />}
            onClick={() => handleResearchActionLifecycle(
              action,
              'snoozed',
              '稍后复核',
              '已稍后处理'
            )}
          >
            稍后
          </Button>
          <Button
            size="small"
            icon={<StopOutlined />}
            onClick={() => handleResearchActionLifecycle(
              action,
              'dismissed',
              '从今日行动队列忽略',
              '已从行动队列忽略'
            )}
          >
            忽略
          </Button>
        </Space>
      </div>
    );
  };

  const renderManualEntryCard = () => (
    <Panel
      icon={<PlusOutlined />}
      title="新增记录"
      actions={<span className="text-xs text-subtle">盘前计划、人工判断或临时线索</span>}
    >
      <p className="mb-3 text-sm leading-relaxed text-muted">
        盘前计划、人工判断或临时线索可以直接沉淀到档案。
      </p>
      <Form layout="vertical" form={form} onFinish={handleCreateManualEntry}>
        <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
          <Input placeholder="例如：半导体龙头继续跟踪" />
        </Form.Item>
        <Space.Compact style={{ width: '100%' }}>
          <Form.Item name="symbol" label="标的" style={{ flex: 1 }}>
            <Input placeholder="600519.SS / AAPL" />
          </Form.Item>
          <Form.Item name="industry" label="行业" style={{ flex: 1 }}>
            <Input placeholder="半导体" />
          </Form.Item>
        </Space.Compact>
        <Form.Item name="priority" label="优先级" initialValue="medium">
          <Select
            options={[
              { label: '高', value: 'high' },
              { label: '中', value: 'medium' },
              { label: '低', value: 'low' },
            ]}
          />
        </Form.Item>
        <Form.Item name="summary" label="摘要">
          <Input placeholder="一句话说明为什么要跟踪" />
        </Form.Item>
        <Form.Item name="note" label="记录">
          <TextArea rows={4} placeholder="写下判断依据、下一步动作或需要复核的数据源" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block>
          加入研究档案
        </Button>
      </Form>
    </Panel>
  );

  const renderEmptyWorkbench = () => (
    <Panel className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="text-xs uppercase tracking-widest text-accent">今日入口</div>
        <div className="text-base font-medium text-fg">先把第一条线索放进工作台</div>
        <p className="text-sm leading-relaxed text-muted">
          工作台会把回测快照、实时复盘、行业观察和人工判断统一成可回看的研究流。
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button icon={<BarChartOutlined />} onClick={() => handleOpenModule('backtest')}>
          跑一次回测
        </Button>
        <Button icon={<LineChartOutlined />} onClick={() => handleOpenModule('realtime')}>
          保存实时复盘
        </Button>
        <Button icon={<FireOutlined />} onClick={() => handleOpenModule('industry')}>
          加入行业观察
        </Button>
      </div>
    </Panel>
  );

  const renderPrimaryQueueEntry = () => {
    if (!primaryQueueEntry) {
      return (
        <div className="today-research-focus-card today-research-focus-card--empty">
          <Empty description="当前没有待处理项" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      );
    }

    return (
      <div className="today-research-focus-card">
        <div className="today-research-focus-card__meta">
          <span>当前优先项</span>
          <Tag color={PRIORITY_COLOR[primaryQueueEntry.priority]}>
            优先级 {TODAY_RESEARCH_PRIORITY_LABELS[primaryQueueEntry.priority]}
          </Tag>
        </div>
        <div className="today-research-focus-card__title">{primaryQueueEntry.title}</div>
        <p>
          {primaryQueueEntry.summary || primaryQueueEntry.note || '先打开上下文确认是否需要升级为回测、复盘或交易计划。'}
        </p>
        <Space wrap>
          <Button type="primary" size="small" onClick={() => handleOpenEntry(primaryQueueEntry)}>
            {primaryQueueEntry.action?.label || '打开'}
          </Button>
          <Button size="small" icon={<CheckCircleOutlined />} onClick={() => handleMarkDone(primaryQueueEntry)}>
            完成
          </Button>
        </Space>
      </div>
    );
  };

  const renderResearchInboxCard = () => (
    <Panel
      testId="today-research-inbox"
      title="研究收件箱"
      actions={<StatusPill tone="info">{inboxEntries.length} 条</StatusPill>}
      className="flex flex-col gap-3"
    >
      <p className="text-sm leading-relaxed text-muted">把今天的线索先分成可处理、继续观察和稍后回看。</p>
      <MetricGrid className="grid-cols-2 sm:grid-cols-5">
        {RESEARCH_INBOX_BUCKET_ORDER.map((bucket) => (
          <StatCard
            key={bucket}
            label={RESEARCH_INBOX_BUCKET_LABELS[bucket]}
            value={inboxGroups[bucket]?.length || 0}
            accent={bucket === 'actionable'}
          />
        ))}
      </MetricGrid>
      <div className="today-research-inbox-list">
        {inboxPreviewEntries.length ? inboxPreviewEntries.map(renderInboxEntry) : (
          <Empty description="收件箱暂无可展示线索" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
    </Panel>
  );

  const renderResearchActionsCard = () => (
    <Panel
      testId="today-research-actions"
      title="研究行动"
      actions={<StatusPill tone="warn">{researchActionCounts.total || 0} 条</StatusPill>}
      className="flex flex-col gap-3"
    >
      <p className="text-sm leading-relaxed text-muted">提醒、计划和观察名单的下一步处理清单。</p>
      <MetricGrid className="grid-cols-2 sm:grid-cols-4">
        <StatCard label="需处理" value={researchActionCounts.actionable || 0} accent />
        <StatCard label="继续观察" value={researchActionCounts.watch || 0} />
        <StatCard label="稍后" value={researchActionCounts.snoozed || 0} />
        <StatCard label="高优先级" value={researchActionCounts.high || 0} />
      </MetricGrid>
      <div className="today-research-action-list">
        {visibleResearchActions.length ? visibleResearchActions.map(renderResearchAction) : (
          <Empty description="暂无下一步研究行动" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
    </Panel>
  );

  if (loading) {
    return (
      <div className="today-research-loading">
        <Spin size="large" />
        <Text type="secondary">正在整理研究工作台...</Text>
      </div>
    );
  }

  return (
    <div className="today-research-page flex flex-col gap-4">
      <FadeIn>
        <PageHero
          eyebrow="今日线索、提醒与复盘档案"
          title="研究工作台"
          subtitle="把分散在回测、实时行情、行业热度里的线索收成一张日内工作台，先判断轻重缓急，再回到具体模块深挖。"
          metrics={(
            <MetricGrid className="basis-96">
              <StatCard label="待处理" value={summary.open_entries || 0} />
              <StatCard label="回测快照" value={getMetricValue(summary, 'backtest')} accent />
              <StatCard
                label="实时记录"
                value={getMetricValue(summary, 'realtime_review') + getMetricValue(summary, 'realtime_alert') + getMetricValue(summary, 'trade_plan')}
              />
              <StatCard
                label="行业观察"
                value={getMetricValue(summary, 'industry_watch') + getMetricValue(summary, 'industry_alert')}
              />
            </MetricGrid>
          )}
        />
      </FadeIn>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone="info">活跃线索 {activeEntries.length} 条</StatusPill>
          <StatusPill tone="warn">高优先级 {highPriorityActiveCount} 条</StatusPill>
          <StatusPill tone="neutral">最近同步 {formatTime(journal.updated_at || journal.generated_at)}</StatusPill>
        </div>
        <Toolbar>
          <Button type="primary" icon={<CloudSyncOutlined />} loading={syncing} onClick={() => syncJournal()}>
            同步当前状态
          </Button>
          <Tooltip title="刷新">
            <Button aria-label="刷新" icon={<ReloadOutlined />} onClick={() => syncJournal()} />
          </Tooltip>
          <Tooltip title="导出备份">
            <Button aria-label="导出备份" icon={<ExportOutlined />} onClick={handleExportBackup} />
          </Tooltip>
          <Tooltip title="导入备份">
            <Button aria-label="导入备份" icon={<ImportOutlined />} onClick={() => setBackupVisible(true)} />
          </Tooltip>
        </Toolbar>
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="研究工作台流程">
        {WORKBENCH_FLOW_STEPS.map((step) => (
          <Surface key={step.key} className="flex items-start gap-3 p-4">
            <span className="text-accent" aria-hidden="true">{step.icon}</span>
            <div className="flex flex-col gap-1">
              <strong className="text-sm font-medium text-fg">{step.title}</strong>
              <span className="text-xs leading-relaxed text-muted">{step.description}</span>
            </div>
          </Surface>
        ))}
      </section>

      {isJournalEmpty ? (
        <div className="today-research-grid today-research-grid--empty">
          {renderEmptyWorkbench()}
          {renderManualEntryCard()}
        </div>
      ) : (
        <Stagger className="flex flex-col gap-4">
          {renderResearchInboxCard()}
          {renderResearchActionsCard()}

          <div className="today-research-grid">
            <Panel
              title="处理队列"
              actions={<StatusPill tone="warn">{actionQueue.length} 条</StatusPill>}
              className="flex flex-col gap-3"
            >
              <p className="text-sm leading-relaxed text-muted">优先看仍处于待处理或跟踪中的线索。</p>
              {renderPrimaryQueueEntry()}
              {nextActions.length ? (
                <div className="today-research-next-actions">
                  {nextActions.map((action) => (
                    <Alert
                      key={action.key}
                      type={action.key === 'review_high_alerts' ? 'warning' : 'info'}
                      showIcon
                      message={action.title}
                      description={action.description}
                    />
                  ))}
                </div>
              ) : null}
              <div className="today-research-entry-list today-research-entry-list--compact">
                {visibleQueueEntries.map((entry) => renderEntry(entry, { compact: true }))}
              </div>
              {hiddenQueueCount > 0 ? (
                <div className="today-research-queue-footnote text-xs text-subtle">
                  其余 {hiddenQueueCount} 条仍保留在下方完整档案流中，避免首屏重复铺满。
                </div>
              ) : null}
            </Panel>

            {renderManualEntryCard()}
          </div>

          <div className="today-research-grid today-research-grid--secondary">
            <Panel
              title="标的时间线"
              actions={<StatusPill tone="neutral">{symbolTimeline.length} 个标的</StatusPill>}
              className="flex flex-col gap-3"
            >
              <p className="text-sm leading-relaxed text-muted">按标的聚合回测、提醒和复盘，方便回看链路。</p>
              {symbolTimeline.length ? (
                <div className="today-research-symbol-list">
                  {symbolTimeline.map((item) => (
                    <div className="today-research-symbol" key={item.symbol}>
                      <div className="today-research-symbol__head">
                        <strong>{item.symbol}</strong>
                        <Tag>{item.count} 条</Tag>
                      </div>
                      <div className="today-research-symbol__events">
                        {(item.entries || []).slice(0, 4).map((entry) => (
                          <button key={entry.id} type="button" onClick={() => handleOpenEntry(entry)}>
                            <span>{TODAY_RESEARCH_TYPE_LABELS[entry.type]}</span>
                            <strong>{entry.title}</strong>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty description="还没有标的级记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Panel>

            <Panel
              title="数据来源"
              actions={<StatusPill tone="success">本地 + 后端</StatusPill>}
              className="flex flex-col gap-3"
            >
              <p className="text-sm leading-relaxed text-muted">当前页从这些已有模块收集状态。</p>
              <MetricGrid className="grid-cols-2 sm:grid-cols-3">
                <StatCard label="回测快照" value={sourceCounts.backtest_snapshots || 0} />
                <StatCard label="复盘快照" value={sourceCounts.realtime_review_snapshots || 0} />
                <StatCard label="实时提醒" value={sourceCounts.realtime_alert_hit_history || 0} />
                <StatCard label="行业观察" value={sourceCounts.industry_watchlist || 0} />
                <StatCard label="行业提醒" value={sourceCounts.industry_alert_history || 0} />
                <StatCard label="提醒规则" value={sourceCounts.price_alert_rules || 0} />
              </MetricGrid>
              <Alert
                className="today-research-backup-alert"
                type="success"
                showIcon
                message="档案已接入后端快照"
                description={`当前 profile: ${profileId}，最近同步 ${formatTime(journal.updated_at || journal.generated_at)}。`}
              />
            </Panel>
          </div>

          <Panel
            title="完整档案流"
            actions={(
              <StatusPill tone={hasActiveEntryFilters ? 'info' : 'neutral'}>
                {hasActiveEntryFilters ? `${filteredEntries.length} / ${entries.length} 条` : `${entries.length} 条`}
              </StatusPill>
            )}
            className="flex flex-col gap-3"
          >
            <p className="text-sm leading-relaxed text-muted">所有来源统一成一条可回看的研究流。</p>
            <div className="today-research-filter-bar">
              <Space wrap size={[10, 10]} className="today-research-filter-bar__controls">
                <Select
                  aria-label="按状态筛选研究档案"
                  className="today-research-filter-bar__select"
                  value={entryFilters.status}
                  options={STATUS_FILTER_OPTIONS}
                  onChange={(value) => handleEntryFilterChange('status', value)}
                />
                <Select
                  aria-label="按优先级筛选研究档案"
                  className="today-research-filter-bar__select"
                  value={entryFilters.priority}
                  options={PRIORITY_FILTER_OPTIONS}
                  onChange={(value) => handleEntryFilterChange('priority', value)}
                />
                <Select
                  aria-label="按类型筛选研究档案"
                  className="today-research-filter-bar__select"
                  value={entryFilters.type}
                  options={TYPE_FILTER_OPTIONS}
                  onChange={(value) => handleEntryFilterChange('type', value)}
                />
                <Input.Search
                  allowClear
                  aria-label="筛选研究档案"
                  className="today-research-filter-bar__search"
                  placeholder="搜索标的、行业或记录"
                  value={entryFilters.keyword}
                  onChange={handleEntryKeywordChange}
                  onSearch={(value) => handleEntryFilterChange('keyword', value)}
                />
                <Button disabled={!hasActiveEntryFilters} onClick={handleClearEntryFilters}>
                  清除筛选
                </Button>
              </Space>
              <div className="today-research-filter-bar__summary">
                显示 <strong>{filteredEntries.length}</strong> / {entries.length} 条
              </div>
            </div>
            <div className="today-research-entry-list today-research-entry-list--archive">
              {filteredEntries.length ? filteredEntries.map(renderEntry) : (
                <Empty description={hasActiveEntryFilters ? '当前筛选没有匹配记录' : '还没有研究档案，先跑一次回测或保存一条实时复盘快照。'} />
              )}
            </div>
          </Panel>
        </Stagger>
      )}

      <Modal
        title="研究档案备份"
        open={backupVisible}
        onCancel={() => setBackupVisible(false)}
        onOk={handleImportBackup}
        okText="导入"
        cancelText="关闭"
        width={760}
      >
        <Text type="secondary">粘贴导出的 JSON，可以恢复统一档案快照。</Text>
        <TextArea
          style={{ marginTop: 12 }}
          rows={12}
          value={backupText}
          onChange={(event) => setBackupText(event.target.value)}
          placeholder="粘贴研究档案 JSON"
        />
      </Modal>
    </div>
  );
};

export default TodayResearchDashboard;
