import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import ResearchPlaybook from './research-playbook/ResearchPlaybook';
import CrossMarketDiagnosticsSection from './cross-market/CrossMarketDiagnosticsSection';
import CrossMarketBasketSummaryCard from './cross-market/CrossMarketBasketSummaryCard';
import {
  buildCrossMarketPlaybook,
} from './research-playbook/playbookViewModels';
import { buildSnapshotComparison } from '../utils/snapshotCompare';
import {
  getCrossMarketTemplates,
  runCrossMarketBacktest,
} from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    ASSET_CLASS_LABELS,
    ASSET_CLASS_OPTIONS,
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
    formatConstructionMode,
    formatExecutionChannel,
    formatTradeAction,
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
    getSelectionQualityMeta,
} from '../utils/crossMarketMeta';
import {
  buildCrossMarketCards,
  CROSS_MARKET_DIMENSION_LABELS,
  CROSS_MARKET_FACTOR_LABELS,
} from '../utils/crossMarketRecommendations';
import { useAppUrlState } from '../hooks/useAppUrlState';
import { formatResearchSource, navigateByResearchAction, readResearchContext } from '../utils/researchContext';

const { Paragraph, Text } = Typography;

// Defaults / formatters / meta-resolvers extracted to dedicated utils so
// the host component focuses on orchestration. See:
//   - utils/crossMarketDefaults.js
//   - utils/crossMarketFormatters.js
//   - utils/crossMarketMeta.js

