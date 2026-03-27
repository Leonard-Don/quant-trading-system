import { buildCrossMarketCards as buildScoredCrossMarketCards } from '../../utils/crossMarketRecommendations';
import { buildResearchTaskRefreshSignals } from '../../utils/researchTaskSignals';

const DIMENSION_META = {
  investment_activity: { label: '投资活跃度', group: 'Supply Chain' },
  project_pipeline: { label: '项目管线', group: 'Supply Chain' },
  talent_structure: { label: '人才结构', group: 'Supply Chain' },
  inventory: { label: '库存压力', group: 'Macro HF' },
  trade: { label: '贸易脉冲', group: 'Macro HF' },
  logistics: { label: '物流摩擦', group: 'Macro HF' },
};

const SIGNAL_LABEL = {
  1: '猎杀窗口',
  0: '观察中',
  '-1': '逆风区',
};

const ACTION_MAP = {
  pricing: { label: '打开定价剧本', target: 'pricing' },
  cross_market: { label: '打开跨市场剧本', target: 'cross-market' },
  observe: { label: '继续观察', target: 'observe' },
};

const COMPANY_SYMBOL_MAP = {
  阿里巴巴: 'BABA',
  腾讯: '0700.HK',
  百度: 'BIDU',
  英伟达: 'NVDA',
  台积电: 'TSM',
};

const TAG_SYMBOL_MAP = {
  AI算力: 'NVDA',
  半导体: 'TSM',
  电网: 'DUK',
  核电: 'CEG',
  风电: 'NEE',
  光伏: 'FSLR',
  储能: 'TSLA',
  新能源汽车: 'TSLA',
};

const TAG_TEMPLATE_MAP = {
  AI算力: 'energy_vs_ai_apps',
  半导体: 'copper_vs_semis',
  电网: 'utilities_vs_growth',
  核电: 'energy_vs_ai_apps',
  风电: 'utilities_vs_growth',
  光伏: 'utilities_vs_growth',
  储能: 'energy_vs_ai_apps',
  新能源汽车: 'energy_vs_ai_apps',
};

const FACTOR_TEMPLATE_MAP = {
  bureaucratic_friction: 'utilities_vs_growth',
  tech_dilution: 'defensive_beta_hedge',
  baseload_mismatch: 'energy_vs_ai_apps',
};

const FACTOR_SYMBOL_MAP = {
  bureaucratic_friction: 'QQQ',
  tech_dilution: 'NVDA',
  baseload_mismatch: 'DUK',
};

const formatTemplateName = (templateId = '') =>
  templateId
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

const formatFactorName = (name = '') => {
  const mapping = {
    bureaucratic_friction: '官僚摩擦',
    tech_dilution: '技术稀释',
    baseload_mismatch: '基荷错配',
  };
  return mapping[name] || name.replace(/_/g, ' ');
};

const toPercentScale = (value) => {
  const numeric = Number(value || 0);
  return Math.min(100, Math.max(8, Math.abs(numeric) * 40 + 15));
};

const scoreTone = (score) => {
  if (score >= 0.35) return 'hot';
  if (score <= -0.35) return 'cold';
  return 'neutral';
};

export const getSignalLabel = (value) => SIGNAL_LABEL[value] || SIGNAL_LABEL[0];

const buildPricingAction = (symbol, source, note) =>
  symbol
    ? {
        ...ACTION_MAP.pricing,
        symbol,
        source,
        note,
      }
    : null;

const buildCrossMarketAction = (template, source, note) =>
  template
    ? {
        ...ACTION_MAP.cross_market,
        template,
        source,
        note,
      }
    : null;

const buildWorkbenchAction = (taskId, source, note, reason = '') =>
  taskId
    ? {
        target: 'workbench',
        label: '打开任务',
        taskId,
        type: 'cross_market',
        refresh: 'high',
        reason,
        source,
        note,
      }
    : null;

