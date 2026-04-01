const DIMENSION_META = {
  investment_activity: { label: '投资活跃度', group: 'Supply Chain' },
  project_pipeline: { label: '项目管线', group: 'Supply Chain' },
  talent_structure: { label: '人才结构', group: 'Supply Chain' },
  inventory: { label: '库存压力', group: 'Macro HF' },
  trade: { label: '贸易脉冲', group: 'Macro HF' },
  logistics: { label: '物流摩擦', group: 'Macro HF' },
};

const FACTOR_LABELS = {
  bureaucratic_friction: '官僚摩擦',
  tech_dilution: '技术稀释',
  baseload_mismatch: '基荷错配',
};

const DEFENSIVE_LONG_SYMBOLS = new Set(['XLU', 'DUK', 'CEG', 'NEE', 'XLE', 'VDE']);
const PHYSICAL_LONG_SYMBOLS = new Set(['HG=F', 'XLE', 'VDE', 'XLU', 'DUK', 'CEG', 'NEE']);
const GROWTH_SHORT_SYMBOLS = new Set(['QQQ', 'ARKK', 'IGV', 'CLOU', 'SOXX', 'SMH']);
const SEMI_SHORT_SYMBOLS = new Set(['SOXX', 'SMH']);

const formatFactorName = (name = '') => FACTOR_LABELS[name] || name.replace(/_/g, ' ');

const clampMin = (value, minimum = 0.05) => Math.max(minimum, Number(value || 0));
const pushContribution = (list, key, label, value) => {
  const numeric = Number(value || 0);
  if (numeric <= 0.005) {
    return;
  }
  list.push({
    key,
    label,
    value: Number(numeric.toFixed(4)),
  });
};

const buildFactorLookup = (overview = {}) =>
  Object.fromEntries((overview?.factors || []).map((factor) => [factor.name, factor]));

const buildDimensionLookup = (snapshot = {}) => ({
  ...(snapshot?.signals?.supply_chain?.dimensions || {}),
  ...(snapshot?.signals?.macro_hf?.dimensions || {}),
});

const buildRecommendationTier = (score) => {
  if (score >= 2.6) return '优先部署';
  if (score >= 1.4) return '重点跟踪';
  return '候选模板';
};

const buildRecommendationTone = (score) => {
  if (score >= 2.6) return 'volcano';
  if (score >= 1.4) return 'gold';
  return 'blue';
};

const buildResonanceMeta = (overview = {}) => {
  const resonance = overview?.resonance_summary || {};
  return {
    label: resonance.label || 'mixed',
    reason: resonance.reason || '',
    positive: new Set(resonance.positive_cluster || []),
    negative: new Set(resonance.negative_cluster || []),
    weakening: new Set(resonance.weakening || []),
    precursor: new Set(resonance.precursor || []),
    reversed: new Set(resonance.reversed_factors || []),
  };
};

const buildPolicySourceHealthMeta = (overview = {}) => {
  const summary = overview?.evidence_summary?.policy_source_health_summary || {};
  return {
    label: summary.label || 'unknown',
    reason: summary.reason || '',
    fragileSources: summary.fragile_sources || [],
    watchSources: summary.watch_sources || [],
    avgFullTextRatio: Number(summary.avg_full_text_ratio || 0),
  };
};

const buildInputReliabilityMeta = (overview = {}) => {
  const summary = overview?.input_reliability_summary || {};
  return {
    label: summary.label || 'unknown',
    score: Number(summary.score || 0),
    lead: summary.lead || '',
    posture: summary.posture || '',
    reason: summary.reason || '',
    dominantIssueLabels: summary.dominant_issue_labels || [],
    dominantSupportLabels: summary.dominant_support_labels || [],
  };
};

export const CROSS_MARKET_FACTOR_LABELS = FACTOR_LABELS;
export const CROSS_MARKET_DIMENSION_LABELS = Object.fromEntries(
  Object.entries(DIMENSION_META).map(([key, meta]) => [key, meta.label])
);

