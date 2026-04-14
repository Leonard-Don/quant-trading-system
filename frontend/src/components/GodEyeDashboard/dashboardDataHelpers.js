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
  buildDecayWatchModel,
  buildFactorPanelModel,
  buildHeatmapModel,
  buildHunterModel,
  buildRadarModel,
  buildTradeThesisWatchModel,
  buildTimelineModel,
} from './viewModels';
import { buildResearchTaskRefreshSignals } from '../../utils/researchTaskSignals';

const DASHBOARD_REQUEST_TIMEOUT_MS = 20000;

const withSoftTimeout = async (promise, fallback, source, timeoutMs = DASHBOARD_REQUEST_TIMEOUT_MS) => {
  let timerId = null;
  try {
    return await Promise.race([
      Promise.resolve(promise).then((data) => ({
        data,
        degraded: null,
      })),
      new Promise((resolve) => {
        timerId = window.setTimeout(() => {
          resolve({
            data: fallback,
            degraded: {
              source,
              reason: 'timeout',
            },
          });
        }, timeoutMs);
      }),
    ]);
  } catch (error) {
    return {
      data: fallback,
      degraded: {
        source,
        reason: error?.userMessage || error?.message || 'request_failed',
      },
    };
  } finally {
    if (timerId) {
      window.clearTimeout(timerId);
    }
  }
};

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
    withSoftTimeout(getMacroOverview(refresh), {}, 'macro_overview'),
    withSoftTimeout(getAltDataSnapshot(refresh), {}, 'alt_snapshot'),
    withSoftTimeout(getAltDataStatus(), {}, 'alt_status'),
    withSoftTimeout(getAltDataHistory({ limit: 120 }), {}, 'alt_history'),
    withSoftTimeout(getAltDataHistory({ category: 'policy', limit: 16 }), {}, 'policy_history'),
    withSoftTimeout(getCrossMarketTemplates(), {}, 'cross_market_templates'),
    withSoftTimeout(getResearchTasks({ limit: 60 }), { data: [] }, 'research_tasks'),
  ]);

  const degradedSources = [
    macroData,
    altData,
    statusData,
    historyData,
    policyData,
    templateData,
    researchTaskData,
  ]
    .map((item) => item?.degraded)
    .filter(Boolean);

  return {
    crossMarketTemplates: templateData?.data || {},
    degradedSources,
    historyPayload: historyData?.data || {},
    overview: macroData?.data || {},
    policyHistory: policyData?.data || {},
    researchTasks: researchTaskData?.data?.data || researchTaskData?.data || [],
    snapshot: altData?.data || {},
    status: statusData?.data || {},
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
  const refreshSignals = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot });
  const hunterAlerts = buildHunterModel({ snapshot, overview, status, researchTasks });
  const decayWatchModel = buildDecayWatchModel(researchTasks);
  const tradeThesisWatchModel = buildTradeThesisWatchModel(researchTasks, refreshSignals.prioritized || []);
  const crossMarketCards = buildCrossMarketCards(crossMarketTemplates, overview, snapshot, researchTasks);

  return {
    crossMarketCards,
    decayWatchModel,
    dashboardStatus: buildDashboardStatus(snapshot, status),
    factorPanelModel,
    heatmapModel,
    hunterAlerts,
    radarData,
    refreshCounts: buildRefreshCounts(refreshSignals.prioritized || []),
    refreshSignals: refreshSignals.prioritized || [],
    tradeThesisWatchModel,
    timelineItems,
  };
}
