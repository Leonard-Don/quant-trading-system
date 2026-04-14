import { formatResearchSource } from '../../utils/researchContext';
import { buildWorkbenchViewFingerprint } from '../../utils/workbenchViewFingerprint';
import {
  buildCrossMarketRefreshPriorityEvent,
  buildPricingRefreshPriorityEvent,
  buildTradeThesisRefreshPriorityEvent,
} from '../../utils/workbenchPriorityEvents';

const STATUS_LABELS = {
  ready: '待执行',
  blocked: '待数据',
  warning: '需复核',
  complete: '已完成',
};

const AI_SYMBOLS = new Set(['NVDA', 'AMD', 'TSM', 'SMH', 'QQQ']);
const POWER_SYMBOLS = new Set(['DUK', 'XLU', 'CEG', 'NEE', 'XLE']);

const toPercent = (value, digits = 1) => `${(Number(value || 0) * 100).toFixed(digits)}%`;
const toSignedPercent = (value, digits = 1) => {
  const numeric = Number(value || 0);
  return `${numeric > 0 ? '+' : ''}${(numeric * 100).toFixed(digits)}%`;
};
const toSignedPercentPoints = (value, digits = 1) => {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(digits)}%`;
};

const compactText = (value = '') => String(value || '').replace(/\s+/g, ' ').trim();

const WORKBENCH_REFRESH_LABELS = {
  high: '建议更新',
  medium: '建议复核',
  low: '继续观察',
};

const WORKBENCH_TYPE_LABELS = {
  pricing: 'Pricing',
  cross_market: 'Cross-Market',
  macro_mispricing: 'Macro Mispricing',
  trade_thesis: 'Trade Thesis',
};

const WORKBENCH_SNAPSHOT_VIEW_LABELS = {
  filtered: '带筛选视角快照',
  scoped: '带任务焦点快照',
};

const WORKBENCH_REASON_LABELS = {
  priority_new: '自动排序首次入列',
  priority_escalated: '自动排序升档',
  priority_relaxed: '自动排序缓和',
  priority_updated: '自动排序同类更新',
  resonance: '共振驱动',
  bias_quality_core: '核心腿受压',
  selection_quality_active: '降级运行',
  review_context: '复核语境切换',
  structural_decay: '结构衰败/系统雷达',
  trade_thesis: '交易 Thesis 漂移',
  people_layer: '人的维度',
  people_fragility: '人的维度',
  department_chaos: '部门混乱',
  policy_execution: '政策执行混乱',
  selection_quality: '自动降级',
  input_reliability: '输入可靠度',
  source_health_degradation: '来源健康退化',
  policy_source: '政策源驱动',
  bias_quality: '偏置收缩',
};

const buildWorkbenchViewContext = (context = {}) => {
  const refresh = String(context?.workbenchRefresh || '').trim();
  const type = String(context?.workbenchType || '').trim();
  const sourceFilter = String(context?.workbenchSource || '').trim();
  const reason = String(context?.workbenchReason || '').trim();
  const snapshotView = String(context?.workbenchSnapshotView || '').trim();
  const snapshotFingerprint = String(context?.workbenchSnapshotFingerprint || '').trim();
  const snapshotSummary = String(context?.workbenchSnapshotSummary || '').trim();
  const keyword = String(context?.workbenchKeyword || '').trim();
  const taskId = String(context?.task || '').trim();

  if (![refresh, type, sourceFilter, reason, snapshotView, snapshotFingerprint, snapshotSummary, keyword, taskId].some(Boolean)) {
    return null;
  }

  const summaryParts = [];

  if (reason) {
    summaryParts.push(
      `${reason.startsWith('priority_') ? '快速视图' : '更新原因'}：${WORKBENCH_REASON_LABELS[reason] || reason}`
    );
  }
  if (keyword) {
    summaryParts.push(`关键词：${keyword}`);
  }
  if (refresh) {
    summaryParts.push(`更新级别：${WORKBENCH_REFRESH_LABELS[refresh] || refresh}`);
  }
  if (snapshotView) {
    summaryParts.push(`快照视角：${WORKBENCH_SNAPSHOT_VIEW_LABELS[snapshotView] || snapshotView}`);
  }
  if (snapshotSummary) {
    summaryParts.push(`研究视角：${snapshotSummary}`);
  }
  if (type) {
    summaryParts.push(`类型：${WORKBENCH_TYPE_LABELS[type] || type}`);
  }
  if (sourceFilter) {
    summaryParts.push(`来源：${formatResearchSource(sourceFilter)}`);
  }

  const viewFingerprint = snapshotFingerprint || buildWorkbenchViewFingerprint({
    refresh,
    type,
    source_filter: sourceFilter,
    reason,
    snapshot_view: snapshotView,
    keyword,
    task_id: taskId,
  });

  return {
    source_view: 'workbench',
    has_filters: summaryParts.length > 0,
    refresh,
    type,
    source_filter: sourceFilter,
    reason,
    snapshot_view: snapshotView,
    view_fingerprint: viewFingerprint,
    snapshot_summary: snapshotSummary,
    keyword,
    task_id: taskId,
    summary: summaryParts.length ? summaryParts.join(' · ') : '全部任务视图',
    scoped_task_label: taskId ? `当前定位：${taskId}` : '',
    note: summaryParts.length
      ? '这次快照是在带筛选的工作台视图下保存的。'
      : '这次快照是在完整工作台视图下保存的。',
  };
};

const buildPricingAction = (symbol, source, note) =>
  symbol
    ? {
        label: '打开定价剧本',
        target: 'pricing',
        symbol,
        source,
        note,
      }
    : null;

const buildCrossMarketAction = (template, source, note) =>
  template
    ? {
        label: '打开跨市场剧本',
        target: 'cross-market',
        template,
        source,
        note,
      }
    : null;

const buildGodEyeAction = (note = '返回 GodEye 继续筛选宏观线索') => ({
  label: '回到 GodEye',
  target: 'godsEye',
  source: 'playbook',
  note,
});

const buildHighlights = (playbook = {}, fallback = []) => {
  const safePlaybook = playbook || {};
  const highlights = [
    ...(safePlaybook.warnings || []),
    ...(fallback || []),
  ].filter(Boolean);
  return highlights.slice(0, 4);
};

const detectMacroCue = (texts = []) =>
  /政策|宏观|能源|电力|电网|地缘|供应|供给|库存|物流|利率|关税|算力|火电|核电/i.test(
    texts.map((item) => compactText(item)).join(' ')
  );

const isMacroSensitiveSector = (sector = '') =>
  /energy|utilities|industrials|materials/i.test(String(sector || '').trim());

const hasProxyFactorInputs = (factorModel = {}) =>
  Boolean(factorModel?.factor_source?.is_proxy || factorModel?.five_factor_source?.is_proxy);

const deriveCrossMarketSignal = (symbol, pricingResult = {}) => {
  const gap = pricingResult?.gap_analysis || {};
  const drivers = pricingResult?.deviation_drivers?.drivers || [];
  const valuation = pricingResult?.valuation || {};
  const implications = pricingResult?.implications || {};
  const factorModel = pricingResult?.factor_model || {};
  const insights = implications?.insights || [];
  const texts = [
    gap.direction,
    gap.severity_label,
    ...drivers.map((item) => item?.description),
    implications?.factor_alignment?.summary,
    implications?.primary_view,
    ...insights,
  ];
  const reasons = [];
  const confidence = implications?.confidence;
  const riskLevel = implications?.risk_level;
  const alignmentStatus = implications?.factor_alignment?.status;
  const severity = gap?.severity;
  const sector = valuation?.comparables?.sector || valuation?.fundamentals?.sector || '';
  const macroCue = detectMacroCue(texts);
  const proxyInputs = hasProxyFactorInputs(factorModel);

  if (alignmentStatus === 'conflict') {
    reasons.push('因子信号与估值结论存在冲突');
  }
  if (confidence === 'low') {
    reasons.push('当前结论置信度偏低');
  }
  if (riskLevel === 'high') {
    reasons.push('风险等级偏高');
  }
  if (proxyInputs) {
    reasons.push('因子数据包含代理估算值');
  }
  if (isMacroSensitiveSector(sector)) {
    reasons.push(`标的处在 ${sector || '宏观敏感行业'}，更容易受跨资产变量驱动`);
  }
  if (macroCue) {
    reasons.push('驱动描述里出现明显的宏观或供需线索');
  }
  if (['moderate', 'extreme', 'unknown'].includes(severity)) {
    reasons.push('当前偏差等级需要额外验证');
  }
  if (POWER_SYMBOLS.has(symbol) || AI_SYMBOLS.has(symbol)) {
    reasons.push(`${symbol} 所在主题常和跨市场变量联动`);
  }

  const hardTriggers = [alignmentStatus === 'conflict', riskLevel === 'high', confidence === 'low'].filter(Boolean).length;
  const supportingSignals = [macroCue, proxyInputs, isMacroSensitiveSector(sector), ['moderate', 'extreme', 'unknown'].includes(severity), POWER_SYMBOLS.has(symbol) || AI_SYMBOLS.has(symbol)].filter(Boolean).length;
  const shouldCrossMarket = hardTriggers >= 2 || (hardTriggers >= 1 && supportingSignals >= 1) || (macroCue && isMacroSensitiveSector(sector));

  return {
    shouldCrossMarket,
    reasons: Array.from(new Set(reasons)),
    macroCue,
    sector,
  };
};

const recommendTemplateForSymbol = (symbol = '', texts = []) => {
  const upper = String(symbol || '').toUpperCase();
  const joined = texts.map((item) => compactText(item)).join(' ');

  if (/能源|电力|电网|火电|核电/i.test(joined) || POWER_SYMBOLS.has(upper)) {
    return 'energy_vs_ai_apps';
  }

  if (/半导体|铜|算力|芯片/i.test(joined) || AI_SYMBOLS.has(upper)) {
    return 'copper_vs_semis';
  }

  return 'defensive_beta_hedge';
};

const describeConfidence = (level = '') => {
  const mapping = {
    low: '低',
    medium: '中',
    high: '高',
  };
  return mapping[level] || '中';
};

export const buildPricingPlaybook = (context = {}, pricingResult = null) => {
  const symbol = String(context.symbol || pricingResult?.symbol || '').trim().toUpperCase();
  const source = context.source || '';
  const stageLabel = pricingResult ? '结果已生成' : symbol ? '待分析' : '待选择标的';

  if (!symbol && !source && !pricingResult) {
    return null;
  }

  const baseContext = [
    symbol ? `标的 ${symbol}` : null,
    `阶段 ${stageLabel}`,
    source ? `来源 ${formatResearchSource(source)}` : null,
  ].filter(Boolean);

  if (!pricingResult) {
    return {
      playbook_type: 'pricing',
      stageLabel,
      headline: symbol ? `${symbol} 的定价研究剧本已建立` : '定价研究剧本待建立',
      thesis: symbol
        ? '先运行定价分析，确认价格偏差、驱动因素和估值锚点，再决定是否需要切换到跨市场对冲。'
        : '当前缺少可研究标的，请先从 GodEye 或手动输入一个 symbol。',
      context: baseContext,
      warnings: symbol ? [] : ['当前没有 symbol，暂时无法生成完整研究剧本。'],
      next_actions: symbol ? [buildGodEyeAction()] : [],
      tasks: [
        {
          id: 'pricing-gap',
          title: '定价差异确认',
          description: symbol ? `等待 ${symbol} 的 gap analysis 结果。` : '先指定一个单标的。',
          status: symbol ? 'ready' : 'blocked',
          cta: null,
        },
        {
          id: 'pricing-drivers',
          title: '驱动因素核对',
          description: '结果返回后，优先核对前 2-3 个主要驱动因素是否能被基本面或宏观叙事解释。',
          status: 'blocked',
          cta: null,
        },
        {
          id: 'pricing-valuation',
          title: '估值锚点复核',
          description: '结果返回后，检查公允价值区间、DCF 假设和可比估值是否一致。',
          status: 'blocked',
          cta: null,
        },
        {
          id: 'pricing-action',
          title: '行动建议',
          description: '待分析完成后，系统会给出继续观察、切换跨市场或回到 GodEye 的建议。',
          status: 'blocked',
          cta: null,
        },
      ],
    };
  }

  const gap = pricingResult?.gap_analysis || {};
  const drivers = pricingResult?.deviation_drivers?.drivers || [];
  const valuation = pricingResult?.valuation || {};
  const fairValue = valuation?.fair_value || {};
  const implications = pricingResult?.implications || {};
  const insights = implications?.insights || [];
  const crossMarketSignal = deriveCrossMarketSignal(symbol, pricingResult);
  const shouldCrossMarket = crossMarketSignal.shouldCrossMarket;
  const recommendedTemplate = shouldCrossMarket
    ? recommendTemplateForSymbol(symbol, insights)
    : null;
  const crossMarketReasonText = crossMarketSignal.reasons.slice(0, 2).join('，');
  const primaryAction = shouldCrossMarket
    ? buildCrossMarketAction(
        recommendedTemplate,
        'pricing_playbook',
        `${symbol} 的单标的结论受跨资产变量干扰较大，${crossMarketReasonText || '建议切换到跨市场模板继续验证'}。`
      )
    : null;
  const nextActions = [primaryAction, buildGodEyeAction()].filter(Boolean);
  const warnings = [];

  if (!drivers.length) {
    warnings.push('当前没有显著驱动因素，结论更依赖估值区间本身。');
  }
  if (!fairValue.mid) {
    warnings.push('当前缺少完整的综合公允价值锚点，需要谨慎解释价格偏差。');
  }
  if (implications.confidence === 'low') {
    warnings.push('分析置信度偏低，建议把结论当作研究线索而不是最终判断。');
  }
  if (implications.risk_level === 'high') {
    warnings.push('风险等级偏高，先控制结论强度，再决定是否继续放大仓位假设。');
  }

  const primaryView = implications.primary_view || gap.direction || '合理';
  const thesis = `${symbol} 当前偏向 ${primaryView}，价格偏差 ${toSignedPercentPoints(gap.gap_pct)}。${
    shouldCrossMarket
      ? `由于${crossMarketReasonText || '跨资产变量干扰较强'}，下一步更适合用跨市场模板继续验证。`
      : '当前更适合继续留在单标的定价研究框架内。'
  }`;

  return {
    playbook_type: 'pricing',
    stageLabel,
    headline: `${symbol} 定价研究剧本`,
    thesis,
    context: [
      ...baseContext,
      fairValue.mid ? `公允价值 ${fairValue.mid}` : null,
      implications.confidence ? `置信度 ${describeConfidence(implications.confidence)}` : null,
    ].filter(Boolean),
    warnings,
    next_actions: nextActions,
    tasks: [
      {
        id: 'pricing-gap',
        title: '定价差异确认',
        description: gap.fair_value_mid
          ? `当前价格 ${gap.current_price || '-'}，公允价值 ${gap.fair_value_mid}，偏差 ${toSignedPercentPoints(gap.gap_pct)}，结论为 ${gap.severity_label || primaryView}。`
          : '已有结果，但缺少明确的价格偏差区间。',
        status: gap.fair_value_mid ? 'complete' : 'warning',
        cta: null,
      },
      {
        id: 'pricing-drivers',
        title: '驱动因素核对',
        description: drivers.length
          ? drivers
              .slice(0, 3)
              .map((item) => `${item.factor}: ${compactText(item.description)}`)
              .join('；')
          : '未检测到足够强的驱动因素，请人工复核行业、政策或风格暴露。',
        status: drivers.length ? 'complete' : 'warning',
        cta: null,
      },
      {
        id: 'pricing-valuation',
        title: '估值锚点复核',
        description: fairValue.mid
          ? `综合公允价值区间 ${fairValue.low} ~ ${fairValue.high}，估值方法 ${fairValue.method || '未标注'}。`
          : '当前没有完整的 fair value 区间，建议先检查 DCF 与可比估值输出。',
        status: fairValue.mid ? 'complete' : 'warning',
        cta: null,
      },
      {
        id: 'pricing-action',
        title: '行动建议',
        description: shouldCrossMarket
          ? `单标的结论受跨市场变量影响较大，${crossMarketReasonText || '建议进入跨市场剧本继续确认对冲结构'}。`
          : '当前更适合继续观察单标的定价偏差，必要时回到 GodEye 寻找新的宏观线索。',
        status: shouldCrossMarket ? 'warning' : 'complete',
        cta: primaryAction || buildGodEyeAction(),
      },
    ],
  };
};

export const buildCrossMarketPlaybook = (context = {}, template = null, backtestResult = null) => {
  const templateId = context.template || template?.id || '';
  const source = context.source || '';
  const stageLabel = backtestResult ? '结果已生成' : templateId ? '待运行' : '待选择模板';

  if (!templateId && !template && !backtestResult && !source) {
    return null;
  }

  const templateName = template?.name || templateId || '当前篮子';
  const templateAssets = template?.assets || [];
  const longCount = templateAssets.filter((asset) => asset.side === 'long').length;
  const shortCount = templateAssets.filter((asset) => asset.side === 'short').length;
  const returnToGodEye = source ? buildGodEyeAction('返回 GodEye 继续筛选宏观模板') : null;

  if (!backtestResult) {
    return {
      playbook_type: 'cross_market',
      stageLabel,
      headline: `${templateName} 跨市场研究剧本`,
      thesis: template
        ? '先确认模板假设和构造模式，再运行回测检查数据覆盖率、执行成本和结论强度。'
        : '当前模板还没有命中，先确认 URL 或从模板列表重新选择一个篮子。',
      context: [
        templateName ? `模板 ${templateName}` : null,
        template?.construction_mode ? `构造 ${template.construction_mode}` : null,
        template?.theme ? `主题 ${template.theme}` : null,
        template?.recommendationTier ? `推荐 ${template.recommendationTier}` : null,
        longCount || shortCount ? `${longCount}L / ${shortCount}S` : null,
        `阶段 ${stageLabel}`,
        source ? `来源 ${formatResearchSource(source)}` : null,
      ].filter(Boolean),
      warnings: template
        ? (template?.driverHeadline ? [`当前推荐依据：${template.driverHeadline}`] : [])
        : ['当前 URL 中的 template 未命中现有模板，请重新选择。'],
      next_actions: [returnToGodEye].filter(Boolean),
      tasks: [
        {
          id: 'cross-template',
          title: '模板假设确认',
          description: template
            ? `${template.description || '已载入模板'}；当前结构为 ${longCount} 个多头、${shortCount} 个空头。${template.driverHeadline ? ` 推荐理由：${template.driverHeadline}。` : ''}`
            : '等待模板命中后再确认叙事和篮子结构。',
          status: template ? 'complete' : 'warning',
          cta: null,
        },
        {
          id: 'cross-data',
          title: '数据质量检查',
          description: '运行回测后检查可交易日占比、丢弃日期数和每个 symbol 的覆盖率。',
          status: 'blocked',
          cta: null,
        },
        {
          id: 'cross-execution',
          title: '执行质量检查',
          description: '运行回测后检查 turnover、cost drag 和平均持有期是否过高。',
          status: 'blocked',
          cta: null,
        },
        {
          id: 'cross-conclusion',
          title: '结论与下一步',
          description: '回测完成后，系统会判断是继续优化、回到 GodEye，还是转去单标的定价剧本。',
          status: 'blocked',
          cta: returnToGodEye,
        },
      ],
    };
  }

  const dataAlignment = backtestResult?.data_alignment || {};
  const execution = backtestResult?.execution_diagnostics || {};
  const constraintOverlay = backtestResult?.constraint_overlay || {};
  const longLeg = backtestResult?.leg_performance?.long || {};
  const shortLeg = backtestResult?.leg_performance?.short || {};
  const coverage = Number(dataAlignment.tradable_day_ratio || 0);
  const totalReturn = Number(backtestResult.total_return || 0);
  const sharpe = Number(backtestResult.sharpe_ratio || 0);
  const longReturn = Number(longLeg.cumulative_return || 0);
  const shortReturn = Number(shortLeg.cumulative_return || 0);
  const lowCoverage = coverage < 0.8;
  const weakResult = totalReturn < 0.03 || sharpe < 0.5;
  const legDivergence = Math.abs(longReturn - shortReturn) > 0.08;
  const weakerLegKey = longReturn <= shortReturn ? 'long' : 'short';
  const candidateSymbol = backtestResult?.leg_performance?.[weakerLegKey]?.assets?.[0]?.symbol
    || templateAssets.find((asset) => asset.side === weakerLegKey)?.symbol
    || '';
  const pricingAction = weakResult && legDivergence && candidateSymbol
    ? buildPricingAction(
        candidateSymbol,
        'cross_market_playbook',
        `当前跨市场结果较弱，建议先回到 ${candidateSymbol} 的单标的定价剧本复核问题来源。`
      )
    : null;
  const warnings = [];

  if (lowCoverage) {
    warnings.push(`可交易日覆盖率仅 ${toPercent(coverage, 1)}，当前结论更适合当作线索而不是成型结论。`);
  }
  if (Number(execution.cost_drag || 0) > 0.02) {
    warnings.push(`成本拖累达到 ${toPercent(execution.cost_drag || 0, 2)}，需要复核换手和交易频率。`);
  }
  if (Number(execution.turnover || 0) > 8) {
    warnings.push('换手率偏高，说明当前阈值或 lookback 可能过于激进。');
  }
  if (execution.concentration_level === 'high') {
    warnings.push(`执行集中度偏高，${execution.concentration_reason || '建议分散 provider 或 venue 暴露。'}`);
  }
  if (Number(execution.lot_efficiency || 1) < 0.97) {
    warnings.push(`最小交易单位效率仅 ${toPercent(execution.lot_efficiency || 0, 2)}，当前篮子可能存在较明显的 sizing 偏差。`);
  }
  if (execution.stress_test_flag === 'high') {
    warnings.push(`资金放大压力测试提示高集中，${execution.stress_test_reason || '继续放大资金前应先拆分批次或分散 venue。'}`);
  }
  if (execution.liquidity_level === 'stretched') {
    warnings.push(`当前最大 ADV 使用率达到 ${toPercent(execution.max_adv_usage || 0, 2)}，流动性偏紧，继续放大资金前应复核容量。`);
  }
  if (execution.margin_level === 'aggressive') {
    warnings.push(`保证金占用达到 ${toPercent(execution.margin_utilization || 0, 2)}，Gross Leverage ${Number(execution.gross_leverage || 0).toFixed(2)}x，当前配置偏激进。`);
  }
  if (execution.beta_level === 'stretched') {
    warnings.push(`当前长短腿 beta 偏离较大，${execution.beta_reason || '建议复核对冲比和长短腿结构。'}`);
  }
  if (execution.calendar_level === 'stretched') {
    warnings.push(`多市场日历错位明显，${execution.calendar_reason || '当前可交易日可能被不同 venue 的休市错配压缩。'}`);
  }
  if (Number(constraintOverlay.binding_count || 0) > 0) {
    warnings.push(`当前有 ${constraintOverlay.binding_count} 个资产触发权重约束，结论需结合约束偏移一起解释。`);
  }

  const thesis = weakResult
    ? `${templateName} 当前结果偏弱，总收益 ${toSignedPercent(totalReturn, 2)}，Sharpe ${sharpe.toFixed(2)}。更适合先做诊断，再决定是否继续扩展。`
    : `${templateName} 当前结果可用，总收益 ${toSignedPercent(totalReturn, 2)}，Sharpe ${sharpe.toFixed(2)}。接下来应重点核对覆盖率和执行成本。`;

  return {
    playbook_type: 'cross_market',
    stageLabel,
    headline: `${templateName} 跨市场研究剧本`,
    thesis,
    context: [
      `阶段 ${stageLabel}`,
      source ? `来源 ${formatResearchSource(source)}` : null,
      template?.construction_mode || execution.construction_mode
        ? `构造 ${template?.construction_mode || execution.construction_mode}`
        : null,
      template?.theme ? `主题 ${template.theme}` : null,
      template?.recommendationTier ? `推荐 ${template.recommendationTier}` : null,
      template?.biasSummary ? `偏置 ${template.biasSummary}` : null,
      coverage ? `覆盖率 ${toPercent(coverage, 1)}` : null,
      `${longLeg.assets?.length || 0}L / ${shortLeg.assets?.length || 0}S`,
    ].filter(Boolean),
    warnings: [
      ...(template?.driverHeadline ? [`当前推荐依据：${template.driverHeadline}`] : []),
      ...(template?.biasSummary ? [`当前权重偏置：${template.biasSummary}`] : []),
      ...warnings,
    ],
    next_actions: [pricingAction, returnToGodEye].filter(Boolean),
    tasks: [
      {
        id: 'cross-template',
        title: '模板假设确认',
        description: template
          ? `${template.description || '已载入模板'}；当前采用 ${template.construction_mode || execution.construction_mode} 构造模式。${template.driverHeadline ? ` 推荐理由：${template.driverHeadline}。` : ''}`
          : `当前篮子包含 ${longLeg.assets?.length || 0} 个多头、${shortLeg.assets?.length || 0} 个空头。`,
        status: 'complete',
        cta: null,
      },
      {
        id: 'cross-data',
        title: '数据质量检查',
        description: `可交易日占比 ${toPercent(coverage, 1)}，丢弃日期 ${dataAlignment.dropped_dates_count || 0} 个，对齐后 ${dataAlignment.aligned_row_count || 0} 行。`,
        status: lowCoverage ? 'warning' : 'complete',
        cta: null,
      },
      {
        id: 'cross-execution',
        title: '执行质量检查',
        description: `Turnover ${Number(execution.turnover || 0).toFixed(2)}，Cost Drag ${toPercent(execution.cost_drag || 0, 2)}，平均持有 ${Number(execution.avg_holding_period || 0).toFixed(1)} 天，Lot 效率 ${toPercent(execution.lot_efficiency || 0, 2)}，Max ADV ${toPercent(execution.max_adv_usage || 0, 2)}，保证金 ${toPercent(execution.margin_utilization || 0, 2)}，Gross ${Number(execution.gross_leverage || 0).toFixed(2)}x，Beta ${execution.beta_level || 'balanced'}，日历 ${execution.calendar_level || 'aligned'}，建议调仓 ${execution.suggested_rebalance || 'biweekly'}，压力测试 ${execution.stress_test_flag || 'balanced'}。`,
        status:
          Number(execution.cost_drag || 0) > 0.02
          || Number(execution.turnover || 0) > 8
          || execution.concentration_level === 'high'
          || execution.liquidity_level === 'stretched'
          || execution.margin_level === 'aggressive'
          || execution.beta_level === 'stretched'
          || execution.calendar_level === 'stretched'
          || execution.stress_test_flag === 'high'
          || Number(execution.lot_efficiency || 1) < 0.97
            ? 'warning'
            : 'complete',
        cta: null,
      },
      {
        id: 'cross-conclusion',
        title: '结论与下一步',
        description: pricingAction
          ? `当前结果偏弱，且长短腿表现分化明显，建议先回到 ${candidateSymbol} 做单标的定价复核。`
          : lowCoverage
            ? '当前结果受覆盖率限制，先谨慎保留结论，再回到 GodEye 寻找更干净的模板。'
            : '当前结果可继续优化参数或扩展样本窗；如需要换叙事，再回到 GodEye。',
        status: pricingAction || lowCoverage || weakResult ? 'warning' : 'complete',
        cta: pricingAction || returnToGodEye,
      },
    ],
  };
};

export { STATUS_LABELS };

export const buildPricingWorkbenchPayload = (context = {}, pricingResult = null, playbook = null) => {
  const symbol = String(context.symbol || pricingResult?.symbol || '').trim().toUpperCase();
  if (!symbol) {
    return null;
  }

  const gap = pricingResult?.gap_analysis || {};
  const valuation = pricingResult?.valuation || {};
  const implications = pricingResult?.implications || {};
  const drivers = pricingResult?.deviation_drivers?.drivers || [];
  const primaryDriver = pricingResult?.deviation_drivers?.primary_driver || drivers[0] || null;
  const factorModel = pricingResult?.factor_model || {};
  const peopleGovernanceOverlay = pricingResult?.people_governance_overlay || {};
  const title = `[Pricing] ${symbol} mispricing review`;
  const analysisPeriod = context.period || '1y';
  const workbenchViewContext = buildWorkbenchViewContext(context);
  const researchInput = {
    macro: {
      people_layer: pricingResult?.people_layer || {},
      policy_execution: peopleGovernanceOverlay?.policy_execution_context || {},
      source_mode_summary: peopleGovernanceOverlay?.source_mode_summary || {},
    },
  };

  const payload = {
    type: 'pricing',
    title,
    source: context.source || 'manual',
    symbol,
    template: '',
    note: context.note || '',
    context: {
      view: 'pricing',
      period: analysisPeriod,
      source: context.source || 'manual',
      stage: playbook?.stageLabel || (pricingResult ? '结果已生成' : '待分析'),
      playbook_context: playbook?.context || [],
      workbench_view_context: workbenchViewContext || {},
    },
    snapshot: {
      headline: playbook?.headline || `${symbol} 定价研究任务`,
      summary: playbook?.thesis || `${symbol} 的定价研究任务已保存。`,
      highlights: buildHighlights(playbook, (implications.insights || []).slice(0, 2)),
      payload: {
        gap_analysis: gap,
        fair_value: valuation?.fair_value || {},
        dcf_scenarios: (valuation?.dcf?.scenarios || []).map((item) => ({
          name: item?.name || '',
          label: item?.label || '',
          intrinsic_value: item?.intrinsic_value ?? null,
          premium_discount: item?.premium_discount ?? null,
          assumptions: {
            wacc: item?.assumptions?.wacc ?? null,
            initial_growth: item?.assumptions?.initial_growth ?? null,
            terminal_growth: item?.assumptions?.terminal_growth ?? null,
            fcf_margin: item?.assumptions?.fcf_margin ?? null,
          },
        })),
        current_price_source: valuation?.current_price_source || '',
        factor_model: {
          period: factorModel?.period || analysisPeriod,
          data_points: factorModel?.data_points ?? null,
          capm_alpha_pct: factorModel?.capm?.alpha_pct ?? null,
          capm_beta: factorModel?.capm?.beta ?? null,
          capm_r_squared: factorModel?.capm?.r_squared ?? null,
          ff3_alpha_pct: factorModel?.fama_french?.alpha_pct ?? null,
          ff3_r_squared: factorModel?.fama_french?.r_squared ?? null,
          ff5_alpha_pct: factorModel?.fama_french_five_factor?.alpha_pct ?? null,
          ff5_profitability: factorModel?.fama_french_five_factor?.factor_loadings?.profitability ?? null,
          ff5_investment: factorModel?.fama_french_five_factor?.factor_loadings?.investment ?? null,
        },
        monte_carlo: valuation?.monte_carlo || {},
        audit_trail: {
          generated_at: new Date().toISOString(),
          price_source: valuation?.current_price_source || '',
          factor_source: factorModel?.factor_source || {},
          five_factor_source: factorModel?.five_factor_source || {},
          comparable_benchmark_source: valuation?.comparable?.benchmark_source || '',
          comparable_peer_symbols: valuation?.comparable?.benchmark_peer_symbols || [],
          analysis_overrides: valuation?.analysis_overrides || {},
        },
        implications,
        period: analysisPeriod,
        people_layer: pricingResult?.people_layer || {},
        people_governance_overlay: peopleGovernanceOverlay,
        structural_decay: pricingResult?.structural_decay || implications?.structural_decay || {},
        macro_mispricing_thesis:
          pricingResult?.macro_mispricing_thesis
          || implications?.macro_mispricing_thesis
          || {},
        primary_driver: primaryDriver,
        drivers: drivers.slice(0, 3),
        research_input: researchInput,
        view_context: workbenchViewContext || {},
      },
    },
  };
  const refreshPriorityEvent = buildPricingRefreshPriorityEvent(pricingResult, context);
  return refreshPriorityEvent
    ? { ...payload, refresh_priority_event: refreshPriorityEvent }
    : payload;
};

export const buildCrossMarketWorkbenchPayload = (
  context = {},
  template = null,
  backtestResult = null,
  assets = [],
  researchInputs = {}
) => {
  const templateId = context.template || template?.id || '';
  const taskLabel = template?.name || templateId || 'custom basket';
  const title = `[CrossMarket] ${taskLabel} thesis`;
  const safeAssets = (assets || []).map((asset) => ({
    symbol: asset.symbol,
    asset_class: asset.asset_class,
    side: asset.side,
    weight: asset.weight,
  }));

  if (!templateId && !safeAssets.length && !backtestResult) {
    return null;
  }

  const macroOverview = researchInputs?.macroOverview || {};
  const altSnapshot = researchInputs?.altSnapshot || {};
  const factorDeltas = macroOverview?.trend?.factor_deltas || {};
  const topFactorShifts = Object.entries(factorDeltas)
    .sort((left, right) => Math.abs(Number(right[1]?.z_score_delta || 0)) - Math.abs(Number(left[1]?.z_score_delta || 0)))
    .slice(0, 3)
    .map(([name, item]) => ({
      name,
      z_score_delta: Number(item?.z_score_delta || 0),
      signal_changed: Boolean(item?.signal_changed),
    }));
  const topAltCategories = Object.entries(altSnapshot?.category_summary || {})
    .sort((left, right) => Math.abs(Number(right[1]?.delta_score || 0)) - Math.abs(Number(left[1]?.delta_score || 0)))
    .slice(0, 4)
    .map(([category, item]) => ({
      category,
      avg_score: Number(item?.avg_score || 0),
      delta_score: Number(item?.delta_score || 0),
      momentum: item?.momentum || 'stable',
      count: Number(item?.count || 0),
    }));
  const allocationOverlay = backtestResult?.allocation_overlay || {};
  const selectionQuality = allocationOverlay.selection_quality || {};
  const baseRecommendationScore = selectionQuality.base_recommendation_score
    ?? template?.baseRecommendationScore
    ?? template?.recommendationScore
    ?? null;
  const effectiveRecommendationScore = selectionQuality.effective_recommendation_score
    ?? template?.recommendationScore
    ?? null;
  const baseRecommendationTier = selectionQuality.base_recommendation_tier
    || template?.baseRecommendationTier
    || template?.recommendationTier
    || '';
  const effectiveRecommendationTier = selectionQuality.effective_recommendation_tier
    || template?.recommendationTier
    || '';
  const rankingPenalty = selectionQuality.ranking_penalty
    ?? template?.rankingPenalty
    ?? 0;
  const rankingPenaltyReason = selectionQuality.reason
    || template?.rankingPenaltyReason
    || '';
  const selectionQualityLabel = selectionQuality.label || (rankingPenalty > 0 ? 'softened' : 'original');
  const selectionQualityReason = selectionQuality.reason || rankingPenaltyReason || '';
  const isReviewRunResult = Boolean(backtestResult && selectionQualityLabel && selectionQualityLabel !== 'original');
  const workbenchViewContext = buildWorkbenchViewContext(context);
  const coreLegSymbols = new Set(
    (template?.coreLegs || [])
      .map((item) => String(item?.symbol || '').trim().toUpperCase())
      .filter(Boolean)
  );
  const themeCoreText = String(template?.themeCore || '').toUpperCase();
  const topCompressedRow = (allocationOverlay.rows || [])
    .slice()
    .sort((left, right) => Math.abs(Number(right?.compression_delta || 0)) - Math.abs(Number(left?.compression_delta || 0)))
    .find((item) => Math.abs(Number(item?.compression_delta || 0)) >= 0.005);
  const topCompressedSymbol = String(topCompressedRow?.symbol || '').trim().toUpperCase();
  const coreLegPressure = {
    affected: Boolean(
      topCompressedSymbol
      && (coreLegSymbols.has(topCompressedSymbol) || (themeCoreText && themeCoreText.includes(topCompressedSymbol)))
    ),
    symbol: topCompressedRow?.symbol || '',
    compression_delta: Number(topCompressedRow?.compression_delta || 0),
    summary: topCompressedRow?.symbol
      ? `${topCompressedRow.symbol} ${(Math.abs(Number(topCompressedRow.compression_delta || 0)) * 100).toFixed(2)}pp`
      : '',
  };
  const researchInput = {
    macro: {
      macro_score: Number(macroOverview?.macro_score || 0),
      macro_signal: Number(macroOverview?.macro_signal || 0),
      confidence: Number(macroOverview?.confidence || 0),
      macro_score_delta: Number(macroOverview?.trend?.macro_score_delta || 0),
      macro_signal_changed: Boolean(macroOverview?.trend?.macro_signal_changed),
      snapshot_timestamp: macroOverview?.snapshot_timestamp || '',
      resonance: {
        label: macroOverview?.resonance_summary?.label || 'mixed',
        reason: macroOverview?.resonance_summary?.reason || '',
        positive_cluster: macroOverview?.resonance_summary?.positive_cluster || [],
        negative_cluster: macroOverview?.resonance_summary?.negative_cluster || [],
        weakening: macroOverview?.resonance_summary?.weakening || [],
        precursor: macroOverview?.resonance_summary?.precursor || [],
        reversed_factors: macroOverview?.resonance_summary?.reversed_factors || [],
      },
      policy_source_health: {
        label: macroOverview?.evidence_summary?.policy_source_health_summary?.label || 'unknown',
        reason: macroOverview?.evidence_summary?.policy_source_health_summary?.reason || '',
        fragile_sources: macroOverview?.evidence_summary?.policy_source_health_summary?.fragile_sources || [],
        watch_sources: macroOverview?.evidence_summary?.policy_source_health_summary?.watch_sources || [],
        healthy_sources: macroOverview?.evidence_summary?.policy_source_health_summary?.healthy_sources || [],
        avg_full_text_ratio: Number(
          macroOverview?.evidence_summary?.policy_source_health_summary?.avg_full_text_ratio || 0
        ),
      },
      department_chaos: {
        label: macroOverview?.department_chaos_summary?.label || 'unknown',
        summary: macroOverview?.department_chaos_summary?.summary || '',
        avg_chaos_score: Number(macroOverview?.department_chaos_summary?.avg_chaos_score || 0),
        department_count: Number(macroOverview?.department_chaos_summary?.department_count || 0),
        chaotic_department_count: Number(macroOverview?.department_chaos_summary?.chaotic_department_count || 0),
        top_departments: (macroOverview?.department_chaos_summary?.top_departments || [])
          .slice(0, 5)
          .map((item) => ({
            department: item?.department || '',
            department_label: item?.department_label || '',
            label: item?.label || '',
            chaos_score: Number(item?.chaos_score || 0),
            policy_reversal_count: Number(item?.policy_reversal_count || 0),
            avg_will_intensity: Number(item?.avg_will_intensity || 0),
            reason: item?.reason || '',
          })),
      },
      people_layer: altSnapshot?.signals?.people_layer || macroOverview?.people_layer_summary || {},
      policy_execution: altSnapshot?.signals?.policy_execution || {},
      source_mode_summary: macroOverview?.source_mode_summary || altSnapshot?.source_mode_summary || {},
      structural_decay_radar: {
        label: macroOverview?.structural_decay_radar?.label || 'stable',
        display_label: macroOverview?.structural_decay_radar?.display_label || '',
        score: Number(macroOverview?.structural_decay_radar?.score || 0),
        critical_axis_count: Number(macroOverview?.structural_decay_radar?.critical_axis_count || 0),
        top_signals: macroOverview?.structural_decay_radar?.top_signals || [],
        action_hint: macroOverview?.structural_decay_radar?.action_hint || '',
      },
      input_reliability: {
        label: macroOverview?.input_reliability_summary?.label || 'unknown',
        score: Number(macroOverview?.input_reliability_summary?.score || 0),
        lead: macroOverview?.input_reliability_summary?.lead || '',
        posture: macroOverview?.input_reliability_summary?.posture || '',
        reason: macroOverview?.input_reliability_summary?.reason || '',
        dominant_issue_labels: macroOverview?.input_reliability_summary?.dominant_issue_labels || [],
        dominant_support_labels: macroOverview?.input_reliability_summary?.dominant_support_labels || [],
      },
      top_factor_shifts: topFactorShifts,
    },
    alt_data: {
      snapshot_timestamp: altSnapshot?.snapshot_timestamp || '',
      freshness_label: altSnapshot?.staleness?.label || '',
      max_snapshot_age_seconds: Number(altSnapshot?.staleness?.max_snapshot_age_seconds || 0),
      top_categories: topAltCategories,
    },
  };

  const payload = {
    type: 'cross_market',
    title,
    source: context.source || 'manual',
    symbol: '',
    template: templateId,
    note: context.note || '',
    context: {
      view: 'backtest',
      tab: 'cross-market',
      source: context.source || 'manual',
      stage: backtestResult ? '结果已生成' : '待运行',
      construction_mode:
        template?.construction_mode || backtestResult?.execution_diagnostics?.construction_mode || '',
      template_name: template?.name || '',
      theme: template?.theme || '',
      allocation_mode: template?.biasSummary ? 'macro_bias' : 'template_base',
      bias_summary: template?.biasSummary || '',
      bias_strength_raw: template?.rawBiasStrength || 0,
      bias_strength: template?.biasStrength || 0,
      bias_scale: template?.biasScale || 1,
      bias_quality_label: template?.biasQualityLabel || 'full',
      bias_quality_reason: template?.biasQualityReason || '',
      department_chaos_label: template?.departmentChaosLabel || 'unknown',
      department_chaos_score: template?.departmentChaosScore ?? null,
      department_chaos_top_department: template?.departmentChaosTopDepartment || '',
      department_chaos_reason: template?.departmentChaosReason || '',
      department_chaos_risk_budget_scale: template?.departmentChaosRiskBudgetScale ?? 1,
      people_fragility_label: template?.peopleFragilityLabel || 'stable',
      people_fragility_score: template?.peopleFragilityScore ?? null,
      people_fragility_focus: template?.peopleFragilityFocus || '',
      people_fragility_reason: template?.peopleFragilityReason || '',
      people_fragility_risk_budget_scale: template?.peopleFragilityRiskBudgetScale ?? 1,
      structural_decay_radar_label: template?.structuralDecayRadarLabel || 'stable',
      structural_decay_radar_display_label: template?.structuralDecayRadarDisplayLabel || '',
      structural_decay_radar_score: template?.structuralDecayRadarScore ?? null,
      structural_decay_radar_action_hint: template?.structuralDecayRadarActionHint || '',
      structural_decay_radar_risk_budget_scale: template?.structuralDecayRadarRiskBudgetScale ?? 1,
      structural_decay_radar_top_signals: template?.structuralDecayRadarTopSignals || [],
      policy_execution_label: template?.policyExecutionLabel || 'unknown',
      policy_execution_score: template?.policyExecutionScore ?? null,
      policy_execution_top_department: template?.policyExecutionTopDepartment || '',
      policy_execution_reason: template?.policyExecutionReason || '',
      policy_execution_risk_budget_scale: template?.policyExecutionRiskBudgetScale ?? 1,
      source_mode_label: template?.sourceModeLabel || 'mixed',
      source_mode_dominant: template?.sourceModeDominant || '',
      source_mode_reason: template?.sourceModeReason || '',
      source_mode_risk_budget_scale: template?.sourceModeRiskBudgetScale ?? 1,
      bias_highlights: template?.biasHighlights || [],
      bias_actions: template?.biasActions || [],
      driver_summary: template?.driverSummary || [],
      dominant_drivers: template?.dominantDrivers || [],
      core_legs: template?.coreLegs || [],
      support_legs: template?.supportLegs || [],
      theme_core: template?.themeCore || '',
      theme_support: template?.themeSupport || '',
      execution_posture: template?.executionPosture || template?.execution_posture || '',
      core_leg_pressure: coreLegPressure,
      resonance_label: template?.resonanceLabel || macroOverview?.resonance_summary?.label || 'mixed',
      resonance_reason: template?.resonanceReason || macroOverview?.resonance_summary?.reason || '',
      resonance_factors: template?.resonanceFactors || {},
      base_recommendation_tier: baseRecommendationTier,
      recommendation_tier: effectiveRecommendationTier,
      base_recommendation_score: baseRecommendationScore,
      recommendation_score: effectiveRecommendationScore,
      ranking_penalty: rankingPenalty,
      ranking_penalty_reason: rankingPenaltyReason,
      selection_quality: {
        label: selectionQualityLabel,
        reason: selectionQualityReason,
      },
      input_reliability: {
        label: macroOverview?.input_reliability_summary?.label || 'unknown',
        score: Number(macroOverview?.input_reliability_summary?.score || 0),
        lead: macroOverview?.input_reliability_summary?.lead || '',
        posture: macroOverview?.input_reliability_summary?.posture || '',
        reason: macroOverview?.input_reliability_summary?.reason || '',
        action_hint: template?.refreshMeta?.inputReliabilityShift?.actionHint || '',
      },
      recommendation_reason: template?.driverHeadline || '',
      research_input: researchInput,
      assets: safeAssets,
      workbench_view_context: workbenchViewContext || {},
    },
    snapshot: {
      headline: isReviewRunResult
        ? `${taskLabel} 跨市场复核型结果`
        : `${taskLabel} 跨市场研究任务`,
      summary: backtestResult
        ? isReviewRunResult
          ? `${taskLabel} 已生成复核型回测结果，当前结果按 ${selectionQualityLabel} 强度运行，可继续在工作台里优先重看。`
          : `${taskLabel} 已生成回测结果，可继续在工作台里跟踪。`
        : `${taskLabel} 已保存为跨市场模板任务，等待进一步运行回测。`,
      highlights: buildHighlights(
        null,
        backtestResult
          ? [
              template?.recommendationTier ? `recommendation ${template.recommendationTier}` : '',
              `total return ${toSignedPercent(backtestResult.total_return || 0, 2)}`,
              `sharpe ${Number(backtestResult.sharpe_ratio || 0).toFixed(2)}`,
              `coverage ${toPercent(backtestResult.data_alignment?.tradable_day_ratio || 0, 1)}`,
            ]
          : [
              template?.recommendationTier ? `recommendation ${template.recommendationTier}` : '',
              template?.driverHeadline || '',
              template?.description || '',
              template?.construction_mode ? `construction ${template.construction_mode}` : '',
            ]
      ),
      payload: backtestResult
        ? {
            template_meta: {
              theme: template?.theme || '',
              allocation_mode: template?.biasSummary ? 'macro_bias' : 'template_base',
              bias_summary: template?.biasSummary || '',
              bias_strength_raw: template?.rawBiasStrength || 0,
              bias_strength: template?.biasStrength || 0,
              bias_scale: template?.biasScale || 1,
              bias_quality_label: template?.biasQualityLabel || 'full',
              bias_quality_reason: template?.biasQualityReason || '',
              department_chaos_label: template?.departmentChaosLabel || 'unknown',
              department_chaos_score: template?.departmentChaosScore ?? null,
              department_chaos_top_department: template?.departmentChaosTopDepartment || '',
              department_chaos_reason: template?.departmentChaosReason || '',
              department_chaos_risk_budget_scale: template?.departmentChaosRiskBudgetScale ?? 1,
              people_fragility_label: template?.peopleFragilityLabel || 'stable',
              people_fragility_score: template?.peopleFragilityScore ?? null,
              people_fragility_focus: template?.peopleFragilityFocus || '',
              people_fragility_reason: template?.peopleFragilityReason || '',
              people_fragility_risk_budget_scale: template?.peopleFragilityRiskBudgetScale ?? 1,
              structural_decay_radar_label: template?.structuralDecayRadarLabel || 'stable',
              structural_decay_radar_display_label: template?.structuralDecayRadarDisplayLabel || '',
              structural_decay_radar_score: template?.structuralDecayRadarScore ?? null,
              structural_decay_radar_action_hint: template?.structuralDecayRadarActionHint || '',
              structural_decay_radar_risk_budget_scale: template?.structuralDecayRadarRiskBudgetScale ?? 1,
              structural_decay_radar_top_signals: template?.structuralDecayRadarTopSignals || [],
              policy_execution_label: template?.policyExecutionLabel || 'unknown',
              policy_execution_score: template?.policyExecutionScore ?? null,
              policy_execution_top_department: template?.policyExecutionTopDepartment || '',
              policy_execution_reason: template?.policyExecutionReason || '',
              policy_execution_risk_budget_scale: template?.policyExecutionRiskBudgetScale ?? 1,
              source_mode_label: template?.sourceModeLabel || 'mixed',
              source_mode_dominant: template?.sourceModeDominant || '',
              source_mode_reason: template?.sourceModeReason || '',
              source_mode_risk_budget_scale: template?.sourceModeRiskBudgetScale ?? 1,
              bias_highlights: template?.biasHighlights || [],
              bias_actions: template?.biasActions || [],
              driver_summary: template?.driverSummary || [],
              dominant_drivers: template?.dominantDrivers || [],
              core_legs: template?.coreLegs || [],
              support_legs: template?.supportLegs || [],
              theme_core: template?.themeCore || '',
              theme_support: template?.themeSupport || '',
              execution_posture: template?.executionPosture || template?.execution_posture || '',
              core_leg_pressure: coreLegPressure,
              resonance_label: template?.resonanceLabel || macroOverview?.resonance_summary?.label || 'mixed',
              resonance_reason: template?.resonanceReason || macroOverview?.resonance_summary?.reason || '',
              resonance_factors: template?.resonanceFactors || {},
              base_recommendation_tier: baseRecommendationTier,
              recommendation_tier: effectiveRecommendationTier,
              base_recommendation_score: baseRecommendationScore,
              recommendation_score: effectiveRecommendationScore,
              ranking_penalty: rankingPenalty,
              ranking_penalty_reason: rankingPenaltyReason,
              selection_quality: {
                label: selectionQualityLabel,
                reason: selectionQualityReason,
              },
              input_reliability: {
                label: macroOverview?.input_reliability_summary?.label || 'unknown',
                score: Number(macroOverview?.input_reliability_summary?.score || 0),
                lead: macroOverview?.input_reliability_summary?.lead || '',
                posture: macroOverview?.input_reliability_summary?.posture || '',
                reason: macroOverview?.input_reliability_summary?.reason || '',
                action_hint: template?.refreshMeta?.inputReliabilityShift?.actionHint || '',
              },
              recommendation_reason: template?.driverHeadline || '',
            },
            price_matrix_summary: backtestResult.price_matrix_summary || {},
            data_alignment: backtestResult.data_alignment || {},
            execution_diagnostics: backtestResult.execution_diagnostics || {},
            execution_plan: backtestResult.execution_plan || {},
            allocation_overlay: backtestResult.allocation_overlay || {},
            constraint_overlay: backtestResult.constraint_overlay || {},
            hedge_portfolio: backtestResult.hedge_portfolio || {},
            research_input: researchInput,
            view_context: workbenchViewContext || {},
            total_return: backtestResult.total_return || 0,
            sharpe_ratio: backtestResult.sharpe_ratio || 0,
            leg_performance: backtestResult.leg_performance || {},
          }
        : {
            template: template || {},
            template_meta: {
              theme: template?.theme || '',
              allocation_mode: template?.biasSummary ? 'macro_bias' : 'template_base',
              bias_summary: template?.biasSummary || '',
              bias_strength_raw: template?.rawBiasStrength || 0,
              bias_strength: template?.biasStrength || 0,
              bias_scale: template?.biasScale || 1,
              bias_quality_label: template?.biasQualityLabel || 'full',
              bias_quality_reason: template?.biasQualityReason || '',
              department_chaos_label: template?.departmentChaosLabel || 'unknown',
              department_chaos_score: template?.departmentChaosScore ?? null,
              department_chaos_top_department: template?.departmentChaosTopDepartment || '',
              department_chaos_reason: template?.departmentChaosReason || '',
              department_chaos_risk_budget_scale: template?.departmentChaosRiskBudgetScale ?? 1,
              people_fragility_label: template?.peopleFragilityLabel || 'stable',
              people_fragility_score: template?.peopleFragilityScore ?? null,
              people_fragility_focus: template?.peopleFragilityFocus || '',
              people_fragility_reason: template?.peopleFragilityReason || '',
              people_fragility_risk_budget_scale: template?.peopleFragilityRiskBudgetScale ?? 1,
              structural_decay_radar_label: template?.structuralDecayRadarLabel || 'stable',
              structural_decay_radar_display_label: template?.structuralDecayRadarDisplayLabel || '',
              structural_decay_radar_score: template?.structuralDecayRadarScore ?? null,
              structural_decay_radar_action_hint: template?.structuralDecayRadarActionHint || '',
              structural_decay_radar_risk_budget_scale: template?.structuralDecayRadarRiskBudgetScale ?? 1,
              structural_decay_radar_top_signals: template?.structuralDecayRadarTopSignals || [],
              policy_execution_label: template?.policyExecutionLabel || 'unknown',
              policy_execution_score: template?.policyExecutionScore ?? null,
              policy_execution_top_department: template?.policyExecutionTopDepartment || '',
              policy_execution_reason: template?.policyExecutionReason || '',
              policy_execution_risk_budget_scale: template?.policyExecutionRiskBudgetScale ?? 1,
              source_mode_label: template?.sourceModeLabel || 'mixed',
              source_mode_dominant: template?.sourceModeDominant || '',
              source_mode_reason: template?.sourceModeReason || '',
              source_mode_risk_budget_scale: template?.sourceModeRiskBudgetScale ?? 1,
              bias_highlights: template?.biasHighlights || [],
              bias_actions: template?.biasActions || [],
              driver_summary: template?.driverSummary || [],
              dominant_drivers: template?.dominantDrivers || [],
              core_legs: template?.coreLegs || [],
              support_legs: template?.supportLegs || [],
              theme_core: template?.themeCore || '',
              theme_support: template?.themeSupport || '',
              execution_posture: template?.executionPosture || template?.execution_posture || '',
              core_leg_pressure: coreLegPressure,
              resonance_label: template?.resonanceLabel || macroOverview?.resonance_summary?.label || 'mixed',
              resonance_reason: template?.resonanceReason || macroOverview?.resonance_summary?.reason || '',
              resonance_factors: template?.resonanceFactors || {},
              base_recommendation_tier: baseRecommendationTier,
              recommendation_tier: effectiveRecommendationTier,
              base_recommendation_score: baseRecommendationScore,
              recommendation_score: effectiveRecommendationScore,
              ranking_penalty: rankingPenalty,
              ranking_penalty_reason: rankingPenaltyReason,
              selection_quality: {
                label: selectionQualityLabel,
                reason: selectionQualityReason,
              },
              input_reliability: {
                label: macroOverview?.input_reliability_summary?.label || 'unknown',
                score: Number(macroOverview?.input_reliability_summary?.score || 0),
                lead: macroOverview?.input_reliability_summary?.lead || '',
                posture: macroOverview?.input_reliability_summary?.posture || '',
                reason: macroOverview?.input_reliability_summary?.reason || '',
                action_hint: template?.refreshMeta?.inputReliabilityShift?.actionHint || '',
              },
              recommendation_reason: template?.driverHeadline || '',
            },
            research_input: researchInput,
            assets: safeAssets,
            view_context: workbenchViewContext || {},
      },
    },
  };
  const refreshPriorityEvent = buildCrossMarketRefreshPriorityEvent(template, backtestResult, researchInputs);
  return refreshPriorityEvent
    ? { ...payload, refresh_priority_event: refreshPriorityEvent }
    : payload;
};

const normalizeTradeThesisTemplate = (template = {}, draft = {}) => ({
  ...template,
  id: template?.id || template?.template_id || draft?.templateId || '',
  name: template?.name || template?.template_name || draft?.title || '',
  theme: template?.theme || template?.stance || draft?.thesis?.stance || '',
  construction_mode: template?.construction_mode || draft?.quality?.construction_mode || '',
  driverHeadline: template?.driverHeadline || template?.recommendation_reason || draft?.thesis?.summary || draft?.note || '',
  coreLegs: template?.coreLegs || template?.core_legs || draft?.templateContext?.core_legs || [],
  supportLegs: template?.supportLegs || template?.support_legs || draft?.templateContext?.support_legs || [],
  themeCore: template?.themeCore || template?.theme_core || draft?.templateContext?.theme_core || '',
  themeSupport: template?.themeSupport || template?.theme_support || draft?.templateContext?.theme_support || '',
  recommendationTier: template?.recommendationTier || draft?.thesis?.stance || '',
  recommendationReason: template?.recommendation_reason || draft?.thesis?.summary || draft?.note || '',
  signalAttribution: template?.signalAttribution || template?.signal_attribution || draft?.templateContext?.signal_attribution || [],
});

export const buildTradeThesisWorkbenchPayload = (
  context = {},
  draft = null,
  template = null,
  backtestResult = null,
  assets = [],
  researchInputs = {}
) => {
  const normalizedTemplate = normalizeTradeThesisTemplate(template || draft?.templateContext || {}, draft || {});
  const basePayload = buildCrossMarketWorkbenchPayload(
    {
      ...context,
      template: context.template || draft?.templateId || normalizedTemplate.id || '',
    },
    normalizedTemplate,
    backtestResult,
    assets,
    researchInputs,
  );

  if (!basePayload) {
    return null;
  }

  const symbol = String(draft?.symbol || context.symbol || '').trim().toUpperCase();
  const taskLabel = draft?.title || normalizedTemplate.name || normalizedTemplate.id || 'Macro Mispricing Trade Thesis';
  const tradeAssets = (draft?.assets || assets || []).map((asset) => ({
    symbol: asset?.symbol || '',
    asset_class: asset?.asset_class || '',
    side: asset?.side || '',
    weight: asset?.weight ?? null,
    role: asset?.role || '',
    thesis: asset?.thesis || '',
  }));
  const tradeThesis = {
    draft_id: draft?.id || '',
    source: draft?.source || context.source || '',
    source_task_id: draft?.sourceTaskId || '',
    source_task_type: draft?.sourceTaskType || '',
    title: taskLabel,
    note: draft?.note || '',
    symbol,
    thesis: draft?.thesis || {},
    structural_decay: draft?.structuralDecay || {},
    people_layer: draft?.peopleLayer || {},
    quality: draft?.quality || {},
    constraints: draft?.constraints || {},
    meta: draft?.meta || {},
    parameters: draft?.parameters || {},
    template_context: draft?.templateContext || {},
    assets: tradeAssets,
    results_summary: backtestResult
      ? {
          total_return: backtestResult?.total_return ?? null,
          sharpe_ratio: backtestResult?.sharpe_ratio ?? null,
          coverage: backtestResult?.data_alignment?.tradable_day_ratio ?? null,
        }
      : {},
  };

  const payload = {
    ...basePayload,
    type: 'trade_thesis',
    title: `[TradeThesis] ${taskLabel}`,
    symbol,
    template: normalizedTemplate.id || basePayload.template,
    context: {
      ...basePayload.context,
      view: 'backtest',
      tab: 'cross-market',
      symbol,
      draft_id: draft?.id || '',
      source_task_id: draft?.sourceTaskId || '',
      source_task_type: draft?.sourceTaskType || '',
      thesis_origin: draft?.source || context.source || '',
      trade_thesis: true,
    },
    snapshot: {
      ...basePayload.snapshot,
      headline: backtestResult ? `${taskLabel} 交易 Thesis` : `${taskLabel} 交易草案`,
      summary: backtestResult
        ? `${taskLabel} 已保存为可回测的交易 Thesis，可继续在工作台里跟踪组合演化。`
        : `${taskLabel} 已保存为交易 Thesis 草案，可继续回测和迭代组合。`,
      highlights: buildHighlights(
        null,
        [
          draft?.thesis?.stance || '',
          draft?.structuralDecay?.label || '',
          draft?.peopleLayer?.risk_level ? `people ${draft.peopleLayer.risk_level}` : '',
          backtestResult ? `total return ${toSignedPercent(backtestResult.total_return || 0, 2)}` : '',
          `legs ${tradeAssets.length}`,
        ]
      ),
      payload: {
        ...basePayload.snapshot.payload,
        draft: draft || {},
        trade_thesis: tradeThesis,
      },
    },
  };
  const refreshPriorityEvent = buildTradeThesisRefreshPriorityEvent(
    draft,
    normalizedTemplate,
    backtestResult,
    researchInputs
  );
  return refreshPriorityEvent
    ? { ...payload, refresh_priority_event: refreshPriorityEvent }
    : payload;
};
