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
import {
  buildCrossMarketPlaybook,
  buildCrossMarketWorkbenchPayload,
} from './research-playbook/playbookViewModels';
import {
  addResearchTaskSnapshot,
  createResearchTask,
  getAltDataSnapshot,
  getCrossMarketTemplates,
  getMacroOverview,
  runCrossMarketBacktest,
} from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { useSafeMessageApi } from '../utils/messageApi';
import {
  buildCrossMarketCards,
  CROSS_MARKET_DIMENSION_LABELS,
  CROSS_MARKET_FACTOR_LABELS,
} from '../utils/crossMarketRecommendations';
import { formatResearchSource, navigateByResearchAction, readResearchContext } from '../utils/researchContext';

const { Paragraph, Text } = Typography;

const ASSET_CLASS_OPTIONS = [
  { value: 'US_STOCK', label: '美股' },
  { value: 'ETF', label: 'ETF 基金' },
  { value: 'COMMODITY_FUTURES', label: '商品期货' },
];

const ASSET_CLASS_LABELS = Object.fromEntries(
  ASSET_CLASS_OPTIONS.map((option) => [option.value, option.label])
);

const CONSTRUCTION_MODE_LABELS = {
  equal_weight: '等权配置',
  ols_hedge: '滚动 OLS 对冲',
};

const DEFAULT_PARAMETERS = {
  lookback: 20,
  entry_threshold: 1.5,
  exit_threshold: 0.5,
};

const DEFAULT_QUALITY = {
  construction_mode: 'equal_weight',
  min_history_days: 60,
  min_overlap_ratio: 0.7,
};

const createAsset = (side, index) => ({
  key: `${side}-${index}-${Date.now()}`,
  side,
  symbol: '',
  asset_class: 'ETF',
  weight: null,
});

const normalizeAssets = (assets, side) =>
  assets
    .filter((asset) => asset.side === side)
    .map((asset) => ({
      ...asset,
      symbol: (asset.symbol || '').trim().toUpperCase(),
    }));

const formatConstructionMode = (value) => CONSTRUCTION_MODE_LABELS[value] || value || '未设置';

const formatTradeAction = (value) => {
  const action = String(value || '').toUpperCase();
  if (!action) {
    return '-';
  }

  return action
    .replace('OPEN', '开仓')
    .replace('CLOSE', '平仓')
    .replace('LONG', '多头')
    .replace('SHORT', '空头')
    .replaceAll('_', ' ');
};

const formatExecutionChannel = (value = '') => {
  const mapping = {
    cash_equity: '现货股票',
    futures: '期货通道',
  };
  return mapping[value] || value || '-';
};

const formatVenue = (value = '') => {
  const mapping = {
    US_EQUITY: '美股主板',
    US_ETF: '美股 ETF',
    COMEX_CME: 'CME / COMEX',
  };
  return mapping[value] || value || '-';
};

const getConcentrationMeta = (level = '') => {
  const mapping = {
    high: { color: 'red', label: '高集中' },
    moderate: { color: 'orange', label: '中等集中' },
    balanced: { color: 'green', label: '相对均衡' },
  };
  return mapping[level] || { color: 'default', label: level || '未评估' };
};

