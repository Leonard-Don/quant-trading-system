import {
  buildCrossMarketLink,
  buildGodEyeLink,
  buildPricingLink,
  buildViewUrlForCurrentState,
  buildWorkbenchLink,
  readResearchContext,
} from '../utils/researchContext';

describe('researchContext retained routing', () => {
  it('falls removed pricing deep links back to the backtest view', () => {
    const url = buildPricingLink(
      'AAPL',
      'research_workbench',
      '从旧系统页回流',
      '?view=workbench&workbench_snapshot_fingerprint=wv_pricing_focus&task=rw_123',
      '6mo',
    );

    expect(url).not.toContain('view=pricing');
    expect(url).not.toContain('symbol=AAPL');
    expect(url).not.toContain('period=6mo');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('backtest');
    expect(parsed.symbol).toBe('');
    expect(parsed.period).toBe('');
  });

  it('falls removed workbench and godeye deep links back to the backtest view', () => {
    const workbenchUrl = buildWorkbenchLink(
      {
        refresh: 'high',
        type: 'cross_market',
        sourceFilter: 'godeye',
        reason: 'resonance',
        keyword: 'hedge',
        queueMode: 'pricing',
        queueAction: 'next_same_type',
        taskId: 'task_123',
      },
      '?view=godsEye'
    );
    const godEyeUrl = buildGodEyeLink('?view=godsEye');

    expect(workbenchUrl).not.toContain('view=workbench');
    expect(workbenchUrl).not.toContain('workbench_refresh=high');
    expect(godEyeUrl).not.toContain('view=godsEye');

    expect(readResearchContext(workbenchUrl.split('?')[1] ? `?${workbenchUrl.split('?')[1]}` : '').view).toBe('backtest');
    expect(readResearchContext(godEyeUrl.split('?')[1] ? `?${godEyeUrl.split('?')[1]}` : '').view).toBe('backtest');
  });

  it('preserves realtime tab state when syncing the realtime view url', () => {
    const url = buildViewUrlForCurrentState(
      'realtime',
      '?view=realtime&tab=crypto'
    );

    expect(url).toContain('view=realtime');
    expect(url).toContain('tab=crypto');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('realtime');
    expect(parsed.tab).toBe('crypto');
  });

  it('preserves cross-market draft params inside the retained backtest workspace', () => {
    const url = buildCrossMarketLink(
      'macro_mispricing_relative_value',
      'pricing_thesis',
      '来自旧系统仓的跨市场草案',
      '?view=workbench&workbench_snapshot_fingerprint=wv_baba_pricing&workbench_keyword=hedge&workbench_queue_mode=pricing',
      'mm_baba_123',
    );

    expect(url).toContain('tab=cross-market');
    expect(url).toContain('template=macro_mispricing_relative_value');
    expect(url).toContain('draft=mm_baba_123');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('backtest');
    expect(parsed.tab).toBe('cross-market');
    expect(parsed.template).toBe('macro_mispricing_relative_value');
    expect(parsed.draft).toBe('mm_baba_123');
  });

  it('cleans removed system params when the app normalizes backtest view urls', () => {
    const url = buildViewUrlForCurrentState(
      'backtest',
      '?view=pricing&symbol=AAPL&period=2y&source=research_workbench&workbench_queue_mode=pricing&task=rw_123'
    );

    expect(url).not.toContain('view=pricing');
    expect(url).not.toContain('symbol=AAPL');
    expect(url).not.toContain('period=2y');
    expect(url).not.toContain('workbench_queue_mode=pricing');
    expect(url).not.toContain('task=rw_123');
  });
});
