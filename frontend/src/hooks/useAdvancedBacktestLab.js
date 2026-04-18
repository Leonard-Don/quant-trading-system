import { useCallback, useEffect, useMemo, useState } from 'react';
import { Form } from 'antd';
import dayjs from '../utils/dayjs';
import {
  compareStrategies,
  runBatchBacktest,
  runMarketRegimeBacktest,
  runPortfolioStrategyBacktest,
  runWalkForwardBacktest,
  saveAdvancedHistoryRecord,
} from '../services/api';
import { getStrategyName } from '../constants/strategies';
import { formatPercentage } from '../utils/formatting';
import { getApiErrorMessage, useSafeMessageApi } from '../utils/messageApi';
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

const DATE_FORMAT = 'YYYY-MM-DD';
const DEFAULT_CAPITAL = 10000;
const DEFAULT_COMMISSION = 0.1;
const DEFAULT_SLIPPAGE = 0.1;
const DEFAULT_BATCH_EXPERIMENT_META = {
  title: '批量回测结果',
  description: '同一实验上下文下的多任务回测结果会集中展示在这里。',
};

const buildDefaultParams = (strategy) =>
  Object.fromEntries(
    Object.entries(strategy?.parameters || {}).map(([key, config]) => [key, config.default])
  );

const getMetricValue = (record, key) => Number(record?.metrics?.[key] ?? record?.[key] ?? 0);
const formatCompactNumber = (value) => Number(value || 0).toFixed(2);

export { DATE_FORMAT, DEFAULT_CAPITAL, DEFAULT_COMMISSION, DEFAULT_SLIPPAGE, getMetricValue, formatCompactNumber };

