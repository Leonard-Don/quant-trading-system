import {
  getAltDataHistory,
  getAltDataSnapshot,
  getAltDataStatus,
  getCrossMarketTemplates,
  getMacroOverview,
  getResearchTasks,
} from '../../services/api';
import { buildRefreshCounts } from './navigationHelpers';
import {
  buildCrossMarketCards,
  buildFactorPanelModel,
  buildHeatmapModel,
  buildHunterModel,
  buildRadarModel,
  buildTimelineModel,
} from './viewModels';

export async function fetchGodEyeDashboardPayload(refresh = false) {
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

  return {
    crossMarketTemplates: templateData,
    historyPayload: historyData,
    overview: macroData,
    policyHistory: policyData,
    researchTasks: researchTaskData?.data || [],
    snapshot: altData,
    status: statusData,
  };
}

export function buildDashboardStatus(snapshot, status) {
  const providerHealth = snapshot?.provider_health || status?.provider_health || {};
  const staleness = snapshot?.staleness || status?.staleness || {};
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  const providerCount = Object.keys(snapshot?.providers || {}).length || 0;
  const snapshotTimestamp = snapshot?.snapshot_timestamp || status?.snapshot_timestamp;
  const schedulerStatus = status?.scheduler || {};
  const degradedProviders = Object.entries(refreshStatus).filter(([, item]) =>
    ['degraded', 'error'].includes(item.status)
  );

  return {
    degradedProviders,
    providerCount,
    providerHealth,
    refreshStatus,
    schedulerStatus,
    snapshotTimestamp,
    staleness,
  };
}

export function buildGodEyeDerivedState({
  crossMarketTemplates,
  historyPayload,
  overview,
  policyHistory,
  researchTasks,
  snapshot,
  status,
}) {
  const heatmapModel = buildHeatmapModel(snapshot, historyPayload);
  const radarData = buildRadarModel(overview);
  const factorPanelModel = buildFactorPanelModel(overview, snapshot);
  const timelineItems = buildTimelineModel(policyHistory);
  const hunterAlerts = buildHunterModel({ snapshot, overview, status, researchTasks });
  const crossMarketCards = buildCrossMarketCards(crossMarketTemplates, overview, snapshot, researchTasks);

  return {
    crossMarketCards,
    dashboardStatus: buildDashboardStatus(snapshot, status),
    factorPanelModel,
    heatmapModel,
    hunterAlerts,
    radarData,
    refreshCounts: buildRefreshCounts(crossMarketCards),
    timelineItems,
  };
}
