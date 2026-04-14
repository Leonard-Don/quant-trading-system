import { buildDecayWatchModel } from '../components/GodEyeDashboard/viewModels';
import { buildMacroMispricingWorkbenchPayload } from '../components/GodEyeDashboard/taskIntelligenceViewModels';

describe('GodEye decay watch model', () => {
  it('extracts pricing structural decay tasks into a ranked watchlist', () => {
    const items = buildDecayWatchModel([
      {
        id: 'pricing_decay_1',
        type: 'pricing',
        status: 'in_progress',
        symbol: 'BABA',
        title: '[Pricing] BABA mispricing review',
        snapshot: {
          payload: {
            gap_analysis: {
              direction: '溢价(高估)',
            },
            implications: {
              primary_view: '高估',
              people_risk: 'high',
            },
            people_layer: {
              risk_level: 'high',
            },
            structural_decay: {
              score: 0.78,
              label: '结构性衰败警报',
              action: 'structural_short',
              dominant_failure_label: '组织与治理稀释',
              summary: '结构性衰败警报，主导失效模式偏向 组织与治理稀释。',
              evidence: ['人的维度已进入高脆弱区间', '招聘稀释度 1.72'],
            },
            macro_mispricing_thesis: {
              thesis_type: 'relative_short',
              stance: '结构性做空',
              trade_legs: [
                { symbol: 'BABA', side: 'short', role: 'core_expression', weight: 0.5 },
                { symbol: 'KWEB', side: 'long', role: 'beta_hedge', weight: 0.3 },
                { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
              ],
              primary_leg: { symbol: 'BABA', side: 'short' },
              hedge_leg: { symbol: 'KWEB', side: 'long' },
            },
          },
        },
      },
      {
        id: 'pricing_decay_2',
        type: 'pricing',
        status: 'in_progress',
        symbol: 'NVDA',
        title: '[Pricing] NVDA mispricing review',
        snapshot: {
          payload: {
            implications: {
              primary_view: '合理',
            },
            people_layer: {
              risk_level: 'medium',
            },
            structural_decay: {
              score: 0.36,
              label: '持续观察',
              action: 'watch',
              dominant_failure_label: '叙事与证据断裂',
              summary: '当前更像阶段性波动，尚不足以直接判断为结构性衰败。',
              evidence: ['因子与估值结论冲突'],
            },
          },
        },
      },
    ]);

    expect(items).toHaveLength(2);
    expect(items[0].symbol).toBe('BABA');
    expect(items[0].score).toBe(0.78);
    expect(items[0].refreshLabel).toBe('优先重看');
    expect(items[0].action.target).toBe('workbench');
    expect(items[0].action.type).toBe('pricing');
    expect(items[0].action.taskId).toBe('pricing_decay_1');
    expect(items[0].evidence).toContain('招聘稀释度 1.72');
    expect(items[1].symbol).toBe('NVDA');
    expect(items[1].refreshLabel).toBe('继续观察');
  });

  it('builds a workbench payload for macro mispricing follow-up', () => {
    const [item] = buildDecayWatchModel([
      {
        id: 'pricing_decay_1',
        type: 'pricing',
        status: 'in_progress',
        symbol: 'BABA',
        title: '[Pricing] BABA mispricing review',
        snapshot: {
          payload: {
            gap_analysis: {
              gap_pct: 18.6,
              direction: '溢价(高估)',
            },
            implications: {
              primary_view: '高估',
              people_risk: 'high',
            },
            people_layer: {
              risk_level: 'high',
              summary: '技术权威持续被稀释，组织脆弱度抬升。',
            },
            structural_decay: {
              score: 0.78,
              label: '结构性衰败警报',
              action: 'structural_short',
              dominant_failure_label: '组织与治理稀释',
              summary: '结构性衰败警报，主导失效模式偏向 组织与治理稀释。',
              evidence: ['人的维度已进入高脆弱区间', '招聘稀释度 1.72'],
            },
            macro_mispricing_thesis: {
              thesis_type: 'relative_short',
              stance: '结构性做空',
              trade_legs: [
                { symbol: 'BABA', side: 'short', role: 'core_expression', weight: 0.5 },
                { symbol: 'KWEB', side: 'long', role: 'beta_hedge', weight: 0.3 },
                { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
              ],
              primary_leg: { symbol: 'BABA', side: 'short' },
              hedge_leg: { symbol: 'KWEB', side: 'long' },
            },
          },
        },
      },
    ]);

    const payload = buildMacroMispricingWorkbenchPayload(item);
    expect(payload.type).toBe('macro_mispricing');
    expect(payload.symbol).toBe('BABA');
    expect(payload.source).toBe('godeye_decay_watch');
    expect(payload.snapshot.payload.structural_decay.label).toBe('结构性衰败警报');
    expect(payload.snapshot.payload.macro_mispricing_thesis).toEqual({
      thesis_type: 'relative_short',
      stance: '结构性做空',
      trade_legs: [
        { symbol: 'BABA', side: 'short', role: 'core_expression', weight: 0.5 },
        { symbol: 'KWEB', side: 'long', role: 'beta_hedge', weight: 0.3 },
        { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
      ],
      primary_leg: { symbol: 'BABA', side: 'short' },
      hedge_leg: { symbol: 'KWEB', side: 'long' },
    });
    expect(payload.snapshot.payload.source_task_id).toBe('pricing_decay_1');
    expect(payload.snapshot.highlights).toContain('主导失效模式 组织与治理稀释');
    expect(payload.refresh_priority_event).toMatchObject({
      reason_key: 'structural_decay',
      reason_label: '结构衰败/系统雷达',
      severity: 'high',
    });
  });
});
