import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ClockCircleOutlined,
  GlobalOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';

import {
  getAltDataHistory,
  getAltDataSnapshot,
  getAltDataStatus,
  getCrossMarketTemplates,
  getMacroOverview,
  getResearchTasks,
  refreshAltData,
} from '../../services/api';
import AlertHunterPanel from './AlertHunterPanel';
import CrossMarketOverview from './CrossMarketOverview';
import MacroFactorPanel from './MacroFactorPanel';
import PolicyTimelineBar from './PolicyTimelineBar';
import RiskPremiumRadar from './RiskPremiumRadar';
import SupplyChainHeatmap from './SupplyChainHeatmap';
import {
  buildCrossMarketCards,
  buildFactorPanelModel,
  buildHeatmapModel,
  buildHunterModel,
  buildRadarModel,
  buildTimelineModel,
  getSignalLabel,
} from './viewModels';
import {
  buildCrossMarketLink,
  buildPricingLink,
  navigateToAppUrl,
} from '../../utils/researchContext';

const { Paragraph, Text, Title } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

function GodEyeDashboard() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [status, setStatus] = useState(null);
  const [historyPayload, setHistoryPayload] = useState(null);
  const [policyHistory, setPolicyHistory] = useState(null);
  const [crossMarketTemplates, setCrossMarketTemplates] = useState(null);
  const [researchTasks, setResearchTasks] = useState([]);

  const navigateTo = (actionOrTarget) => {
    if (!actionOrTarget) return;

    if (typeof actionOrTarget === 'string') {
      if (actionOrTarget === 'pricing') {
        navigateToAppUrl(buildPricingLink('', 'godeye', '来自 GodEye 的研究入口'));
      } else if (actionOrTarget === 'cross-market') {
        navigateToAppUrl(buildCrossMarketLink('', 'godeye', '来自 GodEye 的跨市场入口'));
      }
      return;
    }

    if (actionOrTarget.target === 'pricing') {
      navigateToAppUrl(
        buildPricingLink(
          actionOrTarget.symbol,
          actionOrTarget.source || 'godeye',
          actionOrTarget.note || ''
        )
      );
      return;
    }

    if (actionOrTarget.target === 'cross-market') {
      navigateToAppUrl(
        buildCrossMarketLink(
          actionOrTarget.template,
          actionOrTarget.source || 'godeye',
          actionOrTarget.note || ''
        )
      );
    }
  };

  const loadDashboard = async (refresh = false) => {
    if (refresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [
        macroData,
        altData,
        statusData,
        historyData,
        policyData,
        templateData,
        researchTaskData,
      ] = await Promise.all([
        getMacroOverview(refresh),
        getAltDataSnapshot(refresh),
        getAltDataStatus(),
        getAltDataHistory({ limit: 120 }),
        getAltDataHistory({ category: 'policy', limit: 16 }),
        getCrossMarketTemplates(),
        getResearchTasks({ limit: 40, type: 'cross_market' }),
      ]);

      setOverview(macroData);
      setSnapshot(altData);
      setStatus(statusData);
      setHistoryPayload(historyData);
      setPolicyHistory(policyData);
      setCrossMarketTemplates(templateData);
      setResearchTasks(researchTaskData?.data || []);
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

  const heatmapModel = useMemo(
    () => buildHeatmapModel(snapshot, historyPayload),
    [snapshot, historyPayload]
  );
  const radarData = useMemo(() => buildRadarModel(overview), [overview]);
  const factorPanelModel = useMemo(
    () => buildFactorPanelModel(overview, snapshot),
    [overview, snapshot]
  );
  const timelineItems = useMemo(
    () => buildTimelineModel(policyHistory),
    [policyHistory]
  );
  const hunterAlerts = useMemo(
    () => buildHunterModel({ snapshot, overview, status, researchTasks }),
    [snapshot, overview, status, researchTasks]
  );
  const crossMarketCards = useMemo(
    () => buildCrossMarketCards(crossMarketTemplates, overview, snapshot),
    [crossMarketTemplates, overview, snapshot]
  );

  if (loading && !overview) {
    return (
      <div style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  const providerHealth = snapshot?.provider_health || status?.provider_health || {};
  const staleness = snapshot?.staleness || status?.staleness || {};
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  const snapshotTimestamp = snapshot?.snapshot_timestamp || status?.snapshot_timestamp;
  const schedulerStatus = status?.scheduler || {};
  const degradedProviders = Object.entries(refreshStatus).filter(([, item]) =>
    ['degraded', 'error'].includes(item.status)
  );

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
            'radial-gradient(circle at top left, rgba(26, 66, 98, 0.96), rgba(10, 22, 33, 0.98) 55%, rgba(38, 54, 34, 0.92))',
          color: '#f4f7fb',
          overflow: 'hidden',
          boxShadow: '0 22px 48px rgba(0, 0, 0, 0.25)',
        }}
      >
        <Row gutter={[24, 24]} align="middle">
          <Col xs={24} lg={15}>
            <Space direction="vertical" size={10}>
              <Tag color="cyan" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
                Macro Mispricing Command Center
              </Tag>
              <Title level={2} style={{ margin: 0, color: '#f4f7fb' }}>
                GodEye V2 作战大屏
              </Title>
              <Paragraph style={{ margin: 0, color: 'rgba(244, 247, 251, 0.82)', maxWidth: 760 }}>
                这一版把单页总览升级成六面板战情沙盘。你可以同时看到供应链热区、风险雷达、政策时间轴、
                宏观因子、猎杀信号，以及跨市场模板入口。
              </Paragraph>
              <Space wrap>
                <Button type="primary" onClick={() => navigateTo('cross-market')}>
                  打开跨市场剧本
                </Button>
                <Button onClick={() => navigateTo('pricing')}>
                  打开定价剧本
                </Button>
              </Space>
            </Space>
          </Col>
          <Col xs={24} lg={9} style={{ textAlign: 'right' }}>
            <Space wrap>
              <Button icon={<ReloadOutlined />} loading={refreshing} onClick={handleManualRefresh}>
                强制刷新
              </Button>
              <Tag color={signalColor[overview?.macro_signal ?? 0]} style={{ fontSize: 14, padding: '6px 10px' }}>
                {getSignalLabel(overview?.macro_signal ?? 0)}
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
            <Text type="secondary">最大快照年龄 {staleness?.max_snapshot_age_seconds ?? '-'} 秒</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic
              title="健康提供器"
              value={providerHealth?.healthy_providers ?? 0}
              suffix={`/ ${Object.keys(snapshot?.providers || {}).length || 0}`}
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
              title="宏观错价分数"
              value={overview?.macro_score ?? 0}
              precision={4}
              prefix={<RadarChartOutlined />}
            />
            <Text type="secondary">scheduler jobs {schedulerStatus?.jobs?.length ?? 0}</Text>
          </Card>
        </Col>
      </Row>

      {overview?.macro_signal === 1 ? (
        <Alert
          type="warning"
          showIcon
          message="战场提示"
          description="当前综合因子偏向正向扭曲区间，说明市场可能处于值得重点追踪的错价窗口。"
        />
      ) : null}

      {degradedProviders.length ? (
        <Alert
          type="warning"
          showIcon
          message="数据治理提醒"
          description={`当前有 ${degradedProviders.length} 个 provider 处于 degraded/error 状态，页面继续使用最近成功快照。`}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <SupplyChainHeatmap cells={heatmapModel.cells} anomalies={heatmapModel.anomalies} />
        </Col>
        <Col xs={24} xl={10}>
          <RiskPremiumRadar
            data={radarData}
            macroScore={overview?.macro_score}
            confidence={overview?.confidence}
            macroSignal={overview?.macro_signal}
            primaryAction={factorPanelModel.primaryAction}
            onNavigate={navigateTo}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={13}>
          <MacroFactorPanel model={factorPanelModel} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={11}>
          <PolicyTimelineBar items={timelineItems} onNavigate={navigateTo} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={11}>
          <AlertHunterPanel alerts={hunterAlerts} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={13}>
          <CrossMarketOverview cards={crossMarketCards} onNavigate={navigateTo} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <Card
            title="战术说明"
            bordered={false}
            bodyStyle={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}
          >
            <Text type="secondary">Supply Chain Heatmap 看物理世界堵点和人才结构压力。</Text>
            <Text type="secondary">Risk Radar 和 Macro Factor Panel 看错价强度与因子驱动。</Text>
            <Text type="secondary">Policy Timeline + Alert Hunter 用来决定是去 pricing 还是 cross-market。</Text>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default GodEyeDashboard;
