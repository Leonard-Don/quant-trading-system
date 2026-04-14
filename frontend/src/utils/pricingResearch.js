export const resolveAnalysisSymbol = (input, fallbackSymbol = '') => {
  const candidate = typeof input === 'string' ? input : fallbackSymbol;
  return String(candidate || '').trim().toUpperCase();
};

export const parsePricingUniverseInput = (input = '') => {
  const seen = new Set();
  return String(input || '')
    .split(/[\s,，;；|]+/g)
    .map((item) => resolveAnalysisSymbol(item))
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
};

export const HOT_PRICING_SYMBOLS = [
  { symbol: 'AAPL', name: 'Apple' },
  { symbol: 'MSFT', name: 'Microsoft' },
  { symbol: 'NVDA', name: 'NVIDIA' },
  { symbol: 'AMZN', name: 'Amazon' },
  { symbol: 'GOOGL', name: 'Alphabet' },
  { symbol: 'META', name: 'Meta Platforms' },
];

export const SCREENING_PRESETS = [
  { key: 'megacap', label: '美股巨头', symbols: ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META'] },
  { key: 'semis', label: '半导体', symbols: ['NVDA', 'AMD', 'AVGO', 'TSM', 'QCOM'] },
  { key: 'growth', label: '高增长软件', symbols: ['PLTR', 'SNOW', 'CRM', 'NOW', 'SHOP'] },
];

const DRIVER_IMPACT_META = {
  positive: { color: 'green', label: '超额收益' },
  negative: { color: 'red', label: '收益承压' },
  risk: { color: 'orange', label: '系统性风险' },
  defensive: { color: 'blue', label: '防御溢价' },
  style: { color: 'purple', label: '风格暴露' },
  overvalued: { color: 'red', label: '估值溢价' },
  undervalued: { color: 'green', label: '估值折价' },
};

export const getDriverImpactMeta = (impact) => DRIVER_IMPACT_META[impact] || { color: '#d9d9d9', label: '其他因素' };

export const getSignalStrengthMeta = (value) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return null;
  }

  if (numeric >= 3) {
    return { score: numeric, label: '强', color: 'red' };
  }
  if (numeric >= 1.5) {
    return { score: numeric, label: '中', color: 'gold' };
  }
  return { score: numeric, label: '弱', color: 'blue' };
};

const PRICE_SOURCE_LABELS = {
  live: '实时价格',
  fundamental_current_price: '基本面现价',
  fundamental_regular_market_price: '行情快照价',
  fundamental_previous_close: '前收盘价',
  historical_close: '最近收盘价',
  unavailable: '价格缺失',
};

export const getPriceSourceLabel = (source = '') => PRICE_SOURCE_LABELS[source] || '价格来源未知';

const CONFIDENCE_LABELS = {
  low: '低',
  medium: '中',
  high: '高',
};

export const getConfidenceLabel = (value = '') => CONFIDENCE_LABELS[String(value || '').toLowerCase()] || '';

export const getSourceModeLabel = (summary = {}) => {
  const label = String(summary?.label || '').trim().toLowerCase();
  if (label === 'official-led') {
    return '官方/披露主导';
  }
  if (label === 'fallback-heavy') {
    return '回退源偏多';
  }
  if (label === 'mixed') {
    return '混合来源';
  }
  return summary?.dominant || '来源待确认';
};

export const buildScreeningScore = ({
  gapPct,
  confidenceScore,
  alignmentStatus,
  primaryView,
  governanceDiscountPct,
  governanceConfidence,
}) => {
  const baseScore = Math.abs(Number(gapPct || 0)) * Math.max(Number(confidenceScore || 0), 0.2);
  const alignmentBonus = {
    aligned: 4,
    partial: 1.5,
    neutral: 0,
    conflict: -4,
  }[alignmentStatus] || 0;
  let viewBonus = primaryView === '高估' || primaryView === '低估' ? 2 : 0;
  const governancePenalty = Math.max(Number(governanceDiscountPct || 0), 0) * Math.max(Number(governanceConfidence || 0), 0.2) * 0.18;
  const governanceSupport = Math.abs(Math.min(Number(governanceDiscountPct || 0), 0)) * Math.max(Number(governanceConfidence || 0), 0.2) * 0.12;
  if (primaryView === '高估') {
    viewBonus += governancePenalty;
  } else if (primaryView === '低估') {
    viewBonus -= governancePenalty;
    viewBonus += governanceSupport;
  }
  return Number(Math.max(baseScore + alignmentBonus + viewBonus, 0).toFixed(2));
};