const extractTemplateMeta = (task = {}) =>
  task?.snapshot?.payload?.template_meta
  || task?.snapshot_history?.[0]?.payload?.template_meta
  || {};

const extractAllocationOverlay = (task = {}) =>
  task?.snapshot?.payload?.allocation_overlay
  || task?.snapshot_history?.[0]?.payload?.allocation_overlay
  || {};

const extractTemplateIdentity = (task = {}, meta = {}) =>
  task.template || meta.template_id || '';

const extractDominantDriver = (meta = {}) => meta?.dominant_drivers?.[0] || null;

const formatDriverLabel = (driver = {}) =>
  driver?.label || formatFactorName(driver?.key || '');

const buildDisplayTier = (score) => {
  if (score >= 2.6) return '优先部署';
  if (score >= 1.4) return '重点跟踪';
  return '候选模板';
};

const buildDisplayTone = (score) => {
  if (score >= 2.6) return 'volcano';
  if (score >= 1.4) return 'gold';
  return 'blue';
};

const buildNarrativeShiftAlerts = (tasks = []) => {
  const grouped = tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }

    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }

    if (!accumulator[templateId]) {
      accumulator[templateId] = [];
    }
    accumulator[templateId].push(task);
    return accumulator;
  }, {});

  return Object.entries(grouped)
    .map(([templateId, templateTasks]) => {
      const orderedTasks = [...templateTasks].sort((left, right) =>
        String(right.updated_at || '').localeCompare(String(left.updated_at || ''))
      );
      const latestTask = orderedTasks[0];
      const latestMeta = extractTemplateMeta(latestTask);
      const latestDriver = extractDominantDriver(latestMeta);

      let previousMeta = latestTask?.snapshot_history?.[1]?.payload?.template_meta || null;
      if (!previousMeta && orderedTasks[1]) {
        previousMeta = extractTemplateMeta(orderedTasks[1]);
      }

      const previousDriver = extractDominantDriver(previousMeta || {});
      const driverSwitched =
        previousDriver?.key && latestDriver?.key && previousDriver.key !== latestDriver.key;
      const themeCoreChanged =
        previousMeta?.theme_core
        && latestMeta?.theme_core
        && previousMeta.theme_core !== latestMeta.theme_core;
      const supportChanged =
        previousMeta?.theme_support
        && latestMeta?.theme_support
        && previousMeta.theme_support !== latestMeta.theme_support;

      if (!driverSwitched && !themeCoreChanged && !supportChanged) {
        return null;
      }

      const currentDriverLabel = formatDriverLabel(latestDriver || {});
      const previousDriverLabel = formatDriverLabel(previousDriver || {});
      const templateName = latestTask?.title || latestMeta?.template_name || formatTemplateName(templateId);

      const details = [];
      if (driverSwitched) {
        details.push(`主导驱动从 ${previousDriverLabel} 切换到 ${currentDriverLabel}`);
      }
      if (themeCoreChanged) {
        details.push(`核心腿从 ${previousMeta.theme_core} 调整为 ${latestMeta.theme_core}`);
      }
      if (supportChanged) {
        details.push(`辅助腿从 ${previousMeta.theme_support} 变为 ${latestMeta.theme_support}`);
      }

      return {
        key: `narrative-shift-${templateId}`,
        title: `${templateName} 主导叙事切换`,
        severity: driverSwitched ? 'high' : 'medium',
        description: details.join('；'),
        action: buildCrossMarketAction(
          templateId,
          'alert_hunter',
          `${templateName} 最近研究快照出现叙事切换，建议重新打开跨市场剧本复核。`
        ),
      };
    })
    .filter(Boolean)
    .slice(0, 3);
};

