import { formatResearchSource } from '../../utils/researchContext';

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

const compactText = (value = '') => String(value || '').replace(/\s+/g, ' ').trim();

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

const detectMacroCue = (texts = []) =>
  /政策|宏观|能源|电力|电网|地缘|供应|供给|库存|物流|利率|关税|算力|火电|核电/i.test(
    texts.map((item) => compactText(item)).join(' ')
  );

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
  const macroCue = detectMacroCue([
    gap.direction,
    ...drivers.map((item) => item.description),
    ...insights,
  ]);
  const shouldCrossMarket =
    macroCue
    && (
      implications.confidence === 'low'
      || implications.risk_level === 'high'
      || ['moderate', 'unknown'].includes(gap.severity)
    );
  const recommendedTemplate = shouldCrossMarket
    ? recommendTemplateForSymbol(symbol, insights)
    : null;
  const primaryAction = shouldCrossMarket
    ? buildCrossMarketAction(
        recommendedTemplate,
        'pricing_playbook',
        `${symbol} 的单标的结论受宏观变量干扰较大，建议切换到跨市场模板继续验证。`
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
  const thesis = `${symbol} 当前偏向 ${primaryView}，价格偏差 ${toSignedPercent(gap.gap_pct || 0)}。${
    shouldCrossMarket
      ? '由于宏观变量干扰较强，下一步更适合用跨市场模板继续验证。'
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
          ? `当前价格 ${gap.current_price || '-'}，公允价值 ${gap.fair_value_mid}，偏差 ${toSignedPercent(gap.gap_pct || 0)}，结论为 ${gap.severity_label || primaryView}。`
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
          ? '单标的结论受宏观变量影响较大，建议进入跨市场剧本继续确认对冲结构。'
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
        longCount || shortCount ? `${longCount}L / ${shortCount}S` : null,
        `阶段 ${stageLabel}`,
        source ? `来源 ${formatResearchSource(source)}` : null,
      ].filter(Boolean),
      warnings: template ? [] : ['当前 URL 中的 template 未命中现有模板，请重新选择。'],
      next_actions: [returnToGodEye].filter(Boolean),
      tasks: [
        {
          id: 'cross-template',
          title: '模板假设确认',
          description: template
            ? `${template.description || '已载入模板'}；当前结构为 ${longCount} 个多头、${shortCount} 个空头。`
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
      coverage ? `覆盖率 ${toPercent(coverage, 1)}` : null,
      `${longLeg.assets?.length || 0}L / ${shortLeg.assets?.length || 0}S`,
    ].filter(Boolean),
    warnings,
    next_actions: [pricingAction, returnToGodEye].filter(Boolean),
    tasks: [
      {
        id: 'cross-template',
        title: '模板假设确认',
        description: template
          ? `${template.description || '已载入模板'}；当前采用 ${template.construction_mode || execution.construction_mode} 构造模式。`
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
        description: `Turnover ${Number(execution.turnover || 0).toFixed(2)}，Cost Drag ${toPercent(execution.cost_drag || 0, 2)}，平均持有 ${Number(execution.avg_holding_period || 0).toFixed(1)} 天。`,
        status:
          Number(execution.cost_drag || 0) > 0.02 || Number(execution.turnover || 0) > 8
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
