import React from 'react';
import { Alert, Button } from 'antd';

function GodEyeAlerts({ macroSignal, degradedProviderCount, refreshCounts, structuralDecayRadar, onNavigate }) {
  const radarScore = Number(structuralDecayRadar?.score || 0);
  const radarHot = structuralDecayRadar?.label === 'decay_alert' || radarScore >= 0.68;

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

      {radarHot ? (
        <Alert
          type="error"
          showIcon
          message="系统级结构衰败雷达进入警报区"
          description={`${structuralDecayRadar?.display_label || '结构衰败警报'}，综合分 ${Math.round(radarScore * 100)}%。${structuralDecayRadar?.action_hint || '建议优先检查人的维度、政策治理与跨市场防御模板。'}`}
          action={
            <Button
              size="small"
              type="primary"
              onClick={() => onNavigate({
                target: 'cross-market',
                template: 'defensive_beta_hedge',
                source: 'decay_radar',
                note: structuralDecayRadar?.action_hint || '结构衰败雷达进入警报区。',
              })}
            >
              打开防御模板
            </Button>
          }
        />
      ) : null}

      {(refreshCounts.high || refreshCounts.medium) ? (
        <Alert
          type={refreshCounts.high ? 'error' : 'warning'}
          showIcon
          message="研究任务更新优先级"
          description={`当前有 ${refreshCounts.high} 个研究任务建议立即更新，${refreshCounts.medium} 个任务建议优先复核。默认顺序会优先看共振驱动，其次是核心腿受压、降级运行、复核语境切换，再看结构性衰败、交易 Thesis 漂移、部门混乱、人的维度和输入可靠度变化。当前共有 ${refreshCounts.resonance || 0} 个共振驱动任务，${refreshCounts.biasQualityCore || 0} 个已经压到主题核心腿，${refreshCounts.selectionQualityActive || 0} 个当前结果已处于降级运行状态，${refreshCounts.reviewContext || 0} 个最近两版刚切入复核语境，${refreshCounts.structuralDecay || 0} 个结构性衰败任务继续恶化，${refreshCounts.tradeThesis || 0} 个交易 Thesis 已与最新定价证据出现漂移，${refreshCounts.departmentChaos || 0} 个部门级政策混乱明显恶化，${refreshCounts.peopleLayer || 0} 个人的维度明显走弱，${refreshCounts.inputReliability || 0} 个整体输入可靠度已经发生明显变化；此外还有 ${refreshCounts.selectionQuality || 0} 个已经进入自动降级，${refreshCounts.policySource || 0} 个属于政策源驱动，${refreshCounts.biasQuality || 0} 个已经出现偏置收缩。你可以直接从 Alert Hunter 或工作台重新打开对应任务。`}
          action={
            <Button size="small" type="primary" onClick={() => onNavigate('workbench-refresh')}>
              打开待更新任务
            </Button>
          }
        />
      ) : null}

      {refreshCounts.departmentChaos ? (
        <Alert
          type="warning"
          showIcon
          message="部门级政策混乱正在影响研究输入"
          description={`当前有 ${refreshCounts.departmentChaos} 个任务的部门级政策混乱信号较保存快照明显恶化。它们通常意味着政策执行主体、朝令夕改率或长官意志强度已经改变，适合优先回到工作台确认跨市场模板和交易 Thesis 是否仍然成立。`}
          action={
            <Button
              size="small"
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                reason: 'department_chaos',
              })}
            >
              打开部门混乱任务
            </Button>
          }
        />
      ) : null}

      {refreshCounts.tradeThesis ? (
        <Alert
          type="warning"
          showIcon
          message="交易 Thesis 正在漂移"
          description={`当前有 ${refreshCounts.tradeThesis} 个交易 Thesis 相对保存时已经发生主逻辑、主表达腿或执行周期漂移。这类任务往往意味着组合 thesis 已经不再完全贴合最新定价证据，适合尽快回到工作台优先复核。`}
          action={
            <Button
              size="small"
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                type: 'trade_thesis',
                reason: 'trade_thesis',
              })}
            >
              打开交易 Thesis 任务
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

      {refreshCounts.structuralDecay ? (
        <Alert
          type="error"
          showIcon
          message="结构性衰败任务正在继续恶化"
          description={`当前有 ${refreshCounts.structuralDecay} 个结构性衰败观察任务，相比保存快照已经进一步恶化。这类任务更像长期错误定价或结构性损伤，应优先回到工作台确认是否需要升级处理。`}
          action={
            <Button
              size="small"
              type="primary"
              onClick={() => onNavigate({
                target: 'workbench',
                refresh: 'high',
                type: 'macro_mispricing',
                reason: 'structural_decay',
              })}
            >
              打开衰败任务
            </Button>
          }
        />
      ) : null}
    </>
  );
}

export default GodEyeAlerts;
