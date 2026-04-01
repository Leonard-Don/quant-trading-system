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

export const buildMarketRegimeInsight = (marketRegimeResult) => {
  const regimes = marketRegimeResult?.regimes || [];
  const summary = marketRegimeResult?.summary;

  if (!regimes.length || !summary) {
    return null;
  }

  const strongest = summary.strongest_regime;
  const weakest = summary.weakest_regime;
  const positiveRatio = Number(summary.positive_regimes || 0) / Math.max(Number(summary.regime_count || 0), 1);

  if (positiveRatio >= 0.75) {
    return {
      type: 'success',
      title: '策略在多数市场状态下都能维持正收益',
      description: `${summary.positive_regimes}/${summary.regime_count} 个市场状态为正收益，最强的是 ${strongest?.regime || '未知状态'} (${formatRatio(strongest?.strategy_total_return)})。`,
    };
  }

  if (positiveRatio <= 0.4) {
    return {
      type: 'warning',
      title: '策略对市场状态较敏感，适用面偏窄',
      description: `当前只有 ${summary.positive_regimes}/${summary.regime_count} 个市场状态为正收益，最弱阶段 ${weakest?.regime || '未知状态'} 回报 ${formatRatio(weakest?.strategy_total_return)}。`,
    };
  }

  return {
    type: 'info',
    title: '策略在不同市场状态下表现分化明显',
    description: `最强阶段 ${strongest?.regime || '未知状态'} 收益 ${formatRatio(strongest?.strategy_total_return)}，最弱阶段 ${weakest?.regime || '未知状态'} 收益 ${formatRatio(weakest?.strategy_total_return)}。建议配合稳健性评分一起看。`,
  };
};

const clampScore = (value) => Math.max(0, Math.min(100, Number(value || 0)));

export const buildRobustnessScore = ({
  batchResult = null,
  walkResult = null,
  benchmarkSummary = null,
  marketRegimeResult = null,
} = {}) => {
  const dimensions = [];

  if (batchResult?.summary) {
    const totalTasks = Number(batchResult.summary.total_tasks || 0);
    const successfulTasks = Number(batchResult.summary.successful || 0);
    const successRatio = totalTasks ? successfulTasks / totalTasks : 0;
    const averageReturn = Number(batchResult.summary.average_return || 0);
    const bestDrawdown = Math.abs(Number(batchResult.summary.best_result?.max_drawdown || 0));
    const score = clampScore((successRatio * 45) + (Math.max(Math.min(averageReturn / 0.15, 1), 0) * 35) + ((1 - Math.min(bestDrawdown / 0.25, 1)) * 20));

    dimensions.push({
      key: 'batch',
      label: '批量一致性',
      score,
      detail: `成功率 ${(successRatio * 100).toFixed(0)}%，平均收益 ${formatRatio(averageReturn)}。`,
    });
  }

  if (walkResult?.aggregate_metrics && walkResult?.n_windows) {
    const positiveRatio = Number(walkResult.aggregate_metrics.positive_windows || 0) / Math.max(Number(walkResult.n_windows || 0), 1);
    const averageSharpe = Number(walkResult.aggregate_metrics.average_sharpe || 0);
    const returnStd = Math.abs(Number(walkResult.aggregate_metrics.return_std || 0));
    const score = clampScore((positiveRatio * 50) + (Math.max(Math.min(averageSharpe / 2, 1), 0) * 25) + ((1 - Math.min(returnStd / 0.12, 1)) * 25));

    dimensions.push({
      key: 'walk_forward',
      label: '滚动稳定性',
      score,
      detail: `正收益窗口 ${(positiveRatio * 100).toFixed(0)}%，收益波动 ${formatRatio(returnStd)}。`,
    });
  }

  if (benchmarkSummary) {
    const excessReturn = Number(benchmarkSummary.excessReturn || 0);
    const sharpeDelta = Number(benchmarkSummary.sharpeDelta || 0);
    const drawdownDelta = Number(benchmarkSummary.drawdownDelta || 0);
    const score = clampScore(
      50
      + (Math.max(Math.min(excessReturn / 0.12, 1), -1) * 25)
      + (Math.max(Math.min(sharpeDelta / 1, 1), -1) * 15)
      + (Math.max(Math.min((-drawdownDelta) / 0.12, 1), -1) * 10)
    );

    dimensions.push({
      key: 'benchmark',
      label: '基准优势',
      score,
      detail: `超额收益 ${formatRatio(excessReturn)}，夏普差值 ${sharpeDelta.toFixed(2)}。`,
    });
  }

  if (marketRegimeResult?.summary && Array.isArray(marketRegimeResult?.regimes) && marketRegimeResult.regimes.length) {
    const positiveRatio = Number(marketRegimeResult.summary.positive_regimes || 0) / Math.max(Number(marketRegimeResult.summary.regime_count || 0), 1);
    const strongest = Number(marketRegimeResult.summary.strongest_regime?.strategy_total_return || 0);
    const weakest = Number(marketRegimeResult.summary.weakest_regime?.strategy_total_return || 0);
    const regimeGap = Math.abs(strongest - weakest);
    const score = clampScore((positiveRatio * 65) + ((1 - Math.min(regimeGap / 0.3, 1)) * 35));

    dimensions.push({
      key: 'market_regimes',
      label: '市场适配面',
      score,
      detail: `正收益状态 ${(positiveRatio * 100).toFixed(0)}%，阶段分化 ${formatRatio(regimeGap)}。`,
    });
  }

  if (!dimensions.length) {
    return null;
  }

  const totalScore = dimensions.reduce((sum, item) => sum + item.score, 0) / dimensions.length;
  const roundedScore = Math.round(totalScore);
  const level = roundedScore >= 75 ? '高' : roundedScore >= 55 ? '中' : '低';
  const summary = roundedScore >= 75
    ? '当前策略在不同验证维度下都比较稳，可以继续进入更细的参数或组合研究。'
    : roundedScore >= 55
      ? '当前策略具备一定稳健性，但仍有部分验证维度存在分化，适合继续补充实验。'
      : '当前策略的稳健性还不够，建议优先回到参数、成本或市场状态层继续诊断。';

  return {
    score: roundedScore,
    level,
    summary,
    dimensions,
  };
};

