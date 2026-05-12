import {
  REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY,
  REALTIME_TIMELINE_STORAGE_KEY,
  buildTodayResearchSnapshot,
  collectLocalResearchState,
  deriveResearchActionQueue,
  deriveResearchInboxEntries,
  filterResearchEntries,
  filterResearchInboxEntries,
  groupResearchInboxEntries,
  mergeResearchEntries,
  normalizeResearchEntry,
  summarizeResearchEntries,
} from '../utils/todayResearch';
import { BACKTEST_RESEARCH_SNAPSHOTS_KEY } from '../utils/backtestWorkspace';
import { ALERT_HIT_HISTORY_STORAGE_KEY } from '../utils/realtimeSignals';
import {
  INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
  INDUSTRY_WATCHLIST_STORAGE_KEY,
} from '../components/industry/industryShared';

describe('today research aggregation utilities', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test('normalizes lifecycle metadata without dropping notes or timestamps', () => {
    const entry = normalizeResearchEntry({
      id: 0,
      type: 'realtime_alert',
      status: 'snoozed',
      title: 'BTC 提醒命中',
      status_updated_at: '2026-05-12T10:30:00.000Z',
      lifecycle: {
        status: 'snoozed',
        note: 0,
        updated_at: '2026-05-12T10:31:00.000Z',
      },
    });

    expect(entry.id).toBe('0');
    expect(entry.status_updated_at).toBe('2026-05-12T10:30:00.000Z');
    expect(entry.lifecycle).toEqual({
      status: 'snoozed',
      note: '0',
      updated_at: '2026-05-12T10:31:00.000Z',
    });
  });

  test('builds a unified snapshot from backtest, realtime and industry local state', () => {
    window.localStorage.setItem(BACKTEST_RESEARCH_SNAPSHOTS_KEY, JSON.stringify([
      {
        id: 'bt-1',
        created_at: '2026-05-02T09:00:00.000Z',
        symbol: 'AAPL',
        strategy: 'buy_and_hold',
        note: '继续观察',
        metrics: {
          total_return: 0.12,
          max_drawdown: -0.05,
          sharpe_ratio: 1.2,
          num_trades: 1,
        },
      },
    ]));
    window.localStorage.setItem(REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'review-1',
        createdAt: '2026-05-02T10:00:00.000Z',
        spotlightSymbol: 'MSFT',
        activeTabLabel: '美股',
        outcome: 'pending',
      },
    ]));
    window.localStorage.setItem(REALTIME_TIMELINE_STORAGE_KEY, JSON.stringify([
      {
        id: 'plan-1',
        kind: 'trade_plan',
        symbol: 'NVDA',
        title: 'NVDA 买入计划',
        createdAt: '2026-05-02T11:00:00.000Z',
      },
    ]));
    window.localStorage.setItem(ALERT_HIT_HISTORY_STORAGE_KEY, JSON.stringify([
      {
        id: 'hit-1',
        symbol: 'BTC-USD',
        message: 'BTC 提醒命中',
        triggerTime: '2026-05-02T12:00:00.000Z',
      },
    ]));
    window.localStorage.setItem(INDUSTRY_WATCHLIST_STORAGE_KEY, JSON.stringify(['半导体']));
    const freshIndustrySeenAt = Date.now() - 10 * 60 * 1000;
    window.localStorage.setItem(INDUSTRY_ALERT_HISTORY_STORAGE_KEY, JSON.stringify({
      semiconductor: {
        industry_name: '半导体',
        hitCount: 2,
        priority: 120,
        firstSeenAt: freshIndustrySeenAt - 10 * 60 * 1000,
        lastSeenAt: freshIndustrySeenAt,
      },
    }));

    const localState = collectLocalResearchState();
    const snapshot = buildTodayResearchSnapshot(localState);
    const summary = summarizeResearchEntries(snapshot.entries);

    expect(snapshot.entries.map((entry) => entry.type)).toEqual(expect.arrayContaining([
      'backtest',
      'realtime_review',
      'trade_plan',
      'realtime_alert',
      'industry_watch',
      'industry_alert',
    ]));
    expect(snapshot.source_state.counts.backtest_snapshots).toBe(1);
    expect(summary.open_entries).toBeGreaterThanOrEqual(5);
    expect(summary.symbol_count).toBeGreaterThanOrEqual(4);
  });

  test('merges entries by id and keeps the freshest status', () => {
    const merged = mergeResearchEntries([
      {
        id: 'entry-1',
        type: 'backtest',
        title: '旧记录',
        status: 'open',
        updated_at: '2026-05-02T09:00:00.000Z',
      },
      {
        id: 'entry-1',
        type: 'backtest',
        title: '新记录',
        status: 'done',
        updated_at: '2026-05-02T10:00:00.000Z',
      },
    ]);

    expect(merged).toHaveLength(1);
    expect(merged[0].status).toBe('done');
    expect(merged[0].title).toBe('新记录');
  });

  test('preserves falsy non-null legacy research entry values before fallbacks', () => {
    const normalized = normalizeResearchEntry({
      id: 0,
      type: 'manual',
      title: 0,
      summary: 0,
      note: false,
      symbol: 0,
      industry: 0,
      industry_name: 'fallback-industry',
      source: 0,
      source_label: 0,
      sourceLabel: 'fallback-label',
      tags: [0, false, ' focus ', 'focus', null, ''],
    }, 7);

    expect(normalized.id).toBe('0');
    expect(normalized.title).toBe('0');
    expect(normalized.summary).toBe('0');
    expect(normalized.note).toBe('false');
    expect(normalized.symbol).toBe('0');
    expect(normalized.industry).toBe('0');
    expect(normalized.source).toBe('0');
    expect(normalized.source_label).toBe('0');
    expect(normalized.tags).toEqual(['0', 'focus']);
  });

  test('filters entries by status, priority, type and keyword', () => {
    const entries = [
      {
        id: 'entry-open',
        type: 'backtest',
        title: 'AAPL 均线回测',
        status: 'open',
        priority: 'high',
        symbol: 'AAPL',
        tags: ['趋势'],
        updated_at: '2026-05-02T09:00:00.000Z',
      },
      {
        id: 'entry-watch',
        type: 'industry_watch',
        title: '半导体 行业观察',
        status: 'watching',
        priority: 'medium',
        industry: '半导体',
        updated_at: '2026-05-02T10:00:00.000Z',
      },
      {
        id: 'entry-done',
        type: 'manual',
        title: '复核完成',
        status: 'done',
        priority: 'low',
        note: '已经归档到周报',
        updated_at: '2026-05-02T11:00:00.000Z',
      },
    ];

    expect(filterResearchEntries(entries, { status: 'active' }).map((entry) => entry.id)).toEqual([
      'entry-open',
      'entry-watch',
    ]);
    expect(filterResearchEntries(entries, { status: 'done' }).map((entry) => entry.id)).toEqual([
      'entry-done',
    ]);
    expect(filterResearchEntries(entries, { priority: 'high', type: 'backtest' }).map((entry) => entry.id)).toEqual([
      'entry-open',
    ]);
    expect(filterResearchEntries(entries, { keyword: '半导体' }).map((entry) => entry.id)).toEqual([
      'entry-watch',
    ]);
    expect(filterResearchEntries(entries, { keyword: '回测快照' }).map((entry) => entry.id)).toEqual([
      'entry-open',
    ]);
  });

  test('derives deterministic inbox buckets and priorities from existing research fields', () => {
    const inboxEntries = deriveResearchInboxEntries([
      {
        id: 'fresh-alert',
        type: 'realtime_alert',
        title: 'BTC 提醒命中',
        status: 'watching',
        priority: 'medium',
        source: 'realtime_alert_hit_history',
        updated_at: '2026-05-12T09:30:00.000Z',
        tags: ['alert', false, 7, null],
        action: { view: 'realtime', label: '打开实时看盘' },
      },
      {
        id: 'watch-industry',
        type: 'industry_watch',
        title: '半导体观察',
        status: 'watching',
        priority: 'medium',
        source: 'industry_watchlist',
        updated_at: '2026-05-12T08:00:00.000Z',
        tags: ['观察'],
        action: { view: 'industry', label: '打开行业热度' },
      },
      {
        id: 'finished-note',
        type: 'manual',
        title: '复核完成',
        status: 'done',
        priority: 'high',
        source: 'manual_entry',
        updated_at: '2026-05-12T07:00:00.000Z',
      },
      {
        id: 'old-open',
        type: 'manual',
        title: '旧线索',
        status: 'open',
        priority: 'medium',
        source: 'manual_entry',
        updated_at: '2026-04-20T07:00:00.000Z',
        action: { view: 'today', label: '打开' },
      },
      {
        id: 'archived-note',
        type: 'manual',
        title: '已归档',
        status: 'archived',
        priority: 'high',
        source: 'manual_entry',
        updated_at: '2026-05-12T06:00:00.000Z',
      },
    ], { now: '2026-05-12T10:00:00.000Z' });

    expect(inboxEntries.map((entry) => entry.id)).toEqual([
      'fresh-alert',
      'watch-industry',
      'old-open',
      'finished-note',
      'archived-note',
    ]);
    expect(inboxEntries.find((entry) => entry.id === 'fresh-alert')).toMatchObject({
      inbox_bucket: 'actionable',
      inbox_status: 'actionable',
      inbox_priority: 'high',
    });
    expect(inboxEntries.find((entry) => entry.id === 'fresh-alert').inbox_tags).toEqual(['alert', '7']);
    expect(inboxEntries.find((entry) => entry.id === 'watch-industry')).toMatchObject({
      inbox_bucket: 'watch',
      inbox_priority: 'medium',
    });
    expect(inboxEntries.find((entry) => entry.id === 'old-open')).toMatchObject({
      inbox_bucket: 'read_later',
      inbox_priority: 'low',
    });
    expect(inboxEntries.find((entry) => entry.id === 'finished-note')).toMatchObject({
      inbox_bucket: 'read_later',
      inbox_priority: 'low',
    });
    expect(inboxEntries.find((entry) => entry.id === 'archived-note')).toMatchObject({
      inbox_bucket: 'archived',
      inbox_priority: 'low',
    });
  });

  test('groups and filters research inbox entries by deterministic buckets', () => {
    const entries = [
      {
        id: 'plan',
        type: 'trade_plan',
        title: 'NVDA 买入计划',
        status: 'open',
        priority: 'medium',
        updated_at: '2026-05-12T09:00:00.000Z',
        tags: ['交易计划'],
        action: { view: 'realtime', label: '打开计划' },
      },
      {
        id: 'watch',
        type: 'industry_watch',
        title: '半导体观察',
        status: 'watching',
        priority: 'medium',
        updated_at: '2026-05-12T08:00:00.000Z',
      },
      {
        id: 'archive',
        type: 'manual',
        title: '旧归档',
        status: 'archived',
        priority: 'high',
        updated_at: '2026-05-12T07:00:00.000Z',
      },
    ];

    const groups = groupResearchInboxEntries(entries, { now: '2026-05-12T10:00:00.000Z' });

    expect(groups.actionable.map((entry) => entry.id)).toEqual(['plan']);
    expect(groups.watch.map((entry) => entry.id)).toEqual(['watch']);
    expect(groups.read_later).toEqual([]);
    expect(groups.archived.map((entry) => entry.id)).toEqual(['archive']);
    expect(filterResearchInboxEntries(entries, { bucket: 'actionable' }, { now: '2026-05-12T10:00:00.000Z' }).map((entry) => entry.id)).toEqual(['plan']);
    expect(filterResearchInboxEntries(entries, { bucket: 'watch', priority: 'medium' }, { now: '2026-05-12T10:00:00.000Z' }).map((entry) => entry.id)).toEqual(['watch']);
  });

  test('derives deterministic research actions from inbox entries without leaking boolean tags', () => {
    const actions = deriveResearchActionQueue([
      {
        id: 'watch-industry',
        type: 'industry_watch',
        title: '半导体观察',
        status: 'watching',
        priority: 'medium',
        source: 'industry_watchlist',
        updated_at: '2026-05-12T08:00:00.000Z',
        tags: ['观察'],
        action: { view: 'industry', label: '打开行业热度' },
      },
      {
        id: 'fresh-alert',
        type: 'realtime_alert',
        title: 'BTC 提醒命中',
        status: 'watching',
        priority: 'medium',
        source: 'realtime_alert_hit_history',
        updated_at: '2026-05-12T09:30:00.000Z',
        tags: [false, null, 0, 'alert'],
        action: { view: 'realtime', label: false },
      },
      {
        id: 0,
        type: 'trade_plan',
        title: 0,
        status: 'open',
        priority: 'high',
        symbol: 0,
        updated_at: '2026-05-12T09:00:00.000Z',
        tags: [false, 0],
      },
      {
        id: 'done-note',
        type: 'manual',
        title: '已完成记录',
        status: 'done',
        priority: 'high',
        updated_at: '2026-05-12T07:00:00.000Z',
      },
      {
        id: 'archived-note',
        type: 'manual',
        title: '已归档',
        status: 'archived',
        priority: 'high',
        updated_at: '2026-05-12T06:00:00.000Z',
      },
    ], { now: '2026-05-12T10:00:00.000Z' });

    expect(actions.map((action) => action.entry_id)).toEqual([
      'fresh-alert',
      '0',
      'watch-industry',
    ]);
    expect(actions[0]).toMatchObject({
      key: 'research_action:fresh-alert',
      kind: 'review_alert',
      label: '复核提醒',
      inbox_bucket: 'actionable',
      priority: 'high',
      entry_title: 'BTC 提醒命中',
      source_label: '实时提醒',
    });
    expect(actions[0].tags).toEqual(['0', 'alert']);
    expect(actions[1]).toMatchObject({
      key: 'research_action:0',
      kind: 'confirm_trade_plan',
      label: '确认交易计划',
      entry_title: '0',
      symbol: '0',
    });
    expect(actions[2]).toMatchObject({
      kind: 'follow_watchlist',
      label: '跟进行业观察',
      inbox_bucket: 'watch',
    });
    expect(JSON.stringify(actions)).not.toContain('false');
    expect(JSON.stringify(actions)).not.toContain('null');
  });

  test('keeps snoozed actions in an explicit non-actionable bucket and excludes dismissed actions', () => {
    const actions = deriveResearchActionQueue([
      {
        id: 'open-alert',
        type: 'realtime_alert',
        title: 'BTC 提醒命中',
        status: 'open',
        priority: 'high',
        updated_at: '2026-05-12T09:30:00.000Z',
      },
      {
        id: 'snoozed-plan',
        type: 'trade_plan',
        title: 'NVDA 买入计划',
        status: 'snoozed',
        priority: 'high',
        updated_at: '2026-05-12T09:20:00.000Z',
      },
      {
        id: 'dismissed-alert',
        type: 'industry_alert',
        title: '已忽略提醒',
        status: 'dismissed',
        priority: 'high',
        updated_at: '2026-05-12T09:10:00.000Z',
      },
      {
        id: 'done-backtest',
        type: 'backtest',
        title: '已完成回测',
        status: 'done',
        priority: 'high',
        updated_at: '2026-05-12T09:00:00.000Z',
      },
    ], { now: '2026-05-12T10:00:00.000Z' });

    expect(actions.map((action) => action.entry_id)).toEqual(['open-alert', 'snoozed-plan']);
    expect(actions.map((action) => action.inbox_bucket)).toEqual(['actionable', 'snoozed']);
  });

  test('summarizes research actions alongside legacy summary fields', () => {
    const entries = [
      {
        id: 'alert',
        type: 'realtime_alert',
        title: 'BTC 提醒命中',
        status: 'watching',
        priority: 'medium',
        updated_at: '2026-05-12T09:00:00.000Z',
        tags: [false, 'alert'],
      },
      {
        id: 'watch',
        type: 'industry_watch',
        title: '半导体观察',
        status: 'watching',
        priority: 'medium',
        updated_at: '2026-05-12T08:00:00.000Z',
      },
      {
        id: 'done',
        type: 'manual',
        title: '完成记录',
        status: 'done',
        priority: 'high',
        updated_at: '2026-05-12T07:00:00.000Z',
      },
    ];

    const summary = summarizeResearchEntries(entries, { now: '2026-05-12T10:00:00.000Z' });

    expect(summary.action_queue.map((entry) => entry.id)).toEqual(['alert', 'watch']);
    expect(summary.research_actions.map((action) => action.entry_id)).toEqual(['alert', 'watch']);
    expect(summary.research_action_counts).toEqual({
      total: 2,
      actionable: 1,
      watch: 1,
      snoozed: 0,
      read_later: 0,
      high: 1,
    });
  });
});