export const buildPricingActionPosture = ({
  gapPct,
  confidenceScore,
  alignmentStatus,
  primaryView,
  riskLevel,
} = {}) => {
  const numericGap = Math.abs(Number(gapPct || 0));
  const numericConfidence = Number(confidenceScore || 0);
  const normalizedAlignment = String(alignmentStatus || '').toLowerCase();
  const normalizedView = String(primaryView || '').trim();
  const normalizedRisk = String(riskLevel || '').toLowerCase();
  const isDirectionalView = normalizedView === '低估' || normalizedView === '高估';

  if (
    normalizedAlignment === 'conflict'
    || normalizedRisk === 'high'
    || (isDirectionalView && numericConfidence < 0.45)
  ) {
    return {
      type: 'warning',
      label: 'review',
      posture: '先复核定价假设',
      title: '当前更适合先复核定价逻辑',
      actionHint: normalizedView === '低估'
        ? '先复核低估逻辑和关键因子，再决定是否进入买入清单。'
        : normalizedView === '高估'
          ? '先复核高估逻辑和风险边界，再决定是否进入减仓或回避清单。'
          : '先复核估值假设和证据来源，再决定是否继续沿用当前结论。',
      reason: normalizedAlignment === 'conflict'
        ? '当前估值方向与因子证据存在冲突。'
        : normalizedRisk === 'high'
          ? '当前风险等级偏高，结果更适合作为复核输入。'
          : '当前置信度偏弱，暂时不适合直接把结论推进到执行层。',
    };
  }

  if (
    isDirectionalView
    && numericGap >= 15
    && numericConfidence >= 0.72
    && normalizedAlignment === 'aligned'
    && normalizedRisk !== 'high'
  ) {
    return {
      type: 'success',
      label: 'deploy',
      posture: '可推进到执行清单',
      title: normalizedView === '低估' ? '当前可以推进到优先买入清单' : '当前可以推进到优先减仓清单',
      actionHint: normalizedView === '低估'
        ? '可以把这条标的推进到优先买入清单，并继续围绕目标价和风险边界拆解仓位计划。'
        : '可以把这条标的推进到优先减仓或回避清单，并继续确认风险预算和兑现节奏。',
      reason: `当前偏差 ${numericGap.toFixed(1)}%，且证据共振与置信度都支持这条判断。`,
    };
  }

  return {
    type: 'info',
    label: 'observe',
    posture: '继续观察与跟踪',
    title: '当前更适合继续观察与跟踪',
    actionHint: isDirectionalView
      ? '可以继续跟踪偏差、因子共振和置信度变化，等待更清晰的执行窗口。'
      : '当前更适合把它作为观察名单，而不是立即推进到执行清单。',
    reason: isDirectionalView
      ? `当前偏差 ${numericGap.toFixed(1)}%，但还没到足够清晰的执行状态。`
      : '当前更像是合理定价附近的跟踪结论，适合继续观察而不是立刻动作。',
  };
};

export const buildScreeningRowFromAnalysis = (analysis, period = '1y') => {
  const gap = analysis?.gap_analysis || {};
  const implications = analysis?.implications || {};
  const valuation = analysis?.valuation || {};
  const primaryDriver = analysis?.deviation_drivers?.primary_driver || null;
  const factorAlignment = implications.factor_alignment || {};
  const governanceOverlay = analysis?.people_governance_overlay || {};
  return {
    symbol: analysis?.symbol || '',
    company_name: valuation.company_name || '',
    sector: valuation.sector || '',
    period,
    current_price: gap.current_price,
    fair_value: gap.fair_value_mid,
    gap_pct: gap.gap_pct,
    direction: gap.direction,
    severity: gap.severity,
    severity_label: gap.severity_label,
    primary_view: implications.primary_view,
    confidence: implications.confidence,
    confidence_score: implications.confidence_score,
    factor_alignment_status: factorAlignment.status,
    factor_alignment_label: factorAlignment.label,
    factor_alignment_summary: factorAlignment.summary,
    price_source: valuation.current_price_source,
    primary_driver: primaryDriver?.factor || '',
    primary_driver_reason: primaryDriver?.ranking_reason || '',
    people_governance_discount_pct: governanceOverlay.governance_discount_pct,
    people_governance_confidence: governanceOverlay.confidence,
    people_governance_label: governanceOverlay.label || '',
    people_governance_summary: governanceOverlay.summary || '',
    summary: analysis?.summary || '',
    screening_score: buildScreeningScore({
      gapPct: gap.gap_pct,
      confidenceScore: implications.confidence_score,
      alignmentStatus: factorAlignment.status,
      primaryView: implications.primary_view,
      governanceDiscountPct: governanceOverlay.governance_discount_pct,
      governanceConfidence: governanceOverlay.confidence,
    }),
  };
};