const getCapacityMeta = (band = '') => {
  const mapping = {
    light: { color: 'green', label: '轻量' },
    moderate: { color: 'orange', label: '中等' },
    heavy: { color: 'red', label: '偏重' },
  };
  return mapping[band] || { color: 'default', label: band || '-' };
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
    bias_strength: appliedBiasMeta?.strength || 0,
    bias_highlights: appliedBiasMeta?.highlights || [],
    bias_actions: template.biasActions || [],
    signal_attribution: template.signalAttribution || [],
    driver_summary: template.driverSummary || [],
    dominant_drivers: template.dominantDrivers || [],
    core_legs: template.coreLegs || [],
    support_legs: template.supportLegs || [],
    theme_core: template.themeCore || '',
    theme_support: template.themeSupport || '',
    base_assets: (template.assets || []).map((asset) => ({
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
  const [savingTask, setSavingTask] = useState(false);
  const [assets, setAssets] = useState([
    createAsset('long', 0),
    createAsset('short', 0),
  ]);
  const [parameters, setParameters] = useState(DEFAULT_PARAMETERS);
  const [quality, setQuality] = useState(DEFAULT_QUALITY);
  const [meta, setMeta] = useState({
    initial_capital: 100000,
    commission: 0.1,
    slippage: 0.1,
    start_date: '',
    end_date: '',
  });
  const [results, setResults] = useState(null);
  const [researchContext, setResearchContext] = useState(readResearchContext());
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [savedTaskId, setSavedTaskId] = useState('');
  const [appliedBiasMeta, setAppliedBiasMeta] = useState(null);
  const [macroOverview, setMacroOverview] = useState(null);
  const [altSnapshot, setAltSnapshot] = useState(null);
  const appliedTemplateRef = useRef('');
  const autoRecommendedRef = useRef('');

  useEffect(() => {
    const loadTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const [templateResponse, macroResponse, snapshotResponse] = await Promise.all([
          getCrossMarketTemplates(),
          getMacroOverview(),
          getAltDataSnapshot(),
        ]);
        setTemplates(templateResponse.templates || []);
        setMacroOverview(macroResponse);
        setAltSnapshot(snapshotResponse);
      } catch (error) {
        message.error(error.userMessage || error.message || '加载模板失败');
      } finally {
        setLoadingTemplates(false);
      }
    };

    loadTemplates();
  }, [message]);

  useEffect(() => {
    const syncContext = () => setResearchContext(readResearchContext());
    syncContext();
    window.addEventListener('popstate', syncContext);
    return () => window.removeEventListener('popstate', syncContext);
  }, []);

  const longAssets = useMemo(() => normalizeAssets(assets, 'long'), [assets]);
  const shortAssets = useMemo(() => normalizeAssets(assets, 'short'), [assets]);
  const recommendedTemplates = useMemo(
    () =>
      buildCrossMarketCards(
        { templates },
        macroOverview || {},
        altSnapshot || {},
        (templateId, note) => ({
          label: '载入推荐模板',
          target: 'cross-market',
          template: templateId,
          source: 'cross_market_panel',
          note,
        })
      ),
    [altSnapshot, macroOverview, templates]
  );
  const selectedTemplate = useMemo(
    () =>
      recommendedTemplates.find((item) => item.id === selectedTemplateId)
      || recommendedTemplates.find((item) => item.id === researchContext.template)
      || templates.find((item) => item.id === selectedTemplateId)
      || templates.find((item) => item.id === researchContext.template)
      || null,
    [recommendedTemplates, templates, selectedTemplateId, researchContext.template]
  );
  const effectiveTemplate = useMemo(() => {
    if (!selectedTemplate) {
      return null;
    }
    if (!appliedBiasMeta) {
      return {
        ...selectedTemplate,
        biasSummary: '',
        biasStrength: 0,
        biasHighlights: [],
      };
    }
    return {
      ...selectedTemplate,
      biasSummary: appliedBiasMeta.summary || selectedTemplate.biasSummary || '',
      biasStrength: appliedBiasMeta.strength || selectedTemplate.biasStrength || 0,
      biasHighlights: appliedBiasMeta.highlights || selectedTemplate.biasHighlights || [],
    };
  }, [appliedBiasMeta, selectedTemplate]);
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
      ? (recommendedTemplates.find((item) => item.id === templateOrId) || templates.find((item) => item.id === templateOrId))
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
            strength: template.biasStrength || 0,
            highlights: template.biasHighlights || [],
          }
        : null
    );
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
  }, [message, recommendedTemplates, templates]);

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
    if (researchContext?.template || selectedTemplateId || !recommendedTemplates.length) {
      return;
    }
    const topRecommendation = recommendedTemplates[0];
    if (!topRecommendation || autoRecommendedRef.current === topRecommendation.id) {
      return;
    }
    autoRecommendedRef.current = topRecommendation.id;
    applyTemplate(topRecommendation, { useBias: true, silent: true });
    message.info(`已自动载入当前最优宏观模板: ${topRecommendation.name}`);
  }, [applyTemplate, message, recommendedTemplates, researchContext, selectedTemplateId]);

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
        template_context: buildTemplateContextPayload(selectedTemplate, appliedBiasMeta),
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

  const handleSaveTask = async () => {
    const payload = buildCrossMarketWorkbenchPayload(
      researchContext,
      effectiveTemplate,
      results,
      assets
    );
    if (!payload) {
      message.error('请先载入模板或配置篮子后再保存到研究工作台');
      return;
    }

    setSavingTask(true);
    try {
      const response = await createResearchTask(payload);
      setSavedTaskId(response.data?.id || '');
      message.success(`已保存到研究工作台: ${response.data?.title || payload.title}`);
    } catch (error) {
      message.error(error.userMessage || error.message || '保存研究任务失败');
    } finally {
      setSavingTask(false);
    }
  };

  const handleUpdateSnapshot = async () => {
    if (!savedTaskId) {
      message.info('请先保存任务，再更新当前任务快照');
      return;
    }

    const payload = buildCrossMarketWorkbenchPayload(
      researchContext,
      effectiveTemplate,
      results,
      assets
    );
    if (!payload?.snapshot) {
      message.error('当前还没有可更新的研究快照');
      return;
    }

    setSavingTask(true);
    try {
      await addResearchTaskSnapshot(savedTaskId, { snapshot: payload.snapshot });
      message.success('当前任务快照已更新');
    } catch (error) {
      message.error(error.userMessage || error.message || '更新任务快照失败');
    } finally {
      setSavingTask(false);
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
    ],
    []
  );
  const concentrationMeta = getConcentrationMeta(results?.execution_diagnostics?.concentration_level);
  const stressMeta = getConcentrationMeta(results?.execution_diagnostics?.stress_test_flag);

  return (
    <div className="workspace-tab-view" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="workspace-section workspace-section--accent">
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">跨市场回测</div>
            <div className="workspace-section__description">围绕模板、篮子构造、质量约束和研究联动完成跨资产策略实验，保持与主回测一致的工作台体验。</div>
          </div>
        </div>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            跨市场实验版
          </Tag>
          <div className="summary-strip summary-strip--compact">
            <div className="summary-strip__item">
              <span className="summary-strip__label">多头篮子</span>
              <span className="summary-strip__value">{longAssets.length} 个资产</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">空头篮子</span>
              <span className="summary-strip__value">{shortAssets.length} 个资产</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">构造模式</span>
              <span className="summary-strip__value">{formatConstructionMode(quality.construction_mode)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">状态</span>
              <span className="summary-strip__value">{running ? '运行中' : (results ? '结果已生成' : '待运行')}</span>
            </div>
          </div>
          <Paragraph style={{ marginBottom: 0 }}>
            这一页专门用来演示跨资产长短腿组合。当前版本支持美元计价、日频数据，
            并使用 `spread_zscore` 价差策略完成实验。
          </Paragraph>
        </Space>
      </div>

      {researchContext?.template ? (
        <Alert
          type="info"
          showIcon
          message={`已载入来自 ${formatResearchSource(researchContext.source)} 的跨市场模板 · ${playbook?.stageLabel || '待运行'}`}
          description={
            researchContext.note
              ? researchContext.note
              : `模板 ${researchContext.template} 已自动预载，可继续编辑后再运行回测。当前剧本阶段为 ${playbook?.stageLabel || '待运行'}。`
          }
        />
      ) : null}

      {playbook ? (
        <ResearchPlaybook
          playbook={playbook}
          onAction={(action) => navigateByResearchAction(action)}
          onSaveTask={handleSaveTask}
          onUpdateSnapshot={savedTaskId && (results || selectedTemplate || assets.length) ? handleUpdateSnapshot : null}
          saving={savingTask}
        />
      ) : null}

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
              <Space wrap size={[6, 6]}>
                {(selectedTemplate.linked_factors || []).map((factor) => (
                  <Tag key={factor} color="purple">
                    因子: {CROSS_MARKET_FACTOR_LABELS[factor] || factor}
                  </Tag>
                ))}
                {(selectedTemplate.linked_dimensions || []).map((dimension) => (
                  <Tag key={dimension} color="blue">
                    维度: {CROSS_MARKET_DIMENSION_LABELS[dimension] || dimension}
                  </Tag>
                ))}
              </Space>
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

      {!researchContext?.template && recommendedTemplates[0] ? (
        <Alert
          type="success"
          showIcon
          message={`当前首选模板：${recommendedTemplates[0].name}`}
          description={`${recommendedTemplates[0].driverHeadline}。${recommendedTemplates[0].biasSummary || '该模板会作为默认起点，你也可以在右侧改成其他模板。'}`}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {renderAssetSection('多头篮子', longAssets, 'long')}
            {renderAssetSection('空头篮子', shortAssets, 'short')}
          </Space>
        </Col>

        <Col xs={24} xl={8}>
          <Card title="参数与模板" variant="borderless" className="workspace-panel">
            <Space direction="vertical" style={{ width: '100%' }} size={14}>
              <Card size="small" className="workspace-panel workspace-panel--subtle" title="宏观推荐模板">
                <Space direction="vertical" style={{ width: '100%' }} size={10}>
                  {recommendedTemplates.slice(0, 3).map((template) => (
                    <div
                      key={template.id}
                      style={{
                        padding: 12,
                        borderRadius: 12,
                        border: selectedTemplate?.id === template.id ? '1px solid rgba(45, 183, 245, 0.65)' : '1px solid rgba(148, 163, 184, 0.16)',
                        background: selectedTemplate?.id === template.id ? 'rgba(24, 144, 255, 0.08)' : 'rgba(15, 23, 42, 0.24)',
                      }}
                    >
                      <Space wrap size={[6, 6]} style={{ marginBottom: 8 }}>
                        <Tag color={template.recommendationTone}>{template.recommendationTier}</Tag>
                        <Tag color="cyan">score {Number(template.recommendationScore || 0).toFixed(2)}</Tag>
                      </Space>
                      <div style={{ fontWeight: 600, marginBottom: 6 }}>{template.name}</div>
                      <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                        {template.driverHeadline}
                      </Text>
                      {template.biasSummary ? (
                        <Text style={{ display: 'block', marginBottom: 8 }}>
                          {template.biasSummary}
                        </Text>
                      ) : null}
                      <Space wrap size={[6, 6]} style={{ marginBottom: 10 }}>
                        {(template.matchedDrivers || []).slice(0, 3).map((driver) => (
                          <Tag key={driver.key} color={driver.type === 'factor' ? 'purple' : driver.type === 'alert' ? 'red' : 'blue'}>
                            {driver.label}
                          </Tag>
                        ))}
                        {template.biasStrength ? (
                          <Tag color="green">bias {Number(template.biasStrength).toFixed(1)}pp</Tag>
                        ) : null}
                      </Space>
                      <Button size="small" type={selectedTemplate?.id === template.id ? 'default' : 'primary'} onClick={() => applyTemplate(template, { useBias: true })}>
                        {selectedTemplate?.id === template.id ? '当前已载入' : '载入推荐模板'}
                      </Button>
                    </div>
                  ))}
                </Space>
              </Card>

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

              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Button icon={<ReloadOutlined />} onClick={() => setResults(null)}>
                  清空结果
                </Button>
                <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun}>
                  运行回测
                </Button>
              </Space>
            </Space>
          </Card>
        </Col>
      </Row>

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
            message="跨市场结果已生成"
            description={`样本区间 ${results.price_matrix_summary.start_date} 至 ${results.price_matrix_summary.end_date}，共 ${results.price_matrix_summary.row_count} 个对齐交易日。`}
          />

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

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="数据对齐诊断" variant="borderless" className="workspace-panel">
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="可交易日占比"
                      value={(results.data_alignment?.tradable_day_ratio || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="丢弃日期数"
                      value={results.data_alignment?.dropped_dates_count || 0}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="对齐后行数"
                      value={results.data_alignment?.aligned_row_count || 0}
                    />
                  </Col>
                </Row>
                <Table
                  style={{ marginTop: 16 }}
                  size="small"
                  rowKey="symbol"
                  pagination={false}
                  dataSource={results.data_alignment?.per_symbol || []}
                  columns={[
                    { title: '资产代码', dataIndex: 'symbol', key: 'symbol' },
                    {
                      title: '类别',
                      dataIndex: 'asset_class',
                      key: 'asset_class',
                      render: (value) => ASSET_CLASS_LABELS[value] || value,
                    },
                    {
                      title: 'Provider',
                      dataIndex: 'provider',
                      key: 'provider',
                      render: (value) => <Tag color="blue">{value || '-'}</Tag>,
                    },
                    { title: '原始行数', dataIndex: 'raw_rows', key: 'raw_rows' },
                    { title: '有效行数', dataIndex: 'valid_rows', key: 'valid_rows' },
                    {
                      title: '覆盖率',
                      dataIndex: 'coverage_ratio',
                      key: 'coverage_ratio',
                      render: (value) => formatPercentage(Number(value || 0)),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="执行诊断" variant="borderless" className="workspace-panel">
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="换手率"
                      value={results.execution_diagnostics?.turnover || 0}
                      precision={2}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="成本拖累"
                      value={(results.execution_diagnostics?.cost_drag || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="平均持有期"
                      value={results.execution_diagnostics?.avg_holding_period || 0}
                      precision={1}
                      suffix=" 天"
                    />
                  </Col>
                </Row>
                <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
                  <Col span={8}>
                    <Statistic
                      title="执行路由数"
                      value={results.execution_diagnostics?.route_count || results.execution_plan?.route_count || 0}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="批次数"
                      value={(results.execution_plan?.batches || []).length}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Provider 数"
                      value={Object.keys(results.execution_plan?.by_provider || {}).length}
                    />
                  </Col>
                </Row>
                <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
                  <Col span={12}>
                    <Statistic
                      title="计划资金"
                      value={results.execution_plan?.initial_capital || meta.initial_capital}
                      formatter={(value) => formatCurrency(Number(value || 0))}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="平均对冲比"
                      value={results.execution_plan?.avg_hedge_ratio || results.hedge_portfolio?.hedge_ratio?.average || 0}
                      precision={2}
                    />
                  </Col>
                </Row>
                <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
                  <Col span={12}>
                    <Statistic
                      title="Lot 效率"
                      value={(results.execution_diagnostics?.lot_efficiency || results.execution_plan?.sizing_summary?.lot_efficiency || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="残余资金"
                      value={results.execution_diagnostics?.residual_notional || results.execution_plan?.sizing_summary?.total_residual_notional || 0}
                      formatter={(value) => formatCurrency(Number(value || 0))}
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 16 }}>
                  <Tag color="purple">
                    {formatConstructionMode(results.execution_diagnostics?.construction_mode || quality.construction_mode)}
                  </Tag>
                  <Tag color={concentrationMeta.color}>
                    {concentrationMeta.label}
                  </Tag>
                  {results.execution_diagnostics?.suggested_rebalance ? (
                    <Tag color="geekblue">建议调仓 {results.execution_diagnostics.suggested_rebalance}</Tag>
                  ) : null}
                  <Text type="secondary"> 当前对冲构造模式</Text>
                </div>
                {results.execution_diagnostics?.concentration_reason ? (
                  <Alert
                    style={{ marginTop: 16 }}
                    type={results.execution_diagnostics?.concentration_level === 'high' ? 'warning' : 'info'}
                    showIcon
                    message="执行集中度提示"
                    description={results.execution_diagnostics.concentration_reason}
                  />
                ) : null}
                {Number(results.execution_diagnostics?.residual_notional || 0) > 0 ? (
                  <Alert
                    style={{ marginTop: 16 }}
                    type="info"
                    showIcon
                    message="最小交易单位提示"
                    description={`按最新价格和 lot size 换算后，预计有 ${formatCurrency(Number(results.execution_diagnostics?.residual_notional || 0))} 的名义金额无法精确贴合目标权重。`}
                  />
                ) : null}
                {results.execution_diagnostics?.stress_test_flag ? (
                  <Alert
                    style={{ marginTop: 16 }}
                    type={results.execution_diagnostics.stress_test_flag === 'high' ? 'warning' : 'info'}
                    showIcon
                    message={`压力测试最坏情景：${stressMeta.label}`}
                    description={results.execution_diagnostics.stress_test_reason || '已根据资金放大情景评估路由拥挤度。'}
                  />
                ) : null}
              </Card>
            </Col>
          </Row>

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
                <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Text type="secondary">
                    多头权重 {formatPercentage(results.hedge_portfolio?.long_weight || 0)} ·
                    空头权重 {formatPercentage(results.hedge_portfolio?.short_weight || 0)} ·
                    有效空头 {formatPercentage(results.hedge_portfolio?.effective_short_weight || 0)}
                  </Text>
                  <Text type="secondary">
                    Hedge Ratio 区间 {Number(results.hedge_portfolio?.hedge_ratio?.min || 0).toFixed(2)} ~ {Number(results.hedge_portfolio?.hedge_ratio?.max || 0).toFixed(2)}
                  </Text>
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
            <Col xs={24}>
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

          <Card title="资产篮子摘要" variant="borderless">
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Text strong>多头篮子</Text>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {results.leg_performance.long.assets.map((asset) => (
                    <Tag key={`long-${asset.symbol}`}>{asset.symbol} · {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
                  ))}
                </div>
              </Col>
              <Col xs={24} md={12}>
                <Text strong>空头篮子</Text>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {results.leg_performance.short.assets.map((asset) => (
                    <Tag key={`short-${asset.symbol}`}>{asset.symbol} · {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
                  ))}
                </div>
              </Col>
            </Row>
          </Card>

          {results.allocation_overlay ? (
            <Card title="权重偏置对照" variant="borderless">
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Space wrap size={[8, 8]}>
                  <Tag color={results.allocation_overlay.allocation_mode === 'macro_bias' ? 'green' : 'default'}>
                    {results.allocation_overlay.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
                  </Tag>
                  {results.allocation_overlay.theme ? <Tag color="blue">{results.allocation_overlay.theme}</Tag> : null}
                  {results.allocation_overlay.bias_strength ? <Tag color="green">bias {Number(results.allocation_overlay.bias_strength).toFixed(1)}pp</Tag> : null}
                </Space>
                {results.allocation_overlay.bias_summary ? (
                  <Text>{results.allocation_overlay.bias_summary}</Text>
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
                {results.allocation_overlay.theme_core ? (
                  <Text type="secondary">核心腿：{results.allocation_overlay.theme_core}</Text>
                ) : null}
                {results.allocation_overlay.theme_support ? (
                  <Text type="secondary">辅助腿：{results.allocation_overlay.theme_support}</Text>
                ) : null}
                <Text type="secondary">
                  偏移资产 {results.allocation_overlay.shifted_asset_count || 0} 个 · 最大偏移 {(Number(results.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
                </Text>
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
        </div>
      ) : null}
    </div>
  );
}

export default CrossMarketBacktestPanel;