const buildNarrativeTrendLookup = (tasks = []) => {
  const grouped = tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }

    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }

    if (!accumulator[templateId]) {
      accumulator[templateId] = [];
    }
    accumulator[templateId].push(task);
    return accumulator;
  }, {});

  return Object.fromEntries(
    Object.entries(grouped).map(([templateId, templateTasks]) => {
      const orderedTasks = [...templateTasks].sort((left, right) =>
        String(right.updated_at || '').localeCompare(String(left.updated_at || ''))
      );
      const latestTask = orderedTasks[0];
      const latestMeta = extractTemplateMeta(latestTask);
      const latestOverlay = extractAllocationOverlay(latestTask);
      let previousMeta = latestTask?.snapshot_history?.[1]?.payload?.template_meta || null;
      if (!previousMeta && orderedTasks[1]) {
        previousMeta = extractTemplateMeta(orderedTasks[1]);
      }

      const latestDriver = extractDominantDriver(latestMeta);
      const previousDriver = extractDominantDriver(previousMeta || {});
      const latestDriverValue = Number(latestDriver?.value || 0);
      const previousDriverValue = Number(previousDriver?.value || 0);
      const driverDelta = Number((latestDriverValue - previousDriverValue).toFixed(4));
      const driverSwitched =
        latestDriver?.key && previousDriver?.key && latestDriver.key !== previousDriver.key;
      const themeCoreChanged =
        previousMeta?.theme_core
        && latestMeta?.theme_core
        && previousMeta.theme_core !== latestMeta.theme_core;

      let trendLabel = '新建主题';
      let trendTone = 'blue';
      let trendSummary = '当前模板尚未积累足够的研究快照，先按实时推荐信号处理。';

      if (previousMeta) {
        if (driverSwitched) {
          trendLabel = '叙事切换';
          trendTone = 'volcano';
          trendSummary = `主导驱动从 ${formatDriverLabel(previousDriver || {})} 切换到 ${formatDriverLabel(latestDriver || {})}`;
        } else if (driverDelta >= 0.04) {
          trendLabel = '驱动增强';
          trendTone = 'green';
          trendSummary = `${formatDriverLabel(latestDriver || {})} 持续增强，变化幅度 ${driverDelta.toFixed(2)}`;
        } else if (driverDelta <= -0.04) {
          trendLabel = '驱动走弱';
          trendTone = 'gold';
          trendSummary = `${formatDriverLabel(latestDriver || {})} 走弱，变化幅度 ${driverDelta.toFixed(2)}`;
        } else {
          trendLabel = themeCoreChanged ? '核心腿调整' : '叙事稳定';
          trendTone = themeCoreChanged ? 'purple' : 'cyan';
          trendSummary = themeCoreChanged
            ? `核心腿从 ${previousMeta.theme_core} 调整为 ${latestMeta.theme_core}`
            : `${formatDriverLabel(latestDriver || {})} 仍是主导驱动，主题结构基本稳定`;
        }
      }

      return [templateId, {
        trendLabel,
        trendTone,
        trendSummary,
        trendDelta: driverDelta,
        latestDriverLabel: formatDriverLabel(latestDriver || {}),
        latestDriverValue,
        latestThemeCore: latestMeta?.theme_core || '',
        latestThemeSupport: latestMeta?.theme_support || '',
        latestCompressedAssets: latestOverlay?.compressed_assets || [],
        latestCompressionEffect: Number(latestOverlay?.compression_summary?.compression_effect || 0),
        latestTopCompressedAsset:
          (latestOverlay?.rows || [])
            .slice()
            .sort((left, right) => Math.abs(Number(right?.compression_delta || 0)) - Math.abs(Number(left?.compression_delta || 0)))
            .map((item) =>
              Math.abs(Number(item?.compression_delta || 0)) >= 0.005
                ? `${item.symbol} ${(Math.abs(Number(item.compression_delta || 0)) * 100).toFixed(2)}pp`
                : null
            )
            .find(Boolean)
          || '',
      }];
    })
  );
};

