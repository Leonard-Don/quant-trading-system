import React, { useState, useCallback, useEffect, useMemo, useRef, startTransition, useDeferredValue } from 'react';
import {
  Card, Row, Col, Input, Button, Select, Spin, Statistic, Tag, Space,
  Descriptions, Table, Alert, Typography, Tooltip, Divider, Empty, message,
  AutoComplete, Progress, Skeleton, Slider
} from 'antd';
import {
  SearchOutlined, FundOutlined, DollarOutlined, SwapOutlined,
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
  InfoCircleOutlined, ExperimentOutlined, ThunderboltOutlined, DownloadOutlined
} from '@ant-design/icons';
import {
  addResearchTaskSnapshot,
  createResearchTask,
  getGapAnalysis,
  getPricingGapHistory,
  getPricingPeerComparison,
  getPricingSymbolSuggestions,
  getResearchTasks,
  getValuationSensitivityAnalysis,
} from '../services/api';
import ResearchPlaybook from './research-playbook/ResearchPlaybook';
import { buildPricingPlaybook, buildPricingWorkbenchPayload } from './research-playbook/playbookViewModels';
import { buildAppUrl, formatResearchSource, navigateByResearchAction, readResearchContext } from '../utils/researchContext';
import {
  buildRecentPricingResearchEntries,
  buildScreeningRowFromAnalysis,
  getDriverImpactMeta,
  HOT_PRICING_SYMBOLS,
  getPriceSourceLabel,
  getSignalStrengthMeta,
  mergePricingSuggestions,
  parsePricingUniverseInput,
  resolveAnalysisSymbol,
  SCREENING_PRESETS,
  sortScreeningRows,
  buildPricingActionPosture,
} from '../utils/pricingResearch';
import { exportToJSON } from '../utils/export';
import {
  buildPricingResearchAuditPayload,
  buildPricingResearchReportHtml,
  openPricingResearchPrintWindow,
} from '../utils/pricingResearchReport';
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  Cell,
  LineChart,
  Line,
  AreaChart,
  Area,
  Legend,
  ComposedChart,
} from 'recharts';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const DISPLAY_EMPTY = '—';
const DEFAULT_SCREENING_UNIVERSE = 'AAPL\nMSFT\nNVDA\nAMZN\nGOOGL';
const SEARCH_HISTORY_KEY = 'pricing-research-history';
const ALIGNMENT_TAG_COLORS = {
  aligned: 'green',
  conflict: 'red',
  partial: 'gold',
  neutral: 'default',
};

