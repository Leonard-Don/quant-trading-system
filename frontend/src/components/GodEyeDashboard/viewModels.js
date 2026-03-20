import { buildCrossMarketCards as buildScoredCrossMarketCards } from '../../utils/crossMarketRecommendations';

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

const extractTemplateMeta = (task = {}) =>
  task?.snapshot?.payload?.template_meta
  || task?.snapshot_history?.[0]?.payload?.template_meta
  || {};

const extractTemplateIdentity = (task = {}, meta = {}) =>
  task.template || meta.template_id || '';

const extractDominantDriver = (meta = {}) => meta?.dominant_drivers?.[0] || null;

const formatDriverLabel = (driver = {}) =>
  driver?.label || formatFactorName(driver?.key || '');

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

export const buildHeatmapModel = (snapshot = {}, history = {}) => {
  const supplyDimensions = snapshot?.signals?.supply_chain?.dimensions || {};
  const macroDimensions = snapshot?.signals?.macro_hf?.dimensions || {};
  const records = history?.records || [];

  const cells = Object.entries(DIMENSION_META).map(([key, meta]) => {
    const source = supplyDimensions[key] || macroDimensions[key] || {};
    const relatedRecords = records.filter((item) => {
      if (meta.group === 'Supply Chain') {
        return ['bidding', 'env_assessment', 'hiring'].includes(item.category);
      }
      return ['commodity_inventory', 'customs', 'port_congestion'].includes(item.category);
    });

    const score = Number(source.score || 0);
    return {
      key,
      label: meta.label,
      group: meta.group,
      score,
      tone: scoreTone(score),
      count: Number(source.count || relatedRecords.length || 0),
      summary:
        meta.group === 'Supply Chain'
          ? `最近供应链记录 ${relatedRecords.length}`
          : `最近宏观高频记录 ${relatedRecords.length}`,
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
        description: `${cell.group} score=${cell.score.toFixed(3)}`,
        type: cell.tone,
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
  const factors = (overview?.factors || []).map((factor) => ({
    ...factor,
    displayName: formatFactorName(factor.name),
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

  alerts.push(...buildNarrativeShiftAlerts(researchTasks));

  alerts.sort((a, b) => {
    const priority = { high: 0, medium: 1, low: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return alerts.slice(0, 8);
};

export const buildCrossMarketCards = (payload = {}, overview = {}, snapshot = {}) =>
  buildScoredCrossMarketCards(payload, overview, snapshot, (templateId, note) =>
    buildCrossMarketAction(templateId, 'cross_market_overview', note)
  );
