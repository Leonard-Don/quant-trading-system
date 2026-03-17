import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  List,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  AimOutlined,
  ClockCircleOutlined,
  GlobalOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';

import {
  getAltDataSnapshot,
  getAltDataStatus,
  getMacroOverview,
  refreshAltData,
} from '../../services/api';

const { Paragraph, Text, Title } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

const signalLabel = {
  1: '猎杀窗口',
  0: '观察中',
  '-1': '逆风区',
};

function GodEyeDashboard() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [status, setStatus] = useState(null);

  const loadDashboard = async (refresh = false) => {
    if (refresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [macroData, altData, statusData] = await Promise.all([
        getMacroOverview(refresh),
        getAltDataSnapshot(refresh),
        getAltDataStatus(),
      ]);
      setOverview(macroData);
      setSnapshot(altData);
      setStatus(statusData);
    } catch (error) {
      message.error(error.userMessage || error.message || '加载作战大屏失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadDashboard(false);
  }, []);

  if (loading && !overview) {
    return (
      <div style={{ minHeight: 360, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  const factorRows = (overview?.factors || []).map((factor) => ({
    key: factor.name,
    ...factor,
  }));

  const providerRows = Object.entries(snapshot?.providers || {}).map(([name, provider]) => ({
    key: name,
    name,
    ...provider,
  }));

  const signalRows = Object.entries(overview?.signals || {}).map(([name, signal]) => ({
    key: name,
    name,
    ...signal,
  }));

  const recentRecords = snapshot?.recent_records || [];
  const providerHealth = snapshot?.provider_health || status?.provider_health || {};
  const staleness = snapshot?.staleness || status?.staleness || {};
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  const snapshotTimestamp = snapshot?.snapshot_timestamp || status?.snapshot_timestamp;
  const schedulerStatus = status?.scheduler || {};
  const degradedProviders = Object.entries(refreshStatus).filter(([, item]) => ['degraded', 'error'].includes(item.status));

  const handleManualRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshAltData('all');
      message.success('另类数据快照已刷新');
      await loadDashboard(false);
    } catch (error) {
      message.error(error.userMessage || error.message || '刷新另类数据失败');
      setRefreshing(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card
        bordered={false}
        style={{
          background:
            'linear-gradient(135deg, rgba(7, 26, 43, 0.95) 0%, rgba(19, 54, 74, 0.92) 52%, rgba(61, 83, 42, 0.88) 100%)',
          color: '#f4f7fb',
          overflow: 'hidden',
        }}
      >
        <Row gutter={[24, 24]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={10}>
              <Tag color="cyan" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
                Macro Mispricing Command Center
              </Tag>
              <Title level={2} style={{ margin: 0, color: '#f4f7fb' }}>
                上帝视角作战大屏
              </Title>
              <Paragraph style={{ margin: 0, color: 'rgba(244, 247, 251, 0.82)', maxWidth: 720 }}>
                这一版先打通“另类数据渗透 -> 宏观因子合成 -> 前端总览”的闭环。
                你现在看到的是第一阶段指挥面板，不是最终视觉形态，但已经能把战场态势跑起来。
              </Paragraph>
              <Button
                type="default"
                onClick={() => {
                  window.history.pushState(null, '', `${window.location.pathname}?view=backtest&tab=cross-market`);
                  window.dispatchEvent(new PopStateEvent('popstate'));
                }}
              >
                前往跨市场回测
              </Button>
            </Space>
          </Col>
          <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
            <Space wrap>
              <Button icon={<ReloadOutlined />} loading={refreshing} onClick={handleManualRefresh}>
                强制刷新
              </Button>
              <Tag color={signalColor[overview?.macro_signal ?? 0]} style={{ fontSize: 14, padding: '6px 10px' }}>
                {signalLabel[overview?.macro_signal ?? 0]}
              </Tag>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic
              title="最近刷新"
              value={snapshotTimestamp || '未刷新'}
              valueStyle={{ fontSize: 16 }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic
              title="数据新鲜度"
              value={staleness?.label || 'unknown'}
              prefix={<SyncOutlined spin={refreshing} />}
            />
            <Text type="secondary">
              最大快照年龄 {staleness?.max_snapshot_age_seconds ?? '-'} 秒
            </Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic
              title="健康提供器"
              value={providerHealth?.healthy_providers ?? 0}
              suffix={`/ ${providerRows.length || 0}`}
              prefix={<GlobalOutlined />}
            />
            <Text type="secondary">
              degraded {providerHealth?.degraded_providers ?? 0} / error {providerHealth?.error_providers ?? 0}
            </Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic
              title="调度器"
              value={schedulerStatus?.running ? 'running' : 'idle'}
              prefix={<RadarChartOutlined />}
            />
            <Text type="secondary">
              jobs {schedulerStatus?.jobs?.length ?? 0}
            </Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card bordered={false}>
            <Statistic
              title="宏观错误定价分数"
              value={overview?.macro_score ?? 0}
              precision={4}
              prefix={<RadarChartOutlined />}
            />
            <Progress
              percent={Math.min(100, Math.abs((overview?.macro_score ?? 0) * 100))}
              strokeColor={overview?.macro_signal === 1 ? '#cf1322' : overview?.macro_signal === -1 ? '#389e0d' : '#d48806'}
              showInfo={false}
              style={{ marginTop: 12 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card bordered={false}>
            <Statistic
              title="提供器数量"
              value={providerRows.length}
              prefix={<GlobalOutlined />}
            />
            <Text type="secondary">已接通政策、产业链、宏观高频三条主线</Text>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card bordered={false}>
            <Statistic
              title="近 30 天信号记录"
              value={recentRecords.length}
              prefix={<AimOutlined />}
            />
            <Text type="secondary">当前展示最近抓到的标准化记录样本</Text>
          </Card>
        </Col>
      </Row>

      {overview?.macro_signal === 1 ? (
        <Alert
          type="warning"
          showIcon
          message="战场提示"
          description="当前综合因子偏向正向扭曲区间，说明市场可能存在值得重点追踪的错价窗口。"
        />
      ) : null}

      {degradedProviders.length ? (
        <Alert
          type="warning"
          showIcon
          message="数据治理提醒"
          description={`当前有 ${degradedProviders.length} 个 provider 处于 degraded/error 状态，页面将继续使用最近成功快照。`}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={11}>
          <Card title="宏观因子面板" bordered={false}>
            <Table
              size="small"
              pagination={false}
              dataSource={factorRows}
              locale={{ emptyText: <Empty description="暂无因子结果" /> }}
              columns={[
                {
                  title: '因子',
                  dataIndex: 'name',
                  key: 'name',
                  render: (value) => <Text strong>{value}</Text>,
                },
                {
                  title: '分数',
                  dataIndex: 'value',
                  key: 'value',
                  render: (value) => Number(value).toFixed(4),
                },
                {
                  title: 'Z-Score',
                  dataIndex: 'z_score',
                  key: 'z_score',
                  render: (value) => Number(value).toFixed(4),
                },
                {
                  title: '信号',
                  dataIndex: 'signal',
                  key: 'signal',
                  render: (value) => <Tag color={signalColor[value]}>{signalLabel[value]}</Tag>,
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={13}>
          <Card title="提供器状态" bordered={false}>
            <Table
              size="small"
              pagination={false}
              dataSource={providerRows}
              locale={{ emptyText: <Empty description="暂无提供器状态" /> }}
              columns={[
                {
                  title: '提供器',
                  dataIndex: 'name',
                  key: 'name',
                },
                {
                  title: '类别',
                  dataIndex: 'category',
                  key: 'category',
                },
                {
                  title: '历史记录',
                  dataIndex: 'history_count',
                  key: 'history_count',
                },
                {
                  title: '状态',
                  dataIndex: 'refresh_status',
                  key: 'refresh_status',
                  render: (value) => (
                    <Tag color={value?.status === 'success' ? 'green' : value?.status === 'degraded' ? 'orange' : value?.status === 'error' ? 'red' : 'blue'}>
                      {value?.status || 'idle'}
                    </Tag>
                  ),
                },
                {
                  title: '快照年龄(s)',
                  dataIndex: 'snapshot_age_seconds',
                  key: 'snapshot_age_seconds',
                  render: (value) => value ?? '-',
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={11}>
          <Card title="最新统一信号" bordered={false}>
            <List
              dataSource={signalRows}
              locale={{ emptyText: '暂无统一信号' }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text strong>{item.name}</Text>
                        <Tag color={signalColor[item.signal]}>{signalLabel[item.signal]}</Tag>
                      </Space>
                    }
                    description={`score=${Number(item.score || 0).toFixed(4)} confidence=${Number(item.confidence || 0).toFixed(4)}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <Card title="最近信号记录" bordered={false}>
            <List
              dataSource={recentRecords.slice(0, 8)}
              locale={{ emptyText: '暂无记录' }}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" size={2}>
                    <Space wrap>
                      <Tag>{item.category}</Tag>
                      <Text strong>{item.source}</Text>
                    </Space>
                    <Text type="secondary">
                      score={Number(item.normalized_score || 0).toFixed(4)} confidence={Number(item.confidence || 0).toFixed(4)}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default GodEyeDashboard;