function SensitivityAnalysisCard({
  symbol,
  loading,
  error,
  sensitivity,
  controls,
  onControlChange,
  onRun,
}) {
  const matrix = sensitivity?.sensitivity_matrix || [];
  const heatmapRows = matrix.flatMap((row) => (row.cases || []).map((item) => ({
    key: `${row.growth}-${item.wacc}`,
    growth: row.growth,
    wacc: item.wacc,
    fair_value: item.fair_value,
  })));

  return (
    <Card title="敏感性分析 / What-If">
      <Paragraph type="secondary">
        调整折现率、增长率和现金流转化率，观察公允价值如何变化。当前标的：{resolveAnalysisSymbol(symbol) || '未选择'}。
      </Paragraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Text>WACC</Text>
          <Slider min={5} max={15} step={0.1} value={controls.wacc} onChange={(value) => onControlChange((prev) => ({ ...prev, wacc: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <Text>初始增长率</Text>
          <Slider min={2} max={25} step={0.5} value={controls.initialGrowth} onChange={(value) => onControlChange((prev) => ({ ...prev, initialGrowth: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <Text>终值增长率</Text>
          <Slider min={1} max={5} step={0.1} value={controls.terminalGrowth} onChange={(value) => onControlChange((prev) => ({ ...prev, terminalGrowth: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <Text>FCF 转化率</Text>
          <Slider min={50} max={95} step={1} value={controls.fcfMargin} onChange={(value) => onControlChange((prev) => ({ ...prev, fcfMargin: value }))} />
        </Col>
      </Row>
      <Space style={{ marginTop: 12, marginBottom: 12 }}>
        <Button type="primary" onClick={onRun} loading={loading}>刷新敏感性分析</Button>
        <Tag>{`WACC ${controls.wacc}%`}</Tag>
        <Tag>{`增长 ${controls.initialGrowth}%`}</Tag>
      </Space>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !heatmapRows.length ? (
        <Empty description="运行敏感性分析后查看不同假设下的公允价值变化" />
      ) : null}
      {heatmapRows.length ? (
        <Table
          size="small"
          pagination={false}
          dataSource={heatmapRows}
          columns={[
            { title: '增长率', dataIndex: 'growth', render: (value) => `${Number(value).toFixed(1)}%` },
            { title: 'WACC', dataIndex: 'wacc', render: (value) => `${Number(value).toFixed(1)}%` },
            { title: '公允价值', dataIndex: 'fair_value', render: (value) => `$${Number(value || 0).toFixed(2)}` },
          ]}
        />
      ) : null}
    </Card>
  );
}

function GapHistoryCard({ loading, error, historyData }) {
  const history = historyData?.history || [];
  const summary = historyData?.summary || {};

  return (
    <Card data-testid="pricing-gap-history-card" title="偏差历史时间序列">
      <Paragraph type="secondary">
        用当前公允价值锚点回看过去一段时间的价格偏离轨迹，辅助判断均值回归和情绪扩张是否已经发生。
      </Paragraph>
      {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !error && !history.length ? <Empty description="暂无历史偏差数据" /> : null}
      {history.length ? (
        <>
          <Space wrap size={8} style={{ marginBottom: 12 }}>
            <Tag>{`最新偏差 ${summary.latest_gap_pct > 0 ? '+' : ''}${Number(summary.latest_gap_pct || 0).toFixed(1)}%`}</Tag>
            <Tag color="red">{`最高溢价 ${Number(summary.max_gap_pct || 0).toFixed(1)}%`}</Tag>
            <Tag color="green">{`最低折价 ${Number(summary.min_gap_pct || 0).toFixed(1)}%`}</Tag>
          </Space>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={history} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" minTickGap={28} />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartsTooltip formatter={(value, name) => [name === 'gap_pct' ? `${Number(value).toFixed(2)}%` : `$${Number(value).toFixed(2)}`, name === 'gap_pct' ? '偏差' : '价格']} />
                <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="gap_pct" stroke="#1677ff" strokeWidth={2} dot={false} name="gap_pct" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : null}
    </Card>
  );
}

function PeerComparisonCard({ loading, error, peerComparison, onInspect }) {
  const target = peerComparison?.target || null;
  const peers = peerComparison?.peers || [];
  const rows = [target, ...peers].filter(Boolean).map((item) => ({
    ...item,
    key: item.symbol,
  }));
  const premiumChartData = rows.map((item) => ({
    symbol: item.symbol,
    premium_discount: Number(item.premium_discount || 0),
    is_target: item.is_target,
  }));
  const formatCurrency = (value) => (
    value === null || value === undefined || value === ''
      ? DISPLAY_EMPTY
      : `$${Number(value).toFixed(2)}`
  );

  return (
    <Card data-testid="pricing-peer-comparison-card" title="同行估值对比">
      <Paragraph type="secondary">
        结合同行市值和核心倍数，快速判断当前标的是“自己贵”还是“整个板块一起贵”。
      </Paragraph>
      {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !error && !rows.length ? <Empty description="暂无同行对比数据" /> : null}
      {rows.length ? (
        <>
          <Space wrap size={8} style={{ marginBottom: 12 }}>
            <Tag color="blue">{peerComparison?.sector || '未知板块'}</Tag>
            {peerComparison?.industry ? <Tag>{peerComparison.industry}</Tag> : null}
            <Tag>{`同行 ${peerComparison?.summary?.peer_count || 0} 家`}</Tag>
            {peerComparison?.summary?.same_industry_count ? <Tag>{`同细分行业 ${peerComparison.summary.same_industry_count} 家`}</Tag> : null}
            {peerComparison?.candidate_count ? <Tag>{`候选池 ${peerComparison.candidate_count} 家`}</Tag> : null}
            {peerComparison?.summary?.median_peer_pe ? <Tag>{`Peer P/E 中位数 ${peerComparison.summary.median_peer_pe}`}</Tag> : null}
            {peerComparison?.summary?.median_peer_ps ? <Tag>{`Peer P/S 中位数 ${peerComparison.summary.median_peer_ps}`}</Tag> : null}
          </Space>
          <div style={{ width: '100%', height: 220, marginBottom: 12 }}>
            <ResponsiveContainer>
              <BarChart data={premiumChartData} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="symbol" />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartsTooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, '相对公允价值溢折价']} />
                <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                <Bar dataKey="premium_discount" radius={[6, 6, 0, 0]}>
                  {premiumChartData.map((entry) => (
                    <Cell
                      key={entry.symbol}
                      fill={entry.is_target ? '#1677ff' : entry.premium_discount > 0 ? '#ff7875' : '#73d13d'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Table
            size="small"
            pagination={false}
            dataSource={rows}
            columns={[
              {
                title: '标的',
                dataIndex: 'symbol',
                key: 'symbol',
                render: (value, record) => (
                  <Space direction="vertical" size={0}>
                    <Space size={6}>
                      <Text strong>{value}</Text>
                      {record.is_target ? <Tag color="blue">当前标的</Tag> : null}
                    </Space>
                    {record.company_name ? <Text type="secondary" style={{ fontSize: 12 }}>{record.company_name}</Text> : null}
                  </Space>
                ),
              },
              {
                title: '现价 / 公允',
                key: 'valuation',
                render: (_, record) => `${formatCurrency(record.current_price)} / ${formatCurrency(record.fair_value)}`,
              },
              {
                title: '溢折价',
                dataIndex: 'premium_discount',
                key: 'premium_discount',
                render: (value) => (
                  value === null || value === undefined
                    ? DISPLAY_EMPTY
                    : <Tag color={value > 0 ? 'red' : 'green'}>{`${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`}</Tag>
                ),
              },
              {
                title: 'P/E',
                dataIndex: 'pe_ratio',
                key: 'pe_ratio',
                render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY),
              },
              {
                title: 'P/S',
                dataIndex: 'price_to_sales',
                key: 'price_to_sales',
                render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY),
              },
              {
                title: 'EV/EBITDA',
                dataIndex: 'enterprise_to_ebitda',
                key: 'enterprise_to_ebitda',
                render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY),
              },
              {
                title: '操作',
                key: 'action',
                render: (_, record) => (
                  record.is_target
                    ? <Text type="secondary">当前</Text>
                    : <Button type="link" onClick={() => onInspect(record)}>深入分析</Button>
                ),
              },
            ]}
          />
        </>
      ) : null}
    </Card>
  );
}

/**
 * 定价研究面板
 * 整合因子模型分析、内在价值估值和定价差异分析
 */
const PricingResearch = () => {
  const initialResearchContext = readResearchContext() || {};
  const [symbol, setSymbol] = useState('');
  const [period, setPeriod] = useState(initialResearchContext.period || '1y');
  const [loading, setLoading] = useState(false);
  const [savingTask, setSavingTask] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [researchContext, setResearchContext] = useState(initialResearchContext);
  const [savedTaskId, setSavedTaskId] = useState('');
  const [screeningUniverse, setScreeningUniverse] = useState(DEFAULT_SCREENING_UNIVERSE);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningError, setScreeningError] = useState(null);
  const [screeningResults, setScreeningResults] = useState([]);
  const [screeningMeta, setScreeningMeta] = useState(null);
  const [screeningProgress, setScreeningProgress] = useState({ completed: 0, total: 0, running: false });
  const [screeningFilter, setScreeningFilter] = useState('all');
  const [screeningSector, setScreeningSector] = useState('all');
  const [screeningMinScore, setScreeningMinScore] = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  const [searchHistory, setSearchHistory] = useState([]);
  const [recentResearchEntries, setRecentResearchEntries] = useState([]);
  const [sensitivity, setSensitivity] = useState(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(false);
  const [sensitivityError, setSensitivityError] = useState(null);
  const [gapHistory, setGapHistory] = useState(null);
  const [gapHistoryLoading, setGapHistoryLoading] = useState(false);
  const [gapHistoryError, setGapHistoryError] = useState(null);
  const [peerComparison, setPeerComparison] = useState(null);
  const [peerComparisonLoading, setPeerComparisonLoading] = useState(false);
  const [peerComparisonError, setPeerComparisonError] = useState(null);
  const [sensitivityControls, setSensitivityControls] = useState({
    wacc: 8.2,
    initialGrowth: 12,
    terminalGrowth: 2.5,
    fcfMargin: 80,
  });
  const autoLoadedContextRef = useRef('');
  const deferredSymbolQuery = useDeferredValue(symbol);

  const mergedContext = useMemo(
    () => ({
      ...researchContext,
      symbol: researchContext.symbol || symbol,
    }),
    [researchContext, symbol]
  );

  const playbook = useMemo(
    () => buildPricingPlaybook(mergedContext, data),
    [mergedContext, data]
  );

  const filteredScreeningResults = useMemo(() => {
    return screeningResults.filter((item) => {
      if (screeningFilter === 'undervalued' && item.primary_view !== '低估') {
        return false;
      }
      if (screeningFilter === 'high-confidence' && Number(item.confidence_score || 0) < 0.72) {
        return false;
      }
      if (screeningFilter === 'aligned' && item.factor_alignment_status !== 'aligned') {
        return false;
      }
      if (screeningSector !== 'all' && (item.sector || '未知板块') !== screeningSector) {
        return false;
      }
      if (Number(item.screening_score || 0) < Number(screeningMinScore || 0)) {
        return false;
      }
      return true;
    });
  }, [screeningFilter, screeningMinScore, screeningResults, screeningSector]);

  const screeningSectors = useMemo(() => {
    const sectors = Array.from(new Set(screeningResults.map((item) => item.sector || '未知板块').filter(Boolean)));
    return sectors.sort();
  }, [screeningResults]);

  const handleOpenRecentResearchTask = useCallback((entry = {}) => {
    const taskId = entry?.taskId || entry?.task_id || '';
    if (taskId) {
      navigateByResearchAction({
        target: 'workbench',
        type: 'pricing',
        sourceFilter: 'research_workbench',
        reason: 'recent_pricing_search',
        taskId,
      });
      return;
    }
    if (entry?.period) {
      setPeriod(entry.period);
    }
    if (entry?.symbol) {
      setSymbol(entry.symbol);
    }
  }, []);

  const handleSuggestionSelect = useCallback((value, option) => {
    const taskId = option?.taskId || option?.task_id || '';
    if (taskId) {
      handleOpenRecentResearchTask({
        taskId,
        symbol: value,
        period: option?.period || '',
      });
      return;
    }
    setSymbol(value);
  }, [handleOpenRecentResearchTask]);

  const recentResearchShortcuts = useMemo(
    () => recentResearchEntries.slice(0, 4),
    [recentResearchEntries]
  );

  const recentResearchShortcutCards = useMemo(
    () => recentResearchShortcuts.map((item) => ({
      ...item,
      title: item.headline || item.title || `${item.symbol} 定价研究`,
      subtitle: [
        item.primary_view || '',
        item.confidence_label ? `置信度 ${item.confidence_label}` : '',
        item.factor_alignment_label || '',
        item.period ? `窗口 ${item.period}` : '',
      ].filter(Boolean).join(' · '),
    })),
    [recentResearchShortcuts]
  );

  const handleAnalyze = useCallback(async (overrideSymbol = null, overridePeriod = null) => {
    const targetSymbol = resolveAnalysisSymbol(overrideSymbol, symbol);
    const targetPeriod = typeof overridePeriod === 'string' && overridePeriod ? overridePeriod : period;
    if (!targetSymbol) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getGapAnalysis(targetSymbol, targetPeriod);
      setData(result);
      setResearchContext((prev) => ({
        ...prev,
        view: 'pricing',
        symbol: targetSymbol,
        period: targetPeriod,
      }));
      setSearchHistory((prev) => {
        const next = [targetSymbol, ...prev.filter((item) => item !== targetSymbol)].slice(0, 8);
        try {
          window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next));
        } catch (storageError) {
          console.debug('unable to persist pricing history', storageError);
        }
        return next;
      });
    } catch (err) {
      setError(err.userMessage || err.message || '分析失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, period]);

  useEffect(() => {
    const syncFromUrl = () => {
      const nextContext = readResearchContext() || {};
      setResearchContext(nextContext);
      if (nextContext.view === 'pricing' && nextContext.symbol) {
        setSymbol(nextContext.symbol);
        setPeriod(nextContext.period || '1y');
        const contextKey = `${nextContext.symbol}:${nextContext.period || '1y'}:${nextContext.source}:${nextContext.note}`;
        if (autoLoadedContextRef.current !== contextKey) {
          autoLoadedContextRef.current = contextKey;
          handleAnalyze(nextContext.symbol, nextContext.period || '1y');
        }
      }
    };

    syncFromUrl();
    window.addEventListener('popstate', syncFromUrl);
    return () => window.removeEventListener('popstate', syncFromUrl);
  }, [handleAnalyze]);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(SEARCH_HISTORY_KEY) || '[]');
      if (Array.isArray(stored)) {
        setSearchHistory(stored.filter(Boolean));
      }
    } catch (error) {
      console.debug('unable to read pricing history', error);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getResearchTasks({ limit: 40, type: 'pricing' })
      .then((payload) => {
        if (!active) return;
        const rows = payload?.data || [];
        setRecentResearchEntries(buildRecentPricingResearchEntries(rows).slice(0, 12));
      })
      .catch(() => {
        if (active) {
          setRecentResearchEntries([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (researchContext?.view !== 'pricing') {
      return;
    }
    const nextUrl = buildAppUrl({
      currentSearch: window.location.search,
      view: 'pricing',
      symbol: researchContext.symbol || undefined,
      source: researchContext.source || undefined,
      note: researchContext.note || undefined,
      action: researchContext.action || undefined,
      period,
    });
    window.history.replaceState(null, '', nextUrl);
  }, [period, researchContext]);

  useEffect(() => {
    let active = true;
    const query = String(deferredSymbolQuery || '').trim();
    const preferredEntries = [
      ...buildRecentPricingResearchEntries(
        searchHistory.map((item) => ({ symbol: item }))
      ),
      ...recentResearchEntries,
    ];
    getPricingSymbolSuggestions(query, 8)
      .then((payload) => {
        if (!active) return;
        const mergedSuggestions = mergePricingSuggestions(payload.data || [], preferredEntries, query);
        const options = mergedSuggestions.map((item) => ({
          value: item.symbol,
          taskId: item.task_id || '',
          period: item.period || '',
          label: (
            <Space direction="vertical" size={0}>
              <Space size={6}>
                <Text strong>{item.symbol}</Text>
                {item.recent ? <Tag color="gold">最近研究</Tag> : null}
                {item.primary_view ? (
                  <Tag color={item.primary_view === '低估' ? 'green' : item.primary_view === '高估' ? 'red' : 'default'}>
                    {item.primary_view}
                  </Tag>
                ) : null}
                {item.confidence_label ? <Tag>{`置信度 ${item.confidence_label}`}</Tag> : null}
                {item.factor_alignment_label ? (
                  <Tag color={ALIGNMENT_TAG_COLORS[item.factor_alignment_status] || 'default'}>
                    {item.factor_alignment_label}
                  </Tag>
                ) : null}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>{item.name}</Text>
              {item.group ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {item.group}{item.market ? ` · ${item.market}` : ''}
                </Text>
              ) : null}
              {item.period || item.headline || item.summary ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {[item.period ? `窗口 ${item.period}` : '', item.headline || item.summary].filter(Boolean).join(' · ')}
                </Text>
              ) : null}
              {item.primary_driver ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {`主驱动 ${item.primary_driver}`}
                </Text>
              ) : null}
              {item.task_id ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  点击将直接打开对应研究任务
                </Text>
              ) : null}
            </Space>
          ),
        }));
        setSuggestions(options);
      })
      .catch(() => {
        if (active) {
          setSuggestions([]);
        }
      });
    return () => {
      active = false;
    };
  }, [deferredSymbolQuery, recentResearchEntries, searchHistory]);

  useEffect(() => {
    const anchor = data?.valuation?.dcf?.sensitivity_anchor;
    if (!anchor) {
      return;
    }
    setSensitivityControls({
      wacc: Number((anchor.wacc || 0) * 100).toFixed(1) * 1,
      initialGrowth: Number((anchor.initial_growth || 0) * 100).toFixed(1) * 1,
      terminalGrowth: Number((anchor.terminal_growth || 0) * 100).toFixed(1) * 1,
      fcfMargin: Number((anchor.fcf_margin || 0) * 100).toFixed(0) * 1,
    });
  }, [data]);

  useEffect(() => {
    const targetSymbol = resolveAnalysisSymbol(data?.symbol, symbol);
    if (!data || !targetSymbol) {
      setGapHistory(null);
      setGapHistoryError(null);
      setPeerComparison(null);
      setPeerComparisonError(null);
      return;
    }

    let active = true;
    setGapHistoryLoading(true);
    setGapHistoryError(null);
    setPeerComparisonLoading(true);
    setPeerComparisonError(null);

    getPricingGapHistory(targetSymbol, period, 72)
      .then((payload) => {
        if (!active) return;
        if (payload?.error) {
          setGapHistory(null);
          setGapHistoryError(payload.error);
          return;
        }
        setGapHistory(payload);
      })
      .catch((err) => {
        if (!active) return;
        setGapHistory(null);
        setGapHistoryError(err.userMessage || err.message || '历史偏差数据加载失败');
      })
      .finally(() => {
        if (active) {
          setGapHistoryLoading(false);
        }
      });

    getPricingPeerComparison(targetSymbol, 5)
      .then((payload) => {
        if (!active) return;
        if (payload?.error) {
          setPeerComparison(null);
          setPeerComparisonError(payload.error);
          return;
        }
        setPeerComparison(payload);
      })
      .catch((err) => {
        if (!active) return;
        setPeerComparison(null);
        setPeerComparisonError(err.userMessage || err.message || '同行估值对比加载失败');
      })
      .finally(() => {
        if (active) {
          setPeerComparisonLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [data, period, symbol]);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') handleAnalyze();
  };

  const handleSaveTask = async () => {
    const payload = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    );
    if (!payload) {
      message.error('请先输入标的后再保存到研究工作台');
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

  const handleRunScreener = useCallback(async () => {
    const symbols = parsePricingUniverseInput(screeningUniverse);
    if (!symbols.length) {
      message.warning('请先输入至少一个股票代码');
      return;
    }

    setScreeningLoading(true);
    setScreeningError(null);
    setScreeningResults([]);
    setScreeningProgress({ completed: 0, total: symbols.length, running: true });
    try {
      const concurrency = Math.min(4, symbols.length);
      const rows = [];
      const failures = [];
      let completed = 0;
      let pointer = 0;

      const worker = async () => {
        while (pointer < symbols.length) {
          const currentIndex = pointer;
          pointer += 1;
          const currentSymbol = symbols[currentIndex];
          try {
            const analysis = await getGapAnalysis(currentSymbol, period);
            rows.push(buildScreeningRowFromAnalysis(analysis, period));
            setScreeningResults(sortScreeningRows(rows));
          } catch (error) {
            failures.push({
              symbol: currentSymbol,
              error: error.userMessage || error.message || '分析失败',
            });
          } finally {
            completed += 1;
            setScreeningProgress({ completed, total: symbols.length, running: completed < symbols.length });
          }
        }
      };

      await Promise.all(Array.from({ length: concurrency }, () => worker()));
      const sorted = sortScreeningRows(rows);
      setScreeningResults(sorted);
      setScreeningMeta({
        analyzedCount: sorted.length,
        totalInput: symbols.length,
        failureCount: failures.length,
        failures,
      });
    } catch (err) {
      setScreeningError(err.userMessage || err.message || '候选池筛选失败');
      setScreeningResults([]);
      setScreeningMeta(null);
    } finally {
      setScreeningLoading(false);
      setScreeningProgress((prev) => ({ ...prev, running: false }));
    }
  }, [period, screeningUniverse]);

  const handleInspectScreeningResult = useCallback((record) => {
    if (!record?.symbol) {
      return;
    }
    startTransition(() => {
      setSymbol(record.symbol);
    });
    handleAnalyze(record.symbol, period);
  }, [handleAnalyze, period]);

  const handleRunSensitivity = useCallback(async () => {
    const targetSymbol = resolveAnalysisSymbol(symbol, researchContext.symbol || '');
    if (!targetSymbol) {
      message.warning('请先选择一个标的再做敏感性分析');
      return;
    }

    setSensitivityLoading(true);
    setSensitivityError(null);
    try {
      const payload = await getValuationSensitivityAnalysis({
        symbol: targetSymbol,
        wacc: Number(sensitivityControls.wacc) / 100,
        initial_growth: Number(sensitivityControls.initialGrowth) / 100,
        terminal_growth: Number(sensitivityControls.terminalGrowth) / 100,
        fcf_margin: Number(sensitivityControls.fcfMargin) / 100,
        dcf_weight: data?.valuation?.fair_value?.dcf_weight,
        comparable_weight: data?.valuation?.fair_value?.comparable_weight,
      });
      setSensitivity(payload);
    } catch (err) {
      setSensitivityError(err.userMessage || err.message || '敏感性分析失败');
      setSensitivity(null);
    } finally {
      setSensitivityLoading(false);
    }
  }, [data?.valuation?.fair_value?.comparable_weight, data?.valuation?.fair_value?.dcf_weight, researchContext.symbol, sensitivityControls, symbol]);

  const handleApplyPreset = useCallback((symbols) => {
    setScreeningUniverse(symbols.join('\n'));
  }, []);

  const handleExportScreening = useCallback(() => {
    if (!screeningResults.length) {
      return;
    }
    const header = ['Rank', 'Symbol', 'Company', 'Score', 'View', 'GapPct', 'Confidence', 'Alignment', 'Driver'];
    const rows = screeningResults.map((item) => [
      item.rank,
      item.symbol,
      item.company_name || '',
      item.screening_score,
      item.primary_view || '',
      item.gap_pct ?? '',
      item.confidence_score ?? '',
      item.factor_alignment_label || '',
      item.primary_driver || '',
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pricing-screener-${period}.csv`;
    link.click();
    window.URL.revokeObjectURL(url);
  }, [period, screeningResults]);

  const handleExportReport = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    try {
      const snapshot = buildPricingWorkbenchPayload(
        { ...mergedContext, period },
        data,
        playbook
      )?.snapshot?.payload || null;
      const reportHtml = buildPricingResearchReportHtml({
        symbol: resolveAnalysisSymbol(data?.symbol, symbol),
        period,
        generatedAt: new Date().toLocaleString(),
        analysis: data,
        snapshot,
        context: mergedContext,
        sensitivity,
        history: gapHistory,
        peerComparison,
      });
      const opened = openPricingResearchPrintWindow(reportHtml);
      if (!opened) {
        message.error('无法打开打印窗口，请检查浏览器弹窗设置');
        return;
      }
      message.success('已打开打印窗口，可直接另存为 PDF');
    } catch (exportError) {
      message.error(exportError.message || '导出研究报告失败');
    }
  }, [data, gapHistory, mergedContext, peerComparison, period, playbook, sensitivity, symbol]);

  const handleExportAudit = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    const snapshot = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    )?.snapshot?.payload || null;
    const payload = buildPricingResearchAuditPayload({
      symbol: resolveAnalysisSymbol(data?.symbol, symbol),
      period,
      context: mergedContext,
      analysis: data,
      snapshot,
      playbook,
      sensitivity,
      history: gapHistory,
      peerComparison,
    });
    exportToJSON(payload, `pricing-research-audit-${payload.symbol || 'unknown'}-${period}`);
    message.success('已导出审计 JSON');
  }, [data, gapHistory, mergedContext, peerComparison, period, playbook, sensitivity, symbol]);

  const handleUpdateSnapshot = async () => {
    if (!savedTaskId) {
      message.info('请先保存任务，再更新当前任务快照');
      return;
    }

    const payload = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
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

  return (
    <div data-testid="pricing-research-page">
      <Title level={4} style={{ marginBottom: 16 }}>
        <FundOutlined style={{ marginRight: 8 }} />
        资产定价研究
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 20 }}>
        打通一级市场估值逻辑（DCF / 可比估值）与二级市场因子定价（CAPM / Fama-French），识别定价偏差与驱动因素。
      </Paragraph>

      {researchContext?.source && researchContext?.symbol ? (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message={`来自 ${formatResearchSource(researchContext.source)} 的定价研究建议 · ${playbook?.stageLabel || '待分析'}`}
          description={
            researchContext.note
              ? `${researchContext.symbol} · ${researchContext.note}`
              : `${researchContext.symbol} 已自动带入研究页，当前剧本阶段为 ${playbook?.stageLabel || '待分析'}`
          }
        />
      ) : null}

      {playbook ? (
        <div style={{ marginBottom: 16 }}>
          <ResearchPlaybook
            playbook={playbook}
            onAction={(action) => navigateByResearchAction(action)}
            onSaveTask={handleSaveTask}
            onUpdateSnapshot={data && savedTaskId ? handleUpdateSnapshot : null}
            saving={savingTask}
          />
        </div>
      ) : null}

      {/* 搜索栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size="middle" wrap style={{ width: '100%' }}>
          <AutoComplete
            options={suggestions}
            value={symbol}
            onChange={setSymbol}
            onSelect={handleSuggestionSelect}
            style={{ width: 320 }}
          >
            <Input
            data-testid="pricing-symbol-input"
              placeholder="输入股票代码或公司名，如 AAPL / Apple"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyPress={handleKeyPress}
              prefix={<SearchOutlined />}
              allowClear
            />
          </AutoComplete>
          <Select data-testid="pricing-period-select" value={period} onChange={setPeriod} style={{ width: 120 }}>
            <Option value="6mo">近6个月</Option>
            <Option value="1y">近1年</Option>
            <Option value="2y">近2年</Option>
            <Option value="3y">近3年</Option>
          </Select>
          <Button data-testid="pricing-analyze-button" type="primary" icon={<ExperimentOutlined />}
            onClick={handleAnalyze} loading={loading}>
            开始分析
          </Button>
          <Button
            data-testid="pricing-export-report-button"
            icon={<DownloadOutlined />}
            onClick={handleExportReport}
            disabled={!data}
          >
            导出研究报告
          </Button>
          <Button
            data-testid="pricing-export-audit-button"
            onClick={handleExportAudit}
            disabled={!data}
          >
            导出审计 JSON
          </Button>
        </Space>
        <Space wrap size={8} style={{ marginTop: 12 }}>
          <Text type="secondary">热门标的:</Text>
          {HOT_PRICING_SYMBOLS.map((item) => (
            <Tag
              key={item.symbol}
              style={{ cursor: 'pointer' }}
              onClick={() => setSymbol(item.symbol)}
            >
              {item.symbol}
            </Tag>
          ))}
        </Space>
        {searchHistory.length ? (
          <Space wrap size={8} style={{ marginTop: 8 }}>
            <Text type="secondary">最近搜索:</Text>
            {searchHistory.map((item) => (
              <Tag
                key={item}
                color="blue"
                style={{ cursor: 'pointer' }}
                onClick={() => setSymbol(item)}
              >
                {item}
              </Tag>
            ))}
          </Space>
        ) : null}
        {recentResearchShortcutCards.length ? (
          <div data-testid="pricing-recent-research-shortcuts" style={{ marginTop: 12 }}>
            <Text type="secondary">最近研究捷径:</Text>
            <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
              {recentResearchShortcutCards.map((item) => (
                <Col xs={24} md={12} key={item.task_id || item.symbol}>
                  <Button
                    block
                    style={{ height: 'auto', textAlign: 'left', padding: 12 }}
                    onClick={() => handleOpenRecentResearchTask(item)}
                  >
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Space wrap size={6}>
                        <Text strong>{item.symbol}</Text>
                        {item.primary_view ? (
                          <Tag color={item.primary_view === '低估' ? 'green' : item.primary_view === '高估' ? 'red' : 'default'}>
                            {item.primary_view}
                          </Tag>
                        ) : null}
                        {item.confidence_label ? <Tag>{`置信度 ${item.confidence_label}`}</Tag> : null}
                        {item.factor_alignment_label ? (
                          <Tag color={ALIGNMENT_TAG_COLORS[item.factor_alignment_status] || 'default'}>
                            {item.factor_alignment_label}
                          </Tag>
                        ) : null}
                      </Space>
                      <Text style={{ fontSize: 12 }}>{item.title}</Text>
                      {item.subtitle ? <Text type="secondary" style={{ fontSize: 11 }}>{item.subtitle}</Text> : null}
                      {item.primary_driver ? <Text type="secondary" style={{ fontSize: 11 }}>{`主驱动 ${item.primary_driver}`}</Text> : null}
                      {item.summary ? <Text type="secondary" style={{ fontSize: 11 }}>{item.summary}</Text> : null}
                    </Space>
                  </Button>
                </Col>
              ))}
            </Row>
          </div>
        ) : null}
      </Card>

      <PricingScreenerCard
        value={screeningUniverse}
        onChange={setScreeningUniverse}
        onRun={handleRunScreener}
        onInspect={handleInspectScreeningResult}
        loading={screeningLoading}
        error={screeningError}
        period={period}
        results={filteredScreeningResults}
        meta={screeningMeta}
        progress={screeningProgress}
        filter={screeningFilter}
        onFilterChange={setScreeningFilter}
        sectorFilter={screeningSector}
        onSectorFilterChange={setScreeningSector}
        minScore={screeningMinScore}
        onMinScoreChange={setScreeningMinScore}
        sectorOptions={screeningSectors}
        onApplyPreset={handleApplyPreset}
        onExport={handleExportScreening}
      />

      {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {loading && (
        <Card style={{ marginBottom: 16 }}>
          <Skeleton active paragraph={{ rows: 8 }} />
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: '#8c8c8c' }}>
              正在分析 {symbol.toUpperCase()} 的定价模型，首次加载因子数据可能需要10-20秒...
            </div>
          </div>
        </Card>
      )}

      {data && !loading && (
        <>
          {/* 顶部概览 */}
          <GapOverview data={data} />

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            {/* 因子模型 */}
            <Col xs={24} lg={12}>
              <FactorModelCard data={data.factor_model} />
            </Col>
            {/* 估值分析 */}
            <Col xs={24} lg={12}>
              <ValuationCard data={data.valuation} />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            {/* 偏差驱动因素 */}
            <Col xs={24} lg={12}>
              <DriversCard data={data.deviation_drivers} />
            </Col>
            {/* 投资含义 */}
            <Col xs={24} lg={12}>
              <ImplicationsCard
                data={data.implications}
                valuation={data.valuation}
                factorModel={data.factor_model}
                gapAnalysis={data.gap_analysis}
                onRetry={handleAnalyze}
              />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24}>
              <SensitivityAnalysisCard
                symbol={symbol}
                loading={sensitivityLoading}
                error={sensitivityError}
                sensitivity={sensitivity}
                controls={sensitivityControls}
                onControlChange={setSensitivityControls}
                onRun={handleRunSensitivity}
              />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={12}>
              <GapHistoryCard
                loading={gapHistoryLoading}
                error={gapHistoryError}
                historyData={gapHistory}
              />
            </Col>
            <Col xs={24} lg={12}>
              <PeerComparisonCard
                loading={peerComparisonLoading}
                error={peerComparisonError}
                peerComparison={peerComparison}
                onInspect={handleInspectScreeningResult}
              />
            </Col>
          </Row>
        </>
      )}

      {!data && !loading && !error && (
        <Empty
          description="输入股票代码开始定价研究分析"
          style={{ padding: 80 }}
        />
      )}
    </div>
  );
};

/* ========== 子组件 ========== */

const PricingScreenerCard = ({
  value,
  onChange,
  onRun,
  onInspect,
  loading,
  error,
  period,
  results,
  meta,
  progress,
  filter,
  onFilterChange,
  sectorFilter,
  onSectorFilterChange,
  minScore,
  onMinScoreChange,
  sectorOptions,
  onApplyPreset,
  onExport,
}) => {
  const candidateCount = parsePricingUniverseInput(value).length;

  return (
    <Card
      data-testid="pricing-screener-card"
      size="small"
      style={{ marginBottom: 16 }}
      title={<><ThunderboltOutlined style={{ marginRight: 8 }} />Mispricing 候选池筛选</>}
      extra={<Tag>{`窗口 ${period}`}</Tag>}
    >
      <Paragraph type="secondary" style={{ marginBottom: 12 }}>
        一次跑一组候选标的，按偏差幅度、置信度和证据共振综合排序；点“深入分析”会回到单标的研究视图。
      </Paragraph>
      <Input.TextArea
        data-testid="pricing-screener-input"
        rows={4}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="输入多个股票代码，支持换行、逗号或空格分隔"
        style={{ marginBottom: 12 }}
      />
      <Space wrap size={8} style={{ marginBottom: 12 }}>
        <Text type="secondary">预设候选池:</Text>
        {SCREENING_PRESETS.map((preset) => (
          <Tag
            key={preset.key}
            color="blue"
            style={{ cursor: 'pointer' }}
            onClick={() => onApplyPreset(preset.symbols)}
          >
            {preset.label}
          </Tag>
        ))}
      </Space>
      <Space wrap size="middle" style={{ marginBottom: 12 }}>
        <Button
          data-testid="pricing-screener-run-button"
          type="default"
          icon={<ThunderboltOutlined />}
          loading={loading}
          onClick={onRun}
        >
          批量筛选
        </Button>
        <Button onClick={onExport} disabled={!results?.length}>导出 CSV</Button>
        <Text type="secondary">{`候选 ${candidateCount} 个`}</Text>
        {meta ? (
          <Text type="secondary">{`已分析 ${meta.analyzedCount}/${meta.totalInput} · 失败 ${meta.failureCount}`}</Text>
        ) : null}
      </Space>
      {progress?.total ? (
        <div style={{ marginBottom: 12 }}>
          <Progress
            percent={Math.round((Number(progress.completed || 0) / Number(progress.total || 1)) * 100)}
            status={progress.running ? 'active' : 'normal'}
            format={() => `${progress.completed}/${progress.total}`}
          />
        </div>
      ) : null}

      <Space wrap size={8} style={{ marginBottom: 12 }}>
        <Text type="secondary">筛选视图:</Text>
        <Select value={filter} onChange={onFilterChange} style={{ width: 180 }}>
          <Option value="all">全部结果</Option>
          <Option value="undervalued">只看低估</Option>
          <Option value="high-confidence">只看高置信度</Option>
          <Option value="aligned">只看证据同向</Option>
        </Select>
        <Select value={sectorFilter} onChange={onSectorFilterChange} style={{ width: 180 }}>
          <Option value="all">全部板块</Option>
          {(sectorOptions || []).map((sector) => (
            <Option key={sector} value={sector}>{sector}</Option>
          ))}
        </Select>
        <div style={{ minWidth: 220 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{`机会分阈值 >= ${Number(minScore || 0).toFixed(0)}`}</Text>
          <Slider min={0} max={40} step={1} value={minScore} onChange={onMinScoreChange} />
        </div>
      </Space>

      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}

      {results?.length ? (
        <Table
          data-testid="pricing-screener-results"
          size="small"
          rowKey="symbol"
          pagination={false}
          dataSource={results}
          columns={[
            {
              title: '#',
              dataIndex: 'rank',
              key: 'rank',
              width: 56,
            },
            {
              title: '标的',
              dataIndex: 'symbol',
              key: 'symbol',
              render: (value, record) => (
                <div>
                  <Text strong>{value}</Text>
                  {record.company_name ? (
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>{record.company_name}</div>
                  ) : null}
                  {record.sector ? (
                    <div style={{ fontSize: 12, color: '#bfbfbf' }}>{record.sector}</div>
                  ) : null}
                </div>
              ),
            },
            {
              title: '机会分',
              dataIndex: 'screening_score',
              key: 'screening_score',
              width: 100,
              render: (value) => <Text strong>{Number(value || 0).toFixed(1)}</Text>,
            },
            {
              title: '偏差',
              dataIndex: 'gap_pct',
              key: 'gap_pct',
              width: 96,
              render: (value) => (
                value === null || value === undefined
                  ? DISPLAY_EMPTY
                  : `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`
              ),
            },
            {
              title: '观点',
              dataIndex: 'primary_view',
              key: 'primary_view',
              width: 88,
              render: (value) => <Tag color={value === '低估' ? 'green' : value === '高估' ? 'red' : 'default'}>{value || '合理'}</Tag>,
            },
            {
              title: '置信度',
              dataIndex: 'confidence_score',
              key: 'confidence_score',
              width: 110,
              render: (value, record) => (
                <div>
                  <Tag>{record.confidence || 'medium'}</Tag>
                  <div style={{ fontSize: 12, color: '#8c8c8c' }}>{Number(value || 0).toFixed(2)}</div>
                </div>
              ),
            },
            {
              title: '证据共振',
              dataIndex: 'factor_alignment_label',
              key: 'factor_alignment_label',
              width: 110,
              render: (value, record) => (
                <Tag color={ALIGNMENT_TAG_COLORS[record.factor_alignment_status] || 'default'}>{value || '待确认'}</Tag>
              ),
            },
            {
              title: '主驱动',
              dataIndex: 'primary_driver',
              key: 'primary_driver',
              render: (value) => value || DISPLAY_EMPTY,
            },
            {
              title: '操作',
              key: 'action',
              width: 100,
              render: (_, record) => (
                <Button type="link" onClick={() => onInspect(record)}>
                  深入分析
                </Button>
              ),
            },
          ]}
        />
      ) : null}
    </Card>
  );
};

/** 定价差异概览 */
export const GapOverview = ({ data }) => {
  const gap = data?.gap_analysis || {};
  const valuation = data?.valuation || {};
  const gapPct = gap.gap_pct;
  const severity = gap.severity || 'unknown';
  const priceSourceLabel = getPriceSourceLabel(valuation.current_price_source || '');
  const formatCurrencyStat = (value) =>
    value === null || value === undefined || value === ''
      ? DISPLAY_EMPTY
      : `$${Number(value).toFixed(2)}`;
  const formatPercentPointStat = (value) =>
    value === null || value === undefined || value === ''
      ? DISPLAY_EMPTY
      : `${Math.abs(Number(value)).toFixed(1)}%`;

  const severityColor = {
    extreme: '#ff4d4f', high: '#fa8c16', moderate: '#faad14',
    mild: '#52c41a', negligible: '#1890ff', unknown: '#d9d9d9'
  };

  const directionIcon = gapPct > 0
    ? <ArrowUpOutlined style={{ color: '#ff4d4f' }} />
    : gapPct < 0
    ? <ArrowDownOutlined style={{ color: '#52c41a' }} />
    : gapPct === null || gapPct === undefined
    ? null
    : <MinusOutlined />;
  const rangeChartData = gap.fair_value_low && gap.fair_value_high
    ? [
        { label: '下沿', value: Number(gap.fair_value_low) },
        { label: '公允', value: Number(gap.fair_value_mid || 0) },
        { label: '上沿', value: Number(gap.fair_value_high) },
      ]
    : [];
  const thermometerPercent = gapPct === null || gapPct === undefined
    ? 0
    : Math.min(100, Math.round((Math.abs(Number(gapPct)) / 30) * 100));
  const thermometerStatus = gapPct > 0 ? 'exception' : gapPct < 0 ? 'success' : 'normal';
  const thermometerLabel = gapPct > 0 ? '偏热' : gapPct < 0 ? '偏冷' : '中性';

  return (
    <Card
      data-testid="pricing-gap-overview"
      title={
        <Space>
          <SwapOutlined />
          <span>定价差异概览</span>
          <Tag color="blue">{data.symbol}</Tag>
          {valuation.company_name && <Text type="secondary">{valuation.company_name}</Text>}
        </Space>
      }
    >
      <Row gutter={[24, 16]}>
        <Col xs={12} sm={6}>
          <Statistic
            title="当前市价"
            value={gap.current_price}
            formatter={formatCurrencyStat}
          />
          {gap.current_price !== null && gap.current_price !== undefined ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              现价来源：{priceSourceLabel}
            </Text>
          ) : null}
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="公允价值"
            value={gap.fair_value_mid}
            formatter={formatCurrencyStat}
            valueStyle={{ color: '#1890ff' }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="偏差幅度"
            value={gapPct}
            formatter={formatPercentPointStat}
            prefix={directionIcon}
            valueStyle={gapPct === null || gapPct === undefined ? undefined : { color: gapPct > 0 ? '#ff4d4f' : '#52c41a' }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <div>
            <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 4 }}>估值状态</div>
            <Tag
              color={severityColor[severity]}
              style={{ fontSize: 14, padding: '4px 12px' }}
            >
              {gap.severity_label || '未知'}
            </Tag>
            <div style={{ marginTop: 4 }}>
              <Tag>{gap.direction || ''}</Tag>
            </div>
          </div>
        </Col>
      </Row>
      {gap.fair_value_low && gap.fair_value_high && (
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 8 }}>
            <Text type="secondary">定价温度计</Text>
            <div style={{ marginTop: 6 }}>
              <Space size={8} align="center">
                <Progress
                  percent={thermometerPercent}
                  status={thermometerStatus}
                  size={[220, 10]}
                  showInfo={false}
                  strokeColor={gapPct > 0 ? '#ff4d4f' : gapPct < 0 ? '#52c41a' : '#1677ff'}
                />
                <Tag color={gapPct > 0 ? 'red' : gapPct < 0 ? 'green' : 'blue'}>{thermometerLabel}</Tag>
              </Space>
            </div>
          </div>
          <Text type="secondary">
            公允价值区间: ${gap.fair_value_low} ~ ${gap.fair_value_high}
            {gap.in_fair_range
              ? <Tag color="green" style={{ marginLeft: 8 }}>在合理区间内</Tag>
              : <Tag color="orange" style={{ marginLeft: 8 }}>偏离合理区间</Tag>
            }
          </Text>
          <div style={{ width: '100%', height: 120, marginTop: 8 }}>
            <ResponsiveContainer>
              <BarChart data={rangeChartData} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis hide domain={['dataMin - 5', 'dataMax + 5']} />
                <RechartsTooltip formatter={(value) => [`$${Number(value).toFixed(2)}`, '估值']} />
                <ReferenceLine y={Number(gap.current_price || 0)} stroke="#ff4d4f" strokeDasharray="4 4" label="当前价" />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {rangeChartData.map((entry) => (
                    <Cell key={entry.label} fill={entry.label === '公允' ? '#1677ff' : '#91caff'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
};

/** 因子模型分析卡片 */
export const FactorModelCard = ({ data }) => {
  if (!data) return null;
  const capm = data.capm || {};
  const ff3 = data.fama_french || {};
  const ff5 = data.fama_french_five_factor || {};
  const attribution = data.attribution || {};
  const factorSource = data.factor_source || {};
  const fiveFactorSource = data.five_factor_source || {};

  const hasCAPM = !capm.error;
  const hasFF3 = !ff3.error;
  const hasFF5 = !ff5.error;
  const radarData = hasFF3 ? [
    { subject: '市场', exposure: Number(ff3.factor_loadings?.market || 0) },
    { subject: '规模', exposure: Number(ff3.factor_loadings?.size || 0) },
    { subject: '价值', exposure: Number(ff3.factor_loadings?.value || 0) },
  ] : [];
  const attributionChartData = attribution.components
    ? Object.values(attribution.components).map((item) => ({
        name: item.label.replace('贡献', ''),
        pct: Number(item.pct || 0),
      }))
    : [];
  const residualChartData = [
    {
      model: 'CAPM',
      lag1: Number(capm.residual_diagnostics?.autocorr_lag1 || 0),
      dw: Number(capm.residual_diagnostics?.durbin_watson || 0),
    },
    {
      model: 'FF3',
      lag1: Number(ff3.residual_diagnostics?.autocorr_lag1 || 0),
      dw: Number(ff3.residual_diagnostics?.durbin_watson || 0),
    },
    {
      model: 'FF5',
      lag1: Number(ff5.residual_diagnostics?.autocorr_lag1 || 0),
      dw: Number(ff5.residual_diagnostics?.durbin_watson || 0),
    },
  ].filter((item) => item.dw || item.lag1);

  return (
    <Card
      data-testid="pricing-factor-card"
      title={<><FundOutlined style={{ marginRight: 8 }} />因子模型分析</>}
      extra={
        <Space size={6}>
          <Tag>{data.period || '1y'}</Tag>
          {data.data_points ? <Tag>{`样本 ${data.data_points}`}</Tag> : null}
          {factorSource.is_proxy ? <Tag color="orange">代理因子</Tag> : null}
        </Space>
      }
    >
      {factorSource.warning ? (
        <Alert
          type={factorSource.is_proxy ? 'warning' : 'info'}
          showIcon
          message={`因子来源：${factorSource.label}`}
          description={factorSource.warning}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      {fiveFactorSource.warning && fiveFactorSource.warning !== factorSource.warning ? (
        <Alert
          type={fiveFactorSource.is_proxy ? 'warning' : 'info'}
          showIcon
          message={`五因子来源：${fiveFactorSource.label}`}
          description={fiveFactorSource.warning}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      {/* CAPM */}
      <Divider orientation="left" style={{ fontSize: 13 }}>CAPM 模型</Divider>
      {hasCAPM ? (
        <>
          <Row gutter={16}>
            <Col span={8}>
              <Statistic title="Alpha (年化)" value={capm.alpha_pct || 0} suffix="%" precision={2}
                valueStyle={{ color: (capm.alpha_pct || 0) > 0 ? '#3f8600' : '#cf1322' }} />
            </Col>
            <Col span={8}>
              <Statistic title="Beta" value={capm.beta || 0} precision={3} />
            </Col>
            <Col span={8}>
              <Statistic title="R²" value={(capm.r_squared || 0) * 100} suffix="%" precision={1} />
            </Col>
          </Row>
          {capm.significance ? (
            <Space wrap size={8} style={{ marginTop: 8 }}>
              <Tag>{`Alpha t=${capm.significance.alpha_t_stat}`}</Tag>
              <Tag>{`Alpha p=${capm.significance.alpha_p_value}`}</Tag>
              <Tag>{`Beta t=${capm.significance.beta_t_stat}`}</Tag>
              <Tag>{`DW=${capm.residual_diagnostics?.durbin_watson || 0}`}</Tag>
            </Space>
          ) : null}
          {capm.interpretation && (
            <div style={{ marginTop: 12 }}>
              {Object.entries(capm.interpretation).map(([key, val]) => (
                <Paragraph key={key} style={{ marginBottom: 4, fontSize: 12 }}>
                  <InfoCircleOutlined style={{ marginRight: 4, color: '#1890ff' }} />
                  {val}
                </Paragraph>
              ))}
            </div>
          )}
        </>
      ) : <Text type="secondary">{capm.error}</Text>}

      {/* Fama-French */}
      <Divider orientation="left" style={{ fontSize: 13 }}>Fama-French 三因子</Divider>
      {hasFF3 ? (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="FF3 Alpha" value={ff3.alpha_pct || 0} suffix="%" precision={2}
                valueStyle={{ color: (ff3.alpha_pct || 0) > 0 ? '#3f8600' : '#cf1322' }} />
            </Col>
            <Col span={6}>
              <Tooltip title="市场因子暴露度 (Mkt-RF)">
                <Statistic title="市场" value={ff3.factor_loadings?.market || 0} precision={3} />
              </Tooltip>
            </Col>
            <Col span={6}>
              <Tooltip title="规模因子暴露度 (SMB)">
                <Statistic title="规模" value={ff3.factor_loadings?.size || 0} precision={3} />
              </Tooltip>
            </Col>
            <Col span={6}>
              <Tooltip title="价值因子暴露度 (HML)">
                <Statistic title="价值" value={ff3.factor_loadings?.value || 0} precision={3} />
              </Tooltip>
            </Col>
          </Row>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>R² = {((ff3.r_squared || 0) * 100).toFixed(1)}%</Text>
          </div>
          {ff3.significance ? (
            <Space wrap size={8} style={{ marginTop: 8 }}>
              <Tag>{`Alpha p=${ff3.significance.alpha_p_value}`}</Tag>
              <Tag>{`市场 p=${ff3.significance.market_p_value}`}</Tag>
              <Tag>{`规模 p=${ff3.significance.size_p_value}`}</Tag>
              <Tag>{`价值 p=${ff3.significance.value_p_value}`}</Tag>
            </Space>
          ) : null}
          {radarData.length ? (
            <div style={{ width: '100%', height: 220, marginTop: 12 }}>
              <ResponsiveContainer>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="subject" />
                  <PolarRadiusAxis />
                  <Radar dataKey="exposure" stroke="#722ed1" fill="#b37feb" fillOpacity={0.45} />
                  <RechartsTooltip formatter={(value) => [Number(value).toFixed(2), '暴露度']} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          {ff3.interpretation && (
            <div style={{ marginTop: 8 }}>
              {Object.entries(ff3.interpretation).map(([key, val]) => (
                <Paragraph key={key} style={{ marginBottom: 4, fontSize: 12 }}>
                  <InfoCircleOutlined style={{ marginRight: 4, color: '#722ed1' }} />
                  {val}
                </Paragraph>
              ))}
            </div>
          )}
        </>
      ) : <Text type="secondary">{ff3.error}</Text>}

      <Divider orientation="left" style={{ fontSize: 13 }}>Fama-French 五因子</Divider>
      {hasFF5 ? (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="FF5 Alpha" value={ff5.alpha_pct || 0} suffix="%" precision={2}
                valueStyle={{ color: (ff5.alpha_pct || 0) > 0 ? '#3f8600' : '#cf1322' }} />
            </Col>
            <Col span={6}>
              <Statistic title="盈利能力" value={ff5.factor_loadings?.profitability || 0} precision={3} />
            </Col>
            <Col span={6}>
              <Statistic title="投资" value={ff5.factor_loadings?.investment || 0} precision={3} />
            </Col>
            <Col span={6}>
              <Statistic title="R²" value={(ff5.r_squared || 0) * 100} suffix="%" precision={1} />
            </Col>
          </Row>
          {ff5.significance ? (
            <Space wrap size={8} style={{ marginTop: 8 }}>
              <Tag>{`盈利 p=${ff5.significance.profitability_p_value}`}</Tag>
              <Tag>{`投资 p=${ff5.significance.investment_p_value}`}</Tag>
            </Space>
          ) : null}
          {ff5.interpretation ? (
            <div style={{ marginTop: 8 }}>
              {Object.entries(ff5.interpretation).slice(3).map(([key, val]) => (
                <Paragraph key={key} style={{ marginBottom: 4, fontSize: 12 }}>
                  <InfoCircleOutlined style={{ marginRight: 4, color: '#13c2c2' }} />
                  {val}
                </Paragraph>
              ))}
            </div>
          ) : null}
        </>
      ) : <Text type="secondary">{ff5.error}</Text>}

      {/* 因子归因 */}
      {attribution.components && (
        <>
          <Divider orientation="left" style={{ fontSize: 13 }}>因子归因</Divider>
          {attributionChartData.length ? (
            <div style={{ width: '100%', height: 220, marginBottom: 12 }}>
              <ResponsiveContainer>
                <BarChart data={attributionChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <RechartsTooltip formatter={(value) => [`${Number(value).toFixed(2)}%`, '贡献']} />
                  <Bar dataKey="pct">
                    {attributionChartData.map((item) => (
                      <Cell key={item.name} fill={item.pct >= 0 ? '#52c41a' : '#ff4d4f'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          <Table
            size="small"
            pagination={false}
            dataSource={Object.entries(attribution.components).map(([k, v]) => ({ key: k, ...v }))}
            columns={[
              { title: '因子', dataIndex: 'label', key: 'label' },
              {
                title: '贡献',
                dataIndex: 'pct',
                key: 'pct',
                render: (v) => (
                  <span style={{ color: v > 0 ? '#3f8600' : v < 0 ? '#cf1322' : undefined }}>
                    {v > 0 ? '+' : ''}{v}%
                  </span>
                ),
              },
            ]}
          />
        </>
      )}

      {residualChartData.length ? (
        <>
          <Divider orientation="left" style={{ fontSize: 13 }}>残差诊断</Divider>
          <Space wrap size={8} style={{ marginBottom: 8 }}>
            {capm.idiosyncratic_risk ? <Tag>{`CAPM 特质波动 ${(Number(capm.idiosyncratic_risk) * 100).toFixed(1)}%`}</Tag> : null}
            {ff3.residual_diagnostics?.durbin_watson ? <Tag>{`FF3 DW=${ff3.residual_diagnostics.durbin_watson}`}</Tag> : null}
            {ff5.residual_diagnostics?.durbin_watson ? <Tag>{`FF5 DW=${ff5.residual_diagnostics.durbin_watson}`}</Tag> : null}
          </Space>
          <div style={{ width: '100%', height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={residualChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="model" />
                <YAxis />
                <RechartsTooltip formatter={(value, name) => [Number(value).toFixed(2), name === 'lag1' ? 'Lag1 自相关' : 'Durbin-Watson']} />
                <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                <Bar dataKey="lag1" fill="#faad14" radius={[6, 6, 0, 0]} />
                <Bar dataKey="dw" fill="#1677ff" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : null}
    </Card>
  );
};

const RANGE_BASIS_LABELS = {
  dcf_scenarios_and_multiples: 'DCF 情景 + 可比倍数分布',
  dcf_scenarios: 'DCF 情景区间',
  comparable_method_span: '可比估值方法分布',
  valuation_span: '估值方法分布',
  fallback_band: '默认安全边界',
};

/** 估值分析卡片 */
export const ValuationCard = ({ data }) => {
  if (!data) return null;
  const dcf = data.dcf || {};
  const monteCarlo = data.monte_carlo || {};
  const comparable = data.comparable || {};
  const fairValue = data.fair_value || {};
  const dcfScenarios = dcf.scenarios || [];
  const projectedFcfs = dcf.projected_fcfs || [];
  const fairValueBand = fairValue.mid ? [
    { name: '下沿', value: Number(fairValue.low || 0) },
    { name: '中值', value: Number(fairValue.mid || 0) },
    { name: '上沿', value: Number(fairValue.high || 0) },
  ] : [];

  const hasDCF = !dcf.error;
  const hasComparable = !comparable.error;
  const monteCarloDistribution = monteCarlo.distribution || [];

  return (
    <Card
      data-testid="pricing-valuation-card"
      title={<><DollarOutlined style={{ marginRight: 8 }} />内在价值估值</>}
      extra={data.sector && <Tag color="purple">{data.sector}</Tag>}
    >
      {/* 综合估值结果 */}
      {fairValue.mid && (
        <div style={{
          textAlign: 'center', padding: '12px 0', marginBottom: 16,
          background: 'var(--bg-secondary, #fafafa)', borderRadius: 8
        }}>
          <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 4 }}>综合公允价值</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#1890ff' }}>${fairValue.mid}</div>
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>
            区间: ${fairValue.low} ~ ${fairValue.high}
          </div>
          <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>方法: {fairValue.method}</div>
          {fairValue.range_basis ? (
            <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
              区间依据: {RANGE_BASIS_LABELS[fairValue.range_basis] || fairValue.range_basis}
            </div>
          ) : null}
          {fairValueBand.length ? (
            <div style={{ width: '100%', height: 120, marginTop: 10 }}>
              <ResponsiveContainer>
                <LineChart data={fairValueBand}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis hide />
                  <RechartsTooltip formatter={(value) => [`$${Number(value).toFixed(2)}`, '估值']} />
                  <Line type="monotone" dataKey="value" stroke="#1677ff" strokeWidth={3} dot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </div>
      )}

      {/* DCF 估值 */}
      <Divider orientation="left" style={{ fontSize: 13 }}>DCF 现金流折现</Divider>
      {hasDCF ? (
        <>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="DCF 内在价值">
              <Text strong>${dcf.intrinsic_value}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="溢价/折价">
              <Text style={{ color: (dcf.premium_discount || 0) > 0 ? '#cf1322' : '#3f8600' }}>
                {dcf.premium_discount > 0 ? '+' : ''}{dcf.premium_discount}%
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="WACC">{((dcf.assumptions?.wacc || 0) * 100).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="终值占比">{dcf.terminal_pct}%</Descriptions.Item>
          </Descriptions>
          {projectedFcfs.length ? (
            <div style={{ width: '100%', height: 220, marginTop: 12 }}>
              <ResponsiveContainer>
                <AreaChart data={projectedFcfs}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <Legend />
                  <RechartsTooltip formatter={(value) => [`${Number(value).toFixed(0)}`, '']} />
                  <Area type="monotone" dataKey="fcf" name="预测 FCF" stroke="#1677ff" fill="#91caff" fillOpacity={0.5} />
                  <Line type="monotone" dataKey="pv" name="折现现值" stroke="#fa8c16" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          {dcfScenarios.length ? (
            <>
              <Divider orientation="left" style={{ fontSize: 13 }}>DCF 情景分析</Divider>
              <Table
                size="small"
                pagination={false}
                rowKey="name"
                dataSource={dcfScenarios}
                columns={[
                  { title: '情景', dataIndex: 'label', key: 'label', width: 90 },
                  {
                    title: '公允价值',
                    dataIndex: 'intrinsic_value',
                    key: 'intrinsic_value',
                    render: (value) => `$${Number(value || 0).toFixed(2)}`,
                  },
                  {
                    title: 'WACC',
                    dataIndex: ['assumptions', 'wacc'],
                    key: 'wacc',
                    render: (value) => `${(Number(value || 0) * 100).toFixed(1)}%`,
                  },
                  {
                    title: '初始增长',
                    dataIndex: ['assumptions', 'initial_growth'],
                    key: 'initial_growth',
                    render: (value) => `${(Number(value || 0) * 100).toFixed(1)}%`,
                  },
                  {
                    title: '溢价/折价',
                    dataIndex: 'premium_discount',
                    key: 'premium_discount',
                    render: (value) => (
                      value === null || value === undefined
                        ? '—'
                        : <span style={{ color: value > 0 ? '#cf1322' : '#3f8600' }}>{value > 0 ? '+' : ''}{value}%</span>
                    ),
                  },
                ]}
              />
            </>
          ) : null}
          {monteCarloDistribution.length ? (
            <>
              <Divider orientation="left" style={{ fontSize: 13 }}>Monte Carlo 估值分布</Divider>
              <Space wrap size={8} style={{ marginBottom: 8 }}>
                <Tag>{`样本 ${monteCarlo.sample_count || 0}`}</Tag>
                <Tag>{`P10 $${Number(monteCarlo.p10 || 0).toFixed(2)}`}</Tag>
                <Tag>{`P50 $${Number(monteCarlo.p50 || 0).toFixed(2)}`}</Tag>
                <Tag>{`P90 $${Number(monteCarlo.p90 || 0).toFixed(2)}`}</Tag>
              </Space>
              <div style={{ width: '100%', height: 220, marginTop: 12 }}>
                <ResponsiveContainer>
                  <BarChart data={monteCarloDistribution}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="bucket" hide />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [Number(value).toFixed(0), '样本数']} />
                    <Bar dataKey="count" fill="#36cfc9" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : null}
        </>
      ) : <Text type="secondary">{dcf.error}</Text>}

      {/* 可比估值法 */}
      <Divider orientation="left" style={{ fontSize: 13 }}>可比公司估值</Divider>
      {hasComparable ? (
        <>
          {comparable.warnings?.length ? (
            <Alert
              type="warning"
              showIcon
              message="可比估值提醒"
              description={comparable.warnings.join(' ')}
              style={{ marginBottom: 12 }}
            />
          ) : null}
          <Table
            size="small"
            pagination={false}
            dataSource={(comparable.methods || []).map((m, i) => ({ key: i, ...m }))}
            columns={[
              { title: '方法', dataIndex: 'method', key: 'method', width: 130 },
              { title: '当前倍数', dataIndex: 'current_multiple', key: 'cur', render: v => v?.toFixed(1) },
              { title: '行业基准', dataIndex: 'benchmark_multiple', key: 'bench', render: v => v?.toFixed(1) },
              {
                title: '公允价值',
                dataIndex: 'fair_value',
                key: 'fv',
                render: v => v ? `$${v.toFixed(2)}` : '-'
              },
            ]}
          />
          <Space wrap size={8} style={{ marginTop: 8 }}>
            <Tag>{`权重 DCF ${Math.round(Number(fairValue.dcf_weight || 0) * 100)}%`}</Tag>
            <Tag>{`权重 可比 ${Math.round(Number(fairValue.comparable_weight || 0) * 100)}%`}</Tag>
            {comparable.benchmark_source ? <Tag>{`基准来源 ${comparable.benchmark_source}`}</Tag> : null}
            {comparable.benchmark_peer_count ? <Tag>{`同行样本 ${comparable.benchmark_peer_count}`}</Tag> : null}
            {comparable.benchmark_peer_symbols?.length ? <Tag>{`参考同行 ${comparable.benchmark_peer_symbols.join(', ')}`}</Tag> : null}
          </Space>
        </>
      ) : <Text type="secondary">{comparable.error}</Text>}
    </Card>
  );
};

/** 偏差驱动因素卡片 */
export const DriversCard = ({ data }) => {
  if (!data) return null;
  const drivers = data.drivers || [];
  const primaryDriver = data.primary_driver || drivers[0] || null;
  const driverChartData = drivers.map((driver) => ({
    name: driver.factor,
    contribution: Number(driver.signal_strength || 0)
      * (['negative', 'undervalued', 'defensive'].includes(driver.impact) ? -1 : 1),
  }));
  const waterfallChartData = drivers.reduce((rows, driver) => {
    const contribution = Number(driver.signal_strength || 0)
      * (['negative', 'undervalued', 'defensive'].includes(driver.impact) ? -1 : 1);
    const previousEnd = rows.length ? rows[rows.length - 1].end : 0;
    const nextEnd = previousEnd + contribution;
    rows.push({
      name: driver.factor,
      base: previousEnd,
      contribution,
      end: nextEnd,
    });
    return rows;
  }, []);

  return (
    <Card data-testid="pricing-drivers-card" title={<><SwapOutlined style={{ marginRight: 8 }} />偏差驱动因素</>}>
      {drivers.length > 0 ? (
        <div>
          {primaryDriver ? (
            <div style={{
              padding: '10px 12px',
              marginBottom: 12,
              background: 'var(--bg-secondary, #fafafa)',
              borderRadius: 8,
              border: '1px solid var(--border-color, #f0f0f0)',
            }}>
              {(() => {
                const primaryStrength = getSignalStrengthMeta(primaryDriver.signal_strength);
                const primaryImpact = getDriverImpactMeta(primaryDriver.impact);
                return (
                  <>
                    <Space wrap size={6}>
                      <Tag color="gold">主驱动</Tag>
                      <Text strong>{primaryDriver.factor}</Text>
                      <Tag color={primaryImpact.color}>{primaryImpact.label}</Tag>
                      {primaryStrength ? (
                        <Tag color={primaryStrength.color}>{`强度 ${primaryStrength.label} (${primaryStrength.score.toFixed(2)})`}</Tag>
                      ) : null}
                    </Space>
                    {primaryDriver.ranking_reason ? (
                      <Paragraph style={{ marginBottom: 0, marginTop: 6, fontSize: 12, color: '#8c8c8c' }}>
                        判断依据：{primaryDriver.ranking_reason}
                      </Paragraph>
                    ) : null}
                  </>
                );
              })()}
            </div>
          ) : null}
          {driverChartData.length ? (
            <div style={{ width: '100%', height: 220, marginBottom: 12 }}>
              <ResponsiveContainer>
                <BarChart data={driverChartData} layout="vertical" margin={{ top: 12, right: 12, left: 24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={110} />
                  <ReferenceLine x={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                  <RechartsTooltip formatter={(value) => [Number(value).toFixed(2), '驱动贡献']} />
                  <Bar dataKey="contribution" radius={[0, 6, 6, 0]}>
                    {driverChartData.map((item) => (
                      <Cell key={item.name} fill={item.contribution >= 0 ? '#ff7875' : '#73d13d'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          {waterfallChartData.length ? (
            <>
              <Text type="secondary" style={{ fontSize: 12 }}>驱动瀑布视图</Text>
              <div style={{ width: '100%', height: 240, marginTop: 8, marginBottom: 12 }}>
                <ResponsiveContainer>
                  <ComposedChart data={waterfallChartData} margin={{ top: 12, right: 12, left: 0, bottom: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" angle={-12} textAnchor="end" height={56} interval={0} />
                    <YAxis />
                    <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                    <RechartsTooltip formatter={(value, name) => [Number(value).toFixed(2), name === 'contribution' ? '边际贡献' : '累计偏差']} />
                    <Bar dataKey="base" stackId="waterfall" fill="transparent" />
                    <Bar dataKey="contribution" stackId="waterfall">
                      {waterfallChartData.map((item) => (
                        <Cell key={item.name} fill={item.contribution >= 0 ? '#ff7875' : '#73d13d'} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="end" stroke="#1677ff" strokeWidth={2} dot={{ r: 4 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : null}
          {drivers.map((d, i) => {
            const impactMeta = getDriverImpactMeta(d.impact);
            const strengthMeta = getSignalStrengthMeta(d.signal_strength);
            return (
              <div key={i} style={{
                padding: '10px 12px', marginBottom: 8,
                border: '1px solid var(--border-color, #f0f0f0)',
                borderRadius: 6, borderLeft: `3px solid ${impactMeta.color}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space wrap size={6}>
                    <Text strong style={{ fontSize: 13 }}>{d.factor}</Text>
                    {d.rank === 1 ? <Tag color="gold">#1</Tag> : null}
                    {strengthMeta ? (
                      <Tag color={strengthMeta.color}>{`强度 ${strengthMeta.label} (${strengthMeta.score.toFixed(2)})`}</Tag>
                    ) : null}
                  </Space>
                  <Tag color={impactMeta.color}>{impactMeta.label}</Tag>
                </div>
                <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  {d.description}
                </Paragraph>
                {d.ranking_reason ? (
                  <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 11, color: '#bfbfbf' }}>
                    判断依据：{d.ranking_reason}
                  </Paragraph>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <Empty description="未检测到显著偏差因素" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Card>
  );
};

/** 投资含义卡片 */
export const ImplicationsCard = ({ data, valuation = {}, factorModel = {}, gapAnalysis = {}, onRetry }) => {
  if (!data) return null;

  const riskColors = { low: '#52c41a', medium: '#faad14', high: '#ff4d4f' };
  const riskLabels = { low: '低', medium: '中', high: '高' };
  const confLabels = { low: '低', medium: '中', high: '高' };
  const confidenceReasons = data.confidence_reasons || [];
  const confidenceBreakdown = data.confidence_breakdown || [];
  const confidenceScore = data.confidence_score;
  const alignmentMeta = data.factor_alignment || null;
  const tradeSetup = data.trade_setup || null;
  const evidenceItems = [
    valuation.current_price_source ? `现价来源 ${getPriceSourceLabel(valuation.current_price_source)}` : null,
    factorModel.data_points ? `因子样本 ${factorModel.data_points}` : null,
    factorModel.period ? `分析窗口 ${factorModel.period}` : null,
  ].filter(Boolean);
  const actionPosture = buildPricingActionPosture({
    gapPct: gapAnalysis?.gap_pct,
    confidenceScore,
    alignmentStatus: alignmentMeta?.status,
    primaryView: data.primary_view,
    riskLevel: data.risk_level,
  });

  return (
    <Card data-testid="pricing-implications-card" title={<><InfoCircleOutlined style={{ marginRight: 8 }} />投资含义</>}>
      <div style={{ marginBottom: 12 }}>
        <Space size="large">
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>综合判断</Text>
            <div>
              <Tag
                color={data.primary_view === '低估' ? 'green' : data.primary_view === '高估' ? 'red' : 'blue'}
                style={{ fontSize: 16, padding: '4px 16px', marginTop: 4 }}
              >
                {data.primary_view || '合理'}
              </Tag>
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>风险等级</Text>
            <div>
              <Tag color={riskColors[data.risk_level]} style={{ marginTop: 4 }}>
                {riskLabels[data.risk_level] || '中'}
              </Tag>
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>分析置信度</Text>
            <div>
              <Tag style={{ marginTop: 4 }}>{confLabels[data.confidence] || '中'}</Tag>
            </div>
            {confidenceScore !== undefined && confidenceScore !== null ? (
              <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
                评分 {Number(confidenceScore).toFixed(2)}
              </Text>
            ) : null}
          </div>
          {alignmentMeta ? (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>证据共振</Text>
              <div>
                <Tag color={ALIGNMENT_TAG_COLORS[alignmentMeta.status] || 'default'} style={{ marginTop: 4 }}>
                  {alignmentMeta.label || '待确认'}
                </Tag>
              </div>
            </div>
          ) : null}
        </Space>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {evidenceItems.length ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>证据质量</Text>
          <div style={{ marginTop: 6 }}>
            <Space wrap size={6}>
              {evidenceItems.map((item) => (
                <Tag key={item}>{item}</Tag>
              ))}
            </Space>
          </div>
        </div>
      ) : null}

      {alignmentMeta?.summary ? (
        <Paragraph style={{ marginBottom: 12, fontSize: 12, color: '#8c8c8c' }}>
          <InfoCircleOutlined style={{ marginRight: 6, color: '#52c41a' }} />
          {alignmentMeta.summary}
        </Paragraph>
      ) : null}

      {actionPosture ? (
        <Alert
          type={actionPosture.type}
          showIcon
          style={{ marginBottom: 12 }}
          message={actionPosture.title}
          description={`${actionPosture.actionHint} ${actionPosture.reason}`.trim()}
        />
      ) : null}

      {confidenceReasons.length ? (
        <div style={{ marginBottom: 12 }}>
          {confidenceReasons.map((reason, i) => (
            <Paragraph key={`${reason}-${i}`} style={{ marginBottom: 6, fontSize: 12, color: '#8c8c8c' }}>
              <InfoCircleOutlined style={{ marginRight: 6, color: '#faad14' }} />
              {reason}
            </Paragraph>
          ))}
        </div>
      ) : null}

      {confidenceScore !== undefined && confidenceScore !== null ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>置信度透明度</Text>
          <Progress percent={Math.round(Number(confidenceScore) * 100)} strokeColor="#1677ff" />
        </div>
      ) : null}

      {confidenceBreakdown.length ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>置信度拆解</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
            {confidenceBreakdown.map((item) => (
              <div
                key={item.key}
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--border-color, #f0f0f0)',
                  borderRadius: 8,
                  background: 'var(--bg-secondary, #fafafa)',
                }}
              >
                <Space wrap size={6}>
                  <Text strong style={{ fontSize: 12 }}>{item.label}</Text>
                  <Tag color={item.status === 'positive' ? 'green' : item.status === 'negative' ? 'red' : 'gold'}>
                    {item.delta > 0 ? `+${item.delta.toFixed(2)}` : item.delta.toFixed(2)}
                  </Tag>
                </Space>
                <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  {item.detail}
                </Paragraph>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {tradeSetup ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>交易情景</Text>
          <div
            style={{
              marginTop: 8,
              padding: '12px',
              borderRadius: 10,
              background: 'var(--bg-secondary, #fafafa)',
              border: '1px solid var(--border-color, #f0f0f0)',
            }}
          >
            <Space wrap size={6} style={{ marginBottom: 8 }}>
              <Tag color="blue">{tradeSetup.stance || '观察'}</Tag>
              {tradeSetup.target_price ? <Tag>{`目标价 $${Number(tradeSetup.target_price).toFixed(2)}`}</Tag> : null}
              {tradeSetup.stop_loss ? <Tag color="volcano">{`风险边界 $${Number(tradeSetup.stop_loss).toFixed(2)}`}</Tag> : null}
              {tradeSetup.risk_reward ? <Tag color="purple">{`盈亏比 ${Number(tradeSetup.risk_reward).toFixed(2)}`}</Tag> : null}
            </Space>
            {tradeSetup.summary ? (
              <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#595959' }}>
                {tradeSetup.summary}
              </Paragraph>
            ) : null}
            <Space wrap size={8}>
              {tradeSetup.upside_pct !== undefined ? <Tag color="green">{`基准空间 ${tradeSetup.upside_pct > 0 ? '+' : ''}${tradeSetup.upside_pct}%`}</Tag> : null}
              {tradeSetup.stretch_upside_pct !== undefined ? <Tag>{`扩展空间 ${tradeSetup.stretch_upside_pct > 0 ? '+' : ''}${tradeSetup.stretch_upside_pct}%`}</Tag> : null}
              {tradeSetup.risk_pct !== undefined ? <Tag color="red">{`风险预算 ${tradeSetup.risk_pct}%`}</Tag> : null}
            </Space>
            {tradeSetup.quality_note ? (
              <Paragraph style={{ marginBottom: 0, marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>
                {tradeSetup.quality_note}
              </Paragraph>
            ) : null}
          </div>
        </div>
      ) : null}

      {(data.insights || []).map((insight, i) => (
        <Paragraph key={i} style={{ marginBottom: 6, fontSize: 13 }}>
          <InfoCircleOutlined style={{ marginRight: 6, color: '#1890ff' }} />
          {insight}
        </Paragraph>
      ))}

      {onRetry ? (
        <Button type="link" onClick={() => onRetry()} style={{ paddingLeft: 0 }}>
          重新分析
        </Button>
      ) : null}
    </Card>
  );
};

export default PricingResearch;