export const buildHeatmapModel = (snapshot = {}, history = {}) => {
  const supplyDimensions = snapshot?.signals?.supply_chain?.dimensions || {};
  const macroDimensions = snapshot?.signals?.macro_hf?.dimensions || {};
  const records = history?.records || [];
  const categoryTrends = history?.category_trends || {};
  const categorySeries = history?.category_series || {};

  const groupCategories = {
    'Supply Chain': ['bidding', 'env_assessment', 'hiring'],
    'Macro HF': ['commodity_inventory', 'customs', 'port_congestion'],
  };

  const buildGroupTrend = (group) => {
    const categories = groupCategories[group] || [];
    const trends = categories
      .map((category) => categoryTrends[category])
      .filter(Boolean);
    const count = trends.reduce((sum, item) => sum + Number(item.count || 0), 0);
    const weightedDeltaTotal = trends.reduce(
      (sum, item) => sum + Number(item.delta_score || 0) * Math.max(Number(item.count || 0), 1),
      0
    );
    const deltaScore = count > 0 ? weightedDeltaTotal / count : 0;
    const momentum =
      deltaScore >= 0.12 ? 'strengthening' : deltaScore <= -0.12 ? 'weakening' : 'stable';
    return {
      deltaScore: Number(deltaScore || 0),
      count,
      momentum,
      categories,
      sparkline: categories.flatMap((category) => categorySeries[category] || []).slice(-6),
    };
  };

  const cells = Object.entries(DIMENSION_META).map(([key, meta]) => {
    const source = supplyDimensions[key] || macroDimensions[key] || {};
    const relatedRecords = records.filter((item) => {
      if (meta.group === 'Supply Chain') {
        return ['bidding', 'env_assessment', 'hiring'].includes(item.category);
      }
      return ['commodity_inventory', 'customs', 'port_congestion'].includes(item.category);
    });
    const trend = buildGroupTrend(meta.group);

    const score = Number(source.score || 0);
    return {
      key,
      label: meta.label,
      group: meta.group,
      score,
      tone: scoreTone(score),
      count: Number(source.count || trend.count || relatedRecords.length || 0),
      summary: `${meta.group === 'Supply Chain' ? '供应链' : '宏观高频'} ${trend.momentum === 'strengthening' ? '增强' : trend.momentum === 'weakening' ? '走弱' : '稳定'} · Δ${trend.deltaScore >= 0 ? '+' : ''}${trend.deltaScore.toFixed(2)}`,
      trendDelta: trend.deltaScore,
      momentum: trend.momentum,
    };
  });

  const anomalies = [];
  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  supplyAlerts.slice(0, 3).forEach((alert) => {
    anomalies.push({
      key: `supply-alert-${alert.company || 'unknown'}`,
      title: alert.company || '供应链异常',
      description: alert.message || `dilution ratio ${alert.dilution_ratio || 0}`,
      type: 'alert',
    });
  });

  cells
    .filter((cell) => Math.abs(cell.score) >= 0.3)
    .slice(0, 3)
    .forEach((cell) => {
      anomalies.push({
        key: `heat-${cell.key}`,
        title: `${cell.label}出现显著偏移`,
        description: `${cell.group} score=${cell.score.toFixed(3)} · ${cell.momentum === 'strengthening' ? '增强' : cell.momentum === 'weakening' ? '走弱' : '稳定'} ${cell.trendDelta >= 0 ? '+' : ''}${cell.trendDelta.toFixed(2)}`,
        type: cell.tone,
      });
    });

  Object.entries(categoryTrends)
    .filter(([, trend]) => Math.abs(Number(trend?.delta_score || 0)) >= 0.12)
    .slice(0, 3)
    .forEach(([category, trend]) => {
      anomalies.push({
        key: `trend-${category}`,
        title: `${category} 趋势${trend.momentum === 'strengthening' ? '增强' : '走弱'}`,
        description: `最近窗口 Δ${Number(trend.delta_score || 0) >= 0 ? '+' : ''}${Number(trend.delta_score || 0).toFixed(2)} · 高置信 ${trend.high_confidence_count || 0}`,
        type: trend.momentum === 'strengthening' ? 'hot' : 'cold',
      });
    });

  return { cells, anomalies };
};