export default function useAdvancedBacktestLab({ strategies, onImportTemplateToMainBacktest }) {
  const message = useSafeMessageApi();
  const strategyDefinitions = useMemo(
    () => Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy])),
    [strategies]
  );

  // --- Core state ---
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
  const [batchExperimentMeta, setBatchExperimentMeta] = useState(DEFAULT_BATCH_EXPERIMENT_META);
  const [batchPendingMeta, setBatchPendingMeta] = useState(null);
  const [importedMainDraftSummary, setImportedMainDraftSummary] = useState(null);

  // --- Forms ---
  const [batchForm] = Form.useForm();
  const [walkForm] = Form.useForm();
  const watchedBatchValuesRaw = Form.useWatch([], batchForm);
  const watchedWalkValuesRaw = Form.useWatch([], walkForm);
  const watchedBatchValues = useMemo(() => watchedBatchValuesRaw || {}, [watchedBatchValuesRaw]);
  const watchedWalkValues = useMemo(() => watchedWalkValuesRaw || {}, [watchedWalkValuesRaw]);
  const watchedBatchStrategies = Form.useWatch('strategies', batchForm);
  const selectedBatchStrategies = useMemo(() => watchedBatchStrategies || [], [watchedBatchStrategies]);
  const selectedWalkStrategy = Form.useWatch('strategy', walkForm);

  // --- Sync strategy params ---
  useEffect(() => {
    if (!selectedBatchStrategies.length) return;
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
    if (!selectedWalkStrategy) return;
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
      [strategyName]: { ...(previous[strategyName] || {}), [key]: value },
    }));
  };

  // --- Derived data ---
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

  const walkForwardChartData = useMemo(
    () =>
      (walkResult?.window_results || []).map((record) => ({
        key: `${record.window_id}-${record.test_start}`,
        label: `窗口 ${Number(record.window_id || 0) + 1}`,
        totalReturn: getMetricValue(record, 'total_return'),
        sharpe: getMetricValue(record, 'sharpe_ratio'),
        drawdown: Math.abs(getMetricValue(record, 'max_drawdown')),
        testRange: `${record.test_start} ~ ${record.test_end}`,
      })),
    [walkResult]
  );

  const focusedBatchRecord = useMemo(
    () => batchRecords.find((record) => record.task_id === focusedBatchTaskId) || null,
    [batchRecords, focusedBatchTaskId]
  );

  const focusedWalkRecord = useMemo(
    () =>
      (walkResult?.window_results || []).find(
        (record) => `${record.window_id}-${record.test_start}` === focusedWalkWindowKey
      ) || null,
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
    () => buildRobustnessScore({ batchResult, walkResult, benchmarkSummary, marketRegimeResult }),
    [batchResult, benchmarkSummary, marketRegimeResult, walkResult]
  );
  const overfittingWarnings = useMemo(
    () => buildOverfittingWarnings({ batchResult, walkResult, benchmarkSummary, marketRegimeResult }),
    [batchResult, benchmarkSummary, marketRegimeResult, walkResult]
  );
  const researchConclusion = useMemo(
    () =>
      buildResearchConclusion({
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
    () =>
      Object.entries(benchmarkResult?.data || {}).map(([key, value]) => ({
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
    () =>
      (marketRegimeResult?.regimes || []).map((item) => ({
        key: item.regime,
        label: item.regime,
        strategyTotalReturn: Number(item.strategy_total_return || 0),
        marketTotalReturn: Number(item.market_total_return || 0),
        days: Number(item.days || 0),
      })),
    [marketRegimeResult]
  );
  const currentSnapshot = useMemo(
    () =>
      buildAdvancedExperimentSnapshot({
        batchResult,
        walkResult,
        benchmarkSummary,
        benchmarkContext,
        marketRegimeResult,
        portfolioStrategyResult,
        batchExperimentMeta,
        batchValues: watchedBatchValues,
        walkValues: watchedWalkValues,
        batchConfigs,
        walkParams,
        researchSymbolsInput,
        optimizationDensity,
        portfolioObjective,
        robustnessScore,
      }),
    [
      batchConfigs,
      batchExperimentMeta,
      batchResult,
      benchmarkContext,
      benchmarkSummary,
      marketRegimeResult,
      optimizationDensity,
      portfolioObjective,
      portfolioStrategyResult,
      researchSymbolsInput,
      robustnessScore,
      walkParams,
      watchedBatchValues,
      watchedWalkValues,
      walkResult,
    ]
  );
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
    () =>
      templateCategoryFilter === 'all'
        ? savedTemplates
        : savedTemplates.filter((template) => (template.category || 'general') === templateCategoryFilter),
    [savedTemplates, templateCategoryFilter]
  );
  const groupedTemplateOptions = useMemo(() => {
    const groups = filteredTemplates.reduce((accumulator, template) => {
      const category = template.pinned ? 'pinned' : template.category || 'general';
      if (!accumulator[category]) accumulator[category] = [];
      accumulator[category].push({
        value: template.id,
        label: template.pinned ? `★ ${template.name}` : template.name,
      });
      return accumulator;
    }, {});
    return Object.entries(groups).map(([category, options]) => ({
      label: category === 'pinned' ? '已置顶模板' : ADVANCED_TEMPLATE_CATEGORY_LABELS[category] || category,
      options,
    }));
  }, [filteredTemplates]);
  const experimentComparison = useMemo(
    () =>
      buildExperimentComparison({
        currentSnapshot,
        previousSnapshot: selectedSnapshot,
        formatPercentage,
        formatNumber: formatCompactNumber,
      }),
    [currentSnapshot, selectedSnapshot]
  );

  // --- Focus tracking ---
  useEffect(() => {
    if (!batchRecords.length) {
      setFocusedBatchTaskId('');
      return;
    }
    setFocusedBatchTaskId((previous) =>
      batchRecords.some((record) => record.task_id === previous) ? previous : batchRecords[0].task_id
    );
  }, [batchRecords]);

  useEffect(() => {
    const windowResults = walkResult?.window_results || [];
    if (!windowResults.length) {
      setFocusedWalkWindowKey('');
      return;
    }
    setFocusedWalkWindowKey((previous) => {
      const nextKey = `${windowResults[0].window_id}-${windowResults[0].test_start}`;
      return windowResults.some((record) => `${record.window_id}-${record.test_start}` === previous)
        ? previous
        : nextKey;
    });
  }, [walkResult]);

  // --- Template & snapshot handlers ---
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
    const resolvedName =
      String(templateName || '').trim() ||
      suggestAdvancedExperimentTemplateName({
        batchValues,
        walkValues,
        batchExperimentMeta,
        optimizationDensity,
        portfolioObjective,
      });

    const savedTemplate = saveAdvancedExperimentTemplate(
      buildAdvancedExperimentTemplatePayload({
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
      })
    );
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

    batchForm.setFieldsValue({ ...template.batch, dateRange: nextBatchDateRange });
    walkForm.setFieldsValue({ ...template.walk, dateRange: nextWalkDateRange });
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
    message.success(`已将模板"${template.name}"带回主回测`);
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

  // --- Experiment execution handlers ---
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
    const nextMeta = DEFAULT_BATCH_EXPERIMENT_META;
    setBatchPendingMeta(nextMeta);
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
      setBatchExperimentMeta(nextMeta);
      message.success('批量实验已完成');
    } catch (error) {
      message.error(getApiErrorMessage(error, '批量实验失败'));
    } finally {
      setBatchPendingMeta(null);
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
      message.error(getApiErrorMessage(error, '滚动前瞻分析失败'));
    } finally {
      setWalkLoading(false);
    }
  };

  const getWalkBaseline = useCallback(() => {
    const values = walkForm.getFieldsValue();
    const symbol = String(values.symbol || '').trim().toUpperCase();
    const strategy = values.strategy;
    if (!symbol || !strategy) return null;
    return {
      symbol,
      strategy,
      dateRange: [values.dateRange?.[0]?.format(DATE_FORMAT), values.dateRange?.[1]?.format(DATE_FORMAT)],
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
    setBatchPendingMeta(meta);
    try {
      const response = await runBatchBacktest({ ranking_metric: 'sharpe_ratio', tasks });
      if (!response.success) throw new Error(response.error || '实验执行失败');
      setBatchResult(response.data);
      setBatchExperimentMeta(meta);
      message.success(`${meta.title}已完成`);
    } catch (error) {
      message.error(getApiErrorMessage(error, '实验执行失败'));
    } finally {
      setBatchPendingMeta(null);
      setBatchLoading(false);
    }
  };

  const handleRunParameterOptimization = async () => {
    const baseline = getWalkBaseline();
    if (!baseline) {
      message.warning('请先在滚动前瞻分析里选择标的和策略');
      return;
    }
    const tasks = buildParameterOptimizationTasks({ ...baseline, density: optimizationDensity });
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
      if (!response.success) throw new Error(response.error || '基准对照失败');
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
      message.error(getApiErrorMessage(error, '基准对照失败'));
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
    await runResearchBatchTasks(buildMultiSymbolTasks({ ...baseline, symbols }), {
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
      if (!response.success) throw new Error(response.error || '组合级策略回测失败');
      setPortfolioStrategyResult(response.data);
      message.success('组合级策略回测已完成');
    } catch (error) {
      message.error(getApiErrorMessage(error, '组合级策略回测失败'));
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
      if (!response.success) throw new Error(response.error || '市场状态分层回测失败');
      setMarketRegimeResult(response.data);
      message.success('市场状态分层回测已完成');
    } catch (error) {
      message.error(getApiErrorMessage(error, '市场状态分层回测失败'));
    } finally {
      setMarketRegimeLoading(false);
    }
  }, [getWalkBaseline, message]);

  // --- Save / Export ---
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
      if (!response?.success) throw new Error(response?.error || '保存失败');
      message.success('批量回测结果已保存到历史');
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存批量回测结果失败'));
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
        ...(walkResult.window_results || []).map(
          (item) => Number(item?.metrics?.max_drawdown ?? item?.max_drawdown ?? 0)
        )
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
      if (!response?.success) throw new Error(response?.error || '保存失败');
      message.success('滚动前瞻分析结果已保存到历史');
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存滚动前瞻分析结果失败'));
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

  // --- Import from main backtest ---
  const handleApplyMainBacktestDraft = useCallback(() => {
    const draft = buildBatchDraftState(loadBacktestWorkspaceDraft());
    if (!draft) {
      message.warning('暂未找到主回测配置，请先在"新建回测"页配置一次策略。');
      return;
    }

    const strategyExists = Boolean(strategyDefinitions[draft.strategy]);
    const previousBatchValues = batchForm.getFieldsValue();
    const previousWalkValues = walkForm.getFieldsValue();
    const previousDateRange = [
      previousWalkValues.dateRange?.[0]?.format(DATE_FORMAT) || previousBatchValues.dateRange?.[0]?.format(DATE_FORMAT),
      previousWalkValues.dateRange?.[1]?.format(DATE_FORMAT) || previousBatchValues.dateRange?.[1]?.format(DATE_FORMAT),
    ];
    const nextDateRangeLabel = (draft.dateRange || []).filter(Boolean).join(' ~ ') || '未设置';
    const nextDateRange = draft.dateRange
      ? [dayjs(draft.dateRange[0], DATE_FORMAT), dayjs(draft.dateRange[1], DATE_FORMAT)]
      : undefined;
    const changedFields = [];
    if ((previousWalkValues.symbol || previousBatchValues.symbol || '') !== draft.symbol) {
      changedFields.push('标的');
    }
    if (previousDateRange[0] !== draft.dateRange?.[0] || previousDateRange[1] !== draft.dateRange?.[1]) {
      changedFields.push('区间');
    }
    if ((previousWalkValues.strategy || previousBatchValues.strategies?.[0] || '') !== draft.strategy) {
      changedFields.push('策略');
    }
    if (
      Number(previousWalkValues.initial_capital ?? previousBatchValues.initial_capital ?? DEFAULT_CAPITAL)
      !== Number(draft.initial_capital ?? DEFAULT_CAPITAL)
    ) {
      changedFields.push('资金');
    }
    if (
      Number(previousWalkValues.commission ?? previousBatchValues.commission ?? DEFAULT_COMMISSION)
      !== Number(draft.commission ?? DEFAULT_COMMISSION)
      || Number(previousWalkValues.slippage ?? previousBatchValues.slippage ?? DEFAULT_SLIPPAGE)
      !== Number(draft.slippage ?? DEFAULT_SLIPPAGE)
    ) {
      changedFields.push('成本');
    }
    if (JSON.stringify(walkParams || {}) !== JSON.stringify(draft.parameters || {})) {
      changedFields.push('参数');
    }

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
      const mergedParams = { ...defaultParams, ...(draft.parameters || {}) };
      setBatchConfigs((previous) => ({ ...previous, [draft.strategy]: mergedParams }));
      setWalkParams(mergedParams);
      setImportedMainDraftSummary({
        symbol: draft.symbol,
        dateRangeLabel: nextDateRangeLabel,
        strategyLabel: getStrategyName(draft.strategy),
        changedFields: changedFields.length ? changedFields : ['未检测到字段变化'],
      });
      message.success('已带入主回测当前配置，可直接运行高级实验');
      return;
    }
    setImportedMainDraftSummary({
      symbol: draft.symbol,
      dateRangeLabel: nextDateRangeLabel,
      strategyLabel: draft.strategy || '当前策略未匹配',
      changedFields: changedFields.length ? changedFields : ['未检测到字段变化'],
    });
    message.warning('主回测策略已带入，但当前高级实验页暂不支持该策略参数面板。');
  }, [batchForm, message, strategyDefinitions, walkForm, walkParams]);

  useEffect(() => {
    const intent = consumeAdvancedExperimentIntent();
    if (intent?.type === 'import_main_backtest') {
      handleApplyMainBacktestDraft();
    }
  }, [handleApplyMainBacktestDraft]);

  return {
    // Forms
    batchForm,
    walkForm,
    // Loading states
    batchLoading,
    walkLoading,
    benchmarkLoading,
    portfolioLoading,
    marketRegimeLoading,
    // Results
    batchResult,
    walkResult,
    benchmarkResult,
    benchmarkContext,
    portfolioStrategyResult,
    marketRegimeResult,
    // Derived data
    batchRankingData,
    batchRecords,
    walkForwardChartData,
    focusedBatchRecord,
    focusedWalkRecord,
    batchInsight,
    walkInsight,
    marketRegimeInsight,
    benchmarkSummary,
    benchmarkChartData,
    portfolioChartData,
    portfolioPositionSnapshot,
    portfolioExposureSummary,
    marketRegimeChartData,
    robustnessScore,
    overfittingWarnings,
    researchConclusion,
    batchExperimentMeta,
    batchPendingMeta,
    importedMainDraftSummary,
    // Focus state
    focusedBatchTaskId,
    setFocusedBatchTaskId,
    focusedWalkWindowKey,
    setFocusedWalkWindowKey,
    // Strategy state
    strategyDefinitions,
    selectedBatchStrategies,
    selectedWalkStrategy,
    batchConfigs,
    walkParams,
    setWalkParams,
    updateBatchParam,
    // Research tools state
    researchSymbolsInput,
    setResearchSymbolsInput,
    optimizationDensity,
    setOptimizationDensity,
    portfolioObjective,
    setPortfolioObjective,
    // Template state
    templateName,
    setTemplateName,
    templateNote,
    setTemplateNote,
    templateCategoryFilter,
    setTemplateCategoryFilter,
    selectedTemplateId,
    setSelectedTemplateId,
    savedTemplates,
    selectedTemplate,
    selectedTemplatePreview,
    groupedTemplateOptions,
    // Snapshot state
    savedSnapshots,
    selectedSnapshotId,
    setSelectedSnapshotId,
    currentSnapshot,
    experimentComparison,
    // Handlers
    handleRunBatch,
    handleRunWalkForward,
    handleRunParameterOptimization,
    handleRunBenchmarkComparison,
    handleRunMultiSymbolResearch,
    handleRunCostSensitivity,
    handleRunRobustnessDiagnostic,
    handleRunPortfolioStrategy,
    handleRunMarketRegimeAnalysis,
    handleSaveBatchHistory,
    handleSaveWalkHistory,
    handleExportBatch,
    handleExportWalkForward,
    handleSaveTemplate,
    handleOverwriteTemplate,
    handleSuggestTemplateName,
    handleApplyTemplate,
    handleDeleteTemplate,
    handleTogglePinnedTemplate,
    handleImportTemplateToMainBacktest,
    handleSaveSnapshot,
    handleApplyMainBacktestDraft,
  };
}
