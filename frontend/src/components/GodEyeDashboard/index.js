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
  buildWorkbenchLink,
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
        } else if (actionOrTarget === 'workbench-refresh') {
        const preferredCard =
          crossMarketCards.find((card) => card.taskRefreshResonanceDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshBiasCompressionCore && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshSelectionQualityActive && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshReviewContextDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshInputReliabilityDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshSelectionQualityDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshBiasCompressionDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshPolicySourceDriven && card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshResonanceDriven)
          || crossMarketCards.find((card) => card.taskRefreshBiasCompressionCore)
          || crossMarketCards.find((card) => card.taskRefreshSelectionQualityActive)
          || crossMarketCards.find((card) => card.taskRefreshReviewContextDriven)
          || crossMarketCards.find((card) => card.taskRefreshInputReliabilityDriven)
          || crossMarketCards.find((card) => card.taskRefreshSelectionQualityDriven)
          || crossMarketCards.find((card) => card.taskRefreshBiasCompressionDriven)
          || crossMarketCards.find((card) => card.taskRefreshPolicySourceDriven)
          || crossMarketCards.find((card) => card.taskRefreshSeverity === 'high')
          || crossMarketCards.find((card) => card.taskRefreshLabel === '建议复核');
        const preferredReason = preferredCard?.taskRefreshResonanceDriven
          ? 'resonance'
          : preferredCard?.taskRefreshBiasCompressionCore
            ? 'bias_quality_core'
          : preferredCard?.taskRefreshSelectionQualityActive
            ? 'selection_quality_active'
          : preferredCard?.taskRefreshReviewContextDriven
            ? 'review_context'
          : preferredCard?.taskRefreshInputReliabilityDriven
            ? 'input_reliability'
          : preferredCard?.taskRefreshSelectionQualityDriven
            ? 'selection_quality'
          : preferredCard?.taskRefreshPolicySourceDriven
            ? 'policy_source'
            : preferredCard?.taskRefreshBiasCompressionDriven
              ? 'bias_quality'
            : '';
        navigateToAppUrl(
          buildWorkbenchLink(
            {
              refresh: 'high',
              type: 'cross_market',
              sourceFilter: '',
              reason: preferredReason,
              taskId: preferredCard?.taskRefreshTaskId || '',
            },
            window.location.search
          )
        );
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
      return;
    }

    if (actionOrTarget.target === 'workbench') {
      navigateToAppUrl(
        buildWorkbenchLink(
          {
            refresh: actionOrTarget.refresh || '',
            type: actionOrTarget.type || '',
            sourceFilter: actionOrTarget.sourceFilter || '',
            reason: actionOrTarget.reason || '',
            taskId: actionOrTarget.taskId || '',
          },
          window.location.search
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
    () => buildCrossMarketCards(crossMarketTemplates, overview, snapshot, researchTasks),
    [crossMarketTemplates, overview, snapshot, researchTasks]
  );
  const refreshCounts = useMemo(
    () => ({
      high: crossMarketCards.filter((card) => card.taskRefreshLabel === '建议更新').length,
      medium: crossMarketCards.filter((card) => card.taskRefreshLabel === '建议复核').length,
      resonance: crossMarketCards.filter((card) => card.taskRefreshResonanceDriven).length,
      biasQualityCore: crossMarketCards.filter((card) => card.taskRefreshBiasCompressionCore).length,
      selectionQuality: crossMarketCards.filter((card) => card.taskRefreshSelectionQualityDriven).length,
      selectionQualityActive: crossMarketCards.filter((card) => card.taskRefreshSelectionQualityActive).length,
      reviewContext: crossMarketCards.filter((card) => card.taskRefreshReviewContextDriven).length,
      inputReliability: crossMarketCards.filter((card) => card.taskRefreshInputReliabilityDriven).length,
      policySource: crossMarketCards.filter((card) => card.taskRefreshPolicySourceDriven).length,
      biasQuality: crossMarketCards.filter((card) => card.taskRefreshBiasCompressionDriven).length,
    }),
    [crossMarketCards]
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

      {(refreshCounts.high || refreshCounts.medium) ? (
        <Alert
          type={refreshCounts.high ? 'error' : 'warning'}
          showIcon
          message="研究任务更新优先级"
          description={`当前有 ${refreshCounts.high} 个跨市场任务建议立即更新，${refreshCounts.medium} 个任务建议优先复核。其中默认处理顺序会优先看共振驱动，其次是核心腿受压，再是降级运行，然后看复核语境切换，再看输入可靠度变化，最后才是自动降级排序。当前共有 ${refreshCounts.resonance || 0} 个共振驱动任务，${refreshCounts.biasQualityCore || 0} 个已经压到主题核心腿，${refreshCounts.selectionQualityActive || 0} 个当前结果已处于降级运行状态，${refreshCounts.reviewContext || 0} 个最近两版刚切入复核语境，${refreshCounts.inputReliability || 0} 个当前整体输入可靠度已经发生明显变化；此外还有 ${refreshCounts.selectionQuality || 0} 个已经进入自动降级，${refreshCounts.policySource || 0} 个属于政策源驱动，${refreshCounts.biasQuality || 0} 个已经出现偏置收缩。你可以直接从 Alert Hunter 或模板卡重新打开对应剧本。`}
          action={
            <Button size="small" type="primary" onClick={() => navigateTo('workbench-refresh')}>
              打开待更新任务
            </Button>
          }
        />
      ) : null}

      {refreshCounts.selectionQualityActive ? (
        <Alert
          type="warning"
          showIcon
          message="降级运行任务应优先重看"
          description={`当前有 ${refreshCounts.selectionQualityActive} 个跨市场任务的保存结果已经按 softened/auto_downgraded 强度运行。它们不是普通“建议更新”，而是结果本身已经受推荐质量变化影响，建议优先进入任务页重看。`}
          action={
            <Button
              size="small"
              type="primary"
              onClick={() => navigateToAppUrl(
                buildWorkbenchLink(
                  {
                    refresh: 'high',
                    type: 'cross_market',
                    reason: 'selection_quality_active',
                  },
                  window.location.search
                )
              )}
            >
              优先重看降级运行任务
            </Button>
          }
        />
      ) : null}

      {refreshCounts.reviewContext ? (
        <Alert
          type="info"
          showIcon
          message="复核语境切换任务值得先看一眼"
          description={`当前有 ${refreshCounts.reviewContext} 个跨市场任务最近两版刚从普通结果切到复核型结果，或从复核型结果回到普通结果。这类变化不一定都比“降级运行”更紧急，但通常意味着研究语境已经发生切换，适合尽快进入任务页复核。`}
          action={
            <Button
              size="small"
              onClick={() => navigateToAppUrl(
                buildWorkbenchLink(
                  {
                    refresh: 'high',
                    type: 'cross_market',
                    reason: 'review_context',
                  },
                  window.location.search
                )
              )}
            >
              打开复核语境切换任务
            </Button>
          }
        />
      ) : null}

      {refreshCounts.inputReliability ? (
        <Alert
          type="warning"
          showIcon
          message="输入可靠度变化任务值得尽快复核"
          description={`当前有 ${refreshCounts.inputReliability} 个跨市场任务保存时的整体输入可靠度与现在相比已经明显变化。即使政策源标签本身没切换，这类任务也可能意味着模板强度和研究结论需要重新确认；如果已经进入 fragile，通常更适合先复核输入质量，再决定是否继续沿用当前模板强度。`}
          action={
            <Button
              size="small"
              onClick={() => navigateToAppUrl(
                buildWorkbenchLink(
                  {
                    refresh: 'high',
                    type: 'cross_market',
                    reason: 'input_reliability',
                  },
                  window.location.search
                )
              )}
            >
              先复核输入可靠度任务
            </Button>
          }
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
