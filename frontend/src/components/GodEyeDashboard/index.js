import React, { useEffect } from 'react';
import {
  Col,
  Row,
  Spin,
} from 'antd';

import AlertHunterPanel from './AlertHunterPanel';
import CrossMarketOverview from './CrossMarketOverview';
import DecayWatchPanel from './DecayWatchPanel';
import DepartmentChaosBoard from './DepartmentChaosBoard';
import GodEyeAlerts from './GodEyeAlerts';
import GodEyeHeader from './GodEyeHeader';
import GodEyeStatusStats from './GodEyeStatusStats';
import GodEyeTacticalNotes from './GodEyeTacticalNotes';
import MacroFactorPanel from './MacroFactorPanel';
import PeopleLayerWatchlistPanel from './PeopleLayerWatchlistPanel';
import PhysicalWorldTrackerPanel from './PhysicalWorldTrackerPanel';
import PolicyTimelineBar from './PolicyTimelineBar';
import RiskPremiumRadar from './RiskPremiumRadar';
import StructuralDecayRadarPanel from './StructuralDecayRadarPanel';
import SupplyChainHeatmap from './SupplyChainHeatmap';
import TradeThesisWatchPanel from './TradeThesisWatchPanel';
import { navigateDashboardAction } from './navigationHelpers';
import useGodEyeDashboardData from './useGodEyeDashboardData';
import { buildMacroMispricingDraft, saveMacroMispricingDraft } from '../../utils/macroMispricingDraft';
import { buildCrossMarketLink, navigateToAppUrl } from '../../utils/researchContext';
import { publishQuantAlertEvent } from '../../services/api';

