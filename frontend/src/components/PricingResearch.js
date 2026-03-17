import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Card, Row, Col, Input, Button, Select, Spin, Statistic, Tag, Space,
  Descriptions, Table, Alert, Typography, Tooltip, Divider, Empty, message
} from 'antd';
import {
  SearchOutlined, FundOutlined, DollarOutlined, SwapOutlined,
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
  InfoCircleOutlined, ExperimentOutlined
} from '@ant-design/icons';
import { createResearchTask, getGapAnalysis } from '../services/api';
import ResearchPlaybook from './research-playbook/ResearchPlaybook';
import { buildPricingPlaybook, buildPricingWorkbenchPayload } from './research-playbook/playbookViewModels';
import { formatResearchSource, navigateByResearchAction, readResearchContext } from '../utils/researchContext';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

/**
 * 定价研究面板
 * 整合因子模型分析、内在价值估值和定价差异分析
 */
const PricingResearch = () => {
  const [symbol, setSymbol] = useState('');
  const [period, setPeriod] = useState('1y');
  const [loading, setLoading] = useState(false);
  const [savingTask, setSavingTask] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [researchContext, setResearchContext] = useState(readResearchContext());
  const autoLoadedContextRef = useRef('');

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

  const handleAnalyze = useCallback(async (overrideSymbol = null) => {
    const targetSymbol = (overrideSymbol || symbol).trim().toUpperCase();
    if (!targetSymbol) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getGapAnalysis(targetSymbol, period);
      setData(result);
    } catch (err) {
      setError(err.userMessage || err.message || '分析失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, period]);

  useEffect(() => {
    const syncFromUrl = () => {
      const nextContext = readResearchContext();
      setResearchContext(nextContext);
      if (nextContext.view === 'pricing' && nextContext.symbol) {
        setSymbol(nextContext.symbol);
        const contextKey = `${nextContext.symbol}:${nextContext.source}:${nextContext.note}`;
        if (autoLoadedContextRef.current !== contextKey) {
          autoLoadedContextRef.current = contextKey;
          handleAnalyze(nextContext.symbol);
        }
      }
    };

    syncFromUrl();
    window.addEventListener('popstate', syncFromUrl);
    return () => window.removeEventListener('popstate', syncFromUrl);
  }, [handleAnalyze]);

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
      message.success(`已保存到研究工作台: ${response.data?.title || payload.title}`);
    } catch (error) {
      message.error(error.userMessage || error.message || '保存研究任务失败');
    } finally {
      setSavingTask(false);
    }
  };

  return (
    <div>
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
            onSave={handleSaveTask}
            saving={savingTask}
          />
        </div>
      ) : null}

      {/* 搜索栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size="middle" wrap>
          <Input
            placeholder="输入股票代码，如 AAPL, MSFT, NVDA"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyPress={handleKeyPress}
            style={{ width: 280 }}
            prefix={<SearchOutlined />}
            allowClear
          />
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            <Option value="6mo">近6个月</Option>
            <Option value="1y">近1年</Option>
            <Option value="2y">近2年</Option>
            <Option value="3y">近3年</Option>
          </Select>
          <Button type="primary" icon={<ExperimentOutlined />}
            onClick={handleAnalyze} loading={loading}>
            开始分析
          </Button>
        </Space>
      </Card>

      {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {loading && (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: '#8c8c8c' }}>
            正在分析 {symbol.toUpperCase()} 的定价模型，首次加载因子数据可能需要10-20秒...
          </div>
        </div>
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
              <ImplicationsCard data={data.implications} />
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

/** 定价差异概览 */
const GapOverview = ({ data }) => {
  const gap = data?.gap_analysis || {};
  const valuation = data?.valuation || {};
  const gapPct = gap.gap_pct;
  const severity = gap.severity || 'unknown';

  const severityColor = {
    extreme: '#ff4d4f', high: '#fa8c16', moderate: '#faad14',
    mild: '#52c41a', negligible: '#1890ff', unknown: '#d9d9d9'
  };

  const directionIcon = gapPct > 0
    ? <ArrowUpOutlined style={{ color: '#ff4d4f' }} />
    : gapPct < 0
    ? <ArrowDownOutlined style={{ color: '#52c41a' }} />
    : <MinusOutlined />;

  return (
    <Card
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
            value={gap.current_price || 0}
            prefix="$"
            precision={2}
          />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="公允价值"
            value={gap.fair_value_mid || 0}
            prefix="$"
            precision={2}
            valueStyle={{ color: '#1890ff' }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="偏差幅度"
            value={Math.abs(gapPct || 0)}
            suffix="%"
            precision={1}
            prefix={directionIcon}
            valueStyle={{ color: gapPct > 0 ? '#ff4d4f' : '#52c41a' }}
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
          <Text type="secondary">
            公允价值区间: ${gap.fair_value_low} ~ ${gap.fair_value_high}
            {gap.in_fair_range
              ? <Tag color="green" style={{ marginLeft: 8 }}>在合理区间内</Tag>
              : <Tag color="orange" style={{ marginLeft: 8 }}>偏离合理区间</Tag>
            }
          </Text>
        </div>
      )}
    </Card>
  );
};

/** 因子模型分析卡片 */
const FactorModelCard = ({ data }) => {
  if (!data) return null;
  const capm = data.capm || {};
  const ff3 = data.fama_french || {};
  const attribution = data.attribution || {};

  const hasCAPM = !capm.error;
  const hasFF3 = !ff3.error;

  return (
    <Card
      title={<><FundOutlined style={{ marginRight: 8 }} />因子模型分析</>}
      extra={<Tag>{data.period || '1y'}</Tag>}
    >
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

      {/* 因子归因 */}
      {attribution.components && (
        <>
          <Divider orientation="left" style={{ fontSize: 13 }}>因子归因</Divider>
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
    </Card>
  );
};

/** 估值分析卡片 */
const ValuationCard = ({ data }) => {
  if (!data) return null;
  const dcf = data.dcf || {};
  const comparable = data.comparable || {};
  const fairValue = data.fair_value || {};

  const hasDCF = !dcf.error;
  const hasComparable = !comparable.error;

  return (
    <Card
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
        </>
      ) : <Text type="secondary">{dcf.error}</Text>}

      {/* 可比估值法 */}
      <Divider orientation="left" style={{ fontSize: 13 }}>可比公司估值</Divider>
      {hasComparable ? (
        <>
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
        </>
      ) : <Text type="secondary">{comparable.error}</Text>}
    </Card>
  );
};

/** 偏差驱动因素卡片 */
const DriversCard = ({ data }) => {
  if (!data) return null;
  const drivers = data.drivers || [];

  const impactColor = {
    positive: 'green', negative: 'red', risk: 'orange',
    defensive: 'blue', style: 'purple', overvalued: 'red', undervalued: 'green'
  };

  return (
    <Card title={<><SwapOutlined style={{ marginRight: 8 }} />偏差驱动因素</>}>
      {drivers.length > 0 ? (
        <div>
          {drivers.map((d, i) => (
            <div key={i} style={{
              padding: '10px 12px', marginBottom: 8,
              border: '1px solid var(--border-color, #f0f0f0)',
              borderRadius: 6, borderLeft: `3px solid ${impactColor[d.impact] || '#d9d9d9'}`
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text strong style={{ fontSize: 13 }}>{d.factor}</Text>
                <Tag color={impactColor[d.impact]}>{d.impact}</Tag>
              </div>
              <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                {d.description}
              </Paragraph>
            </div>
          ))}
        </div>
      ) : (
        <Empty description="未检测到显著偏差因素" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Card>
  );
};

/** 投资含义卡片 */
const ImplicationsCard = ({ data }) => {
  if (!data) return null;

  const riskColors = { low: '#52c41a', medium: '#faad14', high: '#ff4d4f' };
  const riskLabels = { low: '低', medium: '中', high: '高' };
  const confLabels = { low: '低', medium: '中', high: '高' };

  return (
    <Card title={<><InfoCircleOutlined style={{ marginRight: 8 }} />投资含义</>}>
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
          </div>
        </Space>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {(data.insights || []).map((insight, i) => (
        <Paragraph key={i} style={{ marginBottom: 6, fontSize: 13 }}>
          <InfoCircleOutlined style={{ marginRight: 6, color: '#1890ff' }} />
          {insight}
        </Paragraph>
      ))}
    </Card>
  );
};

export default PricingResearch;
