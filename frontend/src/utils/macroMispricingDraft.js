const STORAGE_PREFIX = 'macro_mispricing_draft:';
const DEFAULT_TEMPLATE_ID = 'macro_mispricing_relative_value';
const DEFAULT_QUALITY = {
  construction_mode: 'equal_weight',
  min_history_days: 60,
  min_overlap_ratio: 0.7,
};
const DEFAULT_CONSTRAINTS = {
  max_single_weight: null,
  min_single_weight: null,
};
const DEFAULT_META = {
  initial_capital: 100000,
  commission: 0.1,
  slippage: 0.1,
};

const ETF_SYMBOLS = new Set([
  'SPY', 'QQQ', 'KWEB', 'XLK', 'XLC', 'XLY', 'XLP', 'XLF', 'XLV', 'XLE', 'XLI', 'XLB', 'XLU', 'XLRE', 'GLD', 'IEF',
]);

const normalizeSymbol = (value = '') => String(value || '').trim().toUpperCase();

const inferAssetClass = (symbol = '') => {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) return 'ETF';
  if (ETF_SYMBOLS.has(normalized)) return 'ETF';
  return 'US_STOCK';
};

const buildDraftId = (symbol = '') =>
  `mm_${normalizeSymbol(symbol) || 'draft'}_${Date.now().toString(36)}`;

const hasLongShortMix = (tradeLegs = []) => {
  const sides = new Set((tradeLegs || []).map((leg) => leg?.side).filter(Boolean));
  return sides.has('long') && sides.has('short');
};

export const buildMacroMispricingDraft = ({
  symbol = '',
  thesis = {},
  structuralDecay = {},
  peopleLayer = {},
  source = 'macro_mispricing',
  note = '',
  sourceTaskId = '',
  sourceTaskType = '',
} = {}) => {
  const normalizedSymbol = normalizeSymbol(symbol || thesis?.primary_leg?.symbol);
  const tradeLegs = Array.isArray(thesis?.trade_legs) && thesis.trade_legs.length
    ? thesis.trade_legs
    : [
        thesis?.primary_leg ? { ...thesis.primary_leg, weight: 1 } : null,
        thesis?.hedge_leg ? { ...thesis.hedge_leg, weight: 0 } : null,
      ].filter(Boolean);

  const assets = tradeLegs
    .filter((leg) => leg?.symbol && leg?.side && leg.side !== 'watch' && leg.side !== 'avoid')
    .map((leg) => ({
      symbol: normalizeSymbol(leg.symbol),
      asset_class: inferAssetClass(leg.symbol),
      side: leg.side,
      weight: leg.weight ?? undefined,
      role: leg.role || '',
      thesis: leg.thesis || '',
    }));
  const constructionMode = hasLongShortMix(tradeLegs) ? 'ols_hedge' : DEFAULT_QUALITY.construction_mode;
  const maxWeight = assets.length
    ? Math.max(...assets.map((asset) => Number(asset.weight || 0)).filter((value) => Number.isFinite(value)))
    : 0;
  const minWeight = assets.length
    ? Math.min(...assets.map((asset) => Number(asset.weight || 0)).filter((value) => Number.isFinite(value)))
    : 0;
  const coreLegs = tradeLegs
    .filter((leg) => leg?.role === 'core_expression')
    .map((leg) => ({ symbol: normalizeSymbol(leg.symbol), side: leg.side, role: leg.role, delta: leg.weight ?? null }));
  const supportLegs = tradeLegs
    .filter((leg) => leg?.role && leg.role !== 'core_expression')
    .map((leg) => ({ symbol: normalizeSymbol(leg.symbol), side: leg.side, role: leg.role, delta: leg.weight ?? null }));

  const id = buildDraftId(normalizedSymbol);

  return {
    id,
    templateId: DEFAULT_TEMPLATE_ID,
    title: `${normalizedSymbol || '目标'} 宏观错误定价组合草案`,
    note: note || thesis?.summary || structuralDecay?.summary || '',
    source,
    sourceTaskId,
    sourceTaskType,
    symbol: normalizedSymbol,
    assets,
    quality: {
      construction_mode: constructionMode,
      min_history_days: structuralDecay?.action === 'structural_short' ? 90 : DEFAULT_QUALITY.min_history_days,
      min_overlap_ratio: hasLongShortMix(tradeLegs) ? 0.75 : DEFAULT_QUALITY.min_overlap_ratio,
    },
    constraints: {
      max_single_weight: maxWeight ? Math.max(35, Math.round(maxWeight * 100)) : DEFAULT_CONSTRAINTS.max_single_weight,
      min_single_weight: minWeight ? Math.max(5, Math.round(minWeight * 100)) : DEFAULT_CONSTRAINTS.min_single_weight,
    },
    meta: {
      ...DEFAULT_META,
    },
    parameters: {
      lookback: 20,
      entry_threshold: thesis?.stance === '结构性做空' ? 1.25 : 1.5,
      exit_threshold: 0.5,
    },
    templateContext: {
      template_id: DEFAULT_TEMPLATE_ID,
      template_name: 'Macro Mispricing Relative Value',
      theme: thesis?.stance || 'Macro Mispricing Draft',
      thesis_type: thesis?.thesis_type || '',
      stance: thesis?.stance || '',
      horizon: thesis?.horizon || '',
      dominant_failure_label: structuralDecay?.dominant_failure_label || '',
      people_risk: peopleLayer?.risk_level || thesis?.people_risk || '',
      recommendation_reason: thesis?.summary || '',
      construction_mode: constructionMode,
      core_legs: coreLegs,
      support_legs: supportLegs,
      theme_core: coreLegs.map((leg) => leg.symbol).join(' / '),
      theme_support: supportLegs.map((leg) => leg.symbol).join(' / '),
      signal_attribution: tradeLegs.map((leg) => ({
        symbol: normalizeSymbol(leg.symbol),
        side: leg.side,
        role: leg.role || '',
        weight: leg.weight ?? null,
        thesis: leg.thesis || '',
      })),
    },
    thesis,
    structuralDecay,
    peopleLayer,
  };
};

export const saveMacroMispricingDraft = (draft) => {
  if (!draft?.id) return '';
  window.localStorage.setItem(`${STORAGE_PREFIX}${draft.id}`, JSON.stringify(draft));
  return draft.id;
};

export const loadMacroMispricingDraft = (id = '') => {
  const normalized = String(id || '').trim();
  if (!normalized) return null;
  const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${normalized}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (_error) {
    return null;
  }
};
