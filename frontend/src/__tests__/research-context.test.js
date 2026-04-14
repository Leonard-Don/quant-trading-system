import {
  buildCrossMarketLink,
  buildPricingLink,
  buildViewUrlForCurrentState,
  buildWorkbenchLink,
  readResearchContext,
} from '../utils/researchContext';

describe('researchContext workbench deep links', () => {
  it('builds and reads workbench filter params', () => {
    const url = buildWorkbenchLink(
      {
        refresh: 'high',
        type: 'cross_market',
        sourceFilter: 'godeye',
        reason: 'resonance',
        snapshotView: 'filtered',
        snapshotFingerprint: 'wv_pricing_focus',
        snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
        keyword: 'hedge',
        queueMode: 'pricing',
        queueAction: 'next_same_type',
        taskId: 'task_123',
      },
      '?view=godsEye'
    );

    expect(url).toContain('view=workbench');
    expect(url).toContain('workbench_refresh=high');
    expect(url).toContain('workbench_type=cross_market');
    expect(url).toContain('workbench_source=godeye');
    expect(url).toContain('workbench_reason=resonance');
    expect(url).toContain('workbench_snapshot_view=filtered');
    expect(url).toContain('workbench_snapshot_fingerprint=wv_pricing_focus');
    expect(url).toContain('workbench_snapshot_summary=');
    expect(url).toContain('workbench_keyword=hedge');
    expect(url).toContain('workbench_queue_mode=pricing');
    expect(url).toContain('workbench_queue_action=next_same_type');
    expect(url).toContain('task=task_123');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('workbench');
    expect(parsed.workbenchRefresh).toBe('high');
    expect(parsed.workbenchType).toBe('cross_market');
    expect(parsed.workbenchSource).toBe('godeye');
    expect(parsed.workbenchReason).toBe('resonance');
    expect(parsed.workbenchSnapshotView).toBe('filtered');
    expect(parsed.workbenchSnapshotFingerprint).toBe('wv_pricing_focus');
    expect(parsed.workbenchSnapshotSummary).toBe('快速视图：自动排序升档 · 类型：Pricing');
    expect(parsed.workbenchKeyword).toBe('hedge');
    expect(parsed.workbenchQueueMode).toBe('pricing');
    expect(parsed.workbenchQueueAction).toBe('next_same_type');
    expect(parsed.task).toBe('task_123');
  });

  it('preserves workbench filters when syncing the current workbench view url', () => {
    const url = buildViewUrlForCurrentState(
      'workbench',
      '?view=workbench&workbench_refresh=high&workbench_type=pricing&workbench_source=pricing_playbook&workbench_reason=policy_source&workbench_snapshot_view=scoped&workbench_snapshot_fingerprint=wv_policy_scope&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E8%A7%92%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E7%BC%93%E5%92%8C&workbench_keyword=policy&workbench_queue_mode=pricing&workbench_queue_action=next_same_type&task=rw_123'
    );

    expect(url).toContain('view=workbench');
    expect(url).toContain('workbench_refresh=high');
    expect(url).toContain('workbench_type=pricing');
    expect(url).toContain('workbench_source=pricing_playbook');
    expect(url).toContain('workbench_reason=policy_source');
    expect(url).toContain('workbench_snapshot_view=scoped');
    expect(url).toContain('workbench_snapshot_fingerprint=wv_policy_scope');
    expect(url).toContain('workbench_snapshot_summary=');
    expect(url).toContain('workbench_keyword=policy');
    expect(url).toContain('workbench_queue_mode=pricing');
    expect(url).toContain('workbench_queue_action=next_same_type');
    expect(url).toContain('task=rw_123');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('workbench');
    expect(parsed.workbenchRefresh).toBe('high');
    expect(parsed.workbenchType).toBe('pricing');
    expect(parsed.workbenchSource).toBe('pricing_playbook');
    expect(parsed.workbenchReason).toBe('policy_source');
    expect(parsed.workbenchSnapshotView).toBe('scoped');
    expect(parsed.workbenchSnapshotFingerprint).toBe('wv_policy_scope');
    expect(parsed.workbenchSnapshotSummary).toBe('快速视角：自动排序缓和');
    expect(parsed.workbenchKeyword).toBe('policy');
    expect(parsed.workbenchQueueMode).toBe('pricing');
    expect(parsed.workbenchQueueAction).toBe('next_same_type');
    expect(parsed.task).toBe('rw_123');
  });

  it('preserves pricing period when syncing the pricing view url', () => {
    const url = buildViewUrlForCurrentState(
      'pricing',
      '?view=pricing&symbol=AAPL&period=2y&source=research_workbench&note=reopen'
    );

    expect(url).toContain('view=pricing');
    expect(url).toContain('symbol=AAPL');
    expect(url).toContain('period=2y');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('pricing');
    expect(parsed.symbol).toBe('AAPL');
    expect(parsed.period).toBe('2y');
  });

  it('preserves cross-market draft deep link params', () => {
    const url = buildCrossMarketLink(
      'macro_mispricing_relative_value',
      'pricing_thesis',
      '来自定价 thesis 的跨市场草案',
      '?view=workbench&symbol=BABA&workbench_snapshot_view=filtered&workbench_snapshot_fingerprint=wv_baba_pricing&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E5%9B%BE%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E5%8D%87%E6%A1%A3%20%C2%B7%20%E7%B1%BB%E5%9E%8B%EF%BC%9APricing&workbench_keyword=hedge&workbench_queue_mode=pricing',
      'mm_baba_123',
    );

    expect(url).toContain('tab=cross-market');
    expect(url).toContain('template=macro_mispricing_relative_value');
    expect(url).toContain('draft=mm_baba_123');
    expect(url).toContain('workbench_snapshot_fingerprint=wv_baba_pricing');
    expect(url).toContain('workbench_keyword=hedge');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('backtest');
    expect(parsed.tab).toBe('cross-market');
    expect(parsed.template).toBe('macro_mispricing_relative_value');
    expect(parsed.draft).toBe('mm_baba_123');
    expect(parsed.workbenchSnapshotFingerprint).toBe('wv_baba_pricing');
    expect(parsed.workbenchKeyword).toBe('hedge');
    expect(parsed.workbenchQueueMode).toBe('pricing');
  });

  it('preserves workbench snapshot context when reopening pricing research', () => {
    const url = buildPricingLink(
      'AAPL',
      'research_workbench',
      '从工作台重开',
      '?view=workbench&workbench_snapshot_view=filtered&workbench_snapshot_fingerprint=wv_pricing_focus&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E5%9B%BE%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E5%8D%87%E6%A1%A3%20%C2%B7%20%E7%B1%BB%E5%9E%8B%EF%BC%9APricing&workbench_keyword=hedge&workbench_queue_mode=pricing&task=rw_123',
      '6mo',
    );

    expect(url).toContain('view=pricing');
    expect(url).toContain('symbol=AAPL');
    expect(url).toContain('period=6mo');
    expect(url).toContain('workbench_snapshot_fingerprint=wv_pricing_focus');
    expect(url).toContain('workbench_keyword=hedge');
    expect(url).toContain('workbench_queue_mode=pricing');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('pricing');
    expect(parsed.symbol).toBe('AAPL');
    expect(parsed.period).toBe('6mo');
    expect(parsed.workbenchSnapshotFingerprint).toBe('wv_pricing_focus');
    expect(parsed.workbenchKeyword).toBe('hedge');
    expect(parsed.workbenchQueueMode).toBe('pricing');
  });
});