const normalizeSideWeights = (assets = []) => {
  const total = assets.reduce((sum, asset) => sum + Number(asset.weight || 0), 0) || 1;
  return assets.map((asset) => ({
    ...asset,
    weight: Number((Number(asset.weight || 0) / total).toFixed(6)),
  }));
};

const buildSignalContext = (overview = {}, snapshot = {}) => {
  const factorLookup = buildFactorLookup(overview);
  const dimensionLookup = buildDimensionLookup(snapshot);
  return {
    baseload:
      Math.max(
        Math.abs(Number(factorLookup.baseload_mismatch?.z_score || factorLookup.baseload_mismatch?.value || 0)),
        Math.abs(Number(dimensionLookup.inventory?.score || 0)),
        Math.abs(Number(dimensionLookup.project_pipeline?.score || 0))
      ),
    techDilution:
      Math.max(
        Math.abs(Number(factorLookup.tech_dilution?.z_score || factorLookup.tech_dilution?.value || 0)),
        Math.abs(Number(dimensionLookup.talent_structure?.score || 0))
      ),
    bureaucratic:
      Math.max(
        Math.abs(Number(factorLookup.bureaucratic_friction?.z_score || factorLookup.bureaucratic_friction?.value || 0)),
        Math.abs(Number(dimensionLookup.logistics?.score || 0))
      ),
    trade:
      Math.max(
        Math.abs(Number(dimensionLookup.trade?.score || 0)),
        Math.abs(Number(dimensionLookup.logistics?.score || 0))
      ),
    investment: Math.abs(Number(dimensionLookup.investment_activity?.score || 0)),
  };
};

const buildBiasQualityMeta = (policySourceHealth = {}, inputReliability = {}) => {
  if (policySourceHealth.label === 'fragile' || inputReliability.label === 'fragile') {
    const reasons = [policySourceHealth.reason, inputReliability.lead || inputReliability.reason].filter(Boolean);
    return {
      scale: policySourceHealth.label === 'fragile' ? 0.55 : 0.72,
      label: 'compressed',
      reason: reasons.join(' · ') || '整体输入可靠度偏脆弱，宏观偏置已收缩到更保守的幅度',
    };
  }
  if (policySourceHealth.label === 'watch' || inputReliability.label === 'watch') {
    const reasons = [policySourceHealth.reason, inputReliability.lead || inputReliability.reason].filter(Boolean);
    return {
      scale: policySourceHealth.label === 'watch' ? 0.78 : 0.88,
      label: 'cautious',
      reason: reasons.join(' · ') || '整体输入可靠度需要观察，宏观偏置已适度收缩',
    };
  }
  return {
    scale: 1,
    label: 'full',
    reason: policySourceHealth.reason || '',
  };
};

