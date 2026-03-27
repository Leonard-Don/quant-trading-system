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
import moment from 'moment';
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

import { compareStrategies, runBatchBacktest, runPortfolioStrategyBacktest, runWalkForwardBacktest, saveAdvancedHistoryRecord } from '../services/api';
import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../constants/strategies';
import { formatPercentage, formatCurrency, getValueColor } from '../utils/formatting';
import { useSafeMessageApi } from '../utils/messageApi';
import { consumeAdvancedExperimentIntent, loadBacktestWorkspaceDraft } from '../utils/backtestWorkspace';
import {
  buildBatchDraftState,
  buildBatchInsight,
  buildWalkForwardInsight,
} from '../utils/advancedBacktestLab';
import {
  buildBenchmarkSummary,
  buildCostSensitivityTasks,
  buildMultiSymbolTasks,
  buildParameterOptimizationTasks,
  buildRobustnessTasks,
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

function AdvancedBacktestLab({ strategies }) {
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
  const [benchmarkResult, setBenchmarkResult] = useState(null);
  const [portfolioStrategyResult, setPortfolioStrategyResult] = useState(null);
  const [focusedBatchTaskId, setFocusedBatchTaskId] = useState('');
  const [focusedWalkWindowKey, setFocusedWalkWindowKey] = useState('');
  const [batchConfigs, setBatchConfigs] = useState({});
  const [walkParams, setWalkParams] = useState({});
  const [researchSymbolsInput, setResearchSymbolsInput] = useState('AAPL,MSFT,NVDA');
  const [optimizationDensity, setOptimizationDensity] = useState(3);
  const [portfolioObjective, setPortfolioObjective] = useState('equal_weight');
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
  const benchmarkSummary = useMemo(
    () => buildBenchmarkSummary(benchmarkResult?.data, selectedWalkStrategy),
    [benchmarkResult, selectedWalkStrategy]
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
    () => (portfolioStrategyResult?.portfolio_history || []).map((point) => ({
      date: point.date,
      total: Number(point.total || 0),
    })),
    [portfolioStrategyResult]
  );

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
  ];

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
      const response = await runWalkForwardBacktest({
        symbol: values.symbol.trim().toUpperCase(),
        strategy: values.strategy,
        parameters: walkParams,
        start_date: values.dateRange?.[0]?.format(DATE_FORMAT),
        end_date: values.dateRange?.[1]?.format(DATE_FORMAT),
        initial_capital: values.initial_capital,
        commission: (values.commission ?? DEFAULT_COMMISSION) / 100,
        slippage: (values.slippage ?? DEFAULT_SLIPPAGE) / 100,
        train_period: values.train_period,
        test_period: values.test_period,
        step_size: values.step_size,
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
      ? [moment(draft.dateRange[0], DATE_FORMAT), moment(draft.dateRange[1], DATE_FORMAT)]
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
                dateRange: [moment().subtract(1, 'year'), moment()],
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
                dateRange: [moment().subtract(2, 'year'), moment()],
                initial_capital: DEFAULT_CAPITAL,
                commission: DEFAULT_COMMISSION,
                slippage: DEFAULT_SLIPPAGE,
                train_period: 252,
                test_period: 63,
                step_size: 21,
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
                      <div className="workspace-section__description">滚动前瞻分析会在每个窗口内用同一组参数进行滚动评估。</div>
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
        <Col xs={24} xl={12}>
          <Card className="workspace-panel workspace-chart-card" title="基准对照">
            {benchmarkResult?.data && selectedWalkStrategy ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <Alert
                  type={benchmarkSummary?.beatBenchmark ? 'success' : 'warning'}
                  showIcon
                  message={`${getStrategyName(selectedWalkStrategy)} vs 买入持有`}
                  description={
                    benchmarkSummary
                      ? `超额收益 ${formatPercentage(benchmarkSummary.excessReturn)}，夏普差值 ${benchmarkSummary.sharpeDelta.toFixed(2)}，回撤差值 ${formatPercentage(-benchmarkSummary.drawdownDelta)}`
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
                {portfolioChartData.length ? (
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
                ) : null}
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
