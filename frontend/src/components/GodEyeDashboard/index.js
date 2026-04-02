import React from 'react';
import {
  Col,
  Row,
  Spin,
} from 'antd';

import AlertHunterPanel from './AlertHunterPanel';
import CrossMarketOverview from './CrossMarketOverview';
import GodEyeAlerts from './GodEyeAlerts';
import GodEyeHeader from './GodEyeHeader';
import GodEyeStatusStats from './GodEyeStatusStats';
import GodEyeTacticalNotes from './GodEyeTacticalNotes';
import MacroFactorPanel from './MacroFactorPanel';
import PolicyTimelineBar from './PolicyTimelineBar';
import RiskPremiumRadar from './RiskPremiumRadar';
import SupplyChainHeatmap from './SupplyChainHeatmap';
import { navigateDashboardAction } from './navigationHelpers';
import useGodEyeDashboardData from './useGodEyeDashboardData';

function GodEyeDashboard() {
  const {
    crossMarketCards,
    dashboardStatus,
    factorPanelModel,
    handleManualRefresh,
    heatmapModel,
    hunterAlerts,
    loading,
    overview,
    radarData,
    refreshCounts,
    refreshing,
    timelineItems,
  } = useGodEyeDashboardData();

  const navigateTo = (actionOrTarget) => {
    navigateDashboardAction(actionOrTarget, {
      crossMarketCards,
      search: window.location.search,
    });
  };

  if (loading && !overview) {
    return (
      <div style={{ minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  const {
    degradedProviders,
    providerCount,
    providerHealth,
    schedulerStatus,
    snapshotTimestamp,
    staleness,
  } = dashboardStatus;

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
        <Col xs={24} xl={11}>
          <AlertHunterPanel alerts={hunterAlerts} onNavigate={navigateTo} />
        </Col>
        <Col xs={24} xl={13}>
          <CrossMarketOverview cards={crossMarketCards} onNavigate={navigateTo} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <GodEyeTacticalNotes />
        </Col>
      </Row>
    </div>
  );
}

export default GodEyeDashboard;
