import React from 'react';
import { Alert, Button } from 'antd';

function GodEyeAlerts({ macroSignal, degradedProviderCount, refreshCounts, onNavigate }) {
  return (
    <>
      {macroSignal === 1 ? (
        <Alert
          type="warning"
          showIcon
          message="战场提示"
          description="当前综合因子偏向正向扭曲区间，说明市场可能处于值得重点追踪的错价窗口。"
        />
      ) : null}

      {degradedProviderCount ? (
        <Alert
          type="warning"
          showIcon
          message="数据治理提醒"
          description={`当前有 ${degradedProviderCount} 个 provider 处于 degraded/error 状态，页面继续使用最近成功快照。`}
        />
      ) : null}

      {(refreshCounts.high || refreshCounts.medium) ? (
        <Alert
          type={refreshCounts.high ? 'error' : 'warning'}
          showIcon
          message="研究任务更新优先级"
          description={`当前有 ${refreshCounts.high} 个跨市场任务建议立即更新，${refreshCounts.medium} 个任务建议优先复核。其中默认处理顺序会优先看共振驱动，其次是核心腿受压，再是降级运行，然后看复核语境切换，再看输入可靠度变化，最后才是自动降级排序。当前共有 ${refreshCounts.resonance || 0} 个共振驱动任务，${refreshCounts.biasQualityCore || 0} 个已经压到主题核心腿，${refreshCounts.selectionQualityActive || 0} 个当前结果已处于降级运行状态，${refreshCounts.reviewContext || 0} 个最近两版刚切入复核语境，${refreshCounts.inputReliability || 0} 个当前整体输入可靠度已经发生明显变化；此外还有 ${refreshCounts.selectionQuality || 0} 个已经进入自动降级，${refreshCounts.policySource || 0} 个属于政策源驱动，${refreshCounts.biasQuality || 0} 个已经出现偏置收缩。你可以直接从 Alert Hunter 或模板卡重新打开对应剧本。`}
          action={
            <Button size="small" type="primary" onClick={() => onNavigate('workbench-refresh')}>
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
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                type: 'cross_market',
                reason: 'selection_quality_active',
              })}
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
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                type: 'cross_market',
                reason: 'review_context',
              })}
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
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                type: 'cross_market',
                reason: 'input_reliability',
              })}
            >
              先复核输入可靠度任务
            </Button>
          }
        />
      ) : null}
    </>
  );
}

export default GodEyeAlerts;
