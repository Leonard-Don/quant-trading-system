const getMetricValue = (record, key) => Number(record?.metrics?.[key] ?? record?.[key] ?? 0);

export const buildBatchDraftState = (draft) => {
  if (!draft?.symbol || !draft?.strategy) {
    return null;
  }

  return {
    symbol: String(draft.symbol).trim().toUpperCase(),
    strategy: draft.strategy,
    dateRange: Array.isArray(draft.dateRange) && draft.dateRange[0] && draft.dateRange[1]
      ? draft.dateRange
      : null,
    initial_capital: Number(draft.initial_capital ?? 10000),
    commission: Number(draft.commission ?? 0.1),
    slippage: Number(draft.slippage ?? 0.1),
    parameters: draft.parameters || {},
  };
};

export const buildBatchInsight = (batchResult) => {
  const records = batchResult?.ranked_results?.length
    ? batchResult.ranked_results
    : batchResult?.results || [];
  const successfulRecords = records.filter((record) => record?.success !== false);

  if (!successfulRecords.length) {
    return null;
  }

  const bestRecord = batchResult?.summary?.best_result
    ? {
        ...batchResult.summary.best_result,
        metrics: {
          total_return: Number(batchResult.summary.best_result.total_return ?? 0),
          sharpe_ratio: Number(batchResult.summary.best_result.sharpe_ratio ?? 0),
          max_drawdown: Number(batchResult.summary.best_result.max_drawdown ?? 0),
        },
      }
    : successfulRecords[0];
  const secondRecord = successfulRecords.find((record) => record.task_id !== bestRecord.task_id && record.strategy !== bestRecord.strategy) || null;
  const bestReturn = getMetricValue(bestRecord, 'total_return');
  const bestDrawdown = Math.abs(getMetricValue(bestRecord, 'max_drawdown'));
  const secondReturn = secondRecord ? getMetricValue(secondRecord, 'total_return') : null;
  const returnGap = secondReturn === null ? null : bestReturn - secondReturn;

  if (bestDrawdown >= 0.2) {
    return {
      type: 'warning',
      title: '最佳策略收益领先，但回撤偏深',
      description: `${bestRecord.strategy || '当前最佳策略'} 的总收益 ${formatRatio(bestReturn)}，但最大回撤达到 ${formatRatio(-bestDrawdown)}，建议回到主回测页继续压缩风险参数。`,
    };
  }

  if (returnGap !== null && returnGap >= 0.05) {
    return {
      type: 'success',
      title: '领先策略已经比较清晰',
      description: `${bestRecord.strategy || '当前最佳策略'} 比第二名多出 ${formatRatio(returnGap)} 的总收益，可以优先围绕这组参数继续做稳定性验证。`,
    };
  }

  return {
    type: 'info',
    title: '策略之间差距不大，适合继续细调参数',
    description: `当前最佳策略总收益 ${formatRatio(bestReturn)}，夏普 ${getMetricValue(bestRecord, 'sharpe_ratio').toFixed(2)}。建议继续对比成本设置和参数组合，而不是只看当前排名。`,
  };
};

export const buildWalkForwardInsight = (walkResult) => {
  const metrics = walkResult?.aggregate_metrics;
  const totalWindows = Number(walkResult?.n_windows ?? 0);

  if (!metrics || totalWindows <= 0) {
    return null;
  }

  const positiveWindows = Number(metrics.positive_windows ?? 0);
  const positiveRatio = totalWindows ? positiveWindows / totalWindows : 0;
  const averageReturn = Number(metrics.average_return ?? 0);
  const averageSharpe = Number(metrics.average_sharpe ?? 0);
  const returnStd = Math.abs(Number(metrics.return_std ?? 0));

  if (positiveRatio >= 0.7 && returnStd <= 0.06 && averageReturn > 0) {
    return {
      type: 'success',
      title: '策略在滚动窗口里表现较稳定',
      description: `${positiveWindows}/${totalWindows} 个窗口为正收益，平均收益 ${formatRatio(averageReturn)}，波动 ${formatRatio(returnStd)}。这更像是可继续放大的稳定型策略。`,
    };
  }

  if (positiveRatio < 0.5 || averageReturn <= 0) {
    return {
      type: 'warning',
      title: '窗口分化明显，稳定性仍然不足',
      description: `当前只有 ${positiveWindows}/${totalWindows} 个窗口为正收益，平均收益 ${formatRatio(averageReturn)}。建议缩短测试区间或回到主回测页重新调整策略参数。`,
    };
  }

  return {
    type: 'info',
    title: '策略有一定延续性，但还不算稳健',
    description: `${positiveWindows}/${totalWindows} 个窗口为正收益，平均夏普 ${averageSharpe.toFixed(2)}，收益波动 ${formatRatio(returnStd)}。可以继续观察不同训练窗口下的变化。`,
  };
};

const formatRatio = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
