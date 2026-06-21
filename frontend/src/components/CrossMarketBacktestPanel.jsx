import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';

import { Panel } from '../design/components';

import ResearchPlaybook from './research-playbook/ResearchPlaybook';
import CrossMarketAssetSection from './cross-market/CrossMarketAssetSection';
import CrossMarketTemplateInsights from './cross-market/CrossMarketTemplateInsights';
import CrossMarketControlSidebar from './cross-market/CrossMarketControlSidebar';
import CrossMarketResultsView from './cross-market/CrossMarketResultsView';
import {
  buildCrossMarketPlaybook,
} from './research-playbook/playbookViewModels.js';
import {
  getCrossMarketTemplates,
  runCrossMarketBacktest,
} from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    ASSET_CLASS_LABELS,
    DEFAULT_CONSTRAINTS,
    DEFAULT_CROSS_MARKET_END_DATE,
    DEFAULT_CROSS_MARKET_START_DATE,
    DEFAULT_PARAMETERS,
    DEFAULT_QUALITY,
    createAsset,
    normalizeAssets,
} from '../utils/crossMarketDefaults';
import {
    buildDisplayTier,
    buildDisplayTone,
    formatBiasQualityLabel,
    formatConstructionMode,
    formatExecutionChannel,
    formatSignalLabel,
    formatStatusLabel,
    formatTemplateName,
    formatTemplateNarrative,
    formatTemplateTheme,
    formatVenue,
} from '../utils/crossMarketFormatters';
import {
    getBetaMeta,
    getCalendarMeta,
    getCapacityMeta,
    getCointegrationMeta,
    getConcentrationMeta,
    getLiquidityMeta,
    getMarginMeta,
} from '../utils/crossMarketMeta';
import {
  extractRecentComparisonLead,
  getSelectionQualityExplanationLines,
} from '../utils/crossMarketReviewHelpers';
import {
  buildCrossMarketCards,
} from '../utils/crossMarketRecommendations';
import { useAppUrlState } from '../hooks/useAppUrlState';
import { formatResearchSource, navigateByResearchAction, readResearchContext } from '../utils/researchContext.js';

const { Paragraph, Text } = Typography;

// Defaults / formatters / meta-resolvers extracted to dedicated utils so
// the host component focuses on orchestration. See:
//   - utils/crossMarketDefaults.js
//   - utils/crossMarketFormatters.js
//   - utils/crossMarketMeta.js
//   - utils/crossMarketReviewHelpers.js (pure refresh-meta / snapshot helpers)
//
// The banner stack, control sidebar and results canvas are layer-2 child
// components under components/cross-market/:
//   - CrossMarketTemplateInsights
//   - CrossMarketControlSidebar
//   - CrossMarketResultsView

const buildTemplateContextPayload = (template, appliedBiasMeta) => {
  if (!template?.id) {
    return undefined;
  }
  return {
    template_id: template.id,
    template_name: template.name || '',
    theme: template.theme || '',
    allocation_mode: appliedBiasMeta ? 'macro_bias' : 'template_base',
    bias_summary: appliedBiasMeta?.summary || '',
    bias_strength_raw: appliedBiasMeta?.rawStrength || 0,
    bias_strength: appliedBiasMeta?.strength || 0,
    bias_scale: appliedBiasMeta?.scale || 1,
    bias_quality_label: appliedBiasMeta?.qualityLabel || 'full',
    bias_quality_reason: appliedBiasMeta?.qualityReason || '',
    base_recommendation_score: template.baseRecommendationScore ?? template.recommendationScore ?? null,
    recommendation_score: template.recommendationScore ?? null,
    base_recommendation_tier: template.baseRecommendationTier || template.recommendationTier || '',
    recommendation_tier: template.recommendationTier || '',
    ranking_penalty: template.rankingPenalty || 0,
    ranking_penalty_reason: template.rankingPenaltyReason || '',
    input_reliability_label: template.inputReliabilityLabel || 'unknown',
    input_reliability_score: template.inputReliabilityScore ?? null,
    input_reliability_lead: template.inputReliabilityLead || '',
    input_reliability_posture: template.inputReliabilityPosture || '',
    input_reliability_reason: template.inputReliabilityReason || '',
    input_reliability_action_hint: template.refreshMeta?.inputReliabilityShift?.actionHint || '',
    department_chaos_label: template.departmentChaosLabel || 'unknown',
    department_chaos_score: template.departmentChaosScore ?? null,
    department_chaos_top_department: template.departmentChaosTopDepartment || '',
    department_chaos_reason: template.departmentChaosReason || '',
    department_chaos_risk_budget_scale: template.departmentChaosRiskBudgetScale ?? 1,
    policy_execution_label: template.policyExecutionLabel || 'unknown',
    policy_execution_score: template.policyExecutionScore ?? null,
    policy_execution_top_department: template.policyExecutionTopDepartment || '',
    policy_execution_reason: template.policyExecutionReason || '',
    policy_execution_risk_budget_scale: template.policyExecutionRiskBudgetScale ?? 1,
    people_fragility_label: template.peopleFragilityLabel || 'stable',
    people_fragility_score: template.peopleFragilityScore ?? null,
    people_fragility_focus: template.peopleFragilityFocus || '',
    people_fragility_reason: template.peopleFragilityReason || '',
    people_fragility_risk_budget_scale: template.peopleFragilityRiskBudgetScale ?? 1,
    source_mode_label: template.sourceModeLabel || 'mixed',
    source_mode_dominant: template.sourceModeDominant || '',
    source_mode_reason: template.sourceModeReason || '',
    source_mode_risk_budget_scale: template.sourceModeRiskBudgetScale ?? 1,
    structural_decay_radar_label: template.structuralDecayRadarLabel || 'stable',
    structural_decay_radar_display_label: template.structuralDecayRadarDisplayLabel || '',
    structural_decay_radar_score: template.structuralDecayRadarScore ?? null,
    structural_decay_radar_action_hint: template.structuralDecayRadarActionHint || '',
    structural_decay_radar_risk_budget_scale: template.structuralDecayRadarRiskBudgetScale ?? 1,
    structural_decay_radar_top_signals: template.structuralDecayRadarTopSignals || [],
    bias_highlights_raw: appliedBiasMeta?.rawHighlights || [],
    bias_highlights: appliedBiasMeta?.highlights || [],
    bias_actions: template.biasActions || [],
    signal_attribution: template.signalAttribution || [],
    driver_summary: template.driverSummary || [],
    dominant_drivers: template.dominantDrivers || [],
    core_legs: template.coreLegs || [],
    support_legs: template.supportLegs || [],
    theme_core: template.themeCore || '',
    theme_support: template.themeSupport || '',
    execution_posture: template.executionPosture || '',
    base_assets: (template.assets || []).map((asset) => ({
      symbol: asset.symbol,
      asset_class: asset.asset_class,
      side: asset.side,
      weight: asset.weight,
    })),
    raw_bias_assets: (template.rawAdjustedAssets || []).map((asset) => ({
      symbol: asset.symbol,
      asset_class: asset.asset_class,
      side: asset.side,
      weight: asset.weight,
    })),
  };
};

