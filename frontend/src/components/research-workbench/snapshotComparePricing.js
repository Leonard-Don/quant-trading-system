import { getPriceSourceLabel } from '../../utils/pricingResearch';
import {
  formatNumber,
  formatPercentPoints,
  formatSignedDelta,
  extractViewContextMetrics,
} from './snapshotCompareFormatters';

const formatSourceModeSummaryLabel = (summary = {}) => {
  const label = String(summary?.label || '').toLowerCase();
  if (label === 'official-led') return '官方/披露主导';
  if (label === 'fallback-heavy') return '回退源偏多';
  if (label === 'mixed') return '混合来源';
  return summary?.dominant || summary?.label || '-';
};

const buildTextDelta = (left, right, fallbackLabel) => (
  left === right ? '不变' : (fallbackLabel || `${left} -> ${right}`)
);

export const extractPricingMetrics = (snapshot) => {
  const payload = snapshot?.payload || {};
  const fairValue = payload.fair_value || {};
  const implications = payload.implications || {};
  const drivers = payload.drivers || [];
  const primaryDriver = payload.primary_driver || drivers[0] || {};
  const factorModel = payload.factor_model || {};
  const dcfScenarios = payload.dcf_scenarios || [];
  const bearCase = dcfScenarios.find((item) => item?.name === 'bear') || dcfScenarios[0] || null;
  const bullCase = dcfScenarios.find((item) => item?.name === 'bull') || dcfScenarios[dcfScenarios.length - 1] || null;
  const scenarioSpread = bearCase?.intrinsic_value != null && bullCase?.intrinsic_value != null
    ? Number(bullCase.intrinsic_value) - Number(bearCase.intrinsic_value)
    : null;
  const governanceOverlay = payload.people_governance_overlay || {};
  const researchInputMacro = payload.research_input?.macro || {};
  const policyExecutionContext = governanceOverlay.policy_execution_context || researchInputMacro.policy_execution || {};
  const sourceModeSummary = governanceOverlay.source_mode_summary || researchInputMacro.source_mode_summary || {};
  const peopleLayer = payload.people_layer || researchInputMacro.people_layer || {};
  return {
    fairValueMid: fairValue.mid ?? payload.gap_analysis?.fair_value_mid ?? null,
    fairValueLow: fairValue.low ?? bearCase?.intrinsic_value ?? null,
    fairValueHigh: fairValue.high ?? bullCase?.intrinsic_value ?? null,
    gapPct: payload.gap_analysis?.gap_pct ?? null,
    analysisPeriod: payload.period || factorModel.period || '-',
    currentPriceSource: getPriceSourceLabel(payload.current_price_source || ''),
    factorDataPoints: factorModel.data_points ?? null,
    primaryView: implications.primary_view || '-',
    alignmentLabel: implications.factor_alignment?.label || '-',
    driverHeadline: primaryDriver.factor || primaryDriver.name || '-',
    confidence: implications.confidence || '-',
    confidenceScore: implications.confidence_score ?? null,
    scenarioSpread,
    ff5Alpha: factorModel.ff5_alpha_pct ?? null,
    profitability: factorModel.ff5_profitability ?? null,
    investment: factorModel.ff5_investment ?? null,
    monteCarloMedian: payload.monte_carlo?.p50 ?? payload.monte_carlo?.median ?? null,
    monteCarloP90: payload.monte_carlo?.p90 ?? null,
    auditPriceSource: payload.audit_trail?.price_source || payload.current_price_source || '',
    auditBenchmarkSource: payload.audit_trail?.comparable_benchmark_source || payload.comparable?.benchmark_source || '-',
    governanceOverlayLabel: governanceOverlay.label || '-',
    governanceDiscountPct: governanceOverlay.governance_discount_pct ?? null,
    governanceConfidence: governanceOverlay.confidence ?? null,
    governanceSummary: governanceOverlay.summary || '-',
    executiveEvidence:
      governanceOverlay.executive_evidence?.leadership_balance
      || governanceOverlay.executive_evidence?.summary
      || peopleLayer.executive_profile?.leadership_balance
      || '-',
    insiderEvidence:
      governanceOverlay.insider_evidence?.label
      || governanceOverlay.insider_evidence?.summary
      || peopleLayer.insider_flow?.label
      || '-',
    hiringEvidence:
      governanceOverlay.hiring_evidence?.alert_message
      || governanceOverlay.hiring_evidence?.signal
      || peopleLayer.hiring_signal?.alert_message
      || '-',
    peopleLayerSummary: peopleLayer.summary || '-',
    policyExecutionLabel: policyExecutionContext.label || policyExecutionContext.execution_status || '-',
    policyExecutionSummary: policyExecutionContext.summary || '-',
    policyExecutionTopDepartment:
      policyExecutionContext.top_department
      || policyExecutionContext.top_departments?.[0]?.department_label
      || policyExecutionContext.top_departments?.[0]?.department
      || '-',
    sourceModeLabel: formatSourceModeSummaryLabel(sourceModeSummary),
    sourceModeCoverage: sourceModeSummary.coverage ?? null,
    sourceModeSummary:
      sourceModeSummary.summary
      || sourceModeSummary.fallback_reason
      || sourceModeSummary.dominant
      || '-',
    ...extractViewContextMetrics(payload),
  };
};

