import { useCallback, useEffect, useMemo, useState } from 'react';
import { message } from 'antd';

import { refreshAltData } from '../../services/api';
import {
  buildGodEyeDerivedState,
  fetchGodEyeDashboardPayload,
} from './dashboardDataHelpers';

export default function useGodEyeDashboardData() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [status, setStatus] = useState(null);
  const [historyPayload, setHistoryPayload] = useState(null);
  const [policyHistory, setPolicyHistory] = useState(null);
  const [crossMarketTemplates, setCrossMarketTemplates] = useState(null);
  const [researchTasks, setResearchTasks] = useState([]);

  const loadDashboard = useCallback(async (refresh = false) => {
    if (refresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const payload = await fetchGodEyeDashboardPayload(refresh);
      setOverview(payload.overview);
      setSnapshot(payload.snapshot);
      setStatus(payload.status);
      setHistoryPayload(payload.historyPayload);
      setPolicyHistory(payload.policyHistory);
      setCrossMarketTemplates(payload.crossMarketTemplates);
      setResearchTasks(payload.researchTasks);
    } catch (error) {
      message.error(error.userMessage || error.message || '加载作战大屏失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard(false);
  }, [loadDashboard]);

  const handleManualRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshAltData('all');
      message.success('另类数据快照已刷新');
      await loadDashboard(false);
    } catch (error) {
      message.error(error.userMessage || error.message || '刷新另类数据失败');
      setRefreshing(false);
    }
  }, [loadDashboard]);

  const {
    crossMarketCards,
    dashboardStatus,
    factorPanelModel,
    heatmapModel,
    hunterAlerts,
    radarData,
    refreshCounts,
    timelineItems,
  } = useMemo(
    () =>
      buildGodEyeDerivedState({
        crossMarketTemplates,
        historyPayload,
        overview,
        policyHistory,
        researchTasks,
        snapshot,
        status,
      }),
    [crossMarketTemplates, historyPayload, overview, policyHistory, researchTasks, snapshot, status]
  );

  return {
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
  };
}
