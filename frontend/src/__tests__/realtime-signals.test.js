import {
  buildAlertHitHistoryEntry,
  buildAlertDraftFromAnomaly,
  buildAlertDraftFromTradePlan,
  buildRealtimeAnomalyFeed,
  buildTradePlanDraftFromAnomaly,
  evaluateAlertHitFollowThrough,
  evaluateRealtimeAlert,
  getAlertConditionLabel,
  normalizePriceAlert,
  summarizeAlertHitFollowThrough,
  summarizeAlertHitHistory,
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
    expect(feed.find((item) => item.symbol === 'NVDA' && item.kind === 'price_down')).toEqual(
      expect.objectContaining({
        level: 'medium',
        label: '关注',
      })
    );
    expect(feed.find((item) => item.symbol === 'AAPL' && item.kind === 'volume_spike')).toEqual(
      expect.objectContaining({
        level: 'critical',
        label: '极强',
      })
    );
  });

  test('uses asset-type adaptive thresholds for anomaly detection', () => {
    const feed = buildRealtimeAnomalyFeed(
      ['AAPL', 'BTC-USD'],
      {
        AAPL: {
          price: 201,
          change_percent: 3.8,
          volume: 260,
          high: 203,
          low: 196,
          previous_close: 194,
          _clientReceivedAt: Date.now(),
        },
        'BTC-USD': {
          price: 70200,
          change_percent: 3.8,
          volume: 1200,
          high: 70800,
          low: 68100,
          previous_close: 67620,
          _clientReceivedAt: Date.now(),
        },
      },
      { limit: 8 }
    );

    expect(feed.some((item) => item.symbol === 'AAPL' && item.kind === 'price_up')).toBe(true);
    expect(feed.some((item) => item.symbol === 'BTC-USD' && item.kind === 'price_up')).toBe(false);
    expect(feed.some((item) => item.symbol === 'BTC-USD' && item.kind === 'range_expansion')).toBe(false);
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

  test('builds alert hit history entries and summarizes them', () => {
    const firstHit = buildAlertHitHistoryEntry({
      alert: {
        id: 'alert-1',
        symbol: 'AAPL',
        condition: 'price_above',
        threshold: 195.2,
      },
      triggerValue: 196.4,
      message: 'AAPL 当前价格 $196.40 已突破 $195.20',
      quote: {
        price: 196.4,
        change_percent: 1.8,
        high: 197.2,
        low: 191.6,
        previous_close: 193.1,
      },
    });
    const secondHit = buildAlertHitHistoryEntry({
      alert: {
        id: 'alert-2',
        symbol: 'AAPL',
        condition: 'price_above',
        threshold: 198.8,
      },
      triggerValue: 199.1,
      message: 'AAPL 当前价格 $199.10 已突破 $198.80',
      quote: {
        price: 199.1,
        change_percent: 2.4,
        high: 200.2,
        low: 196.1,
        previous_close: 194.4,
      },
    });

    expect(firstHit).toEqual(expect.objectContaining({
      symbol: 'AAPL',
      conditionLabel: '价格 ≥ $195.20',
      triggerPrice: 196.4,
      triggerValue: 196.4,
    }));

    expect(summarizeAlertHitHistory([secondHit, firstHit])).toEqual(expect.objectContaining({
      totalHits: 2,
      uniqueSymbols: 1,
      topSymbol: 'AAPL · 2 次',
      topCondition: '价格 ≥ $198.80 · 1 次',
    }));
  });

  test('evaluates follow-through after alert hits', () => {
    const continued = evaluateAlertHitFollowThrough(
      {
        symbol: 'AAPL',
        condition: 'price_above',
        threshold: 195.2,
        triggerPrice: 196.4,
      },
      { price: 198.1 }
    );
    const reversed = evaluateAlertHitFollowThrough(
      {
        symbol: 'TSLA',
        condition: 'price_below',
        threshold: 170.5,
        triggerPrice: 169.9,
      },
      { price: 173.2 }
    );

    expect(continued).toEqual(expect.objectContaining({
      state: 'continued',
      label: '命中后仍在阈值上方',
    }));
    expect(reversed).toEqual(expect.objectContaining({
      state: 'reversed',
      label: '命中后回到阈值上方',
    }));

    expect(summarizeAlertHitFollowThrough([
      { symbol: 'AAPL', condition: 'price_above', threshold: 195.2, triggerPrice: 196.4 },
      { symbol: 'TSLA', condition: 'price_below', threshold: 170.5, triggerPrice: 169.9 },
    ], {
      AAPL: { price: 198.1 },
      TSLA: { price: 173.2 },
    })).toEqual({
      continued: 1,
      reversed: 1,
      pending: 0,
    });
  });

  test('evaluates non-price alert follow-through by original condition semantics', () => {
    expect(evaluateAlertHitFollowThrough(
      {
        symbol: 'AAPL',
        condition: 'change_pct_above',
        threshold: 3,
        triggerPrice: 195.1,
      },
      {
        price: 196.4,
        change_percent: 3.4,
      }
    )).toEqual(expect.objectContaining({
      state: 'continued',
      label: '命中后涨幅仍然成立',
    }));

    expect(evaluateAlertHitFollowThrough(
      {
        symbol: 'AAPL',
        condition: 'intraday_range_above',
        threshold: 4,
      },
      {
        price: 196.4,
        high: 198.1,
        low: 190.2,
        previous_close: 194,
      }
    )).toEqual(expect.objectContaining({
      state: 'continued',
      label: '命中后振幅仍在放大',
    }));

    expect(evaluateAlertHitFollowThrough(
      {
        symbol: 'AAPL',
        condition: 'relative_volume_above',
        threshold: 2,
      },
      {
        price: 196.4,
        volume: 320,
      },
      {
        AAPL: { volume: 320 },
        MSFT: { volume: 100 },
        NVDA: { volume: 120 },
      }
    )).toEqual(expect.objectContaining({
      state: 'continued',
      label: '命中后仍在相对放量',
    }));
  });
});