function CrossMarketBacktestPanel() {
  const message = useSafeMessageApi();
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [running, setRunning] = useState(false);
  const [assets, setAssets] = useState([
    createAsset('long', 0),
    createAsset('short', 0),
  ]);
  const [parameters, setParameters] = useState(DEFAULT_PARAMETERS);
  const [quality, setQuality] = useState(DEFAULT_QUALITY);
  const [constraints, setConstraints] = useState(DEFAULT_CONSTRAINTS);
  const [meta, setMeta] = useState({
    initial_capital: 100000,
    commission: 0.1,
    slippage: 0.1,
    start_date: DEFAULT_CROSS_MARKET_START_DATE,
    end_date: DEFAULT_CROSS_MARKET_END_DATE,
  });
  const [results, setResults] = useState(null);
  const appUrlState = useAppUrlState();
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [appliedBiasMeta, setAppliedBiasMeta] = useState(null);
  const [draftTemplateContext, setDraftTemplateContext] = useState(null);
  const appliedTemplateRef = useRef('');
  const autoRecommendedRef = useRef('');
  const researchContext = useMemo(
    () => readResearchContext(appUrlState.search),
    [appUrlState.search]
  );

  useEffect(() => {
    const loadTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const templateResponse = await getCrossMarketTemplates();
        setTemplates(templateResponse.templates || []);
      } catch (error) {
        message.error(error.userMessage || error.message || '加载模板失败');
      } finally {
        setLoadingTemplates(false);
      }
    };

    loadTemplates();
  }, [message]);

  const longAssets = useMemo(() => normalizeAssets(assets, 'long'), [assets]);
  const shortAssets = useMemo(() => normalizeAssets(assets, 'short'), [assets]);
  const recommendedTemplates = useMemo(
    () =>
      buildCrossMarketCards(
        { templates },
        {},
        {},
        (templateId, note) => ({
          label: '载入推荐模板',
          target: 'cross-market',
          template: templateId,
          source: 'cross_market_panel',
          note,
        })
      ),
    [templates]
  );
  const refreshByTemplate = useMemo(() => ({}), []);
  const taskByTemplate = useMemo(() => ({}), []);
  const displayRecommendedTemplates = useMemo(
    () =>
      recommendedTemplates
        .map((template) => {
          const refreshMeta = refreshByTemplate[template.id] || null;
          const recentComparisonLead = extractRecentComparisonLead(taskByTemplate[template.id]);
          const rankingPenalty = refreshMeta?.biasCompressionShift?.coreLegAffected
            ? 0.45
            : refreshMeta?.selectionQualityRunState?.active
              ? 0.3
            : refreshMeta?.reviewContextDriven
              ? 0.24
            : refreshMeta?.inputReliabilityDriven
              ? 0.16
            : refreshMeta?.selectionQualityDriven
              ? 0.2
              : 0;
          const recommendationScore = Number(Math.max(0, Number(template.recommendationScore || 0) - rankingPenalty).toFixed(2));
          return {
            ...template,
            baseRecommendationScore: template.baseRecommendationScore ?? template.recommendationScore,
            baseRecommendationTier: template.baseRecommendationTier || template.recommendationTier,
            rankingPenalty,
            rankingPenaltyReason: rankingPenalty
              ? refreshMeta?.biasCompressionShift?.coreLegAffected
                ? `核心腿 ${refreshMeta?.biasCompressionShift?.topCompressedAsset || ''} 已进入压缩焦点，默认模板选择自动降级`
                : refreshMeta?.selectionQualityRunState?.active
                  ? `当前结果已按 ${formatStatusLabel(refreshMeta?.selectionQualityRunState?.label || 'degraded')} 强度运行，默认模板选择进一步下调`
                : refreshMeta?.reviewContextDriven
                  ? `复核语境切换：${refreshMeta?.reviewContextShift?.lead || '最近两版已发生复核语境切换，默认模板选择谨慎下调'}`
                : refreshMeta?.inputReliabilityDriven
                  ? `输入可靠度变化：${refreshMeta?.inputReliabilityShift?.currentLead || '整体输入可靠度下降，默认模板选择适度下调'}`
                : '当前主题已进入自动降级处理，默认模板选择谨慎下调'
              : '',
            recommendationScore,
            recommendationTier: buildDisplayTier(recommendationScore),
            recommendationTone: buildDisplayTone(recommendationScore),
            refreshMeta,
            recentComparisonLead,
          };
        })
        .sort((left, right) => Number(right.recommendationScore || 0) - Number(left.recommendationScore || 0)),
    [recommendedTemplates, refreshByTemplate, taskByTemplate]
  );
  const selectedTemplate = useMemo(
    () =>
      displayRecommendedTemplates.find((item) => item.id === selectedTemplateId)
      || displayRecommendedTemplates.find((item) => item.id === researchContext.template)
      || templates.find((item) => item.id === selectedTemplateId)
      || templates.find((item) => item.id === researchContext.template)
      || null,
    [displayRecommendedTemplates, templates, selectedTemplateId, researchContext.template]
  );
  const effectiveTemplate = useMemo(() => {
    if (!selectedTemplate) {
      return null;
    }
    if (!appliedBiasMeta) {
      return {
        ...selectedTemplate,
        biasSummary: '',
        rawBiasStrength: 0,
        biasStrength: 0,
        biasScale: 1,
        biasQualityLabel: 'full',
        biasQualityReason: '',
        rawBiasHighlights: [],
        biasHighlights: [],
      };
    }
    return {
      ...selectedTemplate,
      biasSummary: appliedBiasMeta.summary || selectedTemplate.biasSummary || '',
      rawBiasStrength: appliedBiasMeta.rawStrength || selectedTemplate.rawBiasStrength || 0,
      biasStrength: appliedBiasMeta.strength || selectedTemplate.biasStrength || 0,
      biasScale: appliedBiasMeta.scale || selectedTemplate.biasScale || 1,
      biasQualityLabel: appliedBiasMeta.qualityLabel || selectedTemplate.biasQualityLabel || 'full',
      biasQualityReason: appliedBiasMeta.qualityReason || selectedTemplate.biasQualityReason || '',
      rawBiasHighlights: appliedBiasMeta.rawHighlights || selectedTemplate.rawBiasHighlights || [],
      biasHighlights: appliedBiasMeta.highlights || selectedTemplate.biasHighlights || [],
    };
  }, [appliedBiasMeta, selectedTemplate]);
  const selectedTemplateSelectionQualityLines = useMemo(
    () => getSelectionQualityExplanationLines(selectedTemplate?.refreshMeta),
    [selectedTemplate]
  );
  const playbook = useMemo(
    () =>
      buildCrossMarketPlaybook(
        {
          ...researchContext,
          template: researchContext.template || selectedTemplateId,
        },
        effectiveTemplate,
        results
      ),
    [effectiveTemplate, researchContext, results, selectedTemplateId]
  );
  const topRecommendationSelectionQualityLines = useMemo(
    () => getSelectionQualityExplanationLines(displayRecommendedTemplates[0]?.refreshMeta),
    [displayRecommendedTemplates]
  );
  const topRecommendation = displayRecommendedTemplates[0] || null;
  const topRecommendationNeedsPriorityReview = Boolean(
    topRecommendation?.refreshMeta?.selectionQualityRunState?.active
    || topRecommendation?.refreshMeta?.reviewContextDriven
    || topRecommendation?.refreshMeta?.inputReliabilityDriven
  );
  const selectedTemplateNeedsPriorityReview = Boolean(
    selectedTemplate?.refreshMeta?.selectionQualityRunState?.active
    || selectedTemplate?.refreshMeta?.reviewContextDriven
    || selectedTemplate?.refreshMeta?.inputReliabilityDriven
  );

  const updateAsset = (key, field, value) => {
    setAssets((prev) =>
      prev.map((asset) => (asset.key === key ? { ...asset, [field]: value } : asset))
    );
  };

  const removeAsset = (key) => {
    setAssets((prev) => prev.filter((asset) => asset.key !== key));
  };

  const addAsset = (side) => {
    setAssets((prev) => [...prev, createAsset(side, prev.length)]);
  };

  const applyTemplate = useCallback((templateOrId, options = {}) => {
    const { useBias = false, silent = false } = options;
    const template = typeof templateOrId === 'string'
      ? (displayRecommendedTemplates.find((item) => item.id === templateOrId) || templates.find((item) => item.id === templateOrId))
      : templateOrId;
    if (!template) {
      return;
    }
    setSelectedTemplateId(template.id);
    setAssets(
      (useBias && template.adjustedAssets ? template.adjustedAssets : template.assets).map((asset, index) => ({
        key: `${asset.side}-${index}-${template.id}`,
        ...asset,
      }))
    );
    setAppliedBiasMeta(
      useBias
        ? {
            mode: 'macro_bias',
            summary: template.biasSummary || '',
            rawStrength: template.rawBiasStrength || 0,
            strength: template.biasStrength || 0,
            scale: template.biasScale || 1,
            qualityLabel: template.biasQualityLabel || 'full',
            qualityReason: template.biasQualityReason || '',
            rawHighlights: template.rawBiasHighlights || [],
            highlights: template.biasHighlights || [],
            departmentChaosLabel: template.departmentChaosLabel || 'unknown',
            departmentChaosScore: template.departmentChaosScore || 0,
            departmentChaosTopDepartment: template.departmentChaosTopDepartment || '',
            departmentChaosReason: template.departmentChaosReason || '',
            departmentChaosRiskBudgetScale: template.departmentChaosRiskBudgetScale ?? 1,
            policyExecutionLabel: template.policyExecutionLabel || 'unknown',
            policyExecutionScore: template.policyExecutionScore || 0,
            policyExecutionTopDepartment: template.policyExecutionTopDepartment || '',
            policyExecutionReason: template.policyExecutionReason || '',
            policyExecutionRiskBudgetScale: template.policyExecutionRiskBudgetScale ?? 1,
            peopleFragilityLabel: template.peopleFragilityLabel || 'stable',
            peopleFragilityScore: template.peopleFragilityScore || 0,
            peopleFragilityFocus: template.peopleFragilityFocus || '',
            peopleFragilityReason: template.peopleFragilityReason || '',
            peopleFragilityRiskBudgetScale: template.peopleFragilityRiskBudgetScale ?? 1,
            sourceModeLabel: template.sourceModeLabel || 'mixed',
            sourceModeDominant: template.sourceModeDominant || '',
            sourceModeReason: template.sourceModeReason || '',
            sourceModeRiskBudgetScale: template.sourceModeRiskBudgetScale ?? 1,
            structuralDecayRadarLabel: template.structuralDecayRadarLabel || 'stable',
            structuralDecayRadarDisplayLabel: template.structuralDecayRadarDisplayLabel || '',
            structuralDecayRadarScore: template.structuralDecayRadarScore || 0,
            structuralDecayRadarActionHint: template.structuralDecayRadarActionHint || '',
            structuralDecayRadarRiskBudgetScale: template.structuralDecayRadarRiskBudgetScale ?? 1,
          }
        : null
    );
    setDraftTemplateContext(null);
    setParameters({
      lookback: template.parameters?.lookback ?? DEFAULT_PARAMETERS.lookback,
      entry_threshold: template.parameters?.entry_threshold ?? DEFAULT_PARAMETERS.entry_threshold,
      exit_threshold: template.parameters?.exit_threshold ?? DEFAULT_PARAMETERS.exit_threshold,
    });
    setQuality((prev) => ({
      ...prev,
      construction_mode: template.construction_mode || DEFAULT_QUALITY.construction_mode,
    }));
    if (!silent) {
      message.success(`已载入模板: ${formatTemplateName(template)}${useBias ? '（含宏观权重偏置）' : ''}`);
    }
  }, [displayRecommendedTemplates, message, templates]);

  useEffect(() => {
    if (!templates.length || !researchContext?.template) {
      return;
    }
    if (appliedTemplateRef.current === researchContext.template) {
      return;
    }
    const template = templates.find((item) => item.id === researchContext.template);
    if (!template) {
      return;
    }
    appliedTemplateRef.current = researchContext.template;
    applyTemplate(researchContext.template, { useBias: false });
  }, [applyTemplate, researchContext, templates]);

  useEffect(() => {
    setDraftTemplateContext(null);
  }, [researchContext?.draft]);

  useEffect(() => {
    if (researchContext?.template || selectedTemplateId || !displayRecommendedTemplates.length) {
      return;
    }
    const topRecommendation = displayRecommendedTemplates[0];
    if (!topRecommendation || autoRecommendedRef.current === topRecommendation.id) {
      return;
    }
    autoRecommendedRef.current = topRecommendation.id;
    applyTemplate(topRecommendation, { useBias: true, silent: true });
    message.info(`已自动载入当前最优宏观模板: ${formatTemplateName(topRecommendation)}`);
  }, [applyTemplate, displayRecommendedTemplates, message, researchContext, selectedTemplateId]);

  const handleRun = async () => {
    const payloadAssets = assets
      .map((asset) => ({
        symbol: (asset.symbol || '').trim().toUpperCase(),
        asset_class: asset.asset_class,
        side: asset.side,
        weight: asset.weight || undefined,
      }))
      .filter((asset) => asset.symbol);

    if (payloadAssets.length < 2) {
      message.error('请至少填写两个资产');
      return;
    }

    setRunning(true);
    setResults(null);
    try {
      const response = await runCrossMarketBacktest({
        assets: payloadAssets,
        template_context: selectedTemplate
          ? buildTemplateContextPayload(selectedTemplate, appliedBiasMeta)
          : (draftTemplateContext || undefined),
        allocation_constraints: {
          ...(constraints.max_single_weight ? { max_single_weight: constraints.max_single_weight / 100 } : {}),
          ...(constraints.min_single_weight ? { min_single_weight: constraints.min_single_weight / 100 } : {}),
        },
        strategy: 'spread_zscore',
        construction_mode: quality.construction_mode,
        parameters,
        min_history_days: quality.min_history_days,
        min_overlap_ratio: quality.min_overlap_ratio,
        initial_capital: meta.initial_capital,
        commission: meta.commission / 100,
        slippage: meta.slippage / 100,
        start_date: meta.start_date || undefined,
        end_date: meta.end_date || undefined,
      });
      if (response.success) {
        setResults(response.data);
        message.success('跨市场回测完成');
      } else {
        message.error(response.error || '跨市场回测失败');
      }
    } catch (error) {
      message.error(error.userMessage || error.message || '跨市场回测失败');
    } finally {
      setRunning(false);
    }
  };

  // renderAssetSection 拆到 ./cross-market/CrossMarketAssetSection.js（layer 2 子组件）
  const renderAssetSection = (title, sideAssets, side) => (
    <CrossMarketAssetSection
      title={title}
      side={side}
      sideAssets={sideAssets}
      onAdd={addAsset}
      onUpdate={updateAsset}
      onRemove={removeAsset}
    />
  );

  const correlationColumns = useMemo(() => {
    if (!results?.correlation_matrix?.columns) {
      return [];
    }
    return [
      {
        title: '资产代码',
        dataIndex: 'symbol',
        key: 'symbol',
        fixed: 'left',
      },
      ...results.correlation_matrix.columns.map((column) => ({
        title: column,
        dataIndex: column,
        key: column,
        render: (value) => Number(value).toFixed(3),
      })),
    ];
  }, [results]);

  const contributionColumns = useMemo(
    () => [
      {
        title: '资产',
        dataIndex: 'symbol',
        key: 'symbol',
      },
      {
        title: '方向',
        dataIndex: 'side',
        key: 'side',
        render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
      },
      {
        title: '类别',
        dataIndex: 'asset_class',
        key: 'asset_class',
        render: (value) => ASSET_CLASS_LABELS[value] || value,
      },
      {
        title: '权重',
        dataIndex: 'weight',
        key: 'weight',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '累计贡献',
        dataIndex: 'cumulative_return',
        key: 'cumulative_return',
        render: (value) => <span style={{ color: getValueColor(value) }}>{formatPercentage(Number(value || 0))}</span>,
      },
      {
        title: '波动率',
        dataIndex: 'volatility',
        key: 'volatility',
        render: (value) => formatPercentage(Number(value || 0)),
      },
    ],
    []
  );

  const assetContributionRows = useMemo(
    () => Object.values(results?.asset_contributions || {}),
    [results]
  );
  const hasResults = Boolean(results);
  const activeConstraintCount = Number(Boolean(constraints.max_single_weight)) + Number(Boolean(constraints.min_single_weight));
  const heroMetrics = useMemo(
    () => [
      {
        label: '当前主题',
        value: selectedTemplate ? formatTemplateTheme(selectedTemplate) : '自动推荐模板',
      },
      {
        label: '篮子规模',
        value: `多 ${longAssets.length} / 空 ${shortAssets.length}`,
      },
      {
        label: '构造模式',
        value: formatConstructionMode(quality.construction_mode),
      },
      {
        label: '当前状态',
        value: running
          ? '运行中'
          : (hasResults ? '结果已生成' : '待运行'),
      },
    ],
    [hasResults, longAssets.length, quality.construction_mode, running, selectedTemplate, shortAssets.length]
  );
  const heroWorkflow = useMemo(
    () => [
      {
        label: '模板与偏置',
        value: selectedTemplate
          ? `${formatTemplateName(selectedTemplate)}${appliedBiasMeta ? ' · 宏观偏置已启用' : ' · 原始权重'}`
          : '等待绑定模板',
        detail: selectedTemplate?.driverHeadline || '先确认主题模板，再决定长短腿篮子的构造方式。',
      },
      {
        label: '时间与成本',
        value: `${meta.start_date || '自动开始'} 至 ${meta.end_date || '自动结束'}`,
        detail: `资金 ${formatCurrency(Number(meta.initial_capital || 0))} · 手续费 ${Number(meta.commission || 0).toFixed(2)}% · 滑点 ${Number(meta.slippage || 0).toFixed(2)}%`,
      },
      {
        label: '结果理解',
        value: hasResults
          ? `${(Number(results?.total_return || 0) * 100).toFixed(2)}% 总收益 · Sharpe ${Number(results?.sharpe_ratio || 0).toFixed(2)}`
          : '运行后在主画布查看组合结论',
        detail: hasResults
          ? `样本 ${results?.price_matrix_summary?.row_count || 0} 个对齐交易日`
          : (activeConstraintCount
            ? `当前已启用 ${activeConstraintCount} 个单资产约束`
            : '当前未启用单资产约束'),
      },
    ],
    [
      activeConstraintCount,
      appliedBiasMeta,
      hasResults,
      meta.commission,
      meta.end_date,
      meta.initial_capital,
      meta.slippage,
      meta.start_date,
      results,
      selectedTemplate,
    ]
  );
  const sidebarOverviewItems = useMemo(
    () => [
      {
        label: '策略骨架',
        value: `${formatSignalLabel('spread_zscore')} · ${formatConstructionMode(quality.construction_mode)}`,
      },
      {
        label: '时间窗口',
        value: `${meta.start_date || '自动'} 至 ${meta.end_date || '自动'}`,
      },
      {
        label: '成本设置',
        value: `手续费 ${Number(meta.commission || 0).toFixed(2)}% · 滑点 ${Number(meta.slippage || 0).toFixed(2)}%`,
      },
      {
        label: '单资产约束',
        value: activeConstraintCount
          ? [
              constraints.max_single_weight ? `上限 ${Number(constraints.max_single_weight).toFixed(0)}%` : '',
              constraints.min_single_weight ? `下限 ${Number(constraints.min_single_weight).toFixed(0)}%` : '',
            ].filter(Boolean).join(' · ')
          : '未启用',
      },
    ],
    [
      activeConstraintCount,
      constraints.max_single_weight,
      constraints.min_single_weight,
      meta.commission,
      meta.end_date,
      meta.slippage,
      meta.start_date,
      quality.construction_mode,
    ]
  );
  const basketPreviewGroups = useMemo(
    () => [
      {
        key: 'long',
        title: '多头篮子',
        empty: '继续补充多头资产，形成清晰的主题暴露。',
        items: longAssets,
      },
      {
        key: 'short',
        title: '空头篮子',
        empty: '继续补充空头资产，完成对冲或相对价值表达。',
        items: shortAssets,
      },
    ],
    [longAssets, shortAssets]
  );
  const previewHighlights = useMemo(
    () => [
      {
        label: '模板结论',
        value: selectedTemplate?.driverHeadline || topRecommendation?.driverHeadline || '当前还没有模板结论，可先从推荐模板开始。',
      },
      {
        label: '风险预算',
        value: appliedBiasMeta
          ? `${Number(appliedBiasMeta.strength || 0).toFixed(1)}pp 偏置强度 · ${formatBiasQualityLabel(appliedBiasMeta.qualityLabel || 'full')}`
          : '按模板原始权重执行',
      },
      {
        label: '资金与样本',
        value: `${formatCurrency(Number(meta.initial_capital || 0))} 初始资金 · 回看 ${parameters.lookback} 天`,
      },
    ],
    [appliedBiasMeta, meta.initial_capital, parameters.lookback, selectedTemplate, topRecommendation]
  );
  const executionBatchColumns = useMemo(
    () => [
      {
        title: '执行通道',
        dataIndex: 'execution_channel',
        key: 'execution_channel',
        render: (value) => formatExecutionChannel(value),
      },
      {
        title: '交易场所',
        dataIndex: 'venue',
        key: 'venue',
        render: (value) => formatVenue(value),
      },
      {
        title: '数据源',
        dataIndex: 'preferred_provider',
        key: 'preferred_provider',
        render: (value) => <Tag color="blue">{value || '-'}</Tag>,
      },
      {
        title: '订单数',
        dataIndex: 'order_count',
        key: 'order_count',
      },
      {
        title: '总权重',
        dataIndex: 'gross_weight',
        key: 'gross_weight',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '目标资金',
        dataIndex: 'target_notional',
        key: 'target_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '预计成交',
        dataIndex: 'estimated_fill_notional',
        key: 'estimated_fill_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '容量',
        dataIndex: 'capacity_band',
        key: 'capacity_band',
        render: (value) => {
          const meta = getCapacityMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      {
        title: '日成交额占用',
        dataIndex: 'adv_usage',
        key: 'adv_usage',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '流动性',
        dataIndex: 'liquidity_band',
        key: 'liquidity_band',
        render: (value) => {
          const meta = getLiquidityMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      {
        title: '保证金',
        dataIndex: 'margin_requirement',
        key: 'margin_requirement',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '资产代码',
        dataIndex: 'symbols',
        key: 'symbols',
        render: (value) => (value || []).join(', '),
      },
    ],
    []
  );
  const executionRouteColumns = useMemo(
    () => [
      {
        title: '资产',
        dataIndex: 'symbol',
        key: 'symbol',
      },
      {
        title: '方向',
        dataIndex: 'side',
        key: 'side',
        render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
      },
      {
        title: '类别',
        dataIndex: 'asset_class',
        key: 'asset_class',
        render: (value) => ASSET_CLASS_LABELS[value] || value,
      },
      {
        title: '执行通道',
        dataIndex: 'execution_channel',
        key: 'execution_channel',
        render: (value) => formatExecutionChannel(value),
      },
      {
        title: '交易场所',
        dataIndex: 'venue',
        key: 'venue',
        render: (value) => formatVenue(value),
      },
      {
        title: '数据源',
        dataIndex: 'preferred_provider',
        key: 'preferred_provider',
      },
      {
        title: '资金占比',
        dataIndex: 'capital_fraction',
        key: 'capital_fraction',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '参考价',
        dataIndex: 'reference_price',
        key: 'reference_price',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '目标数量',
        dataIndex: 'target_quantity',
        key: 'target_quantity',
        render: (value) => Number(value || 0).toFixed(2),
      },
      {
        title: '下单数量',
        dataIndex: 'rounded_quantity',
        key: 'rounded_quantity',
      },
      {
        title: '目标资金',
        dataIndex: 'target_notional',
        key: 'target_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '最小单位损耗',
        dataIndex: 'residual_fraction',
        key: 'residual_fraction',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '容量',
        dataIndex: 'capacity_band',
        key: 'capacity_band',
        render: (value) => {
          const meta = getCapacityMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      {
        title: '日均成交额',
        dataIndex: 'avg_daily_notional',
        key: 'avg_daily_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '日成交额占用',
        dataIndex: 'adv_usage',
        key: 'adv_usage',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '流动性',
        dataIndex: 'liquidity_band',
        key: 'liquidity_band',
        render: (value) => {
          const meta = getLiquidityMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      {
        title: '保证金率',
        dataIndex: 'margin_rate',
        key: 'margin_rate',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '保证金',
        dataIndex: 'margin_requirement',
        key: 'margin_requirement',
        render: (value) => formatCurrency(Number(value || 0)),
      },
    ],
    []
  );
  const providerAllocationColumns = useMemo(
    () => [
      {
        title: '数据源',
        dataIndex: 'key',
        key: 'key',
        render: (value) => <Tag color="blue">{value || '-'}</Tag>,
      },
      {
        title: '路由数',
        dataIndex: 'route_count',
        key: 'route_count',
      },
      {
        title: '资金占比',
        dataIndex: 'capital_fraction',
        key: 'capital_fraction',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '目标资金',
        dataIndex: 'target_notional',
        key: 'target_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
    ],
    []
  );
  const venueAllocationColumns = useMemo(
    () => [
      {
        title: '交易场所',
        dataIndex: 'key',
        key: 'key',
        render: (value) => formatVenue(value),
      },
      {
        title: '路由数',
        dataIndex: 'route_count',
        key: 'route_count',
      },
      {
        title: '资金占比',
        dataIndex: 'capital_fraction',
        key: 'capital_fraction',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '目标资金',
        dataIndex: 'target_notional',
        key: 'target_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
    ],
    []
  );
  const stressScenarioColumns = useMemo(
    () => [
      {
        title: '资金放大',
        dataIndex: 'label',
        key: 'label',
      },
      {
        title: '批次数',
        dataIndex: 'batch_count',
        key: 'batch_count',
      },
      {
        title: '集中度',
        dataIndex: 'concentration_level',
        key: 'concentration_level',
        render: (value) => {
          const meta = getConcentrationMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      {
        title: '最大批次',
        dataIndex: 'largest_batch_notional',
        key: 'largest_batch_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '最小单位效率',
        dataIndex: 'lot_efficiency',
        key: 'lot_efficiency',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '残余资金',
        dataIndex: 'total_residual_notional',
        key: 'total_residual_notional',
        render: (value) => formatCurrency(Number(value || 0)),
      },
      {
        title: '最大日成交额占用',
        dataIndex: 'max_adv_usage',
        key: 'max_adv_usage',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '流动性',
        dataIndex: 'liquidity_level',
        key: 'liquidity_level',
        render: (value) => {
          const meta = getLiquidityMeta(value);
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
    ],
    []
  );
  const allocationOverlayColumns = useMemo(
    () => [
      {
        title: '资产',
        dataIndex: 'symbol',
        key: 'symbol',
      },
      {
        title: '方向',
        dataIndex: 'side',
        key: 'side',
        render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
      },
      {
        title: '原始权重',
        dataIndex: 'base_weight',
        key: 'base_weight',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '原始偏置权重',
        dataIndex: 'raw_bias_weight',
        key: 'raw_bias_weight',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '有效权重',
        dataIndex: 'effective_weight',
        key: 'effective_weight',
        render: (value) => formatPercentage(Number(value || 0)),
      },
      {
        title: '偏移',
        dataIndex: 'delta_weight',
        key: 'delta_weight',
        render: (value) => {
          const numeric = Number(value || 0);
          return <span style={{ color: getValueColor(numeric) }}>{numeric > 0 ? '+' : ''}{(numeric * 100).toFixed(2)}pp</span>;
        },
      },
      {
        title: '压缩差',
        dataIndex: 'compression_delta',
        key: 'compression_delta',
        render: (value) => {
          const numeric = Number(value || 0);
          return <span style={{ color: getValueColor(-numeric) }}>{numeric > 0 ? '-' : ''}{(Math.abs(numeric) * 100).toFixed(2)}pp</span>;
        },
      },
    ],
    []
  );
  const concentrationMeta = getConcentrationMeta(results?.execution_diagnostics?.concentration_level);
  const stressMeta = getConcentrationMeta(results?.execution_diagnostics?.stress_test_flag);
  const liquidityMeta = getLiquidityMeta(results?.execution_diagnostics?.liquidity_level);
  const marginMeta = getMarginMeta(results?.execution_diagnostics?.margin_level);
  const betaMeta = getBetaMeta(results?.execution_diagnostics?.beta_level);
  const calendarMeta = getCalendarMeta(results?.execution_diagnostics?.calendar_level);
  const cointegrationMeta = getCointegrationMeta(results?.execution_diagnostics?.cointegration_level);

  return (
    <div className="workspace-tab-view app-page-shell app-page-shell--wide" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="workspace-section workspace-section--accent app-page-hero app-page-hero--cross-market">
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">跨市场回测</div>
            <div className="workspace-section__description">围绕模板、篮子构造、质量约束和研究联动完成跨资产策略实验，保持与主回测一致的工作台体验。</div>
          </div>
        </div>
        <div className="cross-market-hero-grid">
          <div className="cross-market-hero-story">
            <Space wrap size={[8, 8]}>
              <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
                跨市场实验版
              </Tag>
              <Tag color={hasResults ? 'green' : (running ? 'processing' : 'default')}>
                {running ? '运行中' : (hasResults ? '结果已生成' : '待运行')}
              </Tag>
              {activeConstraintCount ? (
                <Tag color="gold">{`单资产约束 ${activeConstraintCount} 个`}</Tag>
              ) : null}
            </Space>
            <Paragraph style={{ marginBottom: 0 }}>
              用一条主画布把模板选择、长短腿篮子、质量约束和回测结果串起来。
              右侧侧栏负责快选模板与参数调整，主区域专注查看篮子和实验结论。
            </Paragraph>
            <div className="cross-market-hero-lanes">
              {heroWorkflow.map((item) => (
                <div key={item.label} className="cross-market-hero-lane">
                  <span className="cross-market-hero-lane__label">{item.label}</span>
                  <span className="cross-market-hero-lane__value">{item.value}</span>
                  <span className="cross-market-hero-lane__detail">{item.detail}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="cross-market-hero-summary">
            {heroMetrics.map((item) => (
              <div key={item.label} className="app-page-metric-card">
                <span className="app-page-metric-card__label">{item.label}</span>
                <span className="app-page-metric-card__value">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {researchContext?.template ? (
        <Panel className="app-page-context-rail">
          <div className="app-page-context-rail__header">
            <div>
              <div className="app-page-context-rail__eyebrow">执行上下文</div>
              <Text strong style={{ fontSize: 18, color: 'var(--text-primary)' }}>
                当前跨市场执行上下文
              </Text>
              <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                当前仓只保留模板载入语境，让首屏重点继续回到模板构造、风险预算和执行结果。
              </Paragraph>
            </div>
            <div className="app-page-context-rail__actions" />
          </div>
          <div className="app-page-context-rail__grid">
            {researchContext?.template ? (
              <div className="app-page-context-item">
                <span className="app-page-context-item__title">
                  {`已载入来自 ${formatResearchSource(researchContext.source)} 的跨市场模板 · ${playbook?.stageLabel || '待运行'}`}
                </span>
                <span className="app-page-context-item__detail">
                  {researchContext.note
                    ? researchContext.note
                    : `模板 ${formatTemplateName(researchContext.template)} 已自动预载，可继续编辑后再运行回测。当前剧本阶段为 ${playbook?.stageLabel || '待运行'}。`}
                </span>
              </div>
            ) : null}
          </div>
        </Panel>
      ) : null}

      {playbook ? (
        <div className="app-page-section-block">
          <div className="app-page-section-kicker">跨市场剧本</div>
          <ResearchPlaybook
            playbook={playbook}
            onAction={(action) => navigateByResearchAction(action)}
          />
        </div>
      ) : null}

      <CrossMarketTemplateInsights
        researchContext={researchContext}
        selectedTemplate={selectedTemplate}
        selectedTemplateSelectionQualityLines={selectedTemplateSelectionQualityLines}
        appliedBiasMeta={appliedBiasMeta}
        effectiveTemplate={effectiveTemplate}
        topRecommendation={topRecommendation}
        topRecommendationNeedsPriorityReview={topRecommendationNeedsPriorityReview}
        topRecommendationSelectionQualityLines={topRecommendationSelectionQualityLines}
      />

      <div className="cross-market-layout">
        <div className="cross-market-main">
          <div className="cross-market-asset-grid">
            {renderAssetSection('多头篮子', longAssets, 'long')}
            {renderAssetSection('空头篮子', shortAssets, 'short')}
          </div>

          <Panel className="workspace-panel cross-market-preview-card">
            <div className="cross-market-preview-grid">
              <div className="cross-market-preview-copy">
                <Text strong className="cross-market-preview-card__title">
                  {selectedTemplate ? formatTemplateName(selectedTemplate) : (draftTemplateContext?.template_name ? formatTemplateName(draftTemplateContext.template_name) : '当前实验还未绑定模板')}
                </Text>
                <Paragraph type="secondary" style={{ margin: '10px 0 0' }}>
                  {formatTemplateNarrative(
                    selectedTemplate?.narrative
                    || selectedTemplate?.description
                    || draftTemplateContext?.recommendation_reason
                    || topRecommendation?.narrative
                    || '先从侧栏模板快选开始，锁定主题、约束和时间窗口，再运行跨市场实验。'
                  )}
                </Paragraph>
                <div className="cross-market-preview-copy__list">
                  {previewHighlights.map((item) => (
                    <div key={item.label} className="cross-market-sidebar-card__item">
                      <span className="cross-market-sidebar-card__item-label">{item.label}</span>
                      <span className="cross-market-sidebar-card__item-value">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="cross-market-preview-baskets">
                {basketPreviewGroups.map((group) => {
                  const filledItems = group.items.filter((asset) => asset.symbol || asset.weight);
                  return (
                    <div key={group.key} className="cross-market-preview-basket">
                      <div className="cross-market-preview-basket__title">{group.title}</div>
                      {filledItems.length ? (
                        <div className="cross-market-preview-basket__tags">
                          {filledItems.map((asset) => (
                            <Tag key={`${group.key}-${asset.key}`} color={group.key === 'long' ? 'green' : 'volcano'}>
                              {asset.symbol || '待填写'}
                              {asset.asset_class ? ` · ${ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class}` : ''}
                              {asset.weight ? ` · ${formatPercentage(Number(asset.weight || 0))}` : ''}
                            </Tag>
                          ))}
                        </div>
                      ) : (
                        <Text type="secondary">{group.empty}</Text>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </Panel>
        </div>

        <CrossMarketControlSidebar
          sidebarOverviewItems={sidebarOverviewItems}
          selectedTemplate={selectedTemplate}
          displayRecommendedTemplates={displayRecommendedTemplates}
          templates={templates}
          loadingTemplates={loadingTemplates}
          selectedTemplateId={selectedTemplateId}
          parameters={parameters}
          quality={quality}
          constraints={constraints}
          meta={meta}
          selectedTemplateNeedsPriorityReview={selectedTemplateNeedsPriorityReview}
          running={running}
          applyTemplate={applyTemplate}
          setParameters={setParameters}
          setQuality={setQuality}
          setConstraints={setConstraints}
          setMeta={setMeta}
          setResults={setResults}
          onRun={handleRun}
        />
      </div>

      {running && !results ? (
        <Panel className="workspace-panel">
          <div style={{ minHeight: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin size="large" />
          </div>
        </Panel>
      ) : null}

      {results ? (
        <CrossMarketResultsView
          results={results}
          selectedTemplate={selectedTemplate}
          meta={meta}
          quality={quality}
          concentrationMeta={concentrationMeta}
          liquidityMeta={liquidityMeta}
          marginMeta={marginMeta}
          betaMeta={betaMeta}
          cointegrationMeta={cointegrationMeta}
          calendarMeta={calendarMeta}
          stressMeta={stressMeta}
          executionBatchColumns={executionBatchColumns}
          executionRouteColumns={executionRouteColumns}
          providerAllocationColumns={providerAllocationColumns}
          venueAllocationColumns={venueAllocationColumns}
          stressScenarioColumns={stressScenarioColumns}
          allocationOverlayColumns={allocationOverlayColumns}
          correlationColumns={correlationColumns}
          contributionColumns={contributionColumns}
          assetContributionRows={assetContributionRows}
        />
      ) : null}
    </div>
  );
}

export default CrossMarketBacktestPanel;
