import {
  REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY,
  REALTIME_TIMELINE_STORAGE_KEY,
  buildTodayResearchSnapshot,
  collectLocalResearchState,
  mergeResearchEntries,
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
    window.localStorage.setItem(INDUSTRY_ALERT_HISTORY_STORAGE_KEY, JSON.stringify({
      semiconductor: {
        industry_name: '半导体',
        hitCount: 2,
        priority: 120,
        firstSeenAt: Date.parse('2026-05-02T13:00:00.000Z'),
        lastSeenAt: Date.parse('2026-05-02T13:10:00.000Z'),
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
});