export const buildRadarModel = (overview = {}) => {
  const factors = overview?.factors || [];
  return factors.map((factor) => ({
    factor: formatFactorName(factor.name),
    intensity: toPercentScale(factor.z_score || factor.value),
    confidence: Math.min(100, Math.max(10, Number(factor.confidence || 0) * 100)),
    rawValue: Number(factor.value || 0),
    zScore: Number(factor.z_score || 0),
    signal: factor.signal,
  }));
};

export const buildFactorPanelModel = (overview = {}, snapshot = {}) => {
  const factorDeltas = overview?.trend?.factor_deltas || {};
  const factors = (overview?.factors || []).map((factor) => ({
    ...factor,
    displayName: formatFactorName(factor.name),
    trendDelta: Number(factorDeltas[factor.name]?.z_score_delta || 0),
    trendValueDelta: Number(factorDeltas[factor.name]?.value_delta || 0),
    signalChanged: Boolean(factorDeltas[factor.name]?.signal_changed),
    previousSignal: Number(factorDeltas[factor.name]?.previous_signal || 0),
    evidenceSummary: factor?.metadata?.evidence_summary || {},
    action:
      factor.signal === 1
        ? buildCrossMarketAction(
            FACTOR_TEMPLATE_MAP[factor.name],
            'factor_panel',
            `${formatFactorName(factor.name)} 偏向正向扭曲，建议先看跨市场对冲模板`
          )
        : factor.signal === -1
          ? buildPricingAction(
              FACTOR_SYMBOL_MAP[factor.name],
              'factor_panel',
              `${formatFactorName(factor.name)} 偏向负向错价，建议先看单标的定价研究`
            )
          : null,
  }));

  const topFactors = [...factors]
    .sort((a, b) => Math.abs(Number(b.z_score || 0)) - Math.abs(Number(a.z_score || 0)))
    .slice(0, 3);

  return {
    topFactors,
    factors,
    providerHealth: overview?.provider_health || snapshot?.provider_health || {},
    staleness: overview?.data_freshness || snapshot?.staleness || {},
    macroTrend: overview?.trend || {},
    resonanceSummary: overview?.resonance_summary || {},
    evidenceSummary: overview?.evidence_summary || snapshot?.evidence_summary || {},
    confidenceAdjustment: overview?.confidence_adjustment || {},
    primaryAction: topFactors[0]?.action || null,
  };
};

export const buildTimelineModel = (policyHistory = {}) => {
  const records = policyHistory?.records || [];
  return records.map((item) => {
    const raw = item.raw_value || {};
    const shift = Number(raw.policy_shift || 0);
    const tags = Object.keys(raw.industry_impact || {});
    const primaryTag = tags.find((tag) => TAG_SYMBOL_MAP[tag] || TAG_TEMPLATE_MAP[tag]);
    return {
      key: item.record_id,
      title: raw.title || item.source,
      timestamp: item.timestamp,
      source: item.source,
      direction: shift > 0.15 ? 'stimulus' : shift < -0.15 ? 'tightening' : 'neutral',
      directionLabel: shift > 0.15 ? '偏刺激' : shift < -0.15 ? '偏收紧' : '中性',
      tags,
      score: shift,
      confidence: Number(item.confidence || 0),
      details: raw.industry_impact || {},
      primaryAction:
        primaryTag && TAG_SYMBOL_MAP[primaryTag]
          ? buildPricingAction(
              TAG_SYMBOL_MAP[primaryTag],
              'policy_timeline',
              `${primaryTag} 受到政策影响，建议先做定价研究`
            )
          : null,
      secondaryAction:
        primaryTag && TAG_TEMPLATE_MAP[primaryTag]
          ? buildCrossMarketAction(
              TAG_TEMPLATE_MAP[primaryTag],
              'policy_timeline',
              `${primaryTag} 对应的宏观主题已映射到跨市场模板`
            )
          : null,
    };
  });
};

