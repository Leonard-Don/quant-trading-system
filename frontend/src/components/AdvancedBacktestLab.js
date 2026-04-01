import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'antd';
import { DownloadOutlined, ExperimentOutlined, PartitionOutlined, RiseOutlined } from '@ant-design/icons';
import dayjs from '../utils/dayjs';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { compareStrategies, runBatchBacktest, runMarketRegimeBacktest, runPortfolioStrategyBacktest, runWalkForwardBacktest, saveAdvancedHistoryRecord } from '../services/api';
import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../constants/strategies';
import { formatPercentage, formatCurrency, getValueColor } from '../utils/formatting';
import { useSafeMessageApi } from '../utils/messageApi';
import {
  consumeAdvancedExperimentIntent,
  loadBacktestWorkspaceDraft,
  saveBacktestWorkspaceDraft,
} from '../utils/backtestWorkspace';
import {
  buildBatchDraftState,
  buildBatchInsight,
  buildMarketRegimeInsight,
  buildOverfittingWarnings,
  buildPortfolioExposureChartData,
  buildPortfolioExposureSummary,
  buildPortfolioPositionSnapshot,
  buildResearchConclusion,
  buildRobustnessScore,
  buildWalkForwardInsight,
} from '../utils/advancedBacktestLab';
import {
  ADVANCED_TEMPLATE_CATEGORY_LABELS,
  buildMainBacktestDraftFromTemplate,
  buildAdvancedExperimentTemplatePreview,
  buildAdvancedExperimentSnapshot,
  buildAdvancedExperimentTemplatePayload,
  buildExperimentComparison,
  deleteAdvancedExperimentTemplate,
  inferAdvancedExperimentTemplateCategory,
  loadAdvancedExperimentSnapshots,
  loadAdvancedExperimentTemplates,
  saveAdvancedExperimentSnapshot,
  saveAdvancedExperimentTemplate,
  suggestAdvancedExperimentTemplateName,
  toggleAdvancedExperimentTemplatePinned,
} from '../utils/advancedExperimentTemplates';
import {
  buildBenchmarkSummary,
  buildCostSensitivityTasks,
  buildMultiSymbolTasks,
  buildParameterOptimizationTasks,
  buildRobustnessTasks,
  buildWalkForwardParameterCandidates,
  parseSymbolsInput,
} from '../utils/backtestResearch';
import {
  exportToCSV,
  exportToJSON,
  formatBatchExperimentForExport,
  formatWalkForwardForExport,
} from '../utils/export';

const { RangePicker } = DatePicker;
const DATE_FORMAT = 'YYYY-MM-DD';

const DEFAULT_CAPITAL = 10000;
const DEFAULT_COMMISSION = 0.1;
const DEFAULT_SLIPPAGE = 0.1;

const buildDefaultParams = (strategy) => Object.fromEntries(
  Object.entries(strategy?.parameters || {}).map(([key, config]) => [key, config.default])
);

const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';
const CHART_NEUTRAL = '#0ea5e9';

const getMetricValue = (record, key) => Number(record?.metrics?.[key] ?? record?.[key] ?? 0);
const formatCompactNumber = (value) => Number(value || 0).toFixed(2);