const buildAdjustedAssets = (template = {}, signalContext = {}, qualityMeta = {}) => {
  const longAssets = [];
  const shortAssets = [];
  const rawLongAssets = [];
  const rawShortAssets = [];
  const signalAttribution = [];
  const driverSummary = {};
  const qualityScale = Number(qualityMeta.scale || 1);

  (template.assets || []).forEach((asset) => {
    const currentWeight = Number(asset.weight || 0) || 1;
    let multiplier = 1;
    const symbol = String(asset.symbol || '').toUpperCase();
    const isLong = asset.side === 'long';
    const biasReasons = [];
    const breakdown = [];

    if (isLong) {
      if (asset.asset_class === 'COMMODITY_FUTURES') {
        const uplift = signalContext.baseload * 0.16 + signalContext.trade * 0.12;
        multiplier += uplift;
        pushContribution(breakdown, 'physical_tightness', '上游实物紧张', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`上游实物紧张 ${uplift.toFixed(2)}`);
        }
      }
      if (DEFENSIVE_LONG_SYMBOLS.has(symbol)) {
        const uplift = signalContext.bureaucratic * 0.1 + signalContext.baseload * 0.08;
        multiplier += uplift;
        pushContribution(breakdown, 'defensive_premium', '防守资产溢价', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`防守资产溢价 ${uplift.toFixed(2)}`);
        }
      }
      if (PHYSICAL_LONG_SYMBOLS.has(symbol)) {
        const uplift = signalContext.investment * 0.12 + signalContext.baseload * 0.1;
        multiplier += uplift;
        pushContribution(breakdown, 'baseload_support', '基建/基荷支撑', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`基建/基荷支撑 ${uplift.toFixed(2)}`);
        }
      }
    } else {
      if (GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = signalContext.techDilution * 0.14 + signalContext.baseload * 0.08;
        multiplier += uplift;
        pushContribution(breakdown, 'growth_pressure', '成长端估值压力', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`成长端估值压力 ${uplift.toFixed(2)}`);
        }
      }
      if (SEMI_SHORT_SYMBOLS.has(symbol)) {
        const uplift = signalContext.trade * 0.1;
        multiplier += uplift;
        pushContribution(breakdown, 'trade_friction', '贸易摩擦抬升', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`贸易摩擦抬升 ${uplift.toFixed(2)}`);
        }
      }
      if (symbol === 'QQQ') {
        const uplift = signalContext.bureaucratic * 0.06;
        multiplier += uplift;
        pushContribution(breakdown, 'bureaucratic_drag', '官僚摩擦压制估值', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`官僚摩擦压制估值 ${uplift.toFixed(2)}`);
        }
      }
    }

    breakdown.forEach((item) => {
      driverSummary[item.key] = {
        key: item.key,
        label: item.label,
        value: Number(((driverSummary[item.key]?.value || 0) + item.value).toFixed(4)),
      };
    });

    const adjustedMultiplier = 1 + (multiplier - 1) * qualityScale;
    const adjusted = {
      ...asset,
      weight: clampMin(currentWeight * adjustedMultiplier, 0.01),
      base_weight: Number(currentWeight.toFixed(6)),
      bias_reasons: biasReasons,
      bias_breakdown: breakdown,
    };
    const rawAdjusted = {
      ...asset,
      weight: clampMin(currentWeight * multiplier, 0.01),
      base_weight: Number(currentWeight.toFixed(6)),
    };
    signalAttribution.push({
      symbol,
      side: asset.side,
      asset_class: asset.asset_class,
      multiplier: Number(adjustedMultiplier.toFixed(4)),
      raw_multiplier: Number(multiplier.toFixed(4)),
      quality_scale: Number(qualityScale.toFixed(2)),
      reasons: biasReasons,
      breakdown,
    });
    if (isLong) {
      longAssets.push(adjusted);
      rawLongAssets.push(rawAdjusted);
    } else {
      shortAssets.push(adjusted);
      rawShortAssets.push(rawAdjusted);
    }
  });

  const normalizedLong = normalizeSideWeights(longAssets);
  const normalizedShort = normalizeSideWeights(shortAssets);
  const normalizedRawLong = normalizeSideWeights(rawLongAssets);
  const normalizedRawShort = normalizeSideWeights(rawShortAssets);
  const adjustedAssets = [...normalizedLong, ...normalizedShort];
  const rawAdjustedAssets = [...normalizedRawLong, ...normalizedRawShort];
  const deltas = adjustedAssets
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      delta: Number(((asset.weight || 0) - (asset.base_weight || 0)).toFixed(4)),
    }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const rawDeltas = rawAdjustedAssets
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      delta: Number(((asset.weight || 0) - (asset.base_weight || 0)).toFixed(4)),
    }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  const longLeader = deltas.find((item) => item.side === 'long' && item.delta > 0);
  const shortLeader = deltas.find((item) => item.side === 'short' && item.delta > 0);
  const strongestShift = deltas[0] ? Math.abs(deltas[0].delta) : 0;
  const rawStrongestShift = rawDeltas[0] ? Math.abs(rawDeltas[0].delta) : 0;

  const summaryParts = [];
  if (longLeader) {
    summaryParts.push(`多头增配 ${longLeader.symbol}`);
  }
  if (shortLeader) {
    summaryParts.push(`空头增配 ${shortLeader.symbol}`);
  }

  const biasHighlights = deltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 4)
    .map((item) => `${item.symbol} ${item.delta > 0 ? '+' : ''}${(item.delta * 100).toFixed(1)}pp`);
  const biasActions = deltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 6)
    .map((item) => ({
      symbol: item.symbol,
      side: item.side,
      action: item.delta > 0 ? 'increase' : 'reduce',
      delta: Number(item.delta.toFixed(4)),
    }));
  const rawBiasHighlights = rawDeltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 4)
    .map((item) => `${item.symbol} ${item.delta > 0 ? '+' : ''}${(item.delta * 100).toFixed(1)}pp`);
  const dominantDrivers = Object.values(driverSummary)
    .sort((a, b) => b.value - a.value)
    .slice(0, 3);
  const coreLegs = adjustedAssets
    .filter((asset) => Math.abs((asset.weight || 0) - (asset.base_weight || 0)) >= 0.025)
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      role: 'core',
      delta: Number((((asset.weight || 0) - (asset.base_weight || 0)) * 100).toFixed(2)),
    }));
  const supportLegs = adjustedAssets
    .filter((asset) => Math.abs((asset.weight || 0) - (asset.base_weight || 0)) < 0.025)
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      role: 'support',
      delta: Number((((asset.weight || 0) - (asset.base_weight || 0)) * 100).toFixed(2)),
    }));
  const themeCore = coreLegs.length
    ? coreLegs.map((item) => `${item.symbol}${item.delta > 0 ? '+' : ''}${item.delta.toFixed(1)}pp`).join('，')
    : '暂无明确主题核心腿';
  const themeSupport = supportLegs.length
    ? supportLegs.map((item) => item.symbol).join('，')
    : '无辅助腿';

  return {
    rawAdjustedAssets,
    adjustedAssets,
    biasSummary: summaryParts.join('，') || '当前信号更适合作为方向参考，权重保持接近模板原始配置',
    rawBiasStrength: Number((rawStrongestShift * 100).toFixed(2)),
    biasStrength: Number((strongestShift * 100).toFixed(2)),
    biasScale: Number(qualityScale.toFixed(2)),
    biasQualityLabel: qualityMeta.label || 'full',
    biasQualityReason: qualityMeta.reason || '',
    rawBiasHighlights,
    biasHighlights,
    biasActions,
    signalAttribution,
    driverSummary: Object.values(driverSummary).sort((a, b) => b.value - a.value),
    dominantDrivers,
    coreLegs,
    supportLegs,
    themeCore,
    themeSupport,
  };
};

