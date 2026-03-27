import {
  buildAlertDraftFromAnomaly,
  buildAlertDraftFromTradePlan,
  buildRealtimeAnomalyFeed,
  buildTradePlanDraftFromAnomaly,
  evaluateRealtimeAlert,
  getAlertConditionLabel,
  normalizePriceAlert,
} from '../utils/realtimeSignals';

describe('realtimeSignals utilities', () => {
  test('normalizes legacy price alert conditions', () => {
    expect(normalizePriceAlert({
      symbol: 'AAPL',
      condition: 'above',
      price: 150,
    })).toEqual(expect.objectContaining({
      symbol: 'AAPL',
      condition: 'price_above',
      threshold: 150,
    }));
  });

  test('evaluates percentage-based realtime alerts', () => {
    const result = evaluateRealtimeAlert(
      {
        symbol: 'NVDA',
        condition: 'change_pct_above',
        threshold: 3,
      },
      {
        price: 900,
        change_percent: 4.2,
      }
    );

    expect(result.triggered).toBe(true);
    expect(result.message).toContain('NVDA');
    expect(result.message).toContain('4.20%');
  });

  test('builds anomaly radar entries for strong movers and volume spikes', () => {
    const feed = buildRealtimeAnomalyFeed(
      ['AAPL', 'MSFT', 'NVDA'],
      {
        AAPL: {
          price: 201,
          change_percent: 2.5,
          volume: 900,
          high: 201.02,
          low: 194,
          previous_close: 195,
          _clientReceivedAt: Date.now(),
        },
        MSFT: {
          price: 401,
          change_percent: 0.4,
          volume: 120,
          high: 401.02,
          low: 398,
          previous_close: 399,
          _clientReceivedAt: Date.now(),
        },
        NVDA: {
          price: 880,
          change_percent: -2.8,
          volume: 110,
          high: 910,
          low: 878,
          previous_close: 905,
          _clientReceivedAt: Date.now(),
        },
      },
      { limit: 6 }
    );

    expect(feed.some((item) => item.symbol === 'AAPL' && item.kind === 'price_up')).toBe(true);
    expect(feed.some((item) => item.symbol === 'AAPL' && item.kind === 'volume_spike')).toBe(true);
    expect(feed.some((item) => item.symbol === 'NVDA' && item.kind === 'price_down')).toBe(true);
  });

  test('formats human-readable alert labels', () => {
    expect(getAlertConditionLabel({
      condition: 'intraday_range_above',
      threshold: 4.5,
    })).toBe('日内振幅 ≥ 4.50%');
  });

  test('builds alert drafts from anomaly feed items', () => {
    const draft = buildAlertDraftFromAnomaly(
      {
        symbol: 'AAPL',
        kind: 'volume_spike',
        title: '放量异动',
        description: 'AAPL 当前成交量约为分组中位数的 2.6 倍。',
      },
      {
        volume: 260,
      },
      {
        AAPL: { volume: 260 },
        MSFT: { volume: 100 },
        NVDA: { volume: 90 },
      }
    );

    expect(draft).toEqual(expect.objectContaining({
      symbol: 'AAPL',
      condition: 'relative_volume_above',
      threshold: 3,
      sourceTitle: '放量异动',
    }));
  });

  test('builds trade plan drafts from anomaly feed items', () => {
    const draft = buildTradePlanDraftFromAnomaly(
      {
        symbol: 'NVDA',
        kind: 'price_up',
        title: '强势拉升',
        description: 'NVDA 当前涨幅 3.20%，处于盘中强势区间。',
      },
      {
        price: 920.16,
        low: 901.2,
        high: 926.8,
      }
    );

    expect(draft).toEqual(expect.objectContaining({
      symbol: 'NVDA',
      action: 'BUY',
      quantity: 25,
      limitPrice: 920.16,
      suggestedEntry: 920.16,
      sourceTitle: '强势拉升',
    }));
    expect(draft.stopLoss).toBeLessThan(draft.suggestedEntry);
    expect(draft.takeProfit).toBeGreaterThan(draft.suggestedEntry);
  });

  test('builds alert drafts from trade plans for entry and stop control', () => {
    const planDraft = {
      symbol: 'AAPL',
      action: 'BUY',
      suggestedEntry: 195.2,
      stopLoss: 191.8,
      takeProfit: 201.5,
      sourceTitle: '强势拉升',
    };

    expect(buildAlertDraftFromTradePlan(planDraft, 'entry')).toEqual(expect.objectContaining({
      symbol: 'AAPL',
      condition: 'price_above',
      threshold: 195.2,
      sourceTitle: '强势拉升 · 入场提醒',
    }));

    expect(buildAlertDraftFromTradePlan(planDraft, 'stop')).toEqual(expect.objectContaining({
      symbol: 'AAPL',
      condition: 'price_below',
      threshold: 191.8,
      sourceTitle: '强势拉升 · 止损提醒',
    }));
  });
});
