import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, SafetyCertificateOutlined, SwapOutlined } from '@ant-design/icons';

import { getEtfRotationDailySignal } from '../services/api';

const { Text, Title } = Typography;

const ETF_NAMES = {
  '159985': '豆粕ETF华夏',
  '512400': '有色金属ETF南方',
  '510300': '沪深300ETF华泰柏瑞',
  '518680': '金ETF富国',
  '513130': '恒生科技ETF华泰柏瑞',
  CASH: '现金',
};

const ACTION_META = {
  buy: { color: 'red', label: '买入' },
  sell: { color: 'green', label: '卖出' },
  hold: { color: 'default', label: '持有' },
};

const formatPercent = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `${(number * 100).toFixed(2)}%`;
};

const formatCurrency = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `¥${number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
};

const buildWeightRows = (plan) => {
  const current = plan?.current_weights || {};
  const target = plan?.target_weights || {};
  const adjusted = plan?.adjusted_weights || {};
  const codes = Array.from(new Set([...Object.keys(current), ...Object.keys(target), ...Object.keys(adjusted)]));
  const orderedCodes = [...codes.filter((code) => code !== 'CASH').sort(), ...codes.filter((code) => code === 'CASH')];
  return orderedCodes.map((code) => ({
    key: code,
    code,
    name: ETF_NAMES[code] || code,
    current: current[code],
    target: target[code],
    adjusted: adjusted[code],
  }));
};

const EtfRotationDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEtfRotationDailySignal()
      .then((response) => {
        if (cancelled) return;
        const data = response?.data || response || null;
        setPlan(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.userMessage || err?.message || 'ETF轮动信号加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const weightRows = useMemo(() => buildWeightRows(plan), [plan]);
  const suggestions = Array.isArray(plan?.suggestions) ? plan.suggestions : [];
  const riskReasons = Array.isArray(plan?.risk_reasons) ? plan.risk_reasons : [];

  const weightColumns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 110 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '当前权重', dataIndex: 'current', key: 'current', render: formatPercent },
    { title: '策略目标', dataIndex: 'target', key: 'target', render: formatPercent },
    { title: '风控后目标', dataIndex: 'adjusted', key: 'adjusted', render: formatPercent },
  ];

  const suggestionColumns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 110 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '动作',
      dataIndex: 'action',
      key: 'action',
      render: (action) => {
        const meta = ACTION_META[action] || ACTION_META.hold;
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    { title: '股数', dataIndex: 'shares', key: 'shares', render: (value) => Number(value || 0).toLocaleString('zh-CN') },
    { title: '估算金额', dataIndex: 'estimated_amount', key: 'estimated_amount', render: formatCurrency },
    { title: '原因', dataIndex: 'reason', key: 'reason' },
  ];

  return (
    <div className="etf-rotation-dashboard" data-testid="etf-rotation-dashboard">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }} wrap>
              <Space>
                <SwapOutlined style={{ color: 'var(--accent-primary)' }} />
                <Title level={3} style={{ margin: 0 }}>ETF轮动调仓</Title>
              </Space>
              <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>刷新信号</Button>
            </Space>
            <Alert
              type="info"
              showIcon
              message={plan?.banner || 'Manual trade plan — review and execute manually. No broker API is called and no auto-ordering occurs.'}
              description="本页只展示目标权重和手动买卖建议，不连接券商、不自动下单。"
              data-testid="etf-manual-only-banner"
            />
          </Space>
        </Card>

        {error ? <Alert type="error" showIcon message="ETF轮动信号加载失败" description={error} /> : null}

        {loading && !plan ? (
          <Card><Spin /> <Text type="secondary">正在加载 ETF 轮动信号...</Text></Card>
        ) : !plan ? (
          <Card><Empty description="暂无 ETF 轮动信号" /></Card>
        ) : (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={8}>
                <Card>
                  <Statistic title="组合资产" value={plan.total_asset || 0} precision={2} prefix="¥" />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card>
                  <Statistic title="建议条数" value={suggestions.length} suffix="条" />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card>
                  <Space>
                    <SafetyCertificateOutlined style={{ color: 'var(--accent-success)' }} />
                    <Text strong>{plan.manual_only && plan.auto_ordering === false ? '手动执行 / 无自动下单' : '请复核执行模式'}</Text>
                  </Space>
                </Card>
              </Col>
            </Row>

            <Card title="权重对比" data-testid="etf-weight-table">
              <Table columns={weightColumns} dataSource={weightRows} pagination={false} size="small" />
            </Card>

            <Card title="手动交易建议" data-testid="etf-suggestion-table">
              <Table
                columns={suggestionColumns}
                dataSource={suggestions.map((item) => ({ ...item, key: item.code }))}
                pagination={false}
                size="small"
              />
            </Card>

            <Card title="风控原因" data-testid="etf-risk-reasons">
              {riskReasons.length === 0 ? (
                <Text type="secondary">暂无风控调整。</Text>
              ) : (
                <Space size={[8, 8]} wrap>
                  {riskReasons.map((reason, index) => <Tag key={`${reason}-${index}`}>{reason}</Tag>)}
                </Space>
              )}
            </Card>
          </>
        )}
      </Space>
    </div>
  );
};

export default EtfRotationDashboard;
