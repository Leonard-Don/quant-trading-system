/**
 * Pure refresh-meta / snapshot-comparison helpers for the cross-market backtest
 * panel. Extracted verbatim from CrossMarketBacktestPanel.jsx so both the host
 * panel and its child sub-components can share them without re-importing the
 * whole component. No React, no component state — easy to unit-test.
 */

import { buildSnapshotComparison } from './snapshotCompare';
import { formatStatusLabel } from './crossMarketFormatters';

export const extractRecentComparisonLead = (task = {}) => {
  const history = task?.snapshot_history || [];
  if (history.length < 2 || task?.type !== 'cross_market') {
    return '';
  }
  const [latestSnapshot, previousSnapshot] = history;
  const latestSelectionQuality =
    latestSnapshot?.payload?.allocation_overlay?.selection_quality?.label
    || latestSnapshot?.payload?.template_meta?.selection_quality?.label;
  const previousSelectionQuality =
    previousSnapshot?.payload?.allocation_overlay?.selection_quality?.label
    || previousSnapshot?.payload?.template_meta?.selection_quality?.label;
  if (!latestSelectionQuality && !previousSelectionQuality) {
    return '';
  }
  return buildSnapshotComparison(task.type, history[1], history[0])?.lead || '';
};

export const extractCoreLegPressure = (overlay = {}) => {
  const topCompressed = (overlay.rows || [])
    .slice()
    .sort((left, right) => Math.abs(Number(right?.compression_delta || 0)) - Math.abs(Number(left?.compression_delta || 0)))
    .find((item) => Math.abs(Number(item?.compression_delta || 0)) >= 0.005);
  const symbol = String(topCompressed?.symbol || '').trim().toUpperCase();
  const themeCore = String(overlay.theme_core || '').toUpperCase();
  if (!symbol) {
    return { affected: false, summary: '' };
  }
  return {
    affected: Boolean(themeCore && themeCore.includes(symbol)),
    summary: `${topCompressed.symbol} ${(Math.abs(Number(topCompressed.compression_delta || 0)) * 100).toFixed(2)}pp`,
  };
};

export const getSelectionQualityExplanationLines = (refreshMeta = {}) => {
  const lines = [];
  const runState = refreshMeta?.selectionQualityRunState;
  const shift = refreshMeta?.selectionQualityShift;

  if (runState?.active) {
    const scoreText =
      Number.isFinite(runState.baseScore) || Number.isFinite(runState.effectiveScore)
        ? ` · ${Number(runState.baseScore || 0).toFixed(2)}→${Number(runState.effectiveScore || 0).toFixed(2)}`
        : '';
    lines.push(
      `降级运行 ${formatStatusLabel(runState.label)}${scoreText}${runState.reason ? ` · ${runState.reason}` : ''}`
    );
  }

  if (refreshMeta?.selectionQualityDriven && shift?.currentReason) {
    lines.push(`自动降级 ${formatStatusLabel(shift.currentLabel)} · ${shift.currentReason}`);
  }

  return lines;
};

export const getReviewPriorityTitleSuffix = (refreshMeta = {}) => {
  if (refreshMeta?.selectionQualityRunState?.active) {
    return '建议优先重看';
  }
  if (refreshMeta?.reviewContextShift?.enteredReview) {
    return '建议按复核结果重看';
  }
  if (refreshMeta?.reviewContextShift?.exitedReview) {
    return '建议确认恢复普通结果';
  }
  if (refreshMeta?.reviewContextDriven) {
    return '建议重新确认结果语境';
  }
  if (refreshMeta?.inputReliabilityShift?.enteredFragile) {
    return '建议先复核输入可靠度';
  }
  if (refreshMeta?.inputReliabilityShift?.recoveredRobust) {
    return '建议确认恢复正常强度';
  }
  if (refreshMeta?.inputReliabilityDriven) {
    return '建议重新确认输入质量';
  }
  return '';
};

export const getReviewPriorityContextLine = (refreshMeta = {}) => {
  if (refreshMeta?.selectionQualityRunState?.active) {
    return '该主题当前保存结果已经在降级强度下运行，默认起点仍保留，但更适合先重看当前任务判断。';
  }
  if (refreshMeta?.reviewContextShift?.actionHint) {
    return refreshMeta.reviewContextShift.actionHint;
  }
  if (refreshMeta?.reviewContextDriven) {
    return '该主题最近两版已发生复核语境切换，默认起点仍保留，但更适合先重看当前任务判断。';
  }
  if (refreshMeta?.inputReliabilityShift?.actionHint) {
    return refreshMeta.inputReliabilityShift.actionHint;
  }
  if (refreshMeta?.inputReliabilityDriven) {
    return '该主题当前整体输入可靠度已经变化，默认起点仍保留，但更适合先确认输入质量再决定是否继续沿用当前模板。';
  }
  return '';
};