export const buildPricingComparisonRows = (base, target) => ({
  summary: [
    `视角 ${base.primaryView} -> ${target.primaryView}`,
    `主驱动 ${base.driverHeadline} -> ${target.driverHeadline}`,
    `情景区间 ${formatNumber(base.fairValueLow)}-${formatNumber(base.fairValueHigh)} -> ${formatNumber(target.fairValueLow)}-${formatNumber(target.fairValueHigh)}`,
    `治理折价 ${formatPercentPoints(base.governanceDiscountPct)} -> ${formatPercentPoints(target.governanceDiscountPct)}`,
  ],
  rows: [
    { key: 'fair-value', label: 'Fair Value', left: formatNumber(base.fairValueMid), right: formatNumber(target.fairValueMid), delta: formatSignedDelta(base.fairValueMid, target.fairValueMid, (v) => formatNumber(v)) },
    { key: 'fair-value-bear', label: 'Bear Case', left: formatNumber(base.fairValueLow), right: formatNumber(target.fairValueLow), delta: formatSignedDelta(base.fairValueLow, target.fairValueLow, (v) => formatNumber(v)) },
    { key: 'fair-value-bull', label: 'Bull Case', left: formatNumber(base.fairValueHigh), right: formatNumber(target.fairValueHigh), delta: formatSignedDelta(base.fairValueHigh, target.fairValueHigh, (v) => formatNumber(v)) },
    { key: 'scenario-spread', label: 'Scenario Spread', left: formatNumber(base.scenarioSpread), right: formatNumber(target.scenarioSpread), delta: formatSignedDelta(base.scenarioSpread, target.scenarioSpread, (v) => formatNumber(v)) },
    { key: 'gap-pct', label: 'Gap', left: formatPercentPoints(base.gapPct), right: formatPercentPoints(target.gapPct), delta: formatSignedDelta(base.gapPct, target.gapPct, (v) => formatPercentPoints(v)) },
    { key: 'primary-view', label: 'Primary View', left: base.primaryView, right: target.primaryView, delta: base.primaryView === target.primaryView ? '不变' : `${base.primaryView} -> ${target.primaryView}` },
    { key: 'workbench-view', label: 'Workbench View', left: base.viewContextSummary, right: target.viewContextSummary, delta: base.viewContextSummary === target.viewContextSummary ? '不变' : '工作台筛选视角已变化' },
    { key: 'workbench-task', label: 'Workbench Focus', left: base.viewContextTask, right: target.viewContextTask, delta: base.viewContextTask === target.viewContextTask ? '不变' : '任务焦点已变化' },
    { key: 'driver', label: 'Top Driver', left: base.driverHeadline, right: target.driverHeadline, delta: base.driverHeadline === target.driverHeadline ? '不变' : '已切换' },
    { key: 'alignment', label: 'Evidence Alignment', left: base.alignmentLabel, right: target.alignmentLabel, delta: base.alignmentLabel === target.alignmentLabel ? '不变' : `${base.alignmentLabel} -> ${target.alignmentLabel}` },
    {
      key: 'governance-overlay',
      label: 'Governance Overlay',
      left: base.governanceOverlayLabel,
      right: target.governanceOverlayLabel,
      delta: buildTextDelta(base.governanceOverlayLabel, target.governanceOverlayLabel, '治理判断已变化'),
    },
    {
      key: 'governance-discount',
      label: 'Governance Discount',
      left: formatPercentPoints(base.governanceDiscountPct),
      right: formatPercentPoints(target.governanceDiscountPct),
      delta: formatSignedDelta(base.governanceDiscountPct, target.governanceDiscountPct, (v) => formatPercentPoints(v)),
    },
    {
      key: 'governance-confidence',
      label: 'Governance Confidence',
      left: formatNumber(base.governanceConfidence),
      right: formatNumber(target.governanceConfidence),
      delta: formatSignedDelta(base.governanceConfidence, target.governanceConfidence, (v) => formatNumber(v)),
    },
    {
      key: 'governance-summary',
      label: 'Governance Summary',
      left: base.governanceSummary,
      right: target.governanceSummary,
      delta: buildTextDelta(base.governanceSummary, target.governanceSummary, '治理摘要已变化'),
    },
    {
      key: 'people-layer',
      label: 'People Layer',
      left: base.peopleLayerSummary,
      right: target.peopleLayerSummary,
      delta: buildTextDelta(base.peopleLayerSummary, target.peopleLayerSummary, '人的维度判断已变化'),
    },
    {
      key: 'executive-evidence',
      label: 'Executive Evidence',
      left: base.executiveEvidence,
      right: target.executiveEvidence,
      delta: buildTextDelta(base.executiveEvidence, target.executiveEvidence, '管理层证据已变化'),
    },
    {
      key: 'insider-evidence',
      label: 'Insider Evidence',
      left: base.insiderEvidence,
      right: target.insiderEvidence,
      delta: buildTextDelta(base.insiderEvidence, target.insiderEvidence, '内部人证据已变化'),
    },
    {
      key: 'hiring-evidence',
      label: 'Hiring Evidence',
      left: base.hiringEvidence,
      right: target.hiringEvidence,
      delta: buildTextDelta(base.hiringEvidence, target.hiringEvidence, '招聘结构证据已变化'),
    },
    {
      key: 'policy-execution',
      label: 'Policy Execution',
      left: base.policyExecutionLabel,
      right: target.policyExecutionLabel,
      delta: buildTextDelta(base.policyExecutionLabel, target.policyExecutionLabel, '政策执行状态已变化'),
    },
    {
      key: 'policy-execution-focus',
      label: 'Policy Execution Focus',
      left: `${base.policyExecutionTopDepartment} · ${base.policyExecutionSummary}`,
      right: `${target.policyExecutionTopDepartment} · ${target.policyExecutionSummary}`,
      delta: buildTextDelta(
        `${base.policyExecutionTopDepartment} · ${base.policyExecutionSummary}`,
        `${target.policyExecutionTopDepartment} · ${target.policyExecutionSummary}`,
        '政策执行焦点已变化'
      ),
    },
    {
      key: 'source-mode',
      label: 'Source Mode',
      left: base.sourceModeLabel,
      right: target.sourceModeLabel,
      delta: buildTextDelta(base.sourceModeLabel, target.sourceModeLabel, '来源治理已变化'),
    },
    {
      key: 'source-mode-coverage',
      label: 'Source Mode Coverage',
      left: formatNumber(base.sourceModeCoverage, 0),
      right: formatNumber(target.sourceModeCoverage, 0),
      delta: formatSignedDelta(base.sourceModeCoverage, target.sourceModeCoverage, (v) => formatNumber(v, 0)),
    },
    {
      key: 'source-mode-summary',
      label: 'Source Mode Summary',
      left: base.sourceModeSummary,
      right: target.sourceModeSummary,
      delta: buildTextDelta(base.sourceModeSummary, target.sourceModeSummary, '来源摘要已变化'),
    },
    { key: 'analysis-period', label: 'Analysis Window', left: base.analysisPeriod, right: target.analysisPeriod, delta: base.analysisPeriod === target.analysisPeriod ? '不变' : `${base.analysisPeriod} -> ${target.analysisPeriod}` },
    { key: 'price-source', label: 'Price Source', left: base.currentPriceSource, right: target.currentPriceSource, delta: base.currentPriceSource === target.currentPriceSource ? '不变' : `${base.currentPriceSource} -> ${target.currentPriceSource}` },
    { key: 'factor-samples', label: 'Factor Samples', left: formatNumber(base.factorDataPoints, 0), right: formatNumber(target.factorDataPoints, 0), delta: formatSignedDelta(base.factorDataPoints, target.factorDataPoints, (v) => formatNumber(v, 0)) },
    { key: 'confidence', label: 'Confidence', left: base.confidence, right: target.confidence, delta: base.confidence === target.confidence ? '不变' : `${base.confidence} -> ${target.confidence}` },
    { key: 'confidence-score', label: 'Confidence Score', left: formatNumber(base.confidenceScore), right: formatNumber(target.confidenceScore), delta: formatSignedDelta(base.confidenceScore, target.confidenceScore, (v) => formatNumber(v)) },
    { key: 'ff5-alpha', label: 'FF5 Alpha', left: formatNumber(base.ff5Alpha), right: formatNumber(target.ff5Alpha), delta: formatSignedDelta(base.ff5Alpha, target.ff5Alpha, (v) => formatNumber(v)) },
    { key: 'profitability', label: 'Profitability', left: formatNumber(base.profitability), right: formatNumber(target.profitability), delta: formatSignedDelta(base.profitability, target.profitability, (v) => formatNumber(v)) },
    { key: 'investment', label: 'Investment', left: formatNumber(base.investment), right: formatNumber(target.investment), delta: formatSignedDelta(base.investment, target.investment, (v) => formatNumber(v)) },
    { key: 'monte-carlo-median', label: 'Monte Carlo P50', left: formatNumber(base.monteCarloMedian), right: formatNumber(target.monteCarloMedian), delta: formatSignedDelta(base.monteCarloMedian, target.monteCarloMedian, (v) => formatNumber(v)) },
    { key: 'monte-carlo-p90', label: 'Monte Carlo P90', left: formatNumber(base.monteCarloP90), right: formatNumber(target.monteCarloP90), delta: formatSignedDelta(base.monteCarloP90, target.monteCarloP90, (v) => formatNumber(v)) },
    { key: 'benchmark-source', label: 'Benchmark Source', left: base.auditBenchmarkSource, right: target.auditBenchmarkSource, delta: base.auditBenchmarkSource === target.auditBenchmarkSource ? '不变' : `${base.auditBenchmarkSource} -> ${target.auditBenchmarkSource}` },
  ],
});
