import {
  buildMacroMispricingDraft,
  loadMacroMispricingDraft,
  saveMacroMispricingDraft,
} from '../utils/macroMispricingDraft';

describe('macro mispricing draft bridge', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('builds a cross-market draft from thesis trade legs', () => {
    const draft = buildMacroMispricingDraft({
      symbol: 'BABA',
      thesis: {
        stance: '结构性做空',
        thesis_type: 'relative_short',
        trade_legs: [
          { symbol: 'BABA', side: 'short', role: 'core_expression', weight: 0.5 },
          { symbol: 'KWEB', side: 'long', role: 'beta_hedge', weight: 0.3 },
          { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
        ],
      },
      structuralDecay: {
        dominant_failure_label: '组织与治理稀释',
      },
      peopleLayer: {
        risk_level: 'high',
      },
      source: 'pricing_thesis',
      note: '来自定价研究的跨市场草案',
    });

    expect(draft.templateId).toBe('macro_mispricing_relative_value');
    expect(draft.assets).toEqual([
      { symbol: 'BABA', asset_class: 'US_STOCK', side: 'short', weight: 0.5, role: 'core_expression', thesis: '' },
      { symbol: 'KWEB', asset_class: 'ETF', side: 'long', weight: 0.3, role: 'beta_hedge', thesis: '' },
      { symbol: 'GLD', asset_class: 'ETF', side: 'long', weight: 0.2, role: 'stress_hedge', thesis: '' },
    ]);
    expect(draft.quality).toEqual({
      construction_mode: 'ols_hedge',
      min_history_days: 60,
      min_overlap_ratio: 0.75,
    });
    expect(draft.constraints).toEqual({
      max_single_weight: 50,
      min_single_weight: 20,
    });
    expect(draft.meta).toEqual({
      initial_capital: 100000,
      commission: 0.1,
      slippage: 0.1,
    });
    expect(draft.templateContext.people_risk).toBe('high');
    expect(draft.templateContext.dominant_failure_label).toBe('组织与治理稀释');
    expect(draft.templateContext.construction_mode).toBe('ols_hedge');
    expect(draft.templateContext.theme_core).toBe('BABA');
    expect(draft.templateContext.theme_support).toBe('KWEB / GLD');
    expect(draft.templateContext.signal_attribution).toHaveLength(3);
  });

  it('persists and reloads a saved draft', () => {
    const draft = buildMacroMispricingDraft({
      symbol: 'NVDA',
      thesis: {
        trade_legs: [{ symbol: 'NVDA', side: 'short', role: 'core_expression', weight: 1 }],
      },
    });

    const draftId = saveMacroMispricingDraft(draft);
    const loaded = loadMacroMispricingDraft(draftId);

    expect(loaded.id).toBe(draft.id);
    expect(loaded.symbol).toBe('NVDA');
    expect(loaded.assets[0].symbol).toBe('NVDA');
  });
});