export const sortScreeningRows = (rows = []) => [...rows].sort((left, right) => {
  if (Number(right.screening_score || 0) !== Number(left.screening_score || 0)) {
    return Number(right.screening_score || 0) - Number(left.screening_score || 0);
  }
  return Math.abs(Number(right.gap_pct || 0)) - Math.abs(Number(left.gap_pct || 0));
}).map((item, index) => ({ ...item, rank: index + 1 }));

export const buildRecentPricingResearchEntries = (tasks = []) => {
  const entries = [];
  const seen = new Set();

  (tasks || []).forEach((item) => {
    const symbol = resolveAnalysisSymbol(item?.symbol || item?.context?.symbol || item?.snapshot?.payload?.symbol);
    if (!symbol || seen.has(symbol)) {
      return;
    }

    const payload = item?.snapshot?.payload || {};
    const implications = payload?.implications || {};
    const primaryDriver = payload?.deviation_drivers?.primary_driver || {};
    const factorAlignment = implications?.factor_alignment || {};
    const period = payload?.period || item?.context?.period || payload?.factor_model?.period || '';
    const primaryView = implications?.primary_view || payload?.gap_analysis?.direction || '';
    const confidence = implications?.confidence || '';
    const confidenceLabel = getConfidenceLabel(confidence);

    entries.push({
      symbol,
      task_id: item?.id || '',
      title: item?.title || '',
      headline: item?.snapshot?.headline || '',
      summary: item?.snapshot?.summary || '',
      period,
      primary_view: primaryView,
      confidence,
      confidence_label: confidenceLabel,
      factor_alignment_status: factorAlignment?.status || '',
      factor_alignment_label: factorAlignment?.label || '',
      primary_driver: primaryDriver?.factor || '',
      primary_driver_reason: primaryDriver?.ranking_reason || '',
      recent: true,
      updated_at: item?.updated_at || item?.snapshot?.saved_at || item?.created_at || '',
    });
    seen.add(symbol);
  });

  return entries;
};

export const mergePricingSuggestions = (apiItems = [], preferredEntries = [], query = '') => {
  const normalizedQuery = String(query || '').trim().toUpperCase();
  const normalizedPreferred = [];
  const seenPreferred = new Set();
  preferredEntries.forEach((item) => {
    const entry = typeof item === 'string' ? { symbol: item } : (item || {});
    const symbol = resolveAnalysisSymbol(entry.symbol);
    if (!symbol || seenPreferred.has(symbol)) {
      return;
    }
    const searchBlob = [
      symbol,
      String(entry.title || '').toUpperCase(),
      String(entry.headline || '').toUpperCase(),
      String(entry.summary || '').toUpperCase(),
    ].join(' ');
    if (normalizedQuery && !searchBlob.includes(normalizedQuery)) {
      return;
    }
    seenPreferred.add(symbol);
    normalizedPreferred.push({
      symbol,
      ...entry,
    });
  });

  const apiBySymbol = new Map();
  (apiItems || []).forEach((item) => {
    const symbol = resolveAnalysisSymbol(item?.symbol);
    if (!symbol) {
      return;
    }
    apiBySymbol.set(symbol, {
      ...item,
      symbol,
    });
  });

  const merged = [];
  const used = new Set();

  normalizedPreferred.forEach((entry) => {
    const symbol = resolveAnalysisSymbol(entry.symbol);
    const apiItem = apiBySymbol.get(symbol);
    merged.push({
      symbol,
      name: apiItem?.name || '',
      group: apiItem?.group || '最近研究',
      market: apiItem?.market || '',
      recent: true,
      task_id: entry.task_id || '',
      primary_view: entry.primary_view || '',
      confidence: entry.confidence || '',
      confidence_label: entry.confidence_label || getConfidenceLabel(entry.confidence),
      factor_alignment_status: entry.factor_alignment_status || '',
      factor_alignment_label: entry.factor_alignment_label || '',
      primary_driver: entry.primary_driver || '',
      primary_driver_reason: entry.primary_driver_reason || '',
      period: entry.period || '',
      headline: entry.headline || '',
      summary: entry.summary || '',
    });
    used.add(symbol);
  });

  Array.from(apiBySymbol.values()).forEach((item) => {
    if (used.has(item.symbol)) {
      return;
    }
    merged.push({
      ...item,
      recent: false,
    });
    used.add(item.symbol);
  });

  return merged;
};