export const buildOverfittingWarnings = ({
  batchResult = null,
  walkResult = null,
  benchmarkSummary = null,
  marketRegimeResult = null,
} = {}) => {
  const warnings = [];
  const rankedResults = batchResult?.ranked_results || batchResult?.results || [];
  const successfulResults = rankedResults.filter((record) => record?.success !== false);

  if (successfulResults.length >= 3) {
    const bestReturn = getMetricValue(successfulResults[0], 'total_return');
    const remaining = successfulResults.slice(1).map((record) => getMetricValue(record, 'total_return'));
    const averagePeerReturn = remaining.length
      ? remaining.reduce((sum, value) => sum + value, 0) / remaining.length
      : 0;

    if (bestReturn - averagePeerReturn >= 0.12) {
      warnings.push({
        key: 'batch_gap',
        title: '最优结果和其他实验差距过大',
        description: `最佳实验比其余任务平均高出 ${formatRatio(bestReturn - averagePeerReturn)}，有过拟合到单一参数组合的风险。`,
      });
    }
  }

  if (walkResult?.aggregate_metrics && walkResult?.n_windows) {
    const positiveRatio = Number(walkResult.aggregate_metrics.positive_windows || 0) / Math.max(Number(walkResult.n_windows || 0), 1);
    const returnStd = Math.abs(Number(walkResult.aggregate_metrics.return_std || 0));

    if (positiveRatio < 0.5) {
      warnings.push({
        key: 'walk_ratio',
        title: '滚动窗口正收益占比偏低',
        description: `当前只有 ${(positiveRatio * 100).toFixed(0)}% 的窗口为正收益，策略可能只在少数区间有效。`,
      });
    } else if (returnStd >= 0.08) {
      warnings.push({
        key: 'walk_std',
        title: '窗口收益波动较大',
        description: `滚动窗口收益波动达到 ${formatRatio(returnStd)}，说明样本外表现还不够稳定。`,
      });
    }
  }

  if (benchmarkSummary && Number(benchmarkSummary.excessReturn || 0) <= 0) {
    warnings.push({
      key: 'benchmark',
      title: '主动策略还没有稳定跑赢基准',
      description: `当前超额收益为 ${formatRatio(benchmarkSummary.excessReturn || 0)}，继续调参前先确认策略逻辑是否真正优于买入持有。`,
    });
  }

  if (marketRegimeResult?.summary && Array.isArray(marketRegimeResult.regimes) && marketRegimeResult.regimes.length) {
    const strongest = Number(marketRegimeResult.summary.strongest_regime?.strategy_total_return || 0);
    const weakest = Number(marketRegimeResult.summary.weakest_regime?.strategy_total_return || 0);
    const positiveRatio = Number(marketRegimeResult.summary.positive_regimes || 0) / Math.max(Number(marketRegimeResult.summary.regime_count || 0), 1);
    const regimeGap = Math.abs(strongest - weakest);

    if (positiveRatio <= 0.5) {
      warnings.push({
        key: 'regime_ratio',
        title: '策略只在少数市场状态下有效',
        description: `当前只有 ${(positiveRatio * 100).toFixed(0)}% 的市场状态为正收益，适用范围偏窄。`,
      });
    } else if (regimeGap >= 0.2) {
      warnings.push({
        key: 'regime_gap',
        title: '不同市场状态下收益落差过大',
        description: `最强和最弱市场状态之间相差 ${formatRatio(regimeGap)}，结果可能过度依赖特定行情。`,
      });
    }
  }

  return warnings;
};