function AdvancedBacktestLab({ strategies, onImportTemplateToMainBacktest }) {
  const message = useSafeMessageApi();
  const strategyDefinitions = useMemo(
    () => Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy])),
    [strategies]
  );

  const [batchLoading, setBatchLoading] = useState(false);
  const [walkLoading, setWalkLoading] = useState(false);
  const [batchResult, setBatchResult] = useState(null);
  const [walkResult, setWalkResult] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [marketRegimeLoading, setMarketRegimeLoading] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState(null);
  const [benchmarkContext, setBenchmarkContext] = useState(null);
  const [portfolioStrategyResult, setPortfolioStrategyResult] = useState(null);
  const [marketRegimeResult, setMarketRegimeResult] = useState(null);
  const [focusedBatchTaskId, setFocusedBatchTaskId] = useState('');
  const [focusedWalkWindowKey, setFocusedWalkWindowKey] = useState('');
  const [batchConfigs, setBatchConfigs] = useState({});
  const [walkParams, setWalkParams] = useState({});
  const [researchSymbolsInput, setResearchSymbolsInput] = useState('AAPL,MSFT,NVDA');
  const [optimizationDensity, setOptimizationDensity] = useState(3);
  const [portfolioObjective, setPortfolioObjective] = useState('equal_weight');
  const [templateName, setTemplateName] = useState('');
  const [templateNote, setTemplateNote] = useState('');
  const [templateCategoryFilter, setTemplateCategoryFilter] = useState('all');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [savedTemplates, setSavedTemplates] = useState([]);
  const [savedSnapshots, setSavedSnapshots] = useState([]);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('');
  const [batchExperimentMeta, setBatchExperimentMeta] = useState({
    title: '批量回测结果',
    description: '同一实验上下文下的多任务回测结果会集中展示在这里。',
  });
  const [batchForm] = Form.useForm();
  const [walkForm] = Form.useForm();
  const watchedBatchStrategies = Form.useWatch('strategies', batchForm);
  const selectedBatchStrategies = useMemo(() => watchedBatchStrategies || [], [watchedBatchStrategies]);
  const selectedWalkStrategy = Form.useWatch('strategy', walkForm);

  useEffect(() => {
    if (!selectedBatchStrategies.length) {
      return;
    }

    setBatchConfigs((previous) => {
      const next = {};
      selectedBatchStrategies.forEach((strategyName) => {
        next[strategyName] = {
          ...buildDefaultParams(strategyDefinitions[strategyName]),
          ...(previous[strategyName] || {}),
        };
      });
      return next;
    });
  }, [selectedBatchStrategies, strategyDefinitions]);

  useEffect(() => {
    if (!selectedWalkStrategy) {
      return;
    }

    setWalkParams((previous) => ({
      ...buildDefaultParams(strategyDefinitions[selectedWalkStrategy]),
      ...previous,
    }));
  }, [selectedWalkStrategy, strategyDefinitions]);

  useEffect(() => {
    const templates = loadAdvancedExperimentTemplates();
    const snapshots = loadAdvancedExperimentSnapshots();
    setSavedTemplates(templates);
    setSavedSnapshots(snapshots);
    setSelectedTemplateId((previous) => previous || templates[0]?.id || '');
    setSelectedSnapshotId((previous) => previous || snapshots[0]?.id || '');
  }, []);

  const updateBatchParam = (strategyName, key, value) => {
    setBatchConfigs((previous) => ({
      ...previous,
      [strategyName]: {
        ...(previous[strategyName] || {}),
        [key]: value,
      },
    }));
  };

  const batchRankingData = useMemo(() => {
    const records = batchResult?.ranked_results?.length
      ? batchResult.ranked_results
      : batchResult?.results || [];

    return records
      .filter((record) => record?.success !== false)
      .map((record) => ({
        key: record.task_id,
        taskId: record.task_id,
        label: record.research_label || `${record.symbol} · ${getStrategyName(record.strategy)}`,
        symbol: record.symbol,
        totalReturn: getMetricValue(record, 'total_return'),
        sharpe: getMetricValue(record, 'sharpe_ratio'),
        drawdown: Math.abs(getMetricValue(record, 'max_drawdown')),
        finalValue: getMetricValue(record, 'final_value'),
        researchLabel: record.research_label || '',
      }));
  }, [batchResult]);

  const batchRecords = useMemo(
    () => (batchResult?.ranked_results?.length ? batchResult.ranked_results : batchResult?.results || []),
    [batchResult]
  );

  const walkForwardChartData = useMemo(() => (
    (walkResult?.window_results || []).map((record) => ({
      key: `${record.window_id}-${record.test_start}`,
      label: `窗口 ${Number(record.window_id || 0) + 1}`,
      totalReturn: getMetricValue(record, 'total_return'),
      sharpe: getMetricValue(record, 'sharpe_ratio'),
      drawdown: Math.abs(getMetricValue(record, 'max_drawdown')),
      testRange: `${record.test_start} ~ ${record.test_end}`,
    }))
  ), [walkResult]);

  const focusedBatchRecord = useMemo(
    () => batchRecords.find((record) => record.task_id === focusedBatchTaskId) || null,
    [batchRecords, focusedBatchTaskId]
  );

  const focusedWalkRecord = useMemo(
    () => (walkResult?.window_results || []).find((record) => `${record.window_id}-${record.test_start}` === focusedWalkWindowKey) || null,
    [focusedWalkWindowKey, walkResult]
  );
  const batchInsight = useMemo(() => buildBatchInsight(batchResult), [batchResult]);
  const walkInsight = useMemo(() => buildWalkForwardInsight(walkResult), [walkResult]);
  const marketRegimeInsight = useMemo(() => buildMarketRegimeInsight(marketRegimeResult), [marketRegimeResult]);
  const benchmarkSummary = useMemo(
    () => buildBenchmarkSummary(benchmarkResult?.data, benchmarkContext?.strategy),
    [benchmarkContext, benchmarkResult]
  );
  const robustnessScore = useMemo(
    () => buildRobustnessScore({
      batchResult,
      walkResult,
      benchmarkSummary,
      marketRegimeResult,
    }),
    [batchResult, benchmarkSummary, marketRegimeResult, walkResult]
  );
  const overfittingWarnings = useMemo(
    () => buildOverfittingWarnings({
      batchResult,
      walkResult,
      benchmarkSummary,
      marketRegimeResult,
    }),
    [batchResult, benchmarkSummary, marketRegimeResult, walkResult]
  );
  const researchConclusion = useMemo(
    () => buildResearchConclusion({
      robustnessScore,
      overfittingWarnings,
      batchResult,
      walkResult,
      benchmarkSummary,
      marketRegimeResult,
    }),
    [batchResult, benchmarkSummary, marketRegimeResult, overfittingWarnings, robustnessScore, walkResult]
  );
  const benchmarkChartData = useMemo(
    () => Object.entries(benchmarkResult?.data || {}).map(([key, value]) => ({
      key,
      label: getStrategyName(key),
      totalReturn: Number(value.total_return || 0),
      drawdown: Math.abs(Number(value.max_drawdown || 0)),
    })),
    [benchmarkResult]
  );
  const portfolioChartData = useMemo(
    () => buildPortfolioExposureChartData(portfolioStrategyResult),
    [portfolioStrategyResult]
  );
  const portfolioPositionSnapshot = useMemo(
    () => buildPortfolioPositionSnapshot(portfolioStrategyResult),
    [portfolioStrategyResult]
  );
  const portfolioExposureSummary = useMemo(
    () => buildPortfolioExposureSummary(portfolioStrategyResult),
    [portfolioStrategyResult]
  );
  const marketRegimeChartData = useMemo(
    () => (marketRegimeResult?.regimes || []).map((item) => ({
      key: item.regime,
      label: item.regime,
      strategyTotalReturn: Number(item.strategy_total_return || 0),
      marketTotalReturn: Number(item.market_total_return || 0),
      days: Number(item.days || 0),
    })),
    [marketRegimeResult]
  );
  const currentSnapshot = useMemo(() => buildAdvancedExperimentSnapshot({
    batchResult,
    walkResult,
    benchmarkSummary,
    benchmarkContext,
    marketRegimeResult,
    portfolioStrategyResult,
    batchExperimentMeta,
    batchValues: batchForm.getFieldsValue(),
    walkValues: walkForm.getFieldsValue(),
    batchConfigs,
    walkParams,
    researchSymbolsInput,
    optimizationDensity,
    portfolioObjective,
    robustnessScore,
  }), [
    batchConfigs,
    batchExperimentMeta,
    batchForm,
    batchResult,
    benchmarkContext,
    benchmarkSummary,
    marketRegimeResult,
    optimizationDensity,
    portfolioObjective,
    portfolioStrategyResult,
    researchSymbolsInput,
    robustnessScore,
    walkForm,
    walkParams,
    walkResult,
  ]);
  const selectedSnapshot = useMemo(
    () => savedSnapshots.find((snapshot) => snapshot.id === selectedSnapshotId) || null,
    [savedSnapshots, selectedSnapshotId]
  );
  const selectedTemplate = useMemo(
    () => savedTemplates.find((template) => template.id === selectedTemplateId) || null,
    [savedTemplates, selectedTemplateId]
  );
  const selectedTemplatePreview = useMemo(
    () => buildAdvancedExperimentTemplatePreview(selectedTemplate),
    [selectedTemplate]
  );
  const filteredTemplates = useMemo(
    () => (
      templateCategoryFilter === 'all'
        ? savedTemplates
        : savedTemplates.filter((template) => (template.category || 'general') === templateCategoryFilter)
    ),
    [savedTemplates, templateCategoryFilter]
  );
  const groupedTemplateOptions = useMemo(() => {
    const groups = filteredTemplates.reduce((accumulator, template) => {
      const category = template.pinned ? 'pinned' : (template.category || 'general');
      if (!accumulator[category]) {
        accumulator[category] = [];
      }
      accumulator[category].push({
        value: template.id,
        label: template.pinned ? `★ ${template.name}` : template.name,
      });
      return accumulator;
    }, {});

    return Object.entries(groups).map(([category, options]) => ({
      label: category === 'pinned' ? '已置顶模板' : (ADVANCED_TEMPLATE_CATEGORY_LABELS[category] || category),
      options,
    }));
  }, [filteredTemplates]);
  const experimentComparison = useMemo(() => buildExperimentComparison({
    currentSnapshot,
    previousSnapshot: selectedSnapshot,
    formatPercentage,
    formatNumber: formatCompactNumber,
  }), [currentSnapshot, selectedSnapshot]);

  useEffect(() => {
    if (!batchRecords.length) {
      setFocusedBatchTaskId('');
      return;
    }

    setFocusedBatchTaskId((previous) => (
      batchRecords.some((record) => record.task_id === previous) ? previous : batchRecords[0].task_id
    ));
  }, [batchRecords]);

  useEffect(() => {
    const windowResults = walkResult?.window_results || [];
    if (!windowResults.length) {
      setFocusedWalkWindowKey('');
      return;
    }

    setFocusedWalkWindowKey((previous) => {
      const nextKey = `${windowResults[0].window_id}-${windowResults[0].test_start}`;
      return windowResults.some((record) => `${record.window_id}-${record.test_start}` === previous) ? previous : nextKey;
    });
  }, [walkResult]);

  const renderBatchTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) {
      return null;
    }
    const point = payload[0]?.payload;
    if (!point) {
      return null;
    }

    return (
      <div className="chart-tooltip">
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
        <div>总收益率 {formatPercentage(point.totalReturn)}</div>
        <div>夏普比率 {Number(point.sharpe || 0).toFixed(2)}</div>
        <div>最大回撤 {formatPercentage(-Math.abs(point.drawdown || 0))}</div>
      </div>
    );
  };

  const renderWalkTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) {
      return null;
    }
    const point = payload[0]?.payload;
    if (!point) {
      return null;
    }

    return (
      <div className="chart-tooltip">
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
        <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{point.testRange}</div>
        <div>窗口收益 {formatPercentage(point.totalReturn)}</div>
        <div>夏普比率 {Number(point.sharpe || 0).toFixed(2)}</div>
        <div>最大回撤 {formatPercentage(-Math.abs(point.drawdown || 0))}</div>
      </div>
    );
  };

  const batchRankingColumns = [
    {
      title: '任务',
      dataIndex: 'task_id',
      key: 'task_id',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 700 }}>{record.research_label || getStrategyName(record.strategy)}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{record.symbol} · {getStrategyName(record.strategy)}</div>
        </div>
      ),
    },
    {
      title: '总收益率',
      dataIndex: ['metrics', 'total_return'],
      key: 'total_return',
      render: (value) => (
        <span style={{ color: getValueColor(value || 0) }}>
          {formatPercentage(value || 0)}
        </span>
      ),
    },
    {
      title: '夏普比率',
      dataIndex: ['metrics', 'sharpe_ratio'],
      key: 'sharpe_ratio',
      render: (value) => Number(value || 0).toFixed(2),
    },
    {
      title: '最大回撤',
      dataIndex: ['metrics', 'max_drawdown'],
      key: 'max_drawdown',
      render: (value) => formatPercentage(value || 0),
    },
    {
      title: '最终价值',
      dataIndex: ['metrics', 'final_value'],
      key: 'final_value',
      render: (value) => formatCurrency(value || 0),
    },
    {
      title: '状态',
      dataIndex: 'success',
      key: 'success',
      render: (value, record) => value ? <Tag color="success">成功</Tag> : <Tag color="error">{record.error || '失败'}</Tag>,
    },
  ];

  const walkColumns = [
    {
      title: '窗口',
      dataIndex: 'window_id',
      key: 'window_id',
      render: (value) => `窗口 ${value + 1}`,
    },
    {
      title: '测试区间',
      key: 'test_range',
      render: (_, record) => `${record.test_start} ~ ${record.test_end}`,
    },
    {
      title: '总收益率',
      dataIndex: ['metrics', 'total_return'],
      key: 'total_return',
      render: (value) => formatPercentage(value || 0),
    },
    {
      title: '夏普比率',
      dataIndex: ['metrics', 'sharpe_ratio'],
      key: 'sharpe_ratio',
      render: (value) => Number(value || 0).toFixed(2),
    },
    {
      title: '最大回撤',
      dataIndex: ['metrics', 'max_drawdown'],
      key: 'max_drawdown',
      render: (value) => formatPercentage(value || 0),
    },
    {
      title: '训练窗优选参数',
      dataIndex: 'selected_parameters',
      key: 'selected_parameters',
      render: (value) => {
        const entries = Object.entries(value || {});
        if (!entries.length) {
          return '-';
        }
        return entries.map(([key, item]) => `${getStrategyParameterLabel(key, key)}:${item}`).join(' / ');
      },
    },
  ];

  const refreshSavedArtifacts = useCallback(() => {
    const templates = loadAdvancedExperimentTemplates();
    const snapshots = loadAdvancedExperimentSnapshots();
    setSavedTemplates(templates);
    setSavedSnapshots(snapshots);
    setSelectedTemplateId((previous) => previous || templates[0]?.id || '');
    setSelectedSnapshotId((previous) => previous || snapshots[0]?.id || '');
  }, []);

  const handleSaveTemplate = useCallback(() => {
    const batchValues = batchForm.getFieldsValue();
    const walkValues = walkForm.getFieldsValue();
    const resolvedName = String(templateName || '').trim()
      || suggestAdvancedExperimentTemplateName({
        batchValues,
        walkValues,
        batchExperimentMeta,
        optimizationDensity,
        portfolioObjective,
      });

    const savedTemplate = saveAdvancedExperimentTemplate(buildAdvancedExperimentTemplatePayload({
      name: resolvedName,
      category: inferAdvancedExperimentTemplateCategory({
        batchExperimentMeta,
        portfolioObjective,
        marketRegimeResult,
        benchmarkSummary,
      }),
      note: templateNote,
      batchValues: {
        ...batchValues,
        dateRange: batchValues.dateRange?.map((value) => value?.format?.(DATE_FORMAT)),
      },
      walkValues: {
        ...walkValues,
        dateRange: walkValues.dateRange?.map((value) => value?.format?.(DATE_FORMAT)),
      },
      batchConfigs,
      walkParams,
      researchSymbolsInput,
      optimizationDensity,
      portfolioObjective,
    }));
    refreshSavedArtifacts();
    setTemplateName(savedTemplate.name);
    setTemplateNote(savedTemplate.note || '');
    setSelectedTemplateId(savedTemplate.id);
    message.success('实验模板已保存');
  }, [
    batchExperimentMeta,
    batchConfigs,
    batchForm,
    benchmarkSummary,
    message,
    marketRegimeResult,
    optimizationDensity,
    portfolioObjective,
    refreshSavedArtifacts,
    researchSymbolsInput,
    templateName,
    templateNote,
    walkForm,
    walkParams,
  ]);

  const handleOverwriteTemplate = useCallback(() => {
    const currentTemplate = savedTemplates.find((item) => item.id === selectedTemplateId);
    if (!currentTemplate) {
      message.warning('请先选择要覆盖的模板');
      return;
    }

    const batchValues = batchForm.getFieldsValue();
    const walkValues = walkForm.getFieldsValue();
    const updatedTemplate = saveAdvancedExperimentTemplate({
      ...buildAdvancedExperimentTemplatePayload({
        name: String(templateName || '').trim() || currentTemplate.name,
        category: inferAdvancedExperimentTemplateCategory({
          batchExperimentMeta,
          portfolioObjective,
          marketRegimeResult,
          benchmarkSummary,
        }),
        note: templateNote,
        batchValues: {
          ...batchValues,
          dateRange: batchValues.dateRange?.map((value) => value?.format?.(DATE_FORMAT)),
        },
        walkValues: {
          ...walkValues,
          dateRange: walkValues.dateRange?.map((value) => value?.format?.(DATE_FORMAT)),
        },
        batchConfigs,
        walkParams,
        researchSymbolsInput,
        optimizationDensity,
        portfolioObjective,
      }),
      id: currentTemplate.id,
      created_at: currentTemplate.created_at,
    });
    refreshSavedArtifacts();
    setTemplateName(updatedTemplate.name);
    setTemplateNote(updatedTemplate.note || '');
    setSelectedTemplateId(updatedTemplate.id);
    message.success('当前模板已覆盖更新');
  }, [
    batchConfigs,
    batchExperimentMeta,
    batchForm,
    benchmarkSummary,
    marketRegimeResult,
    message,
    optimizationDensity,
    portfolioObjective,
    refreshSavedArtifacts,
    researchSymbolsInput,
    savedTemplates,
    selectedTemplateId,
    templateName,
    templateNote,
    walkForm,
    walkParams,
  ]);

  const handleSuggestTemplateName = useCallback(() => {
    const suggested = suggestAdvancedExperimentTemplateName({
      batchValues: batchForm.getFieldsValue(),
      walkValues: walkForm.getFieldsValue(),
      batchExperimentMeta,
      optimizationDensity,
      portfolioObjective,
    });
    setTemplateName(suggested);
    message.success('已生成推荐模板名');
  }, [batchExperimentMeta, batchForm, message, optimizationDensity, portfolioObjective, walkForm]);

  const handleApplyTemplate = useCallback(() => {
    const template = savedTemplates.find((item) => item.id === selectedTemplateId);
    if (!template) {
      message.warning('请先选择一个实验模板');
      return;
    }

    const nextBatchDateRange = template.batch?.dateRange
      ? template.batch.dateRange.map((value) => dayjs(value, DATE_FORMAT))
      : undefined;
    const nextWalkDateRange = template.walk?.dateRange
      ? template.walk.dateRange.map((value) => dayjs(value, DATE_FORMAT))
      : undefined;

    batchForm.setFieldsValue({
      ...template.batch,
      dateRange: nextBatchDateRange,
    });
    walkForm.setFieldsValue({
      ...template.walk,
      dateRange: nextWalkDateRange,
    });
    setBatchConfigs(template.batch?.strategy_parameters || {});
    setWalkParams(template.walk?.strategy_parameters || {});
    setResearchSymbolsInput(template.researchSymbolsInput || 'AAPL,MSFT,NVDA');
    setOptimizationDensity(Number(template.optimizationDensity || 3));
    setPortfolioObjective(template.portfolioObjective || 'equal_weight');
    setTemplateName(template.name || '');
    setTemplateNote(template.note || '');
    message.success('实验模板已带入');
  }, [batchForm, message, savedTemplates, selectedTemplateId, walkForm]);

  const handleDeleteTemplate = useCallback(() => {
    if (!selectedTemplateId) {
      message.warning('请先选择一个实验模板');
      return;
    }

    deleteAdvancedExperimentTemplate(selectedTemplateId);
    refreshSavedArtifacts();
    setSelectedTemplateId('');
    message.success('实验模板已删除');
  }, [message, refreshSavedArtifacts, selectedTemplateId]);

  const handleTogglePinnedTemplate = useCallback(() => {
    if (!selectedTemplateId) {
      message.warning('请先选择一个实验模板');
      return;
    }

    const updatedTemplate = toggleAdvancedExperimentTemplatePinned(selectedTemplateId);
    refreshSavedArtifacts();
    if (updatedTemplate) {
      setSelectedTemplateId(updatedTemplate.id);
      message.success(updatedTemplate.pinned ? '模板已置顶' : '模板已取消置顶');
    }
  }, [message, refreshSavedArtifacts, selectedTemplateId]);

  const handleImportTemplateToMainBacktest = useCallback(() => {
    const template = savedTemplates.find((item) => item.id === selectedTemplateId);
    const draft = buildMainBacktestDraftFromTemplate(template);
    if (!draft) {
      message.warning('当前模板缺少完整的主回测配置，暂时无法带回主回测');
      return;
    }

    saveBacktestWorkspaceDraft(draft);
    if (onImportTemplateToMainBacktest) {
      onImportTemplateToMainBacktest(draft);
    }
    message.success(`已将模板“${template.name}”带回主回测`);
  }, [message, onImportTemplateToMainBacktest, savedTemplates, selectedTemplateId]);

  const handleSaveSnapshot = useCallback(() => {
    if (!currentSnapshot) {
      message.warning('当前还没有可保存的实验结果');
      return;
    }

    const previousLatestSnapshotId = savedSnapshots[0]?.id || '';
    const snapshot = saveAdvancedExperimentSnapshot(currentSnapshot);
    refreshSavedArtifacts();
    setSelectedSnapshotId(previousLatestSnapshotId || snapshot.id);
    message.success('实验版本已保存，可用于后续对比');
  }, [currentSnapshot, message, refreshSavedArtifacts, savedSnapshots]);

  const handleRunBatch = async (values) => {
    if (!values.symbol?.trim()) {
      message.warning('请输入批量实验的标的代码');
      return;
    }
    if (!values.strategies?.length) {
      message.warning('请至少选择一个策略');
      return;
    }

    setBatchLoading(true);
    setBatchResult(null);
    setBatchExperimentMeta({
      title: '批量回测结果',
      description: '同一实验上下文下的多任务回测结果会集中展示在这里。',
    });
    try {
      const payload = {
        ranking_metric: values.ranking_metric || 'sharpe_ratio',
        top_n: values.top_n || undefined,
        tasks: values.strategies.map((strategyName, index) => ({
          task_id: `batch_${strategyName}_${index + 1}`,
          symbol: values.symbol.trim().toUpperCase(),
          strategy: strategyName,
          parameters: batchConfigs[strategyName] || {},
          start_date: values.dateRange?.[0]?.format(DATE_FORMAT),
          end_date: values.dateRange?.[1]?.format(DATE_FORMAT),
          initial_capital: values.initial_capital,
          commission: (values.commission ?? DEFAULT_COMMISSION) / 100,
          slippage: (values.slippage ?? DEFAULT_SLIPPAGE) / 100,
        })),
      };
      const response = await runBatchBacktest(payload);
      if (!response.success) {
        throw new Error(response.error || '批量回测失败');
      }
      setBatchResult(response.data);
      message.success('批量实验已完成');
    } catch (error) {
      message.error(error.message || '批量实验失败');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleRunWalkForward = async (values) => {
    if (!values.symbol?.trim()) {
      message.warning('请输入滚动前瞻分析的标的代码');
      return;
    }
    if (!values.strategy) {
      message.warning('请选择一个策略');
      return;
    }

    setWalkLoading(true);
    setWalkResult(null);
    try {
      const walkStrategyDefinition = strategyDefinitions[values.strategy];
      const parameterCandidates = buildWalkForwardParameterCandidates({
        baseParameters: walkParams,
        strategyDefinition: walkStrategyDefinition,
        density: optimizationDensity,
      });
      const response = await runWalkForwardBacktest({
        symbol: values.symbol.trim().toUpperCase(),
        strategy: values.strategy,
        parameters: walkParams,
        parameter_candidates: parameterCandidates,
        start_date: values.dateRange?.[0]?.format(DATE_FORMAT),
        end_date: values.dateRange?.[1]?.format(DATE_FORMAT),
        initial_capital: values.initial_capital,
        commission: (values.commission ?? DEFAULT_COMMISSION) / 100,
        slippage: (values.slippage ?? DEFAULT_SLIPPAGE) / 100,
        train_period: values.train_period,
        test_period: values.test_period,
        step_size: values.step_size,
        optimization_metric: values.optimization_metric || 'sharpe_ratio',
        optimization_method: values.optimization_method || 'grid',
        optimization_budget: values.optimization_budget || undefined,
        monte_carlo_simulations: values.monte_carlo_simulations,
      });
      if (!response.success) {
        throw new Error(response.error || '滚动前瞻分析失败');
      }
      setWalkResult(response.data);
      message.success('滚动前瞻分析已完成');
    } catch (error) {
      message.error(error.message || '滚动前瞻分析失败');
    } finally {
      setWalkLoading(false);
    }
  };

  const getWalkBaseline = useCallback(() => {
    const values = walkForm.getFieldsValue();
    const symbol = String(values.symbol || '').trim().toUpperCase();
    const strategy = values.strategy;
    if (!symbol || !strategy) {
      return null;
    }

    return {
      symbol,
      strategy,
      dateRange: [
        values.dateRange?.[0]?.format(DATE_FORMAT),
        values.dateRange?.[1]?.format(DATE_FORMAT),
      ],
      initialCapital: Number(values.initial_capital ?? DEFAULT_CAPITAL),
      commission: Number(values.commission ?? DEFAULT_COMMISSION) / 100,
      slippage: Number(values.slippage ?? DEFAULT_SLIPPAGE) / 100,
      baseParameters: walkParams,
      strategyDefinition: strategyDefinitions[strategy],
    };
  }, [strategyDefinitions, walkForm, walkParams]);

  const runResearchBatchTasks = async (tasks, meta) => {
    if (!tasks.length) {
      message.warning('当前实验模板没有生成可执行任务，请先检查策略和参数设置。');
      return;
    }

    setBatchLoading(true);
    setBatchResult(null);
    setBatchExperimentMeta(meta);
    try {
      const response = await runBatchBacktest({
        ranking_metric: 'sharpe_ratio',
        tasks,
      });
      if (!response.success) {
        throw new Error(response.error || '实验执行失败');
      }
      setBatchResult(response.data);
      message.success(`${meta.title}已完成`);
    } catch (error) {
      message.error(error.message || '实验执行失败');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleRunParameterOptimization = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择标的和策略');
      return;
    }

    const tasks = buildParameterOptimizationTasks({
      ...baseline,
      density: optimizationDensity,
    });
    await runResearchBatchTasks(tasks, {
      title: '参数寻优结果',
      description: '围绕当前策略参数做局部网格搜索，快速找出更有潜力的参数组合。',
    });
  };

  const handleRunBenchmarkComparison = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择标的和策略');
      return;
    }

    setBenchmarkLoading(true);
    setBenchmarkResult(null);
    setBenchmarkContext(null);
    try {
      const response = await compareStrategies({
        symbol: baseline.symbol,
        start_date: baseline.dateRange?.[0],
        end_date: baseline.dateRange?.[1],
        initial_capital: baseline.initialCapital,
        commission: baseline.commission,
        slippage: baseline.slippage,
        strategy_configs: [
          { name: baseline.strategy, parameters: baseline.baseParameters },
          { name: 'buy_and_hold', parameters: {} },
        ],
      });
      if (!response.success) {
        throw new Error(response.error || '基准对照失败');
      }
      setBenchmarkResult(response);
      setBenchmarkContext({
        symbol: baseline.symbol,
        strategy: baseline.strategy,
        dateRange: baseline.dateRange,
        initialCapital: baseline.initialCapital,
        commission: baseline.commission,
        slippage: baseline.slippage,
        parameters: baseline.baseParameters,
      });
      message.success('基准对照已完成');
    } catch (error) {
      message.error(error.message || '基准对照失败');
    } finally {
      setBenchmarkLoading(false);
    }
  };

  const handleRunMultiSymbolResearch = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择基准策略');
      return;
    }

    const symbols = parseSymbolsInput(researchSymbolsInput);
    if (symbols.length < 2) {
      message.warning('请输入至少两个标的代码');
      return;
    }

    await runResearchBatchTasks(buildMultiSymbolTasks({
      ...baseline,
      symbols,
    }), {
      title: '多标的横向研究',
      description: '在同一策略与参数下，比较不同标的的适配度和泛化能力。',
    });
  };

  const handleRunCostSensitivity = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择基准策略');
      return;
    }

    await runResearchBatchTasks(buildCostSensitivityTasks(baseline), {
      title: '成本敏感性结果',
      description: '比较低成本、基准成本和高成本场景下，策略收益对交易摩擦的敏感度。',
    });
  };

  const handleRunRobustnessDiagnostic = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择基准策略');
      return;
    }

    await runResearchBatchTasks(buildRobustnessTasks(baseline), {
      title: '稳健性诊断结果',
      description: '通过日期窗口扰动和参数轻微扰动，观察策略表现是否足够稳定。',
    });
  };

  const handleRunPortfolioStrategy = useCallback(async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择基准策略');
      return;
    }

    const symbols = parseSymbolsInput(researchSymbolsInput);
    if (symbols.length < 2) {
      message.warning('组合级策略回测至少需要两个标的');
      return;
    }

    setPortfolioLoading(true);
    setPortfolioStrategyResult(null);
    try {
      const response = await runPortfolioStrategyBacktest({
        symbols,
        strategy: baseline.strategy,
        parameters: baseline.baseParameters,
        objective: portfolioObjective,
        start_date: baseline.dateRange?.[0],
        end_date: baseline.dateRange?.[1],
        initial_capital: baseline.initialCapital,
        commission: baseline.commission,
        slippage: baseline.slippage,
      });
      if (!response.success) {
        throw new Error(response.error || '组合级策略回测失败');
      }
      setPortfolioStrategyResult(response.data);
      message.success('组合级策略回测已完成');
    } catch (error) {
      message.error(error.message || '组合级策略回测失败');
    } finally {
      setPortfolioLoading(false);
    }
  }, [getWalkBaseline, message, portfolioObjective, researchSymbolsInput]);

  const handleRunMarketRegimeAnalysis = useCallback(async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择基准策略');
      return;
    }

    setMarketRegimeLoading(true);
    setMarketRegimeResult(null);
    try {
      const response = await runMarketRegimeBacktest({
        symbol: baseline.symbol,
        strategy: baseline.strategy,
        parameters: baseline.baseParameters,
        start_date: baseline.dateRange?.[0],
        end_date: baseline.dateRange?.[1],
        initial_capital: baseline.initialCapital,
        commission: baseline.commission,
        slippage: baseline.slippage,
      });
      if (!response.success) {
        throw new Error(response.error || '市场状态分层回测失败');
      }
      setMarketRegimeResult(response.data);
      message.success('市场状态分层回测已完成');
    } catch (error) {
      message.error(error.message || '市场状态分层回测失败');
    } finally {
      setMarketRegimeLoading(false);
    }
  }, [getWalkBaseline, message]);

  const handleSaveBatchHistory = async () => {
    if (!batchResult) {
      message.warning('请先运行批量回测');
      return;
    }

    try {
      const values = batchForm.getFieldsValue();
      const response = await saveAdvancedHistoryRecord({
        record_type: 'batch_backtest',
        title: `批量回测 · ${String(values.symbol || '').toUpperCase()}`,
        symbol: String(values.symbol || '').toUpperCase(),
        strategy: 'batch_backtest',
        start_date: values.dateRange?.[0]?.format(DATE_FORMAT),
        end_date: values.dateRange?.[1]?.format(DATE_FORMAT),
        parameters: {
          ranking_metric: values.ranking_metric,
          top_n: values.top_n,
          initial_capital: values.initial_capital,
          commission: values.commission,
          slippage: values.slippage,
          strategies: values.strategies || [],
          strategy_parameters: batchConfigs,
        },
        metrics: {
          total_return: batchResult.summary?.average_return || 0,
          sharpe_ratio: batchResult.summary?.average_sharpe || 0,
          total_tasks: batchResult.summary?.total_tasks || 0,
          successful: batchResult.summary?.successful || 0,
          average_return: batchResult.summary?.average_return || 0,
          average_sharpe: batchResult.summary?.average_sharpe || 0,
          ranking_metric: batchResult.summary?.ranking_metric || values.ranking_metric || 'sharpe_ratio',
        },
        result: batchResult,
      });

      if (!response?.success) {
        throw new Error(response?.error || '保存失败');
      }
      message.success('批量回测结果已保存到历史');
    } catch (error) {
      message.error(error.message || '保存批量回测结果失败');
    }
  };

  const handleSaveWalkHistory = async () => {
    if (!walkResult) {
      message.warning('请先运行滚动前瞻分析');
      return;
    }

    try {
      const values = walkForm.getFieldsValue();
      const worstDrawdown = Math.min(
        0,
        ...(walkResult.window_results || []).map((item) => Number(item?.metrics?.max_drawdown ?? item?.max_drawdown ?? 0))
      );
      const response = await saveAdvancedHistoryRecord({
        record_type: 'walk_forward',
        title: `滚动前瞻分析 · ${String(values.symbol || '').toUpperCase()} · ${getStrategyName(values.strategy)}`,
        symbol: String(values.symbol || '').toUpperCase(),
        strategy: values.strategy,
        start_date: values.dateRange?.[0]?.format(DATE_FORMAT),
        end_date: values.dateRange?.[1]?.format(DATE_FORMAT),
        parameters: {
          initial_capital: values.initial_capital,
          commission: values.commission,
          slippage: values.slippage,
          train_period: values.train_period,
          test_period: values.test_period,
          step_size: values.step_size,
          strategy_parameters: walkParams,
        },
        metrics: {
          total_return: walkResult.aggregate_metrics?.average_return || 0,
          sharpe_ratio: walkResult.aggregate_metrics?.average_sharpe || 0,
          max_drawdown: worstDrawdown,
          n_windows: walkResult.n_windows || 0,
          return_std: walkResult.aggregate_metrics?.return_std || 0,
          positive_windows: walkResult.aggregate_metrics?.positive_windows || 0,
          negative_windows: walkResult.aggregate_metrics?.negative_windows || 0,
          train_period: walkResult.train_period || values.train_period,
          test_period: walkResult.test_period || values.test_period,
          step_size: walkResult.step_size || values.step_size,
        },
        result: walkResult,
      });

      if (!response?.success) {
        throw new Error(response?.error || '保存失败');
      }
      message.success('滚动前瞻分析结果已保存到历史');
    } catch (error) {
      message.error(error.message || '保存滚动前瞻分析结果失败');
    }
  };

  const handleExportBatch = (format) => {
    if (!batchResult) {
      message.warning('请先运行批量回测');
      return;
    }

    const symbol = batchForm.getFieldValue('symbol') || 'batch';
    const dateStamp = new Date().toISOString().split('T')[0];
    const filename = `advanced_batch_${String(symbol).toUpperCase()}_${dateStamp}`;
    const formatted = formatBatchExperimentForExport(batchResult);

    if (format === 'json') {
      exportToJSON(formatted, filename);
    } else {
      exportToCSV(formatted.rankedResults.length ? formatted.rankedResults : formatted.allResults, `${filename}_results`);
      exportToCSV(formatted.summary, `${filename}_summary`, [
        { key: 'metric', title: '指标' },
        { key: 'value', title: '值' },
      ]);
    }
    message.success(`批量回测结果已导出为${format.toUpperCase()}`);
  };

  const handleExportWalkForward = (format) => {
    if (!walkResult) {
      message.warning('请先运行滚动前瞻分析');
      return;
    }

    const symbol = walkForm.getFieldValue('symbol') || 'walk_forward';
    const dateStamp = new Date().toISOString().split('T')[0];
    const filename = `advanced_walk_forward_${String(symbol).toUpperCase()}_${dateStamp}`;
    const formatted = formatWalkForwardForExport(walkResult);

    if (format === 'json') {
      exportToJSON(formatted, filename);
    } else {
      exportToCSV(formatted.windows, `${filename}_windows`);
      exportToCSV(formatted.summary, `${filename}_summary`, [
        { key: 'metric', title: '指标' },
        { key: 'value', title: '值' },
      ]);
    }
    message.success(`滚动前瞻分析结果已导出为${format.toUpperCase()}`);
  };

  const handleApplyMainBacktestDraft = useCallback(() => {
    const draft = buildBatchDraftState(loadBacktestWorkspaceDraft());
    if (!draft) {
      message.warning('暂未找到主回测配置，请先在“新建回测”页配置一次策略。');
      return;
    }

    const strategyExists = Boolean(strategyDefinitions[draft.strategy]);
    const nextDateRange = draft.dateRange
      ? [dayjs(draft.dateRange[0], DATE_FORMAT), dayjs(draft.dateRange[1], DATE_FORMAT)]
      : undefined;

    batchForm.setFieldsValue({
      symbol: draft.symbol,
      dateRange: nextDateRange,
      initial_capital: draft.initial_capital,
      commission: draft.commission,
      slippage: draft.slippage,
      strategies: strategyExists ? [draft.strategy] : [],
    });

    walkForm.setFieldsValue({
      symbol: draft.symbol,
      dateRange: nextDateRange,
      initial_capital: draft.initial_capital,
      commission: draft.commission,
      slippage: draft.slippage,
      ...(strategyExists ? { strategy: draft.strategy } : {}),
    });

    if (strategyExists) {
      const defaultParams = buildDefaultParams(strategyDefinitions[draft.strategy]);
      const mergedParams = {
        ...defaultParams,
        ...(draft.parameters || {}),
      };
      setBatchConfigs((previous) => ({
        ...previous,
        [draft.strategy]: mergedParams,
      }));
      setWalkParams(mergedParams);
      message.success('已带入主回测当前配置，可直接运行高级实验');
      return;
    }

    message.warning('主回测策略已带入，但当前高级实验页暂不支持该策略参数面板。');
  }, [batchForm, message, strategyDefinitions, walkForm]);

  useEffect(() => {
    const intent = consumeAdvancedExperimentIntent();
    if (intent?.type === 'import_main_backtest') {
      handleApplyMainBacktestDraft();
    }
  }, [handleApplyMainBacktestDraft]);

  return (
    <div className="workspace-tab-view">
      <div className="workspace-section workspace-section--accent">
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">高级实验台</div>
            <div className="workspace-section__description">把批量回测和滚动前瞻分析接进正式工作流，方便做更系统的策略研究。</div>
          </div>
          <Button type="default" onClick={handleApplyMainBacktestDraft}>
            带入主回测当前配置
          </Button>
        </div>
        <div className="summary-strip summary-strip--compact">
          <div className="summary-strip__item">
            <span className="summary-strip__label">实验模块</span>
            <span className="summary-strip__value">批量回测 + 滚动前瞻分析</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">可选策略</span>
            <span className="summary-strip__value">{strategies.length} 个</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">当前状态</span>
            <span className="summary-strip__value">{batchLoading || walkLoading ? '实验运行中' : '待执行'}</span>
          </div>
        </div>
      </div>

      <Card className="workspace-panel" style={{ marginBottom: 20 }}>
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">实验模板与版本对比</div>
            <div className="workspace-section__description">把常用实验配置保存成模板，并将当前实验结果与上一版关键指标并排比较。</div>
          </div>
        </div>
        <Row gutter={[16, 16]} align="top">
          <Col xs={24} xl={10}>
            <div className="workspace-field-label">模板名称</div>
            <Input
              value={templateName}
              onChange={(event) => setTemplateName(event.target.value)}
              placeholder="例如：趋势策略稳健性模板"
            />
            <div className="workspace-field-label" style={{ marginTop: 12 }}>模板备注</div>
            <Input.TextArea
              value={templateNote}
              onChange={(event) => setTemplateNote(event.target.value)}
              placeholder="例如：适合做趋势策略在大盘股上的参数寻优与稳健性验证"
              rows={3}
              maxLength={160}
              showCount
            />
            <div className="workspace-field-label" style={{ marginTop: 12 }}>已保存模板</div>
            <Select
              value={templateCategoryFilter}
              style={{ width: '100%', marginBottom: 12 }}
              options={[
                { value: 'all', label: '全部研究场景' },
                ...Object.entries(ADVANCED_TEMPLATE_CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
              ]}
              onChange={setTemplateCategoryFilter}
            />
            <Select
              value={selectedTemplateId || undefined}
              style={{ width: '100%' }}
              placeholder="选择一个已保存模板"
              options={groupedTemplateOptions}
              onChange={setSelectedTemplateId}
            />
            <Space wrap style={{ marginTop: 12 }}>
              <Button type="primary" onClick={handleSaveTemplate}>
                保存模板
              </Button>
              <Button onClick={handleSuggestTemplateName}>
                推荐命名
              </Button>
              <Button onClick={handleApplyTemplate} disabled={!savedTemplates.length}>
                套用模板
              </Button>
              <Button onClick={handleImportTemplateToMainBacktest} disabled={!selectedTemplateId}>
                带回主回测
              </Button>
              <Button onClick={handleOverwriteTemplate} disabled={!selectedTemplateId}>
                覆盖当前模板
              </Button>
              <Button onClick={handleTogglePinnedTemplate} disabled={!selectedTemplateId}>
                {selectedTemplate?.pinned ? '取消置顶' : '置顶模板'}
              </Button>
              <Button danger onClick={handleDeleteTemplate} disabled={!selectedTemplateId}>
                删除模板
              </Button>
            </Space>
            {selectedTemplatePreview ? (
              <div className="workspace-section" style={{ marginTop: 16 }}>
                <div className="workspace-section__header" style={{ marginBottom: 12 }}>
                  <div>
                    <div className="workspace-section__title">模板预览</div>
                    <div className="workspace-section__description">套用前先确认这个模板对应的研究场景、标的和关键参数。</div>
                  </div>
                  <Space size="small">
                    {selectedTemplate?.pinned ? <Tag color="gold">已置顶</Tag> : null}
                    <Tag color="processing">
                      {ADVANCED_TEMPLATE_CATEGORY_LABELS[selectedTemplatePreview.category] || selectedTemplatePreview.category}
                    </Tag>
                  </Space>
                </div>
                <div className="summary-strip" style={{ marginTop: 0 }}>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">标的</span>
                    <span className="summary-strip__value">{selectedTemplatePreview.symbol || '未设置'}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">主策略</span>
                    <span className="summary-strip__value">{selectedTemplatePreview.strategy ? getStrategyName(selectedTemplatePreview.strategy) : '未设置'}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">策略数量</span>
                    <span className="summary-strip__value">{selectedTemplatePreview.strategyCount || 1}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">寻优密度</span>
                    <span className="summary-strip__value">{selectedTemplatePreview.optimizationDensity}</span>
                  </div>
                </div>
                <div className="workspace-section__hint">
                  区间：{selectedTemplatePreview.dateRange?.filter(Boolean).join(' 至 ') || '未设置'}
                </div>
                <div className="workspace-section__hint">
                  研究标的池：{selectedTemplatePreview.researchSymbolsInput || '未设置'}
                </div>
                {selectedTemplatePreview.note ? (
                  <div className="workspace-section__hint">
                    备注：{selectedTemplatePreview.note}
                  </div>
                ) : null}
                {selectedTemplatePreview.keyParameters.length ? (
                  <Space wrap style={{ marginTop: 12 }}>
                    {selectedTemplatePreview.keyParameters.map((entry) => (
                      <Tag key={entry.key} color="blue">
                        {getStrategyParameterLabel(entry.key)}: {String(entry.value)}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <div className="workspace-section__hint">这个模板当前没有额外参数覆盖。</div>
                )}
              </div>
            ) : null}
          </Col>
          <Col xs={24} xl={14}>
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">实验版本对比</div>
                  <div className="workspace-section__description">当前结果会与一条已保存实验版本对比，快速确认这次改动到底带来了什么变化。</div>
                </div>
                <Space wrap>
                  <Select
                    value={selectedSnapshotId || undefined}
                    style={{ minWidth: 260 }}
                    placeholder="选择一个历史版本"
                    options={savedSnapshots.map((snapshot) => ({
                      value: snapshot.id,
                      label: snapshot.name,
                    }))}
                    onChange={setSelectedSnapshotId}
                  />
                  <Button onClick={handleSaveSnapshot} disabled={!currentSnapshot}>
                    保存本次版本
                  </Button>
                </Space>
              </div>
              {experimentComparison ? (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Alert
                    type="info"
                    showIcon
                    message="版本对比已生成"
                    description={experimentComparison.title}
                  />
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(record) => record.key}
                    dataSource={experimentComparison.rows}
                    columns={[
                      { title: '指标', dataIndex: 'label', key: 'label' },
                      { title: '当前版本', dataIndex: 'current', key: 'current' },
                      { title: '对比版本', dataIndex: 'previous', key: 'previous' },
                      {
                        title: '变化',
                        dataIndex: 'delta',
                        key: 'delta',
                        render: (value, record) => (
                          <span style={{
                            color: record.direction === 'up'
                              ? CHART_POSITIVE
                              : record.direction === 'down'
                                ? CHART_NEGATIVE
                                : 'var(--text-muted)',
                          }}
                          >
                            {value}
                          </span>
                        ),
                      },
                    ]}
                  />
                </Space>
              ) : (
                <Empty description="先保存至少一版实验结果，再运行或保留当前结果，这里就会显示关键指标差异。" />
              )}
            </div>
          </Col>
        </Row>
      </Card>

      <Card className="workspace-panel" style={{ marginBottom: 20 }}>
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">研究增强工具</div>
            <div className="workspace-section__description">把参数寻优、基准对照、多标的研究、成本敏感性、稳健性诊断和组合级策略回测收进同一组实验模板。</div>
          </div>
        </div>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} xl={10}>
            <div className="workspace-field-label">研究标的池</div>
            <Input
              value={researchSymbolsInput}
              onChange={(event) => setResearchSymbolsInput(event.target.value)}
              placeholder="用逗号分隔标的，例如 AAPL,MSFT,NVDA"
            />
            <div className="workspace-section__hint" style={{ marginTop: 8 }}>
              参数寻优、基准对照会优先使用当前滚动前瞻表单里的单一标的；多标的和组合级回测会读取这里的标的池。
            </div>
          </Col>
          <Col xs={12} xl={4}>
            <div className="workspace-field-label">寻优密度</div>
            <InputNumber
              min={3}
              max={5}
              precision={0}
              style={{ width: '100%' }}
              value={optimizationDensity}
              onChange={(value) => setOptimizationDensity(Number(value || 3))}
            />
          </Col>
          <Col xs={12} xl={4}>
            <div className="workspace-field-label">组合权重模式</div>
            <Select
              value={portfolioObjective}
              style={{ width: '100%' }}
              options={[
                { value: 'equal_weight', label: '等权组合' },
                { value: 'max_sharpe', label: '最大夏普' },
                { value: 'min_volatility', label: '最小波动' },
              ]}
              onChange={setPortfolioObjective}
            />
          </Col>
          <Col xs={24} xl={6}>
            <Space wrap style={{ width: '100%' }}>
              <Button onClick={handleRunParameterOptimization} loading={batchLoading}>
                参数寻优
              </Button>
              <Button onClick={handleRunBenchmarkComparison} loading={benchmarkLoading}>
                基准对照
              </Button>
              <Button onClick={handleRunMultiSymbolResearch} loading={batchLoading}>
                多标的研究
              </Button>
              <Button onClick={handleRunCostSensitivity} loading={batchLoading}>
                成本敏感性
              </Button>
              <Button onClick={handleRunRobustnessDiagnostic} loading={batchLoading}>
                稳健性诊断
              </Button>
              <Button onClick={handleRunMarketRegimeAnalysis} loading={marketRegimeLoading}>
                市场状态
              </Button>
              <Button type="primary" onClick={handleRunPortfolioStrategy} loading={portfolioLoading}>
                组合级策略回测
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={13}>
          <Card
            className="workspace-panel"
            title={(
              <div className="workspace-title">
                <div className="workspace-title__icon">
                  <PartitionOutlined style={{ color: '#fff' }} />
                </div>
                <div>
                  <div className="workspace-title__text">批量回测</div>
                  <div className="workspace-title__hint">同一实验上下文下，一次性跑多策略并输出排名。</div>
                </div>
              </div>
            )}
          >
            <Form
              form={batchForm}
              layout="vertical"
              onFinish={handleRunBatch}
              initialValues={{
                symbol: 'AAPL',
                strategies: ['buy_and_hold', 'moving_average'],
                dateRange: [dayjs().subtract(1, 'year'), dayjs()],
                initial_capital: DEFAULT_CAPITAL,
                commission: DEFAULT_COMMISSION,
                slippage: DEFAULT_SLIPPAGE,
                ranking_metric: 'sharpe_ratio',
                top_n: 3,
              }}
            >
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item label="标的代码" name="symbol" rules={[{ required: true, message: '请输入标的代码' }]}>
                    <Input placeholder="如 AAPL" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={16}>
                  <Form.Item label="实验区间" name="dateRange" rules={[{ required: true, message: '请选择日期区间' }]}>
                    <RangePicker style={{ width: '100%' }} placeholder={['开始日期', '结束日期']} separator="至" />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="策略列表" name="strategies" rules={[{ required: true, message: '请选择至少一个策略' }]}>
                    <Select
                      mode="multiple"
                      placeholder="选择要批量执行的策略"
                      options={strategies.map((strategy) => ({
                        value: strategy.name,
                        label: getStrategyName(strategy.name),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="初始资金" name="initial_capital">
                    <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="手续费 (%)" name="commission">
                    <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="滑点 (%)" name="slippage">
                    <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="排名指标" name="ranking_metric">
                    <Select
                      options={[
                        { value: 'sharpe_ratio', label: '夏普比率' },
                        { value: 'total_return', label: '总收益率' },
                        { value: 'max_drawdown', label: '最大回撤' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item label="保留前 N 名" name="top_n">
                    <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              {selectedBatchStrategies.length ? (
                <div className="workspace-analysis-stack" style={{ marginBottom: 16 }}>
                  {selectedBatchStrategies.map((strategyName) => {
                    const strategy = strategyDefinitions[strategyName];
                    const entries = Object.entries(strategy?.parameters || {});
                    return (
                        <div key={strategyName} className="workspace-section">
                        <div className="workspace-section__header">
                          <div>
                            <div className="workspace-section__title">{getStrategyName(strategyName)}</div>
                            <div className="workspace-section__description">{getStrategyDetails(strategyName).summary}</div>
                          </div>
                        </div>
                        <div className="workspace-section__hint" style={{ marginBottom: 12 }}>
                          {getStrategyDetails(strategyName).marketFit}
                        </div>
                        {entries.length ? (
                          <Row gutter={[12, 12]}>
                            {entries.map(([key, config]) => (
                              <Col key={`${strategyName}-${key}`} xs={24} md={12}>
                                <div className="workspace-field-label">{getStrategyParameterLabel(key, config.description)}</div>
                                <InputNumber
                                  value={batchConfigs[strategyName]?.[key] ?? config.default}
                                  min={config.min}
                                  max={config.max}
                                  step={config.step || 0.01}
                                  style={{ width: '100%' }}
                                  onChange={(value) => updateBatchParam(strategyName, key, value)}
                                />
                              </Col>
                            ))}
                          </Row>
                        ) : (
                          <Alert message="该策略没有额外参数，将按默认规则执行。" type="info" showIcon />
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              <Button type="primary" htmlType="submit" icon={<ExperimentOutlined />} loading={batchLoading} block>
                运行批量回测
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={11}>
          <Card
            className="workspace-panel workspace-panel--emphasis"
            title={(
              <div className="workspace-title">
                <div className="workspace-title__icon workspace-title__icon--accent">
                  <RiseOutlined style={{ color: '#fff' }} />
                </div>
                <div>
                  <div className="workspace-title__text">滚动前瞻分析</div>
                  <div className="workspace-title__hint">查看滚动窗口下的稳定性，而不只盯单次整段结果。</div>
                </div>
              </div>
            )}
          >
            <Form
              form={walkForm}
              layout="vertical"
              onFinish={handleRunWalkForward}
              initialValues={{
                symbol: 'AAPL',
                strategy: 'moving_average',
                dateRange: [dayjs().subtract(2, 'year'), dayjs()],
              initial_capital: DEFAULT_CAPITAL,
              commission: DEFAULT_COMMISSION,
              slippage: DEFAULT_SLIPPAGE,
              train_period: 252,
              test_period: 63,
              step_size: 21,
              optimization_metric: 'sharpe_ratio',
              optimization_method: 'grid',
              optimization_budget: 24,
              monte_carlo_simulations: 120,
            }}
            >
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item label="标的代码" name="symbol" rules={[{ required: true, message: '请输入标的代码' }]}>
                    <Input placeholder="如 AAPL" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={16}>
                  <Form.Item label="实验区间" name="dateRange" rules={[{ required: true, message: '请选择日期区间' }]}>
                    <RangePicker style={{ width: '100%' }} placeholder={['开始日期', '结束日期']} separator="至" />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="策略" name="strategy" rules={[{ required: true, message: '请选择策略' }]}>
                    <Select
                      options={strategies.map((strategy) => ({
                        value: strategy.name,
                        label: getStrategyName(strategy.name),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="训练窗口" name="train_period">
                    <InputNumber min={20} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="测试窗口" name="test_period">
                    <InputNumber min={5} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="滚动步长" name="step_size">
                    <InputNumber min={1} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="优化指标" name="optimization_metric">
                    <Select
                      options={[
                        { value: 'sharpe_ratio', label: '夏普比率' },
                        { value: 'total_return', label: '总收益率' },
                        { value: 'annualized_return', label: '年化收益率' },
                        { value: 'calmar_ratio', label: '卡玛比率' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="优化方式" name="optimization_method">
                    <Select
                      options={[
                        { value: 'grid', label: '网格穷举' },
                        { value: 'bayesian', label: '自适应贝叶斯搜索' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="Monte Carlo 次数" name="monte_carlo_simulations">
                    <InputNumber min={20} max={1000} precision={0} step={20} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="优化预算" name="optimization_budget">
                    <InputNumber min={1} max={500} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="初始资金" name="initial_capital">
                    <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="手续费 (%)" name="commission">
                    <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={8}>
                  <Form.Item label="滑点 (%)" name="slippage">
                    <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              {selectedWalkStrategy ? (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message={`${getStrategyName(selectedWalkStrategy)} · ${getStrategyDetails(selectedWalkStrategy).style}`}
                  description={`${getStrategyDetails(selectedWalkStrategy).summary} ${getStrategyDetails(selectedWalkStrategy).marketFit}`}
                />
              ) : null}

              {selectedWalkStrategy && Object.keys(strategyDefinitions[selectedWalkStrategy]?.parameters || {}).length ? (
                <div className="workspace-section" style={{ marginBottom: 16 }}>
                  <div className="workspace-section__header">
                    <div>
                      <div className="workspace-section__title">策略参数</div>
                      <div className="workspace-section__description">系统会先围绕当前参数生成候选组合，在训练窗口中挑选更优参数，再拿到测试窗口做样本外验证。</div>
                    </div>
                  </div>
                  <Row gutter={[12, 12]}>
                    {Object.entries(strategyDefinitions[selectedWalkStrategy]?.parameters || {}).map(([key, config]) => (
                      <Col key={`walk-${key}`} xs={24} md={12}>
                        <div className="workspace-field-label">{getStrategyParameterLabel(key, config.description)}</div>
                        <InputNumber
                          value={walkParams[key] ?? config.default}
                          min={config.min}
                          max={config.max}
                          step={config.step || 0.01}
                          style={{ width: '100%' }}
                          onChange={(value) => setWalkParams((previous) => ({ ...previous, [key]: value }))}
                        />
                      </Col>
                    ))}
                  </Row>
                </div>
              ) : null}

              <Button type="primary" htmlType="submit" icon={<RiseOutlined />} loading={walkLoading} block>
                运行滚动前瞻分析
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={13}>
          <Card
            className="workspace-panel workspace-chart-card"
            title={batchExperimentMeta.title}
            extra={batchResult ? (
              <Space size="small">
                <Button size="small" onClick={handleSaveBatchHistory}>
                  保存到历史
                </Button>
                <Button size="small" icon={<DownloadOutlined />} onClick={() => handleExportBatch('csv')}>
                  导出CSV
                </Button>
                <Button size="small" onClick={() => handleExportBatch('json')}>
                  导出JSON
                </Button>
              </Space>
            ) : null}
          >
            {batchResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <Alert
                  type="info"
                  showIcon
                  message={batchExperimentMeta.title}
                  description={batchExperimentMeta.description}
                />
                <div className="summary-strip">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">总任务数</span>
                    <span className="summary-strip__value">{batchResult.summary?.total_tasks ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">成功任务</span>
                    <span className="summary-strip__value">{batchResult.summary?.successful ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均收益</span>
                    <span className="summary-strip__value">{formatPercentage(batchResult.summary?.average_return ?? 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均夏普</span>
                    <span className="summary-strip__value">{Number(batchResult.summary?.average_sharpe ?? 0).toFixed(2)}</span>
                  </div>
                </div>
                {batchResult.summary?.best_result ? (
                  <Alert
                    type="success"
                    showIcon
                    message={`当前最佳策略：${getStrategyName(batchResult.summary.best_result.strategy)}`}
                    description={`总收益 ${formatPercentage(batchResult.summary.best_result.total_return || 0)}，夏普 ${Number(batchResult.summary.best_result.sharpe_ratio || 0).toFixed(2)}`}
                  />
                ) : null}
                {batchInsight ? (
                  <Alert
                    type={batchInsight.type}
                    showIcon
                    message={batchInsight.title}
                    description={batchInsight.description}
                  />
                ) : null}
                {focusedBatchRecord ? (
                  <Alert
                    type="info"
                    showIcon
                    message={`当前聚焦：${getStrategyName(focusedBatchRecord.strategy)} · ${focusedBatchRecord.symbol}`}
                    description={`总收益 ${formatPercentage(getMetricValue(focusedBatchRecord, 'total_return'))}，夏普 ${Number(getMetricValue(focusedBatchRecord, 'sharpe_ratio')).toFixed(2)}，最终价值 ${formatCurrency(getMetricValue(focusedBatchRecord, 'final_value'))}`}
                  />
                ) : null}
                {batchRankingData.length ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">策略排名图</div>
                        <div className="workspace-section__description">用收益率和夏普比率快速判断哪几个策略更值得继续深挖。</div>
                      </div>
                    </div>
                    <div style={{ height: 320 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={batchRankingData}
                          margin={{ top: 8, right: 12, left: 8, bottom: 12 }}
                          onClick={(state) => {
                            const nextTaskId = state?.activePayload?.[0]?.payload?.taskId;
                            if (nextTaskId) {
                              setFocusedBatchTaskId(nextTaskId);
                            }
                          }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                          <XAxis
                            dataKey="label"
                            tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                            interval={0}
                            angle={-12}
                            textAnchor="end"
                            height={56}
                          />
                          <YAxis
                            yAxisId="left"
                            tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`}
                            tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                          />
                          <YAxis
                            yAxisId="right"
                            orientation="right"
                            tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                          />
                          <RechartsTooltip content={renderBatchTooltip} />
                          <Legend />
                          <Bar yAxisId="left" dataKey="totalReturn" name="总收益率">
                            {batchRankingData.map((entry) => (
                              <Cell
                                key={entry.key}
                                fill={entry.totalReturn >= 0 ? CHART_POSITIVE : CHART_NEGATIVE}
                                fillOpacity={!focusedBatchTaskId || focusedBatchTaskId === entry.taskId ? 1 : 0.35}
                                stroke={focusedBatchTaskId === entry.taskId ? '#f8fafc' : 'none'}
                                strokeWidth={focusedBatchTaskId === entry.taskId ? 2 : 0}
                              />
                            ))}
                          </Bar>
                          <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey="sharpe"
                            name="夏普比率"
                            stroke={CHART_NEUTRAL}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            activeDot={{ r: 5 }}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                ) : null}
                <Table
                  size="small"
                  rowKey={(record) => record.task_id}
                  dataSource={batchRecords}
                  columns={batchRankingColumns}
                  pagination={false}
                  onRow={(record) => ({
                    onClick: () => setFocusedBatchTaskId(record.task_id),
                    style: {
                      cursor: 'pointer',
                      background: focusedBatchTaskId === record.task_id ? 'rgba(14, 165, 233, 0.12)' : undefined,
                    },
                  })}
                />
              </Space>
            ) : (
              <Empty description="运行批量回测后，这里会显示汇总和排名。" />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={11}>
          <Card
            className="workspace-panel workspace-chart-card"
            title="滚动前瞻分析结果"
            extra={walkResult ? (
              <Space size="small">
                <Button size="small" onClick={handleSaveWalkHistory}>
                  保存到历史
                </Button>
                <Button size="small" icon={<DownloadOutlined />} onClick={() => handleExportWalkForward('csv')}>
                  导出CSV
                </Button>
                <Button size="small" onClick={() => handleExportWalkForward('json')}>
                  导出JSON
                </Button>
              </Space>
            ) : null}
          >
            {walkResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div className="summary-strip">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">滚动窗口</span>
                    <span className="summary-strip__value">{walkResult.n_windows}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均收益</span>
                    <span className="summary-strip__value">{formatPercentage(walkResult.aggregate_metrics?.average_return ?? 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">收益波动</span>
                    <span className="summary-strip__value">{formatPercentage(walkResult.aggregate_metrics?.return_std ?? 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均夏普</span>
                    <span className="summary-strip__value">{Number(walkResult.aggregate_metrics?.average_sharpe ?? 0).toFixed(2)}</span>
                  </div>
                </div>
                <Alert
                  type="info"
                  showIcon
                  message={`正收益窗口 ${walkResult.aggregate_metrics?.positive_windows ?? 0} 个，负收益窗口 ${walkResult.aggregate_metrics?.negative_windows ?? 0} 个`}
                  description="如果窗口之间表现差异很大，就说明策略更依赖某些特定市场阶段，稳定性需要继续验证。"
                />
                {walkInsight ? (
                  <Alert
                    type={walkInsight.type}
                    showIcon
                    message={walkInsight.title}
                    description={walkInsight.description}
                  />
                ) : null}
                {walkResult.monte_carlo?.available ? (
                  <div className="summary-strip">
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">模拟次数</span>
                      <span className="summary-strip__value">{walkResult.monte_carlo.simulations}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">平均收益 P10</span>
                      <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.mean_return_p10 ?? 0)}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">平均收益 P50</span>
                      <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.mean_return_p50 ?? 0)}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">负均值概率</span>
                      <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.negative_mean_probability ?? 0)}</span>
                    </div>
                  </div>
                ) : null}
                {walkResult.overfitting_diagnostics ? (
                  <Alert
                    type={
                      walkResult.overfitting_diagnostics.level === 'high'
                        ? 'warning'
                        : walkResult.overfitting_diagnostics.level === 'medium'
                          ? 'info'
                          : 'success'
                    }
                    showIcon
                    message={`样本外过拟合诊断：${walkResult.overfitting_diagnostics.level === 'high' ? '高风险' : walkResult.overfitting_diagnostics.level === 'medium' ? '中等风险' : '低风险'}`}
                    description={(walkResult.overfitting_diagnostics.warnings || []).join('；') || '训练窗与测试窗表现没有出现明显断裂。'}
                  />
                ) : null}
                {focusedWalkRecord ? (
                  <Alert
                    type="info"
                    showIcon
                    message={`当前聚焦：窗口 ${Number(focusedWalkRecord.window_id || 0) + 1}`}
                    description={`${focusedWalkRecord.test_start} ~ ${focusedWalkRecord.test_end}，窗口收益 ${formatPercentage(getMetricValue(focusedWalkRecord, 'total_return'))}，夏普 ${Number(getMetricValue(focusedWalkRecord, 'sharpe_ratio')).toFixed(2)}，最大回撤 ${formatPercentage(getMetricValue(focusedWalkRecord, 'max_drawdown'))}`}
                  />
                ) : null}
                {walkForwardChartData.length ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">窗口稳定性曲线</div>
                        <div className="workspace-section__description">观察每个测试窗口的收益和回撤变化，判断策略是否只在少数阶段有效。</div>
                      </div>
                    </div>
                    <div style={{ height: 320 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={walkForwardChartData}
                          margin={{ top: 8, right: 12, left: 8, bottom: 8 }}
                          onClick={(state) => {
                            const nextWindowKey = state?.activePayload?.[0]?.payload?.key;
                            if (nextWindowKey) {
                              setFocusedWalkWindowKey(nextWindowKey);
                            }
                          }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                          <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                          <YAxis
                            yAxisId="left"
                            tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`}
                            tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                          />
                          <YAxis
                            yAxisId="right"
                            orientation="right"
                            tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                          />
                          <RechartsTooltip content={renderWalkTooltip} />
                          <Legend />
                          <Line
                            yAxisId="left"
                            type="monotone"
                            dataKey="totalReturn"
                            name="窗口收益"
                            stroke={CHART_POSITIVE}
                            strokeWidth={2.5}
                            dot={(props) => {
                              const isFocused = props?.payload?.key === focusedWalkWindowKey;
                              return (
                                <circle
                                  cx={props.cx}
                                  cy={props.cy}
                                  r={isFocused ? 5 : 3}
                                  fill={CHART_POSITIVE}
                                  stroke={isFocused ? '#f8fafc' : CHART_POSITIVE}
                                  strokeWidth={isFocused ? 2 : 1}
                                />
                              );
                            }}
                            activeDot={{ r: 5 }}
                          />
                          <Line
                            yAxisId="left"
                            type="monotone"
                            dataKey="drawdown"
                            name="最大回撤绝对值"
                            stroke={CHART_NEGATIVE}
                            strokeWidth={2}
                            strokeDasharray="6 4"
                            dot={{ r: 2 }}
                          />
                          <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey="sharpe"
                            name="夏普比率"
                            stroke={CHART_NEUTRAL}
                            strokeWidth={2}
                            dot={{ r: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                ) : null}
                <Table
                  size="small"
                  rowKey={(record) => `${record.window_id}-${record.test_start}`}
                  dataSource={walkResult.window_results || []}
                  columns={walkColumns}
                  pagination={{ pageSize: 5, showSizeChanger: false }}
                  onRow={(record) => {
                    const rowKey = `${record.window_id}-${record.test_start}`;
                    return {
                      onClick: () => setFocusedWalkWindowKey(rowKey),
                      style: {
                        cursor: 'pointer',
                        background: focusedWalkWindowKey === rowKey ? 'rgba(14, 165, 233, 0.12)' : undefined,
                      },
                    };
                  }}
                />
              </Space>
            ) : (
              <Empty description="运行滚动前瞻分析后，这里会显示各窗口表现和聚合结果。" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={9}>
          <Card className="workspace-panel workspace-chart-card" title="稳健性评分">
            {robustnessScore || overfittingWarnings.length || researchConclusion ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                {robustnessScore ? (
                  <>
                    <Alert
                      type={robustnessScore.score >= 75 ? 'success' : robustnessScore.score >= 55 ? 'info' : 'warning'}
                      showIcon
                      message={`稳健性评分 ${robustnessScore.score} / 100`}
                      description={`当前结论：${robustnessScore.level}稳健性。${robustnessScore.summary}`}
                    />
                    <div className="summary-strip">
                      {robustnessScore.dimensions.map((dimension) => (
                        <div className="summary-strip__item" key={dimension.key}>
                          <span className="summary-strip__label">{dimension.label}</span>
                          <span className="summary-strip__value">{dimension.score}</span>
                        </div>
                      ))}
                    </div>
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(record) => record.key}
                      dataSource={robustnessScore.dimensions}
                      columns={[
                        { title: '维度', dataIndex: 'label', key: 'label' },
                        { title: '得分', dataIndex: 'score', key: 'score', render: (value) => `${value}` },
                        { title: '说明', dataIndex: 'detail', key: 'detail' },
                      ]}
                    />
                  </>
                ) : null}
                {overfittingWarnings.length ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">过拟合预警</div>
                        <div className="workspace-section__description">这些信号说明当前优势可能依赖少数参数、少数窗口或少数市场状态。</div>
                      </div>
                    </div>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      {overfittingWarnings.map((warning) => (
                        <Alert
                          key={warning.key}
                          type="warning"
                          showIcon
                          message={warning.title}
                          description={warning.description}
                        />
                      ))}
                    </Space>
                  </div>
                ) : null}
                {researchConclusion ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">自动研究结论</div>
                        <div className="workspace-section__description">把当前结果压缩成结论和下一步动作，减少人工读图和读表的成本。</div>
                      </div>
                    </div>
                    <Alert
                      type={overfittingWarnings.length ? 'warning' : 'success'}
                      showIcon
                      message={researchConclusion.title}
                      description={researchConclusion.summary}
                    />
                    <div className="summary-strip summary-strip--stack">
                      {researchConclusion.nextActions.map((action, index) => (
                        <div key={`${index + 1}-${action.slice(0, 12)}`} className="summary-strip__item">
                          <span className="summary-strip__label">下一步 {index + 1}</span>
                          <span className="summary-strip__value" style={{ whiteSpace: 'normal' }}>{action}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </Space>
            ) : (
              <Empty description="运行批量实验、滚动前瞻、基准对照或市场状态分析后，这里会给出稳健性评分、过拟合预警和自动研究结论。" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card className="workspace-panel workspace-chart-card" title="市场状态分层回测">
            {marketRegimeResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div className="summary-strip">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">市场状态数</span>
                    <span className="summary-strip__value">{marketRegimeResult.summary?.regime_count ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">正收益状态</span>
                    <span className="summary-strip__value">{marketRegimeResult.summary?.positive_regimes ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均阶段收益</span>
                    <span className="summary-strip__value">{formatPercentage(marketRegimeResult.summary?.average_regime_return ?? 0)}</span>
                  </div>
                </div>
                {marketRegimeInsight ? (
                  <Alert
                    type={marketRegimeInsight.type}
                    showIcon
                    message={marketRegimeInsight.title}
                    description={marketRegimeInsight.description}
                  />
                ) : null}
                {marketRegimeChartData.length ? (
                  <div style={{ height: 280 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={marketRegimeChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                        <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <YAxis tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <RechartsTooltip />
                        <Legend />
                        <Bar dataKey="strategyTotalReturn" name="策略收益" fill={CHART_POSITIVE} />
                        <Bar dataKey="marketTotalReturn" name="市场收益" fill={CHART_NEUTRAL} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : null}
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.regime}
                  dataSource={marketRegimeResult.regimes || []}
                  columns={[
                    { title: '市场状态', dataIndex: 'regime', key: 'regime' },
                    { title: '天数', dataIndex: 'days', key: 'days' },
                    { title: '策略收益', dataIndex: 'strategy_total_return', key: 'strategy_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '市场收益', dataIndex: 'market_total_return', key: 'market_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '胜率', dataIndex: 'win_rate', key: 'win_rate', render: (value) => formatPercentage(value || 0) },
                    { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                  ]}
                />
              </Space>
            ) : (
              <Empty description="运行市场状态分层回测后，这里会展示策略在不同市场状态下的表现差异。" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={12}>
          <Card className="workspace-panel workspace-chart-card" title="基准对照">
            {benchmarkResult?.data && benchmarkContext?.strategy ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <Alert
                  type={benchmarkSummary?.beatBenchmark ? 'success' : 'warning'}
                  showIcon
                  message={`${getStrategyName(benchmarkContext.strategy)} vs 买入持有`}
                  description={
                    benchmarkSummary
                      ? `${benchmarkContext.symbol} · ${benchmarkContext.dateRange?.filter(Boolean).join(' 至 ')}，超额收益 ${formatPercentage(benchmarkSummary.excessReturn)}，夏普差值 ${benchmarkSummary.sharpeDelta.toFixed(2)}，回撤差值 ${formatPercentage(-benchmarkSummary.drawdownDelta)}`
                      : '当前结果不足以生成基准对照摘要。'
                  }
                />
                {benchmarkChartData.length ? (
                  <div style={{ height: 260 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={benchmarkChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                        <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <YAxis tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <RechartsTooltip />
                        <Legend />
                        <Bar dataKey="totalReturn" name="总收益率" fill={CHART_POSITIVE} />
                        <Bar dataKey="drawdown" name="最大回撤绝对值" fill={CHART_NEGATIVE} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : null}
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.key}
                  dataSource={Object.entries(benchmarkResult.data).map(([key, value]) => ({
                    key,
                    strategy: getStrategyName(key),
                    total_return: value.total_return,
                    sharpe_ratio: value.sharpe_ratio,
                    max_drawdown: value.max_drawdown,
                    final_value: value.final_value,
                  }))}
                  columns={[
                    { title: '策略', dataIndex: 'strategy', key: 'strategy' },
                    { title: '总收益率', dataIndex: 'total_return', key: 'total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '夏普比率', dataIndex: 'sharpe_ratio', key: 'sharpe_ratio', render: (value) => Number(value || 0).toFixed(2) },
                    { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                    { title: '最终价值', dataIndex: 'final_value', key: 'final_value', render: (value) => formatCurrency(value || 0) },
                  ]}
                />
              </Space>
            ) : (
              <Empty description="运行基准对照后，这里会展示策略与买入持有的差异。" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="workspace-panel workspace-chart-card" title="组合级策略回测">
            {portfolioStrategyResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div className="summary-strip">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">组合收益</span>
                    <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.total_return || 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">年化收益</span>
                    <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.annualized_return || 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">最大回撤</span>
                    <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.max_drawdown || 0)}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">夏普比率</span>
                    <span className="summary-strip__value">{Number(portfolioStrategyResult.sharpe_ratio || 0).toFixed(2)}</span>
                  </div>
                </div>
                <Alert
                  type="info"
                  showIcon
                  message={`${getStrategyName(portfolioStrategyResult.strategy)} · 多资产组合`}
                  description={`当前版本使用同一策略同时作用于多个标的，并按权重合成为组合净值。当前权重模式：${
                    portfolioStrategyResult.portfolio_objective === 'max_sharpe'
                      ? '最大夏普'
                      : portfolioStrategyResult.portfolio_objective === 'min_volatility'
                        ? '最小波动'
                        : '等权组合'
                  }。`}
                />
                {portfolioExposureSummary ? (
                  <div className="summary-strip">
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">总暴露</span>
                      <span className="summary-strip__value">{formatPercentage(portfolioExposureSummary.grossExposure || 0)}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">净暴露</span>
                      <span className="summary-strip__value">{formatPercentage(portfolioExposureSummary.netExposure || 0)}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">现金余额</span>
                      <span className="summary-strip__value">{formatCurrency(portfolioExposureSummary.cash || 0)}</span>
                    </div>
                    <div className="summary-strip__item">
                      <span className="summary-strip__label">活跃头寸</span>
                      <span className="summary-strip__value">{portfolioExposureSummary.activePositions}</span>
                    </div>
                  </div>
                ) : null}
                {portfolioChartData.length ? (
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={12}>
                      <div style={{ height: 260 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={portfolioChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                            <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                            <RechartsTooltip />
                            <Line type="monotone" dataKey="total" name="组合净值" stroke={CHART_NEUTRAL} strokeWidth={2.5} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </Col>
                    <Col xs={24} xl={12}>
                      <div style={{ height: 260 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={portfolioChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                            <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                            <YAxis
                              tickFormatter={(value) => formatPercentage(Number(value || 0))}
                              tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                            />
                            <RechartsTooltip formatter={(value) => formatPercentage(Number(value || 0))} />
                            <Legend />
                            <Line type="monotone" dataKey="grossExposure" name="总暴露" stroke={CHART_POSITIVE} strokeWidth={2.2} dot={false} />
                            <Line type="monotone" dataKey="netExposure" name="净暴露" stroke={CHART_NEGATIVE} strokeWidth={2.2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </Col>
                  </Row>
                ) : null}
                <Row gutter={[16, 16]}>
                  <Col xs={24} xl={12}>
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(record) => record.symbol}
                      dataSource={portfolioStrategyResult.portfolio_components || []}
                      columns={[
                        { title: '标的', dataIndex: 'symbol', key: 'symbol' },
                        { title: '权重', dataIndex: 'weight', key: 'weight', render: (value) => formatPercentage(value || 0) },
                        { title: '总收益率', dataIndex: 'total_return', key: 'total_return', render: (value) => formatPercentage(value || 0) },
                        { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                        { title: '最终价值', dataIndex: 'final_value', key: 'final_value', render: (value) => formatCurrency(value || 0) },
                      ]}
                    />
                  </Col>
                  <Col xs={24} xl={12}>
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(record) => record.symbol}
                      locale={{ emptyText: '当前没有活跃头寸' }}
                      dataSource={portfolioPositionSnapshot}
                      columns={[
                        { title: '标的', dataIndex: 'symbol', key: 'symbol' },
                        {
                          title: '方向',
                          dataIndex: 'direction',
                          key: 'direction',
                          render: (value) => (
                            <Tag color={value === '多头' ? 'green' : 'red'}>{value}</Tag>
                          ),
                        },
                        {
                          title: '持仓份额',
                          dataIndex: 'shares',
                          key: 'shares',
                          render: (value) => formatCompactNumber(value),
                        },
                        {
                          title: '目标权重',
                          dataIndex: 'targetWeight',
                          key: 'targetWeight',
                          render: (value) => formatPercentage(value || 0),
                        },
                      ]}
                    />
                  </Col>
                </Row>
              </Space>
            ) : (
              <Empty description="运行组合级策略回测后，这里会展示组合表现和各资产贡献。" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default AdvancedBacktestLab;
