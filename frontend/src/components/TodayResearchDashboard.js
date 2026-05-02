import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import {
  BellOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  ExportOutlined,
  FileTextOutlined,
  FireOutlined,
  ImportOutlined,
  LineChartOutlined,
  PlusOutlined,
  ReloadOutlined,
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
  TODAY_RESEARCH_PRIORITY_LABELS,
  TODAY_RESEARCH_STATUS_LABELS,
  TODAY_RESEARCH_TYPE_LABELS,
  buildTodayResearchSnapshot,
  collectLocalResearchState,
  filterResearchEntries,
  mergeResearchEntries,
  normalizeResearchEntry,
  summarizeResearchEntries,
} from '../utils/todayResearch';

const { Text, Title } = Typography;
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
  done: 'green',
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

  const handleMarkDone = useCallback(async (entry) => {
    try {
      const response = await updateResearchJournalEntryStatus(entry.id, 'done', profileId);
      setJournal(response?.data || journal);
      messageApi.success('已标记为完成');
    } catch (error) {
      console.error('Failed to update research journal status:', error);
      messageApi.error('状态更新失败');
    }
  }, [journal, messageApi, profileId]);

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

  const renderEntry = (entry) => (
    <div className="today-research-entry" key={entry.id} data-testid="today-research-entry">
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
        {entry.note ? <div className="today-research-entry__note">{entry.note}</div> : null}
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

  if (loading) {
    return (
      <div className="today-research-loading">
        <Spin size="large" />
        <Text type="secondary">正在整理今日研究档案...</Text>
      </div>
    );
  }

  return (
    <div className="today-research-page">
      <section className="today-research-hero">
        <div>
          <div className="app-page-section-kicker">DAILY RESEARCH</div>
          <Title level={1}>今日研究</Title>
          <p>
            把回测快照、行业观察、实时提醒和复盘记录收成一张桌面工作台，先处理队列，再回到具体模块深挖。
          </p>
          <Space wrap>
            <Button type="primary" icon={<CloudSyncOutlined />} loading={syncing} onClick={() => syncJournal()}>
              同步当前状态
            </Button>
            <Button icon={<ExportOutlined />} onClick={handleExportBackup}>
              导出备份
            </Button>
            <Button icon={<ImportOutlined />} onClick={() => setBackupVisible(true)}>
              导入备份
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => syncJournal()}>
              刷新
            </Button>
          </Space>
        </div>
        <div className="today-research-hero__metrics">
          <div className="today-research-metric">
            <span>待处理</span>
            <strong>{summary.open_entries || 0}</strong>
          </div>
          <div className="today-research-metric">
            <span>回测快照</span>
            <strong>{getMetricValue(summary, 'backtest')}</strong>
          </div>
          <div className="today-research-metric">
            <span>实时记录</span>
            <strong>{getMetricValue(summary, 'realtime_review') + getMetricValue(summary, 'realtime_alert') + getMetricValue(summary, 'trade_plan')}</strong>
          </div>
          <div className="today-research-metric">
            <span>行业观察</span>
            <strong>{getMetricValue(summary, 'industry_watch') + getMetricValue(summary, 'industry_alert')}</strong>
          </div>
        </div>
      </section>

      <div className="today-research-grid">
        <Card className="today-research-panel today-research-panel--queue">
          <div className="today-research-panel__head">
            <div>
              <div className="today-research-panel__title">处理队列</div>
              <div className="today-research-panel__desc">优先看仍处于待处理或跟踪中的线索。</div>
            </div>
            <Tag color="orange">{actionQueue.length} 条</Tag>
          </div>
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
          <div className="today-research-entry-list">
            {actionQueue.length ? actionQueue.slice(0, 8).map(renderEntry) : (
              <Empty description="当前没有待处理项" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>
        </Card>

        <Card className="today-research-panel">
          <div className="today-research-panel__head">
            <div>
              <div className="today-research-panel__title">新增记录</div>
              <div className="today-research-panel__desc">盘前计划、人工判断或临时线索可以直接沉淀到档案。</div>
            </div>
            <PlusOutlined />
          </div>
          <Form layout="vertical" form={form} onFinish={handleCreateManualEntry}>
            <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
              <Input placeholder="例如：半导体龙头继续跟踪" />
            </Form.Item>
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="symbol" label="标的" style={{ flex: 1 }}>
                <Input placeholder="AAPL / 600519" />
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
        </Card>
      </div>

      <div className="today-research-grid today-research-grid--secondary">
        <Card className="today-research-panel">
          <div className="today-research-panel__head">
            <div>
              <div className="today-research-panel__title">标的时间线</div>
              <div className="today-research-panel__desc">按标的聚合回测、提醒和复盘，方便回看链路。</div>
            </div>
            <Tag>{symbolTimeline.length} 个标的</Tag>
          </div>
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
        </Card>

        <Card className="today-research-panel">
          <div className="today-research-panel__head">
            <div>
              <div className="today-research-panel__title">数据来源</div>
              <div className="today-research-panel__desc">当前页从这些已有模块收集状态。</div>
            </div>
            <Tag color="green">本地 + 后端</Tag>
          </div>
          <div className="today-research-source-grid">
            <div><span>回测快照</span><strong>{sourceCounts.backtest_snapshots || 0}</strong></div>
            <div><span>复盘快照</span><strong>{sourceCounts.realtime_review_snapshots || 0}</strong></div>
            <div><span>实时提醒</span><strong>{sourceCounts.realtime_alert_hit_history || 0}</strong></div>
            <div><span>行业观察</span><strong>{sourceCounts.industry_watchlist || 0}</strong></div>
            <div><span>行业提醒</span><strong>{sourceCounts.industry_alert_history || 0}</strong></div>
            <div><span>提醒规则</span><strong>{sourceCounts.price_alert_rules || 0}</strong></div>
          </div>
          <Alert
            className="today-research-backup-alert"
            type="success"
            showIcon
            message="档案已接入后端快照"
            description={`当前 profile: ${profileId}，最近同步 ${formatTime(journal.updated_at || journal.generated_at)}。`}
          />
        </Card>
      </div>

      <Card className="today-research-panel">
        <div className="today-research-panel__head">
          <div>
            <div className="today-research-panel__title">完整档案流</div>
            <div className="today-research-panel__desc">所有来源统一成一条可回看的研究流。</div>
          </div>
          <Tag color={hasActiveEntryFilters ? 'blue' : undefined}>
            {hasActiveEntryFilters ? `${filteredEntries.length} / ${entries.length} 条` : `${entries.length} 条`}
          </Tag>
        </div>
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
      </Card>

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