const extractRecentComparisonLead = (task = {}) => {
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

const extractCoreLegPressure = (overlay = {}) => {
  const topCompressed = (overlay.rows || [])
    .slice()
    .sort((left, right) => Math.abs(Number(right?.compression_delta || 0)) - Math.abs(Number(left?.compression_delta || 0)))
    .find((item) => Math.abs(Number(item?.compression_delta || 0)) >= 0.005);
  const symbol = String(topCompressed?.symbol || '').trim().toUpperCase();
  const themeCore = String(overlay.theme_core || '').toUpperCase();
  if (!symbol) {
    return { affected: false, summary: '' };
  }
  return {
    affected: Boolean(themeCore && themeCore.includes(symbol)),
    summary: `${topCompressed.symbol} ${(Math.abs(Number(topCompressed.compression_delta || 0)) * 100).toFixed(2)}pp`,
  };
};

// formatTradeAction / formatExecutionChannel / formatVenue moved to
// utils/crossMarketFormatters.js. The eight `get*Meta` resolvers live in
// utils/crossMarketMeta.js so they can be unit-tested independently of
// this component.

const getSelectionQualityExplanationLines = (refreshMeta = {}) => {
  const lines = [];
  const runState = refreshMeta?.selectionQualityRunState;
  const shift = refreshMeta?.selectionQualityShift;

  if (runState?.active) {
    const scoreText =
      Number.isFinite(runState.baseScore) || Number.isFinite(runState.effectiveScore)
        ? ` · ${Number(runState.baseScore || 0).toFixed(2)}→${Number(runState.effectiveScore || 0).toFixed(2)}`
        : '';
    lines.push(
      `降级运行 ${runState.label}${scoreText}${runState.reason ? ` · ${runState.reason}` : ''}`
    );
  }

  if (refreshMeta?.selectionQualityDriven && shift?.currentReason) {
    lines.push(`自动降级 ${shift.currentLabel} · ${shift.currentReason}`);
  }

  return lines;
};

const getReviewPriorityTitleSuffix = (refreshMeta = {}) => {
  if (refreshMeta?.selectionQualityRunState?.active) {
    return '建议优先重看';
  }
  if (refreshMeta?.reviewContextShift?.enteredReview) {
    return '建议按复核结果重看';
  }
  if (refreshMeta?.reviewContextShift?.exitedReview) {
    return '建议确认恢复普通结果';
  }
  if (refreshMeta?.reviewContextDriven) {
    return '建议重新确认结果语境';
  }
  if (refreshMeta?.inputReliabilityShift?.enteredFragile) {
    return '建议先复核输入可靠度';
  }
  if (refreshMeta?.inputReliabilityShift?.recoveredRobust) {
    return '建议确认恢复正常强度';
  }
  if (refreshMeta?.inputReliabilityDriven) {
    return '建议重新确认输入质量';
  }
  return '';
};

const getReviewPriorityContextLine = (refreshMeta = {}) => {
  if (refreshMeta?.selectionQualityRunState?.active) {
    return '该主题当前保存结果已经在降级强度下运行，默认起点仍保留，但更适合先重看当前任务判断。';
  }
  if (refreshMeta?.reviewContextShift?.actionHint) {
    return refreshMeta.reviewContextShift.actionHint;
  }
  if (refreshMeta?.reviewContextDriven) {
    return '该主题最近两版已发生复核语境切换，默认起点仍保留，但更适合先重看当前任务判断。';
  }
  if (refreshMeta?.inputReliabilityShift?.actionHint) {
    return refreshMeta.inputReliabilityShift.actionHint;
  }
  if (refreshMeta?.inputReliabilityDriven) {
    return '该主题当前整体输入可靠度已经变化，默认起点仍保留，但更适合先确认输入质量再决定是否继续沿用当前模板。';
  }
  return '';
};

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
                  ? `当前结果已按 ${refreshMeta?.selectionQualityRunState?.label || 'degraded'} 强度运行，默认模板选择进一步下调`
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
      message.success(`已载入模板: ${template.name}${useBias ? '（含宏观权重偏置）' : ''}`);
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
    message.info(`已自动载入当前最优宏观模板: ${topRecommendation.name}`);
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

  const renderAssetSection = (title, sideAssets, side) => (
    <Card
      title={title}
      extra={
        <Button size="small" icon={<PlusOutlined />} onClick={() => addAsset(side)}>
          新增
        </Button>
      }
      variant="borderless"
      className="workspace-panel cross-market-asset-card"
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        {sideAssets.map((asset) => (
          <Row gutter={12} key={asset.key}>
            <Col xs={24} md={8}>
              <Input
                value={asset.symbol}
                placeholder="资产代码"
                onChange={(event) => updateAsset(asset.key, 'symbol', event.target.value)}
              />
            </Col>
            <Col xs={24} md={8}>
              <Select
                value={asset.asset_class}
                options={ASSET_CLASS_OPTIONS}
                style={{ width: '100%' }}
                onChange={(value) => updateAsset(asset.key, 'asset_class', value)}
              />
            </Col>
            <Col xs={18} md={6}>
              <InputNumber
                value={asset.weight}
                min={0.01}
                step={0.05}
                placeholder="权重"
                style={{ width: '100%' }}
                onChange={(value) => updateAsset(asset.key, 'weight', value)}
              />
            </Col>
            <Col xs={6} md={2}>
              <Button
                icon={<DeleteOutlined />}
                danger
                onClick={() => removeAsset(asset.key)}
              />
            </Col>
          </Row>
        ))}
      </Space>
    </Card>
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
        value: selectedTemplate?.theme || selectedTemplate?.name || '自动推荐模板',
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
          ? `${selectedTemplate.name}${appliedBiasMeta ? ' · 宏观偏置已启用' : ' · 原始权重'}`
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
        value: `spread_zscore · ${formatConstructionMode(quality.construction_mode)}`,
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
          ? `${Number(appliedBiasMeta.strength || 0).toFixed(1)}pp 偏置强度 · ${appliedBiasMeta.qualityLabel || 'full'}`
          : '按模板原始权重执行',
      },
      {
        label: '资金与样本',
        value: `${formatCurrency(Number(meta.initial_capital || 0))} 初始资金 · lookback ${parameters.lookback} 天`,
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
        title: 'Venue',
        dataIndex: 'venue',
        key: 'venue',
        render: (value) => formatVenue(value),
      },
      {
        title: 'Provider',
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
        title: 'Gross Weight',
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
        title: 'ADV Usage',
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
        title: 'Symbols',
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
        title: 'Venue',
        dataIndex: 'venue',
        key: 'venue',
        render: (value) => formatVenue(value),
      },
      {
        title: 'Provider',
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
        title: 'ADV Usage',
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
        title: 'Provider',
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
        title: 'Venue',
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
        title: 'Lot 效率',
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
        title: 'Max ADV',
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
        <Card className="app-page-context-rail" variant="borderless">
          <div className="app-page-context-rail__header">
            <div>
              <div className="app-page-context-rail__eyebrow">Execution Context</div>
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
                    : `模板 ${researchContext.template} 已自动预载，可继续编辑后再运行回测。当前剧本阶段为 ${playbook?.stageLabel || '待运行'}。`}
                </span>
              </div>
            ) : null}
          </div>
        </Card>
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

      <div className="app-page-banner-stack">
      {selectedTemplate ? (
        <Alert
          type="info"
          showIcon
          message={`当前模板主题：${selectedTemplate.theme || selectedTemplate.name}${selectedTemplate.recommendationTier ? ` · ${selectedTemplate.recommendationTier}` : ''}`}
          description={(
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Text>{selectedTemplate.narrative || selectedTemplate.description}</Text>
              {selectedTemplate.driverHeadline ? (
                <Text type="secondary">{selectedTemplate.driverHeadline}</Text>
              ) : null}
              {selectedTemplate.resonanceReason && selectedTemplate.resonanceLabel !== 'mixed' ? (
                <Text type="secondary">{selectedTemplate.resonanceReason}</Text>
              ) : null}
              <Space wrap size={[6, 6]}>
                {(selectedTemplate.linked_factors || []).map((factor) => (
                  <Tag key={`factor-${factor}`} color="purple">
                    因子: {CROSS_MARKET_FACTOR_LABELS[factor] || factor}
                  </Tag>
                ))}
                {(selectedTemplate.linked_dimensions || []).map((dimension) => (
                  <Tag key={`dimension-${dimension}`} color="blue">
                    维度: {CROSS_MARKET_DIMENSION_LABELS[dimension] || dimension}
                  </Tag>
                ))}
                {selectedTemplate.resonanceLabel && selectedTemplate.resonanceLabel !== 'mixed' ? (
                  <Tag color="magenta">resonance {selectedTemplate.resonanceLabel}</Tag>
                ) : null}
                {selectedTemplate.policySourceHealthLabel && selectedTemplate.policySourceHealthLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.policySourceHealthLabel === 'fragile' ? 'red' : selectedTemplate.policySourceHealthLabel === 'watch' ? 'gold' : 'green'}>
                    policy source {selectedTemplate.policySourceHealthLabel}
                  </Tag>
                ) : null}
                {selectedTemplate.inputReliabilityLabel && selectedTemplate.inputReliabilityLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.inputReliabilityLabel === 'fragile' ? 'red' : selectedTemplate.inputReliabilityLabel === 'watch' ? 'gold' : 'green'}>
                    input {selectedTemplate.inputReliabilityLabel}
                  </Tag>
                ) : null}
                {selectedTemplate.sourceModeLabel && selectedTemplate.sourceModeLabel !== 'mixed' ? (
                  <Tag color={selectedTemplate.sourceModeLabel === 'official-led' ? 'green' : selectedTemplate.sourceModeLabel === 'fallback-heavy' ? 'orange' : 'blue'}>
                    来源 {selectedTemplate.sourceModeLabel}
                  </Tag>
                ) : null}
                {selectedTemplate.policyExecutionLabel && selectedTemplate.policyExecutionLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.policyExecutionLabel === 'chaotic' ? 'red' : selectedTemplate.policyExecutionLabel === 'watch' ? 'gold' : 'green'}>
                    政策执行 {selectedTemplate.policyExecutionLabel}
                  </Tag>
                ) : null}
                {selectedTemplate.executionPosture ? (
                  <Tag color="lime">{selectedTemplate.executionPosture}</Tag>
                ) : null}
              </Space>
              {(selectedTemplate.themeCore || selectedTemplate.themeSupport) ? (
                <Text type="secondary">
                  核心腿：{selectedTemplate.themeCore || '暂无'} · 辅助腿：{selectedTemplate.themeSupport || '暂无'}
                </Text>
              ) : null}
              {selectedTemplate.policySourceHealthReason ? (
                <Text type="secondary">{selectedTemplate.policySourceHealthReason}</Text>
              ) : null}
              {selectedTemplate.policyExecutionReason ? (
                <Text type="secondary">
                  政策执行：{selectedTemplate.policyExecutionReason}
                  {selectedTemplate.policyExecutionTopDepartment
                    ? ` · ${selectedTemplate.policyExecutionTopDepartment}`
                    : ''}
                  {selectedTemplate.policyExecutionRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(selectedTemplate.policyExecutionRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.sourceModeReason ? (
                <Text type="secondary">
                  来源治理：{selectedTemplate.sourceModeReason}
                  {selectedTemplate.sourceModeRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(selectedTemplate.sourceModeRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.inputReliabilityLead ? (
                <Text type="secondary">
                  输入可靠度：{selectedTemplate.inputReliabilityLead}
                  {selectedTemplate.inputReliabilityScore
                    ? ` · score ${Number(selectedTemplate.inputReliabilityScore || 0).toFixed(2)}`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.inputReliabilityPosture ? (
                <Text type="secondary">使用姿势：{selectedTemplate.inputReliabilityPosture}</Text>
              ) : null}
              {selectedTemplate.refreshMeta?.inputReliabilityShift?.actionHint ? (
                <Text type="secondary">{selectedTemplate.refreshMeta.inputReliabilityShift.actionHint}</Text>
              ) : null}
              {selectedTemplateSelectionQualityLines.map((line) => (
                <Text key={line} type="secondary">
                  {line}
                </Text>
              ))}
              {selectedTemplate.biasQualityLabel && selectedTemplate.biasQualityLabel !== 'full' ? (
                <Text type="secondary">
                  偏置收缩 {selectedTemplate.biasQualityLabel} · {selectedTemplate.biasQualityReason}
                </Text>
              ) : null}
            </Space>
          )}
        />
      ) : null}

      {appliedBiasMeta ? (
        <Alert
          type="success"
          showIcon
          message={`宏观权重偏置已启用 · 强度 ${Number(appliedBiasMeta.strength || 0).toFixed(1)}pp`}
          description={(
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text>{appliedBiasMeta.summary}</Text>
              {appliedBiasMeta.qualityLabel && appliedBiasMeta.qualityLabel !== 'full' ? (
                <Text type="secondary">偏置收缩 {appliedBiasMeta.qualityLabel} · {appliedBiasMeta.qualityReason}</Text>
              ) : null}
              {appliedBiasMeta.departmentChaosLabel && appliedBiasMeta.departmentChaosLabel !== 'unknown' ? (
                <Text type="secondary">
                  部门混乱 {appliedBiasMeta.departmentChaosLabel}
                  {appliedBiasMeta.departmentChaosTopDepartment ? ` · ${appliedBiasMeta.departmentChaosTopDepartment}` : ''}
                  {appliedBiasMeta.departmentChaosRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.departmentChaosRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.peopleFragilityLabel && appliedBiasMeta.peopleFragilityLabel !== 'stable' ? (
                <Text type="secondary">
                  人的维度 {appliedBiasMeta.peopleFragilityLabel}
                  {appliedBiasMeta.peopleFragilityFocus ? ` · ${appliedBiasMeta.peopleFragilityFocus}` : ''}
                  {appliedBiasMeta.peopleFragilityRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.peopleFragilityRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.policyExecutionLabel && appliedBiasMeta.policyExecutionLabel !== 'unknown' ? (
                <Text type="secondary">
                  政策执行 {appliedBiasMeta.policyExecutionLabel}
                  {appliedBiasMeta.policyExecutionTopDepartment ? ` · ${appliedBiasMeta.policyExecutionTopDepartment}` : ''}
                  {appliedBiasMeta.policyExecutionRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.policyExecutionRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.sourceModeLabel && appliedBiasMeta.sourceModeLabel !== 'mixed' ? (
                <Text type="secondary">
                  来源治理 {appliedBiasMeta.sourceModeLabel}
                  {appliedBiasMeta.sourceModeReason ? ` · ${appliedBiasMeta.sourceModeReason}` : ''}
                  {appliedBiasMeta.sourceModeRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.sourceModeRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.structuralDecayRadarLabel && appliedBiasMeta.structuralDecayRadarLabel !== 'stable' ? (
                <Text type="secondary">
                  结构衰败 {appliedBiasMeta.structuralDecayRadarDisplayLabel || appliedBiasMeta.structuralDecayRadarLabel}
                  {appliedBiasMeta.structuralDecayRadarScore !== undefined
                    ? ` · ${Math.round(Number(appliedBiasMeta.structuralDecayRadarScore || 0) * 100)}%`
                    : ''}
                  {appliedBiasMeta.structuralDecayRadarRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.structuralDecayRadarRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              <Space wrap size={[6, 6]}>
                {(appliedBiasMeta.highlights || []).map((item) => (
                  <Tag key={item} color="green">{item}</Tag>
                ))}
              </Space>
            </Space>
          )}
        />
      ) : null}

      {effectiveTemplate?.biasActions?.length ? (
        <Card title="建议增减仓名单" variant="borderless">
          <Space wrap size={[8, 8]}>
            {effectiveTemplate.biasActions.map((item) => (
              <Tag key={`${item.side}-${item.symbol}`} color={item.action === 'increase' ? 'green' : 'orange'}>
                {item.action === 'increase' ? '增配' : '减配'} {item.symbol} {item.delta > 0 ? '+' : ''}{(Number(item.delta || 0) * 100).toFixed(1)}pp
              </Tag>
            ))}
          </Space>
        </Card>
      ) : null}

      {effectiveTemplate?.dominantDrivers?.length ? (
        <Card title="主题结论" variant="borderless">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text>{effectiveTemplate.themeCore || '暂无主题核心腿'}</Text>
            <Text type="secondary">辅助腿：{effectiveTemplate.themeSupport || '无'}</Text>
            <Space wrap size={[6, 6]}>
              {effectiveTemplate.dominantDrivers.map((item) => (
                <Tag key={item.key} color="purple">
                  主导驱动 {item.label} {Number(item.value || 0).toFixed(2)}
                </Tag>
              ))}
            </Space>
          </Space>
        </Card>
      ) : null}

      {!researchContext?.template && topRecommendation ? (
        <Alert
          type={topRecommendationNeedsPriorityReview ? 'warning' : 'success'}
          showIcon
          message={`当前首选模板：${topRecommendation.name}${topRecommendationNeedsPriorityReview ? ` · ${getReviewPriorityTitleSuffix(topRecommendation?.refreshMeta)}` : ''}`}
          description={`${topRecommendation.driverHeadline}。${
            topRecommendation.recentComparisonLead
              ? `最近两版：${topRecommendation.recentComparisonLead}。`
              : ''
          }${
            topRecommendationNeedsPriorityReview
              ? getReviewPriorityContextLine(topRecommendation?.refreshMeta)
              : ''
          }${
            topRecommendation.rankingPenaltyReason
            || topRecommendationSelectionQualityLines[0]
            || topRecommendation.biasSummary
            || '该模板会作为默认起点，你也可以在右侧改成其他模板。'
          }`}
        />
      ) : null}
      </div>

      <div className="cross-market-layout">
        <div className="cross-market-main">
          <div className="cross-market-asset-grid">
            {renderAssetSection('多头篮子', longAssets, 'long')}
            {renderAssetSection('空头篮子', shortAssets, 'short')}
          </div>

          <Card variant="borderless" className="workspace-panel cross-market-preview-card">
            <div className="cross-market-preview-grid">
              <div className="cross-market-preview-copy">
                <Text strong className="cross-market-preview-card__title">
                  {selectedTemplate?.name || draftTemplateContext?.template_name || '当前实验还未绑定模板'}
                </Text>
                <Paragraph type="secondary" style={{ margin: '10px 0 0' }}>
                  {selectedTemplate?.narrative
                    || selectedTemplate?.description
                    || draftTemplateContext?.recommendation_reason
                    || topRecommendation?.narrative
                    || '先从侧栏模板快选开始，锁定主题、约束和时间窗口，再运行跨市场实验。'}
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
          </Card>
        </div>

        <aside className="cross-market-sidebar">
          <Card variant="borderless" className="workspace-panel cross-market-sidebar-card cross-market-sidebar-card--overview">
            <div className="app-page-section-kicker">控制总览</div>
            <Text strong className="cross-market-sidebar-card__title">右侧保持输入，左侧专注结果</Text>
            <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
              模板快选、参数和约束都固定在侧栏里，主画布只保留篮子和运行预览，减少宽屏下的视线往返。
            </Paragraph>
            <div className="cross-market-sidebar-card__grid">
              {sidebarOverviewItems.map((item) => (
                <div key={item.label} className="cross-market-sidebar-card__item">
                  <span className="cross-market-sidebar-card__item-label">{item.label}</span>
                  <span className="cross-market-sidebar-card__item-value">{item.value}</span>
                </div>
              ))}
            </div>
            <div className="cross-market-sidebar-card__note">
              {selectedTemplate
                ? `当前模板：${selectedTemplate.name}${selectedTemplate.theme ? ` · ${selectedTemplate.theme}` : ''}`
                : '当前未锁定模板，建议先从模板快选开始。'}
            </div>
          </Card>

          <Card title="模板快选" variant="borderless" className="workspace-panel cross-market-sidebar-card">
            <div className="cross-market-template-list">
              {displayRecommendedTemplates.slice(0, 3).map((template) => (
                <div
                  key={template.id}
                  className={`cross-market-template-card${selectedTemplate?.id === template.id ? ' cross-market-template-card--active' : ''}`}
                >
                  <div className="cross-market-template-card__header">
                    <div>
                      <div className="cross-market-template-card__title">{template.name}</div>
                      <Text type="secondary">{template.driverHeadline}</Text>
                    </div>
                    <Button size="small" type={selectedTemplate?.id === template.id ? 'default' : 'primary'} onClick={() => applyTemplate(template, { useBias: true })}>
                      {selectedTemplate?.id === template.id ? '已载入' : '载入'}
                    </Button>
                  </div>
                  <Space wrap size={[6, 6]} className="cross-market-template-card__tags">
                    <Tag color={template.recommendationTone}>{template.recommendationTier}</Tag>
                    <Tag color="cyan">score {Number(template.recommendationScore || 0).toFixed(2)}</Tag>
                    {template.executionPosture ? (
                      <Tag color="lime">{template.executionPosture}</Tag>
                    ) : null}
                    {template.refreshMeta?.selectionQualityRunState?.active ? (
                      <Tag color="gold">优先重看</Tag>
                    ) : null}
                    {template.refreshMeta?.reviewContextDriven && !template.refreshMeta?.selectionQualityRunState?.active ? (
                      <Tag color="geekblue">语境切换</Tag>
                    ) : null}
                  </Space>
                  {(template.themeCore || template.themeSupport) ? (
                    <Text type="secondary" className="cross-market-template-card__line">
                      核心腿：{template.themeCore || '暂无'} · 辅助腿：{template.themeSupport || '暂无'}
                    </Text>
                  ) : null}
                  {template.recentComparisonLead ? (
                    <Text type="secondary" className="cross-market-template-card__line">
                      最近两版：{template.recentComparisonLead}
                    </Text>
                  ) : null}
                  {(template.rankingPenaltyReason || getSelectionQualityExplanationLines(template.refreshMeta)[0]) ? (
                    <Text type="secondary" className="cross-market-template-card__line">
                      {template.rankingPenaltyReason || getSelectionQualityExplanationLines(template.refreshMeta)[0]}
                    </Text>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>

          <Card title="参数与模板" variant="borderless" className="workspace-panel cross-market-sidebar-card">
            <Space direction="vertical" style={{ width: '100%' }} size={14}>
              <Select
                placeholder="载入演示模板"
                loading={loadingTemplates}
                value={selectedTemplateId || undefined}
                options={templates.map((template) => ({
                  label: template.name,
                  value: template.id,
                }))}
                onChange={(value) => applyTemplate(value, { useBias: false })}
              />

              <Form layout="vertical">
                <Form.Item label="构造模式">
                  <Select
                    value={quality.construction_mode}
                    options={[
                      { value: 'equal_weight', label: '等权配置' },
                      { value: 'ols_hedge', label: '滚动 OLS 对冲' },
                    ]}
                    onChange={(value) => setQuality((prev) => ({ ...prev, construction_mode: value }))}
                  />
                </Form.Item>
                <Form.Item label="回看窗口">
                  <InputNumber
                    min={5}
                    value={parameters.lookback}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, lookback: value || DEFAULT_PARAMETERS.lookback }))
                    }
                  />
                </Form.Item>
                <Form.Item label="入场阈值">
                  <InputNumber
                    min={0.5}
                    step={0.1}
                    value={parameters.entry_threshold}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, entry_threshold: value || DEFAULT_PARAMETERS.entry_threshold }))
                    }
                  />
                </Form.Item>
                <Form.Item label="离场阈值">
                  <InputNumber
                    min={0.1}
                    step={0.1}
                    value={parameters.exit_threshold}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, exit_threshold: value || DEFAULT_PARAMETERS.exit_threshold }))
                    }
                  />
                </Form.Item>
                <Form.Item label="初始资金">
                  <InputNumber
                    min={1000}
                    step={1000}
                    value={meta.initial_capital}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, initial_capital: value || 100000 }))}
                  />
                </Form.Item>
                <Form.Item label="最少历史天数">
                  <InputNumber
                    min={10}
                    step={5}
                    value={quality.min_history_days}
                    style={{ width: '100%' }}
                    onChange={(value) => setQuality((prev) => ({ ...prev, min_history_days: value || 60 }))}
                  />
                </Form.Item>
                <Form.Item label="最小重叠比例">
                  <InputNumber
                    min={0.1}
                    max={1}
                    step={0.05}
                    value={quality.min_overlap_ratio}
                    style={{ width: '100%' }}
                    onChange={(value) => setQuality((prev) => ({ ...prev, min_overlap_ratio: value || 0.7 }))}
                  />
                </Form.Item>
                <Form.Item label="单资产上限 (%)">
                  <InputNumber
                    min={1}
                    max={100}
                    step={1}
                    value={constraints.max_single_weight}
                    style={{ width: '100%' }}
                    placeholder="可留空"
                    onChange={(value) => setConstraints((prev) => ({ ...prev, max_single_weight: value ?? null }))}
                  />
                </Form.Item>
                <Form.Item label="单资产下限 (%)">
                  <InputNumber
                    min={1}
                    max={100}
                    step={1}
                    value={constraints.min_single_weight}
                    style={{ width: '100%' }}
                    placeholder="可留空"
                    onChange={(value) => setConstraints((prev) => ({ ...prev, min_single_weight: value ?? null }))}
                  />
                </Form.Item>
                <Form.Item label="手续费 (%)">
                  <InputNumber
                    min={0}
                    step={0.01}
                    value={meta.commission}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, commission: value ?? 0.1 }))}
                  />
                </Form.Item>
                <Form.Item label="滑点 (%)">
                  <InputNumber
                    min={0}
                    step={0.01}
                    value={meta.slippage}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, slippage: value ?? 0.1 }))}
                  />
                </Form.Item>
                <Form.Item label="开始日期">
                  <Input
                    value={meta.start_date}
                    placeholder="YYYY-MM-DD"
                    onChange={(event) => setMeta((prev) => ({ ...prev, start_date: event.target.value }))}
                  />
                </Form.Item>
                <Form.Item label="结束日期">
                  <Input
                    value={meta.end_date}
                    placeholder="YYYY-MM-DD"
                    onChange={(event) => setMeta((prev) => ({ ...prev, end_date: event.target.value }))}
                  />
                </Form.Item>
              </Form>

              {selectedTemplateNeedsPriorityReview ? (
                <Alert
                  type="warning"
                  showIcon
                  message={`当前模板：${selectedTemplate?.name || ''} · ${getReviewPriorityTitleSuffix(selectedTemplate?.refreshMeta) || '建议优先重看'}`}
                  description={`这次运行更适合作为复核型回测，而不是普通默认模板回测。${
                    selectedTemplate?.recentComparisonLead
                      ? `最近两版：${selectedTemplate.recentComparisonLead} · `
                      : ''
                  }${
                    selectedTemplate?.refreshMeta?.selectionQualityRunState?.active
                      ? `当前保存结果已按 ${selectedTemplate?.refreshMeta?.selectionQualityRunState?.label || 'degraded'} 强度运行`
                      : selectedTemplate?.refreshMeta?.reviewContextDriven
                        ? '最近两版已发生复核语境切换'
                        : selectedTemplate?.refreshMeta?.inputReliabilityDriven
                          ? '当前整体输入可靠度已经发生明显变化'
                          : '当前主题已进入优先重看语境'
                  }${
                    selectedTemplate?.refreshMeta?.selectionQualityRunState?.baseScore || selectedTemplate?.refreshMeta?.selectionQualityRunState?.effectiveScore
                      ? ` · ${Number(selectedTemplate?.refreshMeta?.selectionQualityRunState?.baseScore || 0).toFixed(2)}→${Number(selectedTemplate?.refreshMeta?.selectionQualityRunState?.effectiveScore || 0).toFixed(2)}`
                      : ''
                  }${
                    selectedTemplate?.refreshMeta?.selectionQualityRunState?.reason
                      ? ` · ${selectedTemplate.refreshMeta.selectionQualityRunState.reason}`
                      : selectedTemplate?.refreshMeta?.reviewContextShift?.actionHint
                        ? ` · ${selectedTemplate.refreshMeta.reviewContextShift.actionHint}`
                        : selectedTemplate?.refreshMeta?.inputReliabilityShift?.actionHint
                          ? ` · ${selectedTemplate.refreshMeta.inputReliabilityShift.actionHint}`
                          : selectedTemplate?.refreshMeta?.reviewContextShift?.lead
                            ? ` · ${selectedTemplate.refreshMeta.reviewContextShift.lead}`
                            : selectedTemplate?.refreshMeta?.inputReliabilityShift?.currentLead
                              ? ` · ${selectedTemplate.refreshMeta.inputReliabilityShift.currentLead}`
                              : ''
                  }`}
                />
              ) : null}

              <div className="cross-market-parameter-actions">
                <Button icon={<ReloadOutlined />} onClick={() => setResults(null)}>
                  清空结果
                </Button>
                <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun}>
                  运行回测
                </Button>
              </div>
            </Space>
          </Card>
        </aside>
      </div>

      {running && !results ? (
        <Card variant="borderless" className="workspace-panel">
          <div style={{ minHeight: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin size="large" />
          </div>
        </Card>
      ) : null}

      {results ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Alert
            type={results.total_return >= 0 ? 'success' : 'warning'}
            showIcon
            message={`跨市场结果已生成${
              results.allocation_overlay?.selection_quality?.label && results.allocation_overlay.selection_quality.label !== 'original'
                ? ' · 复核型结果'
                : ''
            }`}
            description={`样本区间 ${results.price_matrix_summary.start_date} 至 ${results.price_matrix_summary.end_date}，共 ${results.price_matrix_summary.row_count} 个对齐交易日。${
              selectedTemplate?.recentComparisonLead
                ? ` 最近两版：${selectedTemplate.recentComparisonLead}`
                : ''
            }${
              results.allocation_overlay?.selection_quality?.label && results.allocation_overlay.selection_quality.label !== 'original'
                ? ` 当前结果按 ${results.allocation_overlay.selection_quality.label} 强度运行，应作为复核型结果理解。`
                : ''
            }${
              results.allocation_overlay?.input_reliability?.action_hint
                ? ` ${results.allocation_overlay.input_reliability.action_hint}`
                : ''
            }`}
          />

          {results.allocation_overlay?.selection_quality ? (
            <Alert
              type={getSelectionQualityMeta(results.allocation_overlay.selection_quality.label).type}
              showIcon
              message={getSelectionQualityMeta(results.allocation_overlay.selection_quality.label).title}
              description={`推荐强度 ${Number(results.allocation_overlay.selection_quality.base_recommendation_score || 0).toFixed(2)} → ${Number(results.allocation_overlay.selection_quality.effective_recommendation_score || 0).toFixed(2)}${
                results.allocation_overlay.selection_quality.base_recommendation_tier
                  ? ` · ${results.allocation_overlay.selection_quality.base_recommendation_tier} → ${results.allocation_overlay.selection_quality.effective_recommendation_tier || '-'}`
                  : ''
              }${
                results.allocation_overlay.selection_quality.ranking_penalty
                  ? ` · 惩罚 ${Number(results.allocation_overlay.selection_quality.ranking_penalty || 0).toFixed(2)}`
                  : ''
              }${
                results.allocation_overlay.selection_quality.reason
                  ? ` · ${results.allocation_overlay.selection_quality.reason}`
                  : ''
              }${
                results.allocation_overlay.input_reliability?.posture
                  ? ` · ${results.allocation_overlay.input_reliability.posture}`
                  : ''
              }${
                results.allocation_overlay.input_reliability?.action_hint
                  ? ` · ${results.allocation_overlay.input_reliability.action_hint}`
                  : ''
              }`}
            />
          ) : null}

          {(results.data_alignment?.tradable_day_ratio || 0) < 0.8 ? (
            <Alert
              type="warning"
              showIcon
              message="数据对齐覆盖率偏低"
              description={`当前可交易日覆盖率为 ${(results.data_alignment?.tradable_day_ratio || 0) * 100}% ，建议检查资产组合或放宽时间窗口。`}
            />
          ) : null}

          <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
              <Card variant="borderless" className="workspace-panel">
                <Statistic
                  title="总收益率"
                  value={results.total_return * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: getValueColor(results.total_return) }}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card variant="borderless" className="workspace-panel">
                <Statistic
                  title="最终净值"
                  value={results.final_value}
                  precision={2}
                  formatter={(value) => formatCurrency(Number(value || 0))}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card variant="borderless" className="workspace-panel">
                <Statistic
                  title="夏普比率"
                  value={results.sharpe_ratio}
                  precision={2}
                />
              </Card>
            </Col>
          </Row>

          <CrossMarketDiagnosticsSection
            results={results}
            meta={meta}
            quality={quality}
            ASSET_CLASS_LABELS={ASSET_CLASS_LABELS}
            concentrationMeta={concentrationMeta}
            liquidityMeta={liquidityMeta}
            marginMeta={marginMeta}
            betaMeta={betaMeta}
            cointegrationMeta={cointegrationMeta}
            calendarMeta={calendarMeta}
            stressMeta={stressMeta}
            formatCurrency={formatCurrency}
            formatPercentage={formatPercentage}
            formatVenue={formatVenue}
            formatConstructionMode={formatConstructionMode}
          />

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="资产宇宙摘要" variant="borderless" className="workspace-panel">
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="资产数量"
                      value={results.asset_universe?.asset_count || 0}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="多头数量"
                      value={results.asset_universe?.by_side?.long || 0}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="空头数量"
                      value={results.asset_universe?.by_side?.short || 0}
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {Object.entries(results.asset_universe?.by_asset_class || {}).map(([key, value]) => (
                    <Tag key={key}>{ASSET_CLASS_LABELS[key] || key} · {value}</Tag>
                  ))}
                  {Object.entries(results.asset_universe?.execution_channels || {}).map(([key, value]) => (
                    <Tag color="cyan" key={key}>{formatExecutionChannel(key)} · {value}</Tag>
                  ))}
                  {Object.entries(results.asset_universe?.providers || {}).map(([key, value]) => (
                    <Tag color="blue" key={key}>{key} · {value}</Tag>
                  ))}
                  {(results.asset_universe?.currencies || []).map((currency) => (
                    <Tag color="blue" key={currency}>{currency}</Tag>
                  ))}
                </div>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="对冲组合画像" variant="borderless" className="workspace-panel">
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="Gross Exposure"
                      value={(results.hedge_portfolio?.gross_exposure || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Net Exposure"
                      value={(results.hedge_portfolio?.net_exposure || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="平均对冲比"
                      value={results.hedge_portfolio?.hedge_ratio?.average || 0}
                      precision={2}
                    />
                  </Col>
                </Row>
                <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
                  <Col span={8}>
                    <Statistic
                      title="Beta"
                      value={results.hedge_portfolio?.beta_neutrality?.beta || 0}
                      precision={2}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Beta Gap"
                      value={(results.hedge_portfolio?.beta_neutrality?.beta_gap || 0) * 100}
                      precision={2}
                      suffix="pp"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Rolling Beta"
                      value={results.hedge_portfolio?.beta_neutrality?.rolling_beta_last || 0}
                      precision={2}
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Text type="secondary">
                    多头权重 {formatPercentage(results.hedge_portfolio?.long_weight || 0)} ·
                    空头权重 {formatPercentage(results.hedge_portfolio?.short_weight || 0)} ·
                    有效空头 {formatPercentage(results.hedge_portfolio?.effective_short_weight || 0)}
                  </Text>
                  <Text type="secondary">
                    Hedge Ratio 区间 {Number(results.hedge_portfolio?.hedge_ratio?.min || 0).toFixed(2)} ~ {Number(results.hedge_portfolio?.hedge_ratio?.max || 0).toFixed(2)}
                  </Text>
                  {results.hedge_portfolio?.beta_neutrality?.reason ? (
                    <Text type="secondary">
                      {results.hedge_portfolio.beta_neutrality.reason}
                    </Text>
                  ) : null}
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="执行批次计划" variant="borderless">
                <Table
                  size="small"
                  rowKey="route_key"
                  pagination={false}
                  dataSource={results.execution_plan?.batches || []}
                  locale={{ emptyText: '暂无执行批次' }}
                  columns={executionBatchColumns}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="逐资产执行路由" variant="borderless">
                <Table
                  size="small"
                  rowKey={(record) => `${record.symbol}-${record.side}`}
                  pagination={{ pageSize: 6, showSizeChanger: false }}
                  dataSource={results.execution_plan?.routes || []}
                  locale={{ emptyText: '暂无执行路由' }}
                  columns={executionRouteColumns}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="Provider 资金分布" variant="borderless">
                <Table
                  size="small"
                  rowKey="key"
                  pagination={false}
                  dataSource={results.execution_plan?.provider_allocation || []}
                  locale={{ emptyText: '暂无 Provider 分布' }}
                  columns={providerAllocationColumns}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="Venue 资金分布" variant="borderless">
                <Table
                  size="small"
                  rowKey="key"
                  pagination={false}
                  dataSource={results.execution_plan?.venue_allocation || []}
                  locale={{ emptyText: '暂无 Venue 分布' }}
                  columns={venueAllocationColumns}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="流动性概况" variant="borderless">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space wrap size={[8, 8]}>
                    <Tag color={liquidityMeta.color}>{liquidityMeta.label}</Tag>
                    <Tag color="cyan">
                      Max ADV {(Number(results.execution_plan?.liquidity_summary?.max_adv_usage || 0) * 100).toFixed(2)}%
                    </Tag>
                    <Tag color="orange">
                      关注路由 {results.execution_plan?.liquidity_summary?.watch_route_count || 0}
                    </Tag>
                    <Tag color="red">
                      紧张路由 {results.execution_plan?.liquidity_summary?.stretched_route_count || 0}
                    </Tag>
                  </Space>
                  {results.execution_plan?.liquidity_summary?.reason ? (
                    <Text type="secondary">{results.execution_plan.liquidity_summary.reason}</Text>
                  ) : null}
                  {results.execution_plan?.liquidity_summary?.largest_adv_route ? (
                    <Text type="secondary">
                      最紧路由 {results.execution_plan.liquidity_summary.largest_adv_route.symbol}
                      {' · '}
                      ADV {(Number(results.execution_plan.liquidity_summary.largest_adv_route.adv_usage || 0) * 100).toFixed(2)}%
                      {' · '}
                      日均成交额 {formatCurrency(Number(results.execution_plan.liquidity_summary.largest_adv_route.avg_daily_notional || 0))}
                    </Text>
                  ) : null}
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="多市场日历概况" variant="borderless">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space wrap size={[8, 8]}>
                    <Tag color={calendarMeta.color}>{calendarMeta.label}</Tag>
                    <Tag color="cyan">
                      Max mismatch {(Number(results.data_alignment?.calendar_diagnostics?.max_mismatch_ratio || 0) * 100).toFixed(2)}%
                    </Tag>
                  </Space>
                  {results.data_alignment?.calendar_diagnostics?.reason ? (
                    <Text type="secondary">{results.data_alignment.calendar_diagnostics.reason}</Text>
                  ) : null}
                  <Table
                    size="small"
                    rowKey="venue"
                    pagination={false}
                    dataSource={results.data_alignment?.calendar_diagnostics?.rows || []}
                    locale={{ emptyText: '暂无日历错位信息' }}
                    columns={[
                      {
                        title: 'Venue',
                        dataIndex: 'venue',
                        key: 'venue',
                        render: (value) => formatVenue(value),
                      },
                      { title: '活跃日', dataIndex: 'active_dates', key: 'active_dates' },
                      { title: '共享日', dataIndex: 'shared_dates', key: 'shared_dates' },
                      {
                        title: '错位率',
                        dataIndex: 'mismatch_ratio',
                        key: 'mismatch_ratio',
                        render: (value) => formatPercentage(Number(value || 0)),
                      },
                    ]}
                  />
                </Space>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="执行压力测试" variant="borderless">
                <Table
                  size="small"
                  rowKey="label"
                  pagination={false}
                  dataSource={results.execution_plan?.execution_stress?.scenarios || []}
                  locale={{ emptyText: '暂无压力测试结果' }}
                  columns={stressScenarioColumns}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="保证金与杠杆画像" variant="borderless">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space wrap size={[8, 8]}>
                    <Tag color={marginMeta.color}>{marginMeta.label}</Tag>
                    <Tag color="volcano">
                      保证金 {(Number(results.execution_plan?.margin_summary?.utilization || 0) * 100).toFixed(2)}%
                    </Tag>
                    <Tag color="purple">
                      Gross {Number(results.execution_plan?.margin_summary?.gross_leverage || 0).toFixed(2)}x
                    </Tag>
                    <Tag color="blue">
                      Short {formatCurrency(Number(results.execution_plan?.margin_summary?.short_notional || 0))}
                    </Tag>
                    <Tag color="cyan">
                      Futures {formatCurrency(Number(results.execution_plan?.margin_summary?.futures_notional || 0))}
                    </Tag>
                  </Space>
                  {results.execution_plan?.margin_summary?.reason ? (
                    <Text type="secondary">{results.execution_plan.margin_summary.reason}</Text>
                  ) : null}
                  {results.execution_plan?.margin_summary?.max_margin_route ? (
                    <Text type="secondary">
                      最大保证金路由 {results.execution_plan.margin_summary.max_margin_route.symbol}
                      {' · '}
                      {formatCurrency(Number(results.execution_plan.margin_summary.max_margin_route.margin_requirement || 0))}
                      {' · '}
                      保证金率 {(Number(results.execution_plan.margin_summary.max_margin_route.margin_rate || 0) * 100).toFixed(2)}%
                    </Text>
                  ) : null}
                </Space>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card title="组合净值曲线" variant="borderless" className="workspace-panel workspace-chart-card">
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
                    <LineChart data={results.portfolio_curve}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" minTickGap={32} />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="total" name="组合净值" stroke="#1677ff" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card title="长短腿累计收益" variant="borderless" className="workspace-panel workspace-chart-card">
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
                    <BarChart
                      data={[
                        {
                          leg: '多头',
                          value: (results.leg_performance.long.cumulative_return || 0) * 100,
                        },
                        {
                          leg: '空头',
                          value: (results.leg_performance.short.cumulative_return || 0) * 100,
                        },
                        {
                          leg: '价差',
                          value: (results.leg_performance.spread.cumulative_return || 0) * 100,
                        },
                      ]}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="leg" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" fill="#52c41a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={results.hedge_ratio_series ? 14 : 24}>
              <Card title="价差与 Z 分数" variant="borderless" className="workspace-panel workspace-chart-card">
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
                    <LineChart data={results.spread_series}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" minTickGap={32} />
                      <YAxis yAxisId="left" />
                      <YAxis yAxisId="right" orientation="right" />
                      <Tooltip />
                      <Legend />
                      <Line yAxisId="left" type="monotone" dataKey="spread" stroke="#13c2c2" dot={false} />
                      <Line yAxisId="right" type="monotone" dataKey="z_score" stroke="#cf1322" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
            {results.hedge_ratio_series ? (
              <Col xs={24} xl={10}>
                <Card title="对冲比率" variant="borderless">
                  <div style={{ width: '100%', height: 320 }}>
                    <ResponsiveContainer width="100%" height={280} minWidth={320} minHeight={280}>
                      <LineChart data={results.hedge_ratio_series}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" minTickGap={32} />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="hedge_ratio" stroke="#722ed1" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              </Col>
            ) : null}
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="交易记录" variant="borderless">
                <Table
                  size="small"
                  rowKey={(record) => [
                    record.date,
                    record.type || record.action,
                    record.symbol,
                    record.price,
                    record.quantity ?? record.value,
                  ].filter(Boolean).join('-')}
                  dataSource={results.trades || []}
                  locale={{ emptyText: '暂无交易记录' }}
                  pagination={{ pageSize: 6, showSizeChanger: false }}
                  columns={[
                    { title: '日期', dataIndex: 'date', key: 'date' },
                    {
                      title: '动作',
                      dataIndex: 'type',
                      key: 'type',
                      render: (value) => (
                        <Tag color={String(value).includes('OPEN') ? 'blue' : 'orange'}>
                          {formatTradeAction(value)}
                        </Tag>
                      ),
                    },
                    {
                      title: '价差',
                      dataIndex: 'spread',
                      key: 'spread',
                      render: (value) => Number(value).toFixed(4),
                    },
                    {
                      title: 'Z',
                      dataIndex: 'z_score',
                      key: 'z_score',
                      render: (value) => Number(value).toFixed(3),
                    },
                    {
                      title: '盈亏',
                      dataIndex: 'pnl',
                      key: 'pnl',
                      render: (value) => <span style={{ color: getValueColor(value) }}>{formatCurrency(Number(value || 0))}</span>,
                    },
                    {
                      title: '持有天数',
                      dataIndex: 'holding_period_days',
                      key: 'holding_period_days',
                      render: (value) => (value === null || value === undefined ? '-' : value),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="资产相关性矩阵" variant="borderless">
                <Table
                  size="small"
                  scroll={{ x: true }}
                  locale={{ emptyText: '暂无相关性数据' }}
                  pagination={false}
                  rowKey="symbol"
                  dataSource={results.correlation_matrix.rows || []}
                  columns={correlationColumns}
                />
              </Card>
            </Col>
          </Row>

          <Card title="资产贡献度" variant="borderless">
            <Table
              size="small"
              rowKey="symbol"
              pagination={false}
              locale={{ emptyText: '暂无贡献度数据' }}
              dataSource={assetContributionRows}
              columns={contributionColumns}
            />
          </Card>

          <CrossMarketBasketSummaryCard
            results={results}
            ASSET_CLASS_LABELS={ASSET_CLASS_LABELS}
            formatPercentage={formatPercentage}
          />

          {results.allocation_overlay ? (
            <Card title="权重偏置对照" variant="borderless">
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Space wrap size={[8, 8]}>
                  <Tag color={results.allocation_overlay.allocation_mode === 'macro_bias' ? 'green' : 'default'}>
                    {results.allocation_overlay.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
                  </Tag>
                  {results.allocation_overlay.theme ? <Tag color="blue">{results.allocation_overlay.theme}</Tag> : null}
                  {results.allocation_overlay.bias_strength ? <Tag color="green">bias {Number(results.allocation_overlay.bias_strength).toFixed(1)}pp</Tag> : null}
                  {results.allocation_overlay.compression_summary?.label && results.allocation_overlay.compression_summary.label !== 'full' ? (
                    <Tag color={results.allocation_overlay.compression_summary.label === 'compressed' ? 'orange' : 'gold'}>
                      压缩 {results.allocation_overlay.compression_summary.label}
                    </Tag>
                  ) : null}
                </Space>
                {results.allocation_overlay.bias_summary ? (
                  <Text>{results.allocation_overlay.bias_summary}</Text>
                ) : null}
                {results.allocation_overlay.compression_summary ? (
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Text type="secondary">
                      原始偏置 {Number(results.allocation_overlay.compression_summary.raw_bias_strength || 0).toFixed(1)}pp
                      {' · '}
                      生效偏置 {Number(results.allocation_overlay.compression_summary.effective_bias_strength || 0).toFixed(1)}pp
                      {' · '}
                      收缩 {Number(results.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp
                      {' · '}
                      比例 {(Number(results.allocation_overlay.compression_summary.compression_ratio || 0) * 100).toFixed(1)}%
                    </Text>
                    {results.allocation_overlay.compression_summary.reason ? (
                      <Text type="secondary">
                        {results.allocation_overlay.compression_summary.reason}
                      </Text>
                    ) : null}
                    <Text type="secondary">
                      受影响资产 {results.allocation_overlay.compressed_asset_count || 0} 个
                      {results.allocation_overlay.compressed_assets?.length
                        ? ` · ${results.allocation_overlay.compressed_assets.join('、')}`
                        : ''}
                    </Text>
                    {results.allocation_overlay.selection_quality?.reason ? (
                      <Text type="secondary">
                        推荐降级 {Number(results.allocation_overlay.selection_quality.base_recommendation_score || 0).toFixed(2)}
                        →{Number(results.allocation_overlay.selection_quality.effective_recommendation_score || 0).toFixed(2)}
                        {results.allocation_overlay.selection_quality.effective_recommendation_tier
                          ? ` · ${results.allocation_overlay.selection_quality.effective_recommendation_tier}`
                          : ''}
                        {' · '}
                        {results.allocation_overlay.selection_quality.reason}
                      </Text>
                    ) : null}
                  </Space>
                ) : null}
                {results.allocation_overlay.bias_highlights?.length ? (
                  <Space wrap size={[6, 6]}>
                    {results.allocation_overlay.bias_highlights.map((item) => (
                      <Tag key={item} color="green">{item}</Tag>
                    ))}
                  </Space>
                ) : null}
                {results.allocation_overlay.bias_actions?.length ? (
                  <Space wrap size={[6, 6]}>
                    {results.allocation_overlay.bias_actions.map((item) => (
                      <Tag key={`${item.side}-${item.symbol}`} color={item.action === 'increase' ? 'green' : 'orange'}>
                        {item.action === 'increase' ? '增配' : '减配'} {item.symbol}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
                {results.allocation_overlay.driver_summary?.length ? (
                  <Space wrap size={[6, 6]}>
                    {results.allocation_overlay.driver_summary.map((item) => (
                      <Tag key={item.key} color="purple">
                        {item.label} {Number(item.value || 0).toFixed(2)}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
                {results.allocation_overlay.dominant_drivers?.length ? (
                  <Space wrap size={[6, 6]}>
                    {results.allocation_overlay.dominant_drivers.map((item) => (
                      <Tag key={`dominant-${item.key}`} color="magenta">
                        主导 {item.label}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
                {results.allocation_overlay.execution_posture ? (
                  <Text type="secondary">执行姿态：{results.allocation_overlay.execution_posture}</Text>
                ) : null}
                {results.allocation_overlay.theme_core ? (
                  <Text type="secondary">核心腿：{results.allocation_overlay.theme_core}</Text>
                ) : null}
                {extractCoreLegPressure(results.allocation_overlay).affected ? (
                  <Text type="secondary">核心腿受压：{extractCoreLegPressure(results.allocation_overlay).summary}</Text>
                ) : null}
                {results.allocation_overlay.theme_support ? (
                  <Text type="secondary">辅助腿：{results.allocation_overlay.theme_support}</Text>
                ) : null}
                {results.allocation_overlay.policy_execution?.active ? (
                  <Text type="secondary">
                    政策执行：{results.allocation_overlay.policy_execution.label}
                    {results.allocation_overlay.policy_execution.top_department
                      ? ` · ${results.allocation_overlay.policy_execution.top_department}`
                      : ''}
                    {results.allocation_overlay.policy_execution.risk_budget_scale !== undefined
                      ? ` · 风险预算 ${Number(results.allocation_overlay.policy_execution.risk_budget_scale || 1).toFixed(2)}x`
                      : ''}
                    {results.allocation_overlay.policy_execution.reason
                      ? ` · ${results.allocation_overlay.policy_execution.reason}`
                      : ''}
                  </Text>
                ) : null}
                {results.allocation_overlay.source_mode_summary?.active ? (
                  <Text type="secondary">
                    来源治理：{results.allocation_overlay.source_mode_summary.label}
                    {results.allocation_overlay.source_mode_summary.dominant
                      ? ` · ${results.allocation_overlay.source_mode_summary.dominant}`
                      : ''}
                    {results.allocation_overlay.source_mode_summary.risk_budget_scale !== undefined
                      ? ` · 风险预算 ${Number(results.allocation_overlay.source_mode_summary.risk_budget_scale || 1).toFixed(2)}x`
                      : ''}
                    {results.allocation_overlay.source_mode_summary.reason
                      ? ` · ${results.allocation_overlay.source_mode_summary.reason}`
                      : ''}
                  </Text>
                ) : null}
                <Text type="secondary">
                  偏移资产 {results.allocation_overlay.shifted_asset_count || 0} 个 · 最大偏移 {(Number(results.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
                </Text>
                {results.allocation_overlay.side_bias_summary ? (
                  <Text type="secondary">
                    多头 {formatPercentage(Number(results.allocation_overlay.side_bias_summary.long_raw_weight || 0))}→{formatPercentage(Number(results.allocation_overlay.side_bias_summary.long_effective_weight || 0))}
                    {' · '}
                    空头 {formatPercentage(Number(results.allocation_overlay.side_bias_summary.short_raw_weight || 0))}→{formatPercentage(Number(results.allocation_overlay.side_bias_summary.short_effective_weight || 0))}
                  </Text>
                ) : null}
                <Table
                  size="small"
                  rowKey={(record) => `${record.symbol}-${record.side}`}
                  pagination={false}
                  locale={{ emptyText: '暂无权重偏置对照' }}
                  dataSource={results.allocation_overlay.rows || []}
                  columns={allocationOverlayColumns}
                />
                {results.allocation_overlay.signal_attribution?.length ? (
                  <Table
                    size="small"
                    rowKey={(record) => `${record.side}-${record.symbol}`}
                    pagination={false}
                    locale={{ emptyText: '暂无归因说明' }}
                    dataSource={results.allocation_overlay.signal_attribution}
                    columns={[
                      { title: '资产', dataIndex: 'symbol', key: 'symbol' },
                      {
                        title: '方向',
                        dataIndex: 'side',
                        key: 'side',
                        render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
                      },
                      {
                        title: '权重乘数',
                        dataIndex: 'multiplier',
                        key: 'multiplier',
                        render: (value) => Number(value || 0).toFixed(2),
                      },
                      {
                        title: '归因',
                        dataIndex: 'reasons',
                        key: 'reasons',
                        render: (value) => (value || []).join('；') || '无显著偏置',
                      },
                      {
                        title: '分解',
                        dataIndex: 'breakdown',
                        key: 'breakdown',
                        render: (value) => (value || []).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('；') || '无',
                      },
                    ]}
                    style={{ marginTop: 12 }}
                  />
                ) : null}
              </Space>
            </Card>
	          ) : null}
	          {results.constraint_overlay?.applied ? (
	            <Card title="组合约束落地" variant="borderless">
	              <Space direction="vertical" size={10} style={{ width: '100%' }}>
	                <Space wrap size={[8, 8]}>
	                  {results.constraint_overlay.constraints?.max_single_weight ? (
	                    <Tag color="blue">
	                      单资产上限 {(Number(results.constraint_overlay.constraints.max_single_weight || 0) * 100).toFixed(1)}%
	                    </Tag>
	                  ) : null}
	                  {results.constraint_overlay.constraints?.min_single_weight ? (
	                    <Tag color="purple">
	                      单资产下限 {(Number(results.constraint_overlay.constraints.min_single_weight || 0) * 100).toFixed(1)}%
	                    </Tag>
	                  ) : null}
	                  <Tag color={results.constraint_overlay.binding_count ? 'orange' : 'green'}>
	                    触发约束 {results.constraint_overlay.binding_count || 0} 个
	                  </Tag>
	                </Space>
	                <Text type="secondary">
	                  最大约束偏移 {(Number(results.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
	                </Text>
	                {results.constraint_overlay.binding_assets?.length ? (
	                  <Space wrap size={[6, 6]}>
	                    {results.constraint_overlay.binding_assets.map((symbol) => (
	                      <Tag key={`binding-${symbol}`} color="orange">{symbol}</Tag>
	                    ))}
	                  </Space>
	                ) : null}
	                <Table
	                  size="small"
	                  rowKey={(record) => `${record.symbol}-${record.side}`}
	                  pagination={false}
	                  locale={{ emptyText: '暂无约束调整' }}
	                  dataSource={results.constraint_overlay.rows || []}
	                  columns={[
	                    { title: '资产', dataIndex: 'symbol', key: 'symbol' },
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
	                      title: '约束后',
	                      dataIndex: 'constrained_weight',
	                      key: 'constrained_weight',
	                      render: (value) => formatPercentage(Number(value || 0)),
	                    },
	                    {
	                      title: '变化',
	                      dataIndex: 'delta_weight',
	                      key: 'delta_weight',
	                      render: (value) => (
	                        <span style={{ color: getValueColor(Number(value || 0)) }}>
	                          {Number(value || 0) >= 0 ? '+' : ''}{formatPercentage(Number(value || 0))}
	                        </span>
	                      ),
	                    },
	                    {
	                      title: '触发',
	                      dataIndex: 'binding',
	                      key: 'binding',
	                      render: (value) => (value ? <Tag color={value === 'max' ? 'red' : 'purple'}>{value}</Tag> : '-'),
	                    },
	                  ]}
	                />
	              </Space>
	            </Card>
	          ) : null}
	        </div>
	      ) : null}
    </div>
  );
}

export default CrossMarketBacktestPanel;
