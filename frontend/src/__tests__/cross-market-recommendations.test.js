import { buildCrossMarketCards } from '../utils/crossMarketRecommendations';

describe('crossMarketRecommendations', () => {
  it('ranks templates consistently based on macro factors and alt-data drivers', () => {
    const payload = {
      templates: [
        {
          id: 'energy_vs_ai_apps',
          name: 'Energy vs AI',
          description: 'Physical energy against AI apps.',
          narrative: 'Baseload scarcity theme.',
          linked_factors: ['baseload_mismatch', 'tech_dilution'],
          linked_dimensions: ['investment_activity', 'inventory'],
          assets: [
            { symbol: 'HG=F', side: 'long', weight: 0.5, asset_class: 'COMMODITY_FUTURES' },
            { symbol: 'XLE', side: 'long', weight: 0.5, asset_class: 'ETF' },
            { symbol: 'IGV', side: 'short', weight: 0.6, asset_class: 'ETF' },
            { symbol: 'SOXX', side: 'short', weight: 0.4, asset_class: 'ETF' },
          ],
          preferred_signal: 'positive',
        },
        {
          id: 'defensive_beta_hedge',
          name: 'Defensive beta hedge',
          description: 'Utilities against tech beta.',
          narrative: 'Execution quality hedge.',
          linked_factors: ['bureaucratic_friction'],
          linked_dimensions: ['talent_structure'],
          assets: [
            { symbol: 'XLU', side: 'long', weight: 0.6, asset_class: 'ETF' },
            { symbol: 'DUK', side: 'long', weight: 0.4, asset_class: 'US_STOCK' },
            { symbol: 'QQQ', side: 'short', weight: 1, asset_class: 'ETF' },
          ],
          preferred_signal: 'mixed',
        },
      ],
    };
    const overview = {
      macro_signal: 1,
      factors: [
        { name: 'baseload_mismatch', z_score: 1.8, value: 0.9, signal: 1 },
        { name: 'tech_dilution', z_score: 1.1, value: 0.6, signal: 1 },
        { name: 'bureaucratic_friction', z_score: 0.5, value: 0.2, signal: 1 },
      ],
    };
    const snapshot = {
      signals: {
        supply_chain: {
          dimensions: {
            talent_structure: { score: 0.7 },
            investment_activity: { score: 0.35 },
          },
          alerts: [{ company: '示例公司', message: '人才结构预警' }],
        },
        macro_hf: {
          dimensions: {
            inventory: { score: 0.45 },
          },
        },
      },
    };

    const cards = buildCrossMarketCards(payload, overview, snapshot);

    expect(cards).toHaveLength(2);
    expect(cards[0].id).toBe('energy_vs_ai_apps');
    expect(cards[0].recommendationScore).toBeGreaterThan(cards[1].recommendationScore);
    expect(cards[0].recommendationTier).toBeTruthy();
    expect(cards[0].driverHeadline).toContain('基荷错配');
    expect(cards[0].biasSummary).toBeTruthy();
    expect(cards[0].biasStrength).toBeGreaterThan(0);
    expect(cards[0].adjustedAssets).toHaveLength(4);
    expect(cards[0].signalAttribution.length).toBe(4);
    expect(cards[0].signalAttribution.some((item) => item.reasons.length > 0)).toBe(true);
    expect(cards[0].driverSummary.length).toBeGreaterThan(0);
    expect(cards[0].dominantDrivers.length).toBeGreaterThan(0);
    expect(cards[0].themeCore).toBeTruthy();
    expect(cards[0].signalAttribution.some((item) => item.breakdown.length > 0)).toBe(true);
    expect(cards[1].matchedDrivers.some((item) => item.type === 'alert')).toBe(true);
  });
});
