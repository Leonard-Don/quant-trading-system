import { buildSnapshotComparison } from '../research-workbench/snapshotCompare';

export const ACTION_MAP = {
  pricing: { label: '打开定价剧本', target: 'pricing' },
  cross_market: { label: '打开跨市场剧本', target: 'cross-market' },
  observe: { label: '继续观察', target: 'observe' },
};

export const COMPANY_SYMBOL_MAP = {
  阿里巴巴: 'BABA',
  腾讯: '0700.HK',
  百度: 'BIDU',
  英伟达: 'NVDA',
  台积电: 'TSM',
};

export const TAG_SYMBOL_MAP = {
  AI算力: 'NVDA',
  半导体: 'TSM',
  电网: 'DUK',
  核电: 'CEG',
  风电: 'NEE',
  光伏: 'FSLR',
  储能: 'TSLA',
  新能源汽车: 'TSLA',
};

export const TAG_TEMPLATE_MAP = {
  AI算力: 'energy_vs_ai_apps',
  半导体: 'copper_vs_semis',
  电网: 'utilities_vs_growth',
  核电: 'energy_vs_ai_apps',
  风电: 'utilities_vs_growth',
  光伏: 'utilities_vs_growth',
  储能: 'energy_vs_ai_apps',
  新能源汽车: 'energy_vs_ai_apps',
};

export const FACTOR_TEMPLATE_MAP = {
  bureaucratic_friction: 'utilities_vs_growth',
  tech_dilution: 'defensive_beta_hedge',
  baseload_mismatch: 'energy_vs_ai_apps',
  rate_curve_pressure: 'defensive_beta_hedge',
  credit_spread_stress: 'defensive_beta_hedge',
  fx_mismatch: 'copper_vs_semis',
  people_fragility: 'people_decay_short_vs_cashflow_defensive',
  policy_execution_disorder: 'utilities_vs_growth',
};

export const FACTOR_SYMBOL_MAP = {
  bureaucratic_friction: 'QQQ',
  tech_dilution: 'NVDA',
  baseload_mismatch: 'DUK',
  rate_curve_pressure: 'TLT',
  credit_spread_stress: 'HYG',
  fx_mismatch: 'UUP',
  people_fragility: 'BABA',
  policy_execution_disorder: 'DUK',
};

export const formatTemplateName = (templateId = '') =>
  templateId
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export const formatFactorName = (name = '') => {
  const mapping = {
    bureaucratic_friction: '官僚摩擦',
    tech_dilution: '技术稀释',
    baseload_mismatch: '基荷错配',
    rate_curve_pressure: '利率曲线压力',
    credit_spread_stress: '信用利差压力',
    fx_mismatch: '汇率错配',
    people_fragility: '人的维度脆弱',
    policy_execution_disorder: '政策执行混乱',
  };
  return mapping[name] || name.replace(/_/g, ' ');
};

export const buildPricingAction = (symbol, source, note) =>
  symbol
    ? {
        ...ACTION_MAP.pricing,
        symbol,
        source,
        note,
      }
    : null;

export const buildCrossMarketAction = (template, source, note) =>
  template
    ? {
        ...ACTION_MAP.cross_market,
        template,
        source,
        note,
      }
    : null;

export const buildWorkbenchAction = (taskId, source, note, reason = '', label = '打开任务', type = 'cross_market') =>
  taskId
    ? {
        target: 'workbench',
        label,
        taskId,
        type,
        refresh: 'high',
        reason,
        source,
        note,
      }
    : null;

export const getReviewContextActionLabel = (reviewContextShift = null) => {
  if (reviewContextShift?.enteredReview) {
    return '按复核结果重看';
  }
  if (reviewContextShift?.exitedReview) {
    return '确认恢复普通结果';
  }
  if (reviewContextShift?.changed) {
    return '重新确认结果语境';
  }
  return '优先重看任务';
};

export const getInputReliabilityActionLabel = (inputReliabilityShift = null) => {
  if (inputReliabilityShift?.enteredFragile) {
    return '先复核输入可靠度';
  }
  if (inputReliabilityShift?.recoveredRobust) {
    return '确认恢复正常强度';
  }
  if (inputReliabilityShift?.recoveredFromFragile) {
    return '确认解除谨慎处理';
  }
  if (inputReliabilityShift?.labelChanged || Math.abs(Number(inputReliabilityShift?.scoreGap || 0)) >= 0.12) {
    return '重新确认输入质量';
  }
  return '打开任务';
};

export const extractTemplateMeta = (task = {}) =>
  task?.snapshot?.payload?.template_meta
  || task?.snapshot_history?.[0]?.payload?.template_meta
  || {};

export const extractAllocationOverlay = (task = {}) =>
  task?.snapshot?.payload?.allocation_overlay
  || task?.snapshot_history?.[0]?.payload?.allocation_overlay
  || {};

export const extractTemplateIdentity = (task = {}, meta = {}) =>
  task.template || meta.template_id || '';

export const extractDominantDriver = (meta = {}) => meta?.dominant_drivers?.[0] || null;

export const extractRecentComparisonLead = (task = {}) => {
  const history = task?.snapshot_history || [];
  if (history.length < 2 || task?.type !== 'cross_market') {
    return '';
  }
  const [latestSnapshot, previousSnapshot] = history;
  const latestSelectionQuality =
    latestSnapshot?.payload?.allocation_overlay?.selection_quality?.label
    || latestSnapshot?.payload?.template_meta?.selection_quality?.label;
  const previousSelectionQuality =
    previousSnapshot?.payload?.allocation_overlay?.selection_quality?.label
    || previousSnapshot?.payload?.template_meta?.selection_quality?.label;
  if (!latestSelectionQuality && !previousSelectionQuality) {
    return '';
  }
  return buildSnapshotComparison(task.type, history[1], history[0])?.lead || '';
};

export const formatDriverLabel = (driver = {}) =>
  driver?.label || formatFactorName(driver?.key || '');

export const buildDisplayTier = (score) => {
  if (score >= 2.6) return '优先部署';
  if (score >= 1.4) return '重点跟踪';
  return '候选模板';
};

export const buildDisplayTone = (score) => {
  if (score >= 2.6) return 'volcano';
  if (score >= 1.4) return 'gold';
  return 'blue';
};
