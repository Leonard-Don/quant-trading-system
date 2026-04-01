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
      input_reliability_summary: {
        label: 'fragile',
        score: 0.42,
        lead: '当前输入可靠度偏脆弱，主要风险来自政策源脆弱与证据分裂。',
        posture: '当前宏观输入更适合先复核来源与证据质量，再用于定价判断。',
        reason: 'effective confidence 0.42 · freshness recent · policy source fragile',
        dominant_issue_labels: ['政策源脆弱', '结论分歧'],
      },
      evidence_summary: {
        policy_source_health_summary: {
          label: 'fragile',
          reason: '正文抓取脆弱源 ndrc',
          fragile_sources: ['ndrc'],
          watch_sources: [],
          healthy_sources: ['fed'],
          avg_full_text_ratio: 0.41,
        },
      },
      resonance_summary: {
        label: 'bullish_cluster',
        reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
        positive_cluster: ['baseload_mismatch', 'tech_dilution'],
        negative_cluster: [],
        weakening: [],
        precursor: [],
        reversed_factors: [],
      },
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
    expect(cards[0].policySourceHealthLabel).toBe('fragile');
    expect(cards[0].policySourceHealthReason).toContain('ndrc');
    expect(cards[0].inputReliabilityLabel).toBe('fragile');
    expect(cards[0].inputReliabilityLead).toContain('输入可靠度偏脆弱');
    expect(cards[0].driverHeadline).toContain('基荷错配');
    expect(cards[0].matchedDrivers.some((item) => item.type === 'quality')).toBe(true);
    expect(cards[0].biasSummary).toBeTruthy();
    expect(cards[0].biasStrength).toBeGreaterThan(0);
    expect(cards[0].biasQualityLabel).toBe('compressed');
    expect(cards[0].biasScale).toBe(0.55);
    expect(cards[0].adjustedAssets).toHaveLength(4);
    expect(cards[0].signalAttribution.length).toBe(4);
    expect(cards[0].signalAttribution.some((item) => item.reasons.length > 0)).toBe(true);
    expect(cards[0].driverSummary.length).toBeGreaterThan(0);
    expect(cards[0].dominantDrivers.length).toBeGreaterThan(0);
    expect(cards[0].themeCore).toBeTruthy();
    expect(cards[0].resonanceLabel).toBe('bullish_cluster');
    expect(cards[0].resonanceReason).toContain('上行共振');
    expect(cards[0].matchedDrivers.some((item) => item.type === 'resonance')).toBe(true);
    expect(cards[0].signalAttribution.some((item) => item.breakdown.length > 0)).toBe(true);
    expect(cards[1].matchedDrivers.some((item) => item.type === 'alert')).toBe(true);
  });

  it('compresses macro bias strength when policy-source health degrades', () => {
    const payload = {
      templates: [
        {
          id: 'energy_vs_ai_apps',
          name: 'Energy vs AI',
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
      ],
    };
    const baseOverview = {
      macro_signal: 1,
      resonance_summary: {
        label: 'bullish_cluster',
        reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
        positive_cluster: ['baseload_mismatch', 'tech_dilution'],
        negative_cluster: [],
        weakening: [],
        precursor: [],
        reversed_factors: [],
      },
      factors: [
        { name: 'baseload_mismatch', z_score: 1.8, value: 0.9, signal: 1 },
        { name: 'tech_dilution', z_score: 1.1, value: 0.6, signal: 1 },
      ],
    };
    const snapshot = {
      signals: {
        supply_chain: { dimensions: { investment_activity: { score: 0.35 } } },
        macro_hf: { dimensions: { inventory: { score: 0.45 } } },
      },
    };

    const healthyCard = buildCrossMarketCards(
      payload,
      {
        ...baseOverview,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'healthy',
            reason: '主要政策源正文覆盖稳定',
            fragile_sources: [],
            watch_sources: [],
            healthy_sources: ['ndrc', 'fed'],
            avg_full_text_ratio: 0.9,
          },
        },
      },
      snapshot
    )[0];
    const fragileCard = buildCrossMarketCards(
      payload,
      {
        ...baseOverview,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'fragile',
            reason: '正文抓取脆弱源 ndrc',
            fragile_sources: ['ndrc'],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.4,
          },
        },
      },
      snapshot
    )[0];

    expect(healthyCard.biasQualityLabel).toBe('full');
    expect(fragileCard.biasQualityLabel).toBe('compressed');
    expect(fragileCard.biasStrength).toBeLessThan(healthyCard.biasStrength);
    expect(fragileCard.biasScale).toBeLessThan(1);
  });

  it('softens recommendation strength when overall input reliability degrades even if policy sources stay healthy', () => {
    const payload = {
      templates: [
        {
          id: 'energy_vs_ai_apps',
          name: 'Energy vs AI',
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
      ],
    };
    const baseOverview = {
      macro_signal: 1,
      resonance_summary: {
        label: 'bullish_cluster',
        reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
        positive_cluster: ['baseload_mismatch', 'tech_dilution'],
        negative_cluster: [],
        weakening: [],
        precursor: [],
        reversed_factors: [],
      },
      factors: [
        { name: 'baseload_mismatch', z_score: 1.8, value: 0.9, signal: 1 },
        { name: 'tech_dilution', z_score: 1.1, value: 0.6, signal: 1 },
      ],
      evidence_summary: {
        policy_source_health_summary: {
          label: 'healthy',
          reason: '主要政策源正文覆盖稳定',
          fragile_sources: [],
          watch_sources: [],
          healthy_sources: ['ndrc', 'fed'],
          avg_full_text_ratio: 0.9,
        },
      },
    };
    const snapshot = {
      signals: {
        supply_chain: { dimensions: { investment_activity: { score: 0.35 } } },
        macro_hf: { dimensions: { inventory: { score: 0.45 } } },
      },
    };

    const robustCard = buildCrossMarketCards(
      payload,
      {
        ...baseOverview,
        input_reliability_summary: {
          label: 'robust',
          score: 0.84,
          lead: '当前输入可靠度整体稳健。',
          dominant_issue_labels: [],
          dominant_support_labels: ['跨源确认'],
        },
      },
      snapshot
    )[0];
    const fragileInputCard = buildCrossMarketCards(
      payload,
      {
        ...baseOverview,
        input_reliability_summary: {
          label: 'fragile',
          score: 0.41,
          lead: '当前输入可靠度偏脆弱，主要风险来自时效偏旧与来源退化。',
          dominant_issue_labels: ['时效偏旧', '来源退化'],
          dominant_support_labels: [],
        },
      },
      snapshot
    )[0];

    expect(robustCard.inputReliabilityLabel).toBe('robust');
    expect(fragileInputCard.inputReliabilityLabel).toBe('fragile');
    expect(fragileInputCard.recommendationScore).toBeLessThan(robustCard.recommendationScore);
    expect(fragileInputCard.biasScale).toBeLessThan(1);
    expect(fragileInputCard.biasQualityLabel).toBe('compressed');
    expect(fragileInputCard.matchedDrivers.some((item) => item.label.includes('输入可靠度'))).toBe(true);
  });
});