export const buildHunterModel = ({ snapshot = {}, overview = {}, status = {}, researchTasks = [] }) => {
  const alerts = [];
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  Object.entries(refreshStatus).forEach(([name, info]) => {
    if (['degraded', 'error'].includes(info.status)) {
      alerts.push({
        key: `provider-${name}`,
        title: `${name} 数据状态 ${info.status}`,
        severity: info.status === 'error' ? 'high' : 'medium',
        description: info.error || '继续使用最近成功快照',
        action: ACTION_MAP.observe,
      });
    }
  });

  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  supplyAlerts.forEach((item, index) => {
    const symbol = COMPANY_SYMBOL_MAP[item.company] || null;
    alerts.push({
      key: `supply-${index}`,
      title: `${item.company || '未知公司'} 人才结构预警`,
      severity: 'high',
      description: item.message || `dilution ratio ${item.dilution_ratio || 0}`,
      action: symbol
        ? buildPricingAction(symbol, 'alert_hunter', item.message || '人才结构预警')
        : buildCrossMarketAction('defensive_beta_hedge', 'alert_hunter', item.message || '人才结构预警'),
    });
  });

  (overview?.factors || [])
    .filter((item) => item.signal !== 0)
    .forEach((factor) => {
      alerts.push({
        key: `factor-${factor.name}`,
        title: `${formatFactorName(factor.name)} 出现偏移`,
        severity: Math.abs(Number(factor.z_score || 0)) > 1 ? 'high' : 'medium',
        description: `value=${Number(factor.value || 0).toFixed(3)} z=${Number(factor.z_score || 0).toFixed(3)}`,
        action:
          factor.signal === 1
            ? buildCrossMarketAction(
                FACTOR_TEMPLATE_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看跨市场模板`
              )
            : buildPricingAction(
                FACTOR_SYMBOL_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看单标的定价研究`
              ),
      });
    });

  const resonance = overview?.resonance_summary || {};
  const resonanceFactors = [
    ...(resonance.positive_cluster || []),
    ...(resonance.negative_cluster || []),
    ...(resonance.reversed_factors || []),
    ...(resonance.precursor || []),
    ...(resonance.weakening || []),
  ];
  if (resonance.label && resonance.label !== 'mixed' && resonanceFactors.length) {
    const primaryFactor = resonanceFactors[0];
    const clusterFactors = Array.from(new Set(resonanceFactors))
      .slice(0, 3)
      .map((name) => formatFactorName(name))
      .join('、');
    const severity =
      resonance.label === 'reversal_cluster'
        ? 'high'
        : resonance.label === 'precursor_cluster' || resonance.label === 'fading_cluster'
          ? 'medium'
          : 'high';

    alerts.push({
      key: `resonance-${resonance.label}`,
      title: `宏观因子共振 ${resonance.label}`,
      severity,
      description: `${resonance.reason} · ${clusterFactors}`,
      action: buildCrossMarketAction(
        FACTOR_TEMPLATE_MAP[primaryFactor],
        'alert_hunter',
        `${clusterFactors} 正在形成宏观共振，建议打开跨市场剧本复核当前模板。`
      ),
    });
  }

  alerts.push(...buildNarrativeShiftAlerts(researchTasks));

  const refreshSignals = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot });
  refreshSignals.prioritized
    .filter((item) => item.severity !== 'low')
    .slice(0, 3)
    .forEach((item) => {
      alerts.push({
        key: `refresh-${item.taskId}`,
        title: `${item.title || formatTemplateName(item.templateId)} ${item.refreshLabel}`,
        severity: item.severity,
        description: [
          item.summary,
          item.selectionQualityDriven && item.selectionQualityShift?.currentLabel
            ? `自动降级 ${item.selectionQualityShift.currentLabel}`
            : '',
          item.biasCompressionDriven && item.biasCompressionShift?.topCompressedAsset
            ? `压缩焦点 ${item.biasCompressionShift.topCompressedAsset}`
            : '',
        ].filter(Boolean).join(' · '),
        action:
          item.severity === 'high'
            ? buildWorkbenchAction(
                item.taskId,
                'alert_hunter',
                `${item.title || formatTemplateName(item.templateId)} 当前研究输入已经变化，建议直接打开对应任务更新判断。`,
                item.priorityReason || ''
              )
            : buildCrossMarketAction(
                item.templateId,
                'alert_hunter',
                `${item.title || formatTemplateName(item.templateId)} 当前研究输入已经变化，建议重新打开跨市场剧本更新判断。`
              ),
      });
    });

  alerts.sort((a, b) => {
    const priority = { high: 0, medium: 1, low: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return alerts.slice(0, 8);
};

export const buildCrossMarketCards = (
  payload = {},
  overview = {},
  snapshot = {},
  researchTasks = [],
) => {
  const trendLookup = buildNarrativeTrendLookup(researchTasks);
  const refreshLookup = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot }).byTemplateId;

  return buildScoredCrossMarketCards(
    payload,
    overview,
    snapshot,
    (templateId, note) => buildCrossMarketAction(templateId, 'cross_market_overview', note)
  )
    .map((card) => {
      const trendMeta = trendLookup[card.id] || {};
      const refreshMeta = refreshLookup[card.id] || null;
      const rankingPenalty = refreshMeta?.biasCompressionShift?.coreLegAffected
        ? 0.45
        : refreshMeta?.selectionQualityDriven
          ? 0.2
          : 0;
      const adjustedScore = Number(Math.max(0, Number(card.recommendationScore || 0) - rankingPenalty).toFixed(2));

      return {
        ...card,
        baseRecommendationScore: card.recommendationScore,
        baseRecommendationTier: card.recommendationTier,
        rankingPenalty,
        rankingPenaltyReason: rankingPenalty
          ? refreshMeta?.biasCompressionShift?.coreLegAffected
            ? `核心腿 ${refreshMeta?.biasCompressionShift?.topCompressedAsset || ''} 已进入偏置收缩焦点，模板排序自动降级`
            : `当前主题已进入自动降级处理，模板排序谨慎下调`
          : '',
        recommendationScore: adjustedScore,
        recommendationTier: buildDisplayTier(adjustedScore),
        recommendationTone: buildDisplayTone(adjustedScore),
        ...trendMeta,
        ...(refreshMeta
          ? {
              taskRefreshTaskId: refreshMeta.taskId,
              taskRefreshSeverity: refreshMeta.severity,
              taskRefreshLabel: refreshMeta.refreshLabel,
              taskRefreshTone: refreshMeta.refreshTone,
              taskRefreshSummary: refreshMeta.summary,
              taskRefreshResonanceDriven: refreshMeta.resonanceDriven,
              taskRefreshPolicySourceDriven: refreshMeta.policySourceDriven,
              taskRefreshBiasCompressionDriven: refreshMeta.biasCompressionDriven,
              taskRefreshSelectionQualityDriven: refreshMeta.selectionQualityDriven,
              taskRefreshSelectionQualityShift: refreshMeta.selectionQualityShift,
              taskRefreshBiasCompressionShift: refreshMeta.biasCompressionShift,
              taskRefreshBiasCompressionCore: refreshMeta.biasCompressionShift?.coreLegAffected || false,
              taskRefreshTopCompressedAsset: refreshMeta.biasCompressionShift?.topCompressedAsset || '',
              taskRefreshPolicySourceShift: refreshMeta.policySourceShift,
              taskAction:
                refreshMeta.severity === 'high'
                  ? buildWorkbenchAction(
                      refreshMeta.taskId,
                      'cross_market_overview',
                      `${card.name} 当前更适合直接打开对应任务处理。`,
                      refreshMeta.priorityReason || ''
                    )
                  : null,
            }
          : {}),
      };
    })
    .sort((left, right) => Number(right.recommendationScore || 0) - Number(left.recommendationScore || 0));
};