function GodEyeDashboard() {
  const {
    crossMarketCards,
    decayWatchModel,
    dashboardStatus,
    factorPanelModel,
    handleManualRefresh,
    handleSaveDecayWatchTask,
    heatmapModel,
    hunterAlerts,
    loading,
    overview,
    radarData,
    refreshCounts,
    refreshSignals,
    refreshing,
    snapshot,
    tradeThesisWatchModel,
    timelineItems,
  } = useGodEyeDashboardData();

  const navigateTo = (actionOrTarget) => {
    navigateDashboardAction(actionOrTarget, {
      crossMarketCards,
      refreshSignals,
      search: window.location.search,
    });
  };

  const handleOpenDecayDraft = (item) => {
    if (!item) return;
    const draft = buildMacroMispricingDraft({
      symbol: item.symbol,
      thesis: item.macroMispricingThesis || {},
      structuralDecay: item.structuralDecay || {},
      peopleLayer: item.peopleLayer || {},
      source: 'godeye_decay_watch',
      note: item.summary || '来自 GodEye Decay Watch 的跨市场草案',
      sourceTaskId: item.taskId || '',
      sourceTaskType: 'pricing',
    });
    const draftId = saveMacroMispricingDraft(draft);
    if (!draftId) return;
    navigateToAppUrl(
      buildCrossMarketLink(
        draft.templateId,
        'godeye_decay_watch',
        item.summary || '来自 GodEye Decay Watch 的跨市场草案',
        window.location.search,
        draftId,
      )
    );
  };
  const {
    degradedProviders,
    providerCount,
    providerHealth,
    schedulerStatus,
    snapshotTimestamp,
    staleness,
  } = dashboardStatus;

  useEffect(() => {
    if (typeof window === 'undefined' || !snapshotTimestamp) {
      return;
    }

    (hunterAlerts || [])
      .filter((alert) => ['high', 'medium'].includes(alert?.severity))
      .slice(0, 6)
      .forEach((alert) => {
        const publishKey = `godeye-alert-bus-published:${alert.key}:${snapshotTimestamp}`;
        if (window.sessionStorage.getItem(publishKey)) {
          return;
        }
        window.sessionStorage.setItem(publishKey, 'true');
        void publishQuantAlertEvent({
          source_module: 'godeye',
          rule_name: alert.title || 'GodEye alert',
          symbol: '',
          severity: alert.severity === 'high' ? 'critical' : 'warning',
          message: alert.description || alert.title || 'GodEye emitted an alert-hunter signal',
          condition_summary: `godeye:${alert.key || 'alert_hunter'}`,
          trigger_value: alert.severity === 'high' ? 1 : 0.5,
          notify_channels: [],
          create_workbench_task: alert.severity === 'high',
          workbench_task_type: 'cross_market',
          persist_event_record: true,
          cascade_actions: [
            { type: 'persist_record', record_type: 'godeye_alert_hit' },
          ],
        }).catch((error) => {
          console.warn('Failed to publish GodEye alert to unified bus:', error);
          window.sessionStorage.removeItem(publishKey);
        });
      });
  }, [hunterAlerts, snapshotTimestamp]);

  useEffect(() => {
    if (typeof window === 'undefined' || !snapshotTimestamp) {
      return;
    }

    const bannerEvents = [];
    const radarScore = Number(overview?.structural_decay_radar?.score || 0);
    const radarHot = overview?.structural_decay_radar?.label === 'decay_alert' || radarScore >= 0.68;

    if (overview?.macro_signal === 1) {
      bannerEvents.push({
        key: `macro_signal:${snapshotTimestamp}`,
        rule_name: '战场提示',
        severity: 'warning',
        message: '当前综合因子偏向正向扭曲区间，市场可能处于值得重点追踪的错价窗口。',
        condition_summary: 'godeye:macro_signal_positive_mispricing',
        trigger_value: Number(overview?.macro_score || 1),
      });
    }

    if (degradedProviders.length) {
      bannerEvents.push({
        key: `provider_health:${degradedProviders.length}:${snapshotTimestamp}`,
        rule_name: '数据治理提醒',
        severity: 'warning',
        message: `当前有 ${degradedProviders.length} 个 provider 处于 degraded/error 状态，页面继续使用最近成功快照。`,
        condition_summary: 'godeye:provider_health_degraded',
        trigger_value: degradedProviders.length,
      });
    }

    if (radarHot) {
      bannerEvents.push({
        key: `structural_decay_radar:${Math.round(radarScore * 100)}:${snapshotTimestamp}`,
        rule_name: '系统级结构衰败雷达进入警报区',
        severity: 'critical',
        message: `${overview?.structural_decay_radar?.display_label || '结构衰败警报'}，综合分 ${Math.round(radarScore * 100)}%。${overview?.structural_decay_radar?.action_hint || '建议优先检查人的维度、政策治理与跨市场防御模板。'}`,
        condition_summary: 'godeye:structural_decay_radar',
        trigger_value: radarScore,
        create_workbench_task: true,
        workbench_task_type: 'macro_mispricing',
      });
    }

    if (refreshCounts.high || refreshCounts.medium) {
      bannerEvents.push({
        key: `refresh_priority:${refreshCounts.high || 0}:${refreshCounts.medium || 0}:${snapshotTimestamp}`,
        rule_name: '研究任务更新优先级',
        severity: refreshCounts.high ? 'critical' : 'warning',
        message: `当前有 ${refreshCounts.high || 0} 个研究任务建议立即更新，${refreshCounts.medium || 0} 个任务建议优先复核。`,
        condition_summary: 'godeye:refresh_priority',
        trigger_value: (refreshCounts.high || 0) + ((refreshCounts.medium || 0) * 0.5),
        create_workbench_task: Boolean(refreshCounts.high),
        workbench_task_type: 'cross_market',
      });
    }

    [
      {
        count: refreshCounts.departmentChaos,
        name: '部门级政策混乱正在影响研究输入',
        condition: 'godeye:department_chaos',
        severity: 'warning',
        taskType: 'cross_market',
      },
      {
        count: refreshCounts.tradeThesis,
        name: '交易 Thesis 正在漂移',
        condition: 'godeye:trade_thesis',
        severity: 'warning',
        taskType: 'cross_market',
      },
      {
        count: refreshCounts.selectionQualityActive,
        name: '降级运行任务应优先重看',
        condition: 'godeye:selection_quality_active',
        severity: 'warning',
        taskType: 'cross_market',
      },
      {
        count: refreshCounts.reviewContext,
        name: '复核语境切换任务值得先看一眼',
        condition: 'godeye:review_context',
        severity: 'warning',
        taskType: 'cross_market',
      },
      {
        count: refreshCounts.inputReliability,
        name: '输入可靠度变化任务值得尽快复核',
        condition: 'godeye:input_reliability',
        severity: 'warning',
        taskType: 'cross_market',
      },
      {
        count: refreshCounts.structuralDecay,
        name: '结构性衰败任务正在继续恶化',
        condition: 'godeye:structural_decay_task',
        severity: 'critical',
        taskType: 'macro_mispricing',
      },
    ].forEach((item) => {
      if (!item.count) {
        return;
      }
      bannerEvents.push({
        key: `${item.condition}:${item.count}:${snapshotTimestamp}`,
        rule_name: item.name,
        severity: item.severity,
        message: `当前有 ${item.count} 个相关任务触发该类提醒。`,
        condition_summary: item.condition,
        trigger_value: item.count,
        create_workbench_task: true,
        workbench_task_type: item.taskType,
      });
    });

    bannerEvents.slice(0, 12).forEach((event) => {
      const publishKey = `godeye-banner-bus-published:${event.key}`;
      if (window.sessionStorage.getItem(publishKey)) {
        return;
      }
      window.sessionStorage.setItem(publishKey, 'true');
      void publishQuantAlertEvent({
        source_module: 'godeye',
        rule_name: event.rule_name,
        symbol: '',
        severity: event.severity,
        message: event.message,
        condition_summary: event.condition_summary,
        trigger_value: event.trigger_value,
        notify_channels: [],
        create_workbench_task: Boolean(event.create_workbench_task),
        workbench_task_type: event.workbench_task_type || 'cross_market',
        persist_event_record: true,
        cascade_actions: [
          { type: 'persist_record', record_type: 'godeye_banner_alert_hit' },
        ],
      }).catch((error) => {
        console.warn('Failed to publish GodEye banner alert to unified bus:', error);
        window.sessionStorage.removeItem(publishKey);
      });
    });
  }, [
    degradedProviders.length,
    overview?.macro_score,
    overview?.macro_signal,
    overview?.structural_decay_radar,
    refreshCounts,
    snapshotTimestamp,
  ]);

  if (loading && !overview) {
    return (
      <div style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <GodEyeHeader
        handleManualRefresh={handleManualRefresh}
        macroSignal={overview?.macro_signal}
        navigateTo={navigateTo}
        refreshing={refreshing}
      />

      <GodEyeStatusStats
        macroScore={overview?.macro_score}
        providerCount={providerCount}
        providerHealth={providerHealth}
        refreshing={refreshing}
        schedulerStatus={schedulerStatus}
        snapshotTimestamp={snapshotTimestamp}
        staleness={staleness}
      />

      <GodEyeAlerts
        macroSignal={overview?.macro_signal}
        degradedProviderCount={degradedProviders.length}
        refreshCounts={refreshCounts}
        structuralDecayRadar={overview?.structural_decay_radar}
        onNavigate={navigateTo}
      />

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
        <Col xs={24} xl={8}>
          <PeopleLayerWatchlistPanel overview={overview} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={8}>
          <DepartmentChaosBoard overview={overview} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={8}>
          <PhysicalWorldTrackerPanel snapshot={snapshot} />
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
        <Col xs={24} xl={6}>
          <StructuralDecayRadarPanel
            model={overview?.structural_decay_radar}
            onNavigate={navigateTo}
          />
        </Col>
        <Col xs={24} xl={6}>
          <DecayWatchPanel
            items={decayWatchModel}
            onNavigate={navigateTo}
            onOpenDraft={handleOpenDecayDraft}
            onSaveTask={handleSaveDecayWatchTask}
          />
        </Col>
        <Col xs={24} xl={6}>
          <TradeThesisWatchPanel items={tradeThesisWatchModel} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={6}>
          <GodEyeTacticalNotes />
        </Col>
      </Row>
    </div>
  );
}

export default GodEyeDashboard;