export const buildCrossMarketCards = (payload = {}, overview = {}, snapshot = {}, buildAction = null) => {
  const templates = payload?.templates || [];
  const factorLookup = buildFactorLookup(overview);
  const dimensionLookup = buildDimensionLookup(snapshot);
  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  const signalContext = buildSignalContext(overview, snapshot);
  const resonanceMeta = buildResonanceMeta(overview);
  const policySourceHealth = buildPolicySourceHealthMeta(overview);
  const inputReliability = buildInputReliabilityMeta(overview);

  return templates
    .map((template) => {
      const longCount = template.assets.filter((asset) => asset.side === 'long').length;
      const shortCount = template.assets.filter((asset) => asset.side === 'short').length;
      const matchedDrivers = [];
      let recommendationScore = 0;

      (template.linked_factors || []).forEach((factorName) => {
        const factor = factorLookup[factorName];
        if (!factor) {
          return;
        }
        const strength = Math.abs(Number(factor.z_score || factor.value || 0));
        if (strength < 0.2 && !factor.signal) {
          return;
        }
        recommendationScore += Math.max(0.4, strength);
        matchedDrivers.push({
          key: `factor-${factorName}`,
          label: formatFactorName(factorName),
          detail: `z=${Number(factor.z_score || 0).toFixed(2)}`,
          type: 'factor',
        });
      });

      (template.linked_dimensions || []).forEach((dimensionName) => {
        const dimension = dimensionLookup[dimensionName];
        if (!dimension) {
          return;
        }
        const strength = Math.abs(Number(dimension.score || 0));
        if (strength < 0.18) {
          return;
        }
        recommendationScore += Math.max(0.25, strength);
        matchedDrivers.push({
          key: `dimension-${dimensionName}`,
          label: DIMENSION_META[dimensionName]?.label || dimensionName,
          detail: `score=${Number(dimension.score || 0).toFixed(2)}`,
          type: 'dimension',
        });
      });

      const linkedFactors = template.linked_factors || [];
      const resonanceMatches = {
        positive: linkedFactors.filter((factorName) => resonanceMeta.positive.has(factorName)),
        negative: linkedFactors.filter((factorName) => resonanceMeta.negative.has(factorName)),
        weakening: linkedFactors.filter((factorName) => resonanceMeta.weakening.has(factorName)),
        precursor: linkedFactors.filter((factorName) => resonanceMeta.precursor.has(factorName)),
        reversed: linkedFactors.filter((factorName) => resonanceMeta.reversed.has(factorName)),
      };

      if (resonanceMatches.positive.length) {
        recommendationScore += resonanceMatches.positive.length * 0.55;
        matchedDrivers.push({
          key: `resonance-positive-${template.id}`,
          label: `正向共振 ${resonanceMatches.positive.map((name) => formatFactorName(name)).join('、')}`,
          detail: resonanceMeta.reason || '多个因子同步强化',
          type: 'resonance',
        });
      }
      if (resonanceMatches.negative.length && template.preferred_signal !== 'positive') {
        recommendationScore += resonanceMatches.negative.length * 0.45;
        matchedDrivers.push({
          key: `resonance-negative-${template.id}`,
          label: `负向共振 ${resonanceMatches.negative.map((name) => formatFactorName(name)).join('、')}`,
          detail: resonanceMeta.reason || '多个因子同步走弱',
          type: 'resonance',
        });
      }
      if (resonanceMatches.precursor.length || resonanceMatches.reversed.length) {
        recommendationScore += 0.2;
        matchedDrivers.push({
          key: `resonance-turn-${template.id}`,
          label: `叙事临界 ${[
            ...resonanceMatches.precursor.map((name) => formatFactorName(name)),
            ...resonanceMatches.reversed.map((name) => formatFactorName(name)),
          ].join('、')}`,
          detail: resonanceMeta.reason || '相关因子进入反转临界区',
          type: 'resonance',
        });
      }
      if (resonanceMatches.weakening.length) {
        recommendationScore = Math.max(0, recommendationScore - Math.min(0.25, resonanceMatches.weakening.length * 0.1));
      }

      if ((template.linked_dimensions || []).includes('talent_structure') && supplyAlerts.length) {
        recommendationScore += Math.min(0.9, supplyAlerts.length * 0.25);
        matchedDrivers.push({
          key: 'supply-alerts',
          label: `供应链预警 ${supplyAlerts.length} 条`,
          detail: '人才结构与执行质量出现扰动',
          type: 'alert',
        });
      }

      if (template.preferred_signal === 'positive' && overview?.macro_signal === 1) {
        recommendationScore += 0.25;
      }

      if (policySourceHealth.label === 'fragile') {
        recommendationScore = Math.max(0, recommendationScore - 0.35);
        matchedDrivers.push({
          key: `policy-source-${template.id}`,
          label: `政策源退化 ${policySourceHealth.fragileSources.slice(0, 2).join('、') || 'fragile'}`,
          detail: policySourceHealth.reason || '政策正文抓取质量下降，推荐级别需打折',
          type: 'quality',
        });
      } else if (policySourceHealth.label === 'watch') {
        recommendationScore = Math.max(0, recommendationScore - 0.18);
        matchedDrivers.push({
          key: `policy-source-${template.id}`,
          label: '政策源需关注',
          detail: policySourceHealth.reason || '政策正文覆盖下降，推荐级别适度打折',
          type: 'quality',
        });
      } else if (policySourceHealth.label === 'healthy') {
        recommendationScore += 0.06;
      }

      if (inputReliability.label === 'fragile') {
        recommendationScore = Math.max(0, recommendationScore - 0.28);
        matchedDrivers.push({
          key: `input-reliability-${template.id}`,
          label: '输入可靠度偏脆弱',
          detail: inputReliability.lead || inputReliability.reason || '宏观输入质量整体偏脆弱，模板排序继续下调',
          type: 'quality',
        });
      } else if (inputReliability.label === 'watch') {
        recommendationScore = Math.max(0, recommendationScore - 0.14);
        matchedDrivers.push({
          key: `input-reliability-${template.id}`,
          label: '输入可靠度需观察',
          detail: inputReliability.lead || inputReliability.reason || '宏观输入质量存在波动，模板排序适度下调',
          type: 'quality',
        });
      } else if (inputReliability.label === 'robust') {
        recommendationScore += 0.05;
      }

      const roundedScore = Number(recommendationScore.toFixed(2));
      const recommendationTier = buildRecommendationTier(roundedScore);
      const biasQuality = buildBiasQualityMeta(policySourceHealth, inputReliability);
      const allocationBias = buildAdjustedAssets(template, signalContext, biasQuality);
      const prioritizedDrivers = [...matchedDrivers].sort((a, b) => {
        const priority = { resonance: 0, quality: 1, factor: 2, alert: 3, dimension: 4 };
        return (priority[a.type] ?? 9) - (priority[b.type] ?? 9);
      });
      const driverHeadline = matchedDrivers.length
        ? prioritizedDrivers
            .slice(0, 3)
            .map((item) => `${item.label}(${item.detail})`)
            .join(' · ')
        : '当前模板更多作为备用情景模板，可结合手动研究继续验证';

      const actionNote = `${template.name} 的推荐依据：${driverHeadline}。${template.narrative || template.description}`;

      return {
        ...template,
        longCount,
        shortCount,
        stance: longCount >= shortCount ? '偏防守/资源端' : '偏对冲/做空端',
        recommendationScore: roundedScore,
        recommendationTier,
        recommendationTone: buildRecommendationTone(roundedScore),
        matchedDrivers: prioritizedDrivers.slice(0, 4),
        driverHeadline,
        resonanceLabel: resonanceMeta.label,
        resonanceReason: resonanceMeta.reason,
        resonanceFactors: resonanceMatches,
        policySourceHealthLabel: policySourceHealth.label,
        policySourceHealthReason: policySourceHealth.reason,
        inputReliabilityLabel: inputReliability.label,
        inputReliabilityScore: inputReliability.score,
        inputReliabilityLead: inputReliability.lead,
        inputReliabilityPosture: inputReliability.posture,
        inputReliabilityReason: inputReliability.reason,
        adjustedAssets: allocationBias.adjustedAssets,
        biasSummary: allocationBias.biasSummary,
        biasStrength: allocationBias.biasStrength,
        biasScale: allocationBias.biasScale,
        biasQualityLabel: allocationBias.biasQualityLabel,
        biasQualityReason: allocationBias.biasQualityReason,
        biasHighlights: allocationBias.biasHighlights,
        biasActions: allocationBias.biasActions,
        signalAttribution: allocationBias.signalAttribution,
        driverSummary: allocationBias.driverSummary,
        dominantDrivers: allocationBias.dominantDrivers,
        coreLegs: allocationBias.coreLegs,
        supportLegs: allocationBias.supportLegs,
        themeCore: allocationBias.themeCore,
        themeSupport: allocationBias.themeSupport,
        action: buildAction ? buildAction(template.id, actionNote) : null,
      };
    })
    .sort((a, b) => b.recommendationScore - a.recommendationScore);
};
