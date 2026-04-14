import { useCallback, useState } from 'react';

import { addResearchTaskSnapshot, createResearchTask } from '../../services/api';
import { buildPricingWorkbenchPayload } from '../research-playbook/playbookViewModels';
import { exportToJSON } from '../../utils/export';
import { useSafeMessageApi } from '../../utils/messageApi';
import {
  buildPricingResearchAuditPayload,
  buildPricingResearchReportHtml,
  openPricingResearchPrintWindow,
} from '../../utils/pricingResearchReport';
import { resolveAnalysisSymbol } from '../../utils/pricingResearch';

export default function usePricingWorkbenchActions({
  data,
  gapHistory,
  mergedContext,
  onSaveSuccess,
  onUpdateSnapshotSuccess,
  peerComparison,
  period,
  playbook,
  sensitivity,
  symbol,
}) {
  const message = useSafeMessageApi();
  const [savingTask, setSavingTask] = useState(false);
  const [updatingSnapshot, setUpdatingSnapshot] = useState(false);
  const [savedTaskId, setSavedTaskId] = useState('');

  const handleSaveTask = useCallback(async () => {
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
      setSavedTaskId(response.data?.id || '');
      onSaveSuccess?.(response.data?.id || '');
      message.success(`已保存到研究工作台: ${response.data?.title || payload.title}`);
    } catch (err) {
      message.error(err.userMessage || err.message || '保存研究任务失败');
    } finally {
      setSavingTask(false);
    }
  }, [data, mergedContext, message, onSaveSuccess, period, playbook]);

  const handleUpdateSnapshot = useCallback(async () => {
    if (!savedTaskId) {
      message.info('请先保存任务，再更新当前任务快照');
      return;
    }

    const payload = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    );
    if (!payload?.snapshot) {
      message.error('当前还没有可更新的研究快照');
      return;
    }

    setUpdatingSnapshot(true);
    try {
      await addResearchTaskSnapshot(savedTaskId, {
        snapshot: payload.snapshot,
        ...(payload.refresh_priority_event
          ? { refresh_priority_event: payload.refresh_priority_event }
          : {}),
      });
      onUpdateSnapshotSuccess?.(savedTaskId);
      message.success('当前任务快照已更新');
    } catch (err) {
      message.error(err.userMessage || err.message || '更新任务快照失败');
    } finally {
      setUpdatingSnapshot(false);
    }
  }, [data, mergedContext, message, onUpdateSnapshotSuccess, period, playbook, savedTaskId]);

  const handleExportReport = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    try {
      const snapshot = buildPricingWorkbenchPayload(
        { ...mergedContext, period },
        data,
        playbook
      )?.snapshot?.payload || null;
      const reportHtml = buildPricingResearchReportHtml({
        symbol: resolveAnalysisSymbol(data?.symbol, symbol),
        period,
        generatedAt: new Date().toLocaleString(),
        analysis: data,
        snapshot,
        context: mergedContext,
        sensitivity,
        history: gapHistory,
        peerComparison,
      });
      const opened = openPricingResearchPrintWindow(reportHtml);
      if (!opened) {
        message.error('无法打开打印窗口，请检查浏览器弹窗设置');
        return;
      }
      message.success('已打开打印窗口，可直接另存为 PDF');
    } catch (exportError) {
      message.error(exportError.message || '导出研究报告失败');
    }
  }, [data, gapHistory, mergedContext, message, peerComparison, period, playbook, sensitivity, symbol]);

  const handleExportAudit = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    const snapshot = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    )?.snapshot?.payload || null;
    const payload = buildPricingResearchAuditPayload({
      symbol: resolveAnalysisSymbol(data?.symbol, symbol),
      period,
      context: mergedContext,
      analysis: data,
      snapshot,
      playbook,
      sensitivity,
      history: gapHistory,
      peerComparison,
    });
    exportToJSON(payload, `pricing-research-audit-${payload.symbol || 'unknown'}-${period}`);
    message.success('已导出审计 JSON');
  }, [data, gapHistory, mergedContext, message, peerComparison, period, playbook, sensitivity, symbol]);

  return {
    handleExportAudit,
    handleExportReport,
    handleSaveTask,
    handleUpdateSnapshot,
    savedTaskId,
    savingTask,
    setSavedTaskId,
    updatingSnapshot,
  };
}