export const buildResearchConclusion = ({
  robustnessScore = null,
  overfittingWarnings = [],
  batchResult = null,
  walkResult = null,
  benchmarkSummary = null,
  marketRegimeResult = null,
} = {}) => {
  if (!robustnessScore && !overfittingWarnings.length && !batchResult && !walkResult && !benchmarkSummary && !marketRegimeResult) {
    return null;
  }

  const warningCount = overfittingWarnings.length;
  const score = Number(robustnessScore?.score || 0);
  let title = '策略还需要继续诊断';
  let summary = '当前验证维度还不够完整，建议继续补充批量实验、滚动前瞻和市场状态分析。';
  const nextActions = [];

  if (score >= 75 && warningCount === 0) {
    title = '策略已经具备继续放大的基础';
    summary = '当前稳健性评分较高，而且没有明显过拟合预警，可以进入更细的参数优化或组合级验证。';
    nextActions.push('优先把当前参数组带入组合级策略回测，确认多资产下是否仍能维持优势。');
    nextActions.push('围绕当前最佳参数做更细密的局部寻优，重点观察回撤是否还能继续压缩。');
  } else if (score >= 60 && warningCount <= 1) {
    title = '策略有研究价值，但还不算完全稳固';
    summary = '当前结果已经展现出一定优势，不过还需要用更多样本外验证来确认不是阶段性收益。';
    nextActions.push('先补滚动前瞻或市场状态分析里最弱的一段，再判断是否进入下一轮寻优。');
    nextActions.push('优先检查成本敏感性和基准对照，确认优势不是被低成本假设放大的。');
  } else {
    title = '当前结果更像阶段性有效，还不建议直接放大';
    summary = warningCount
      ? `目前已经出现 ${warningCount} 条过拟合预警，建议先解决最明显的稳定性问题。`
      : '当前稳健性评分偏低，说明策略还没有通过足够的样本外验证。';
    nextActions.push('先回看过拟合预警里最严重的一项，缩小参数空间或重设研究区间后再跑。');
    nextActions.push('如果连基准都跑不赢，优先重审策略逻辑，而不是继续微调参数。');
  }

  if (benchmarkSummary && Number(benchmarkSummary.excessReturn || 0) > 0 && !nextActions.some((item) => item.includes('基准'))) {
    nextActions.push('当前已经跑赢买入持有，可以把重点放到稳定性而不是绝对收益上。');
  }

  if (marketRegimeResult?.summary?.weakest_regime?.regime) {
    nextActions.push(`重点复盘 ${marketRegimeResult.summary.weakest_regime.regime} 这类市场状态，看看是否需要单独的风控或停手机制。`);
  }

  return {
    title,
    summary,
    nextActions: Array.from(new Set(nextActions)).slice(0, 3),
  };
};

export const buildPortfolioExposureChartData = (portfolioStrategyResult) => (
  (portfolioStrategyResult?.portfolio_history || []).map((point) => ({
    date: point.date,
    total: Number(point.total || 0),
    grossExposure: Number(point.gross_exposure || 0),
    netExposure: Number(point.net_exposure || 0),
    cash: Number(point.cash || 0),
  }))
);

export const buildPortfolioPositionSnapshot = (portfolioStrategyResult) => {
  const positionsHistory = portfolioStrategyResult?.positions_history || [];
  if (!positionsHistory.length) {
    return [];
  }

  const latestRow = positionsHistory[positionsHistory.length - 1] || {};
  const targetWeights = portfolioStrategyResult?.weights || {};

  return Object.entries(latestRow)
    .filter(([key]) => key !== 'date')
    .map(([symbol, rawShares]) => ({
      symbol,
      shares: Number(rawShares || 0),
      targetWeight: Number(targetWeights[symbol] || 0),
    }))
    .filter((position) => Math.abs(position.shares) > 1e-8)
    .sort((left, right) => Math.abs(right.shares) - Math.abs(left.shares))
    .map((position) => ({
      ...position,
      direction: position.shares > 0 ? '多头' : '空头',
    }));
};

export const buildPortfolioExposureSummary = (portfolioStrategyResult) => {
  const exposureSeries = buildPortfolioExposureChartData(portfolioStrategyResult);
  const latestExposure = exposureSeries[exposureSeries.length - 1];
  const positions = buildPortfolioPositionSnapshot(portfolioStrategyResult);

  if (!latestExposure) {
    return null;
  }

  return {
    grossExposure: latestExposure.grossExposure,
    netExposure: latestExposure.netExposure,
    cash: latestExposure.cash,
    activePositions: positions.length,
  };
};

const formatRatio = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
