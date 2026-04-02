import { buildCrossMarketCards as buildScoredCrossMarketCards } from '../../utils/crossMarketRecommendations';
import { buildResearchTaskRefreshSignals } from '../../utils/researchTaskSignals';
import {
  ACTION_MAP,
  COMPANY_SYMBOL_MAP,
  FACTOR_SYMBOL_MAP,
  FACTOR_TEMPLATE_MAP,
  buildCrossMarketAction,
  buildDisplayTier,
  buildDisplayTone,
  buildPricingAction,
  buildWorkbenchAction,
  extractAllocationOverlay,
  extractDominantDriver,
  extractRecentComparisonLead,
  extractTemplateIdentity,
  extractTemplateMeta,
  formatDriverLabel,
  formatFactorName,
  formatTemplateName,
  getInputReliabilityActionLabel,
  getReviewContextActionLabel,
} from './viewModelShared';

const buildNarrativeShiftAlerts = (tasks = []) => {
  const grouped = tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }
    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }
    const history = task?.snapshot_history || [];
    if (history.length < 2) {
      return accumulator;
    }
    const currentMeta = history[0]?.payload?.template_meta || meta;
    const previousMeta = history[1]?.payload?.template_meta || {};
    const currentDriver = extractDominantDriver(currentMeta);
    const previousDriver = extractDominantDriver(previousMeta);
    const currentCore = currentMeta?.theme_core || '';
    const previousCore = previousMeta?.theme_core || '';

    if (!currentDriver && !previousDriver && !currentCore && !previousCore) {
      return accumulator;
    }

    accumulator.push({
      templateId,
      taskId: task.id,
      title: task.title || formatTemplateName(templateId),
      currentDriver,
      previousDriver,
      currentCore,
      previousCore,
    });
    return accumulator;
  }, []);

  return grouped
    .filter((item) => {
      const driverChanged = item.currentDriver?.key && item.previousDriver?.key && item.currentDriver.key !== item.previousDriver.key;
      const coreChanged = item.currentCore && item.previousCore && item.currentCore !== item.previousCore;
      return driverChanged || coreChanged;
    })
    .map((item) => {
      const currentDriverLabel = formatDriverLabel(item.currentDriver);
      const previousDriverLabel = formatDriverLabel(item.previousDriver);
      const details = [];
      if (previousDriverLabel && currentDriverLabel && previousDriverLabel !== currentDriverLabel) {
        details.push(`主导驱动从 ${previousDriverLabel} 切换到 ${currentDriverLabel}`);
      }
      if (item.previousCore && item.currentCore && item.previousCore !== item.currentCore) {
        details.push(`主题核心腿从 ${item.previousCore} 变为 ${item.currentCore}`);
      }

      return {
        key: `narrative-shift-${item.templateId}`,
        title: `${item.title} 主导叙事切换`,
        severity: 'high',
        description: details.join(' · '),
        action: buildCrossMarketAction(
          item.templateId,
          'alert_hunter',
          `${item.title} 最近两版的主导叙事发生切换，建议打开跨市场剧本重新确认当前模板。`
        ),
      };
    });
};

const buildNarrativeTrendLookup = (tasks = []) => {
  return tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }
    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }

    const currentDriver = extractDominantDriver(meta);
    const history = task?.snapshot_history || [];
    const previousMeta = history[1]?.payload?.template_meta || {};
    const previousDriver = extractDominantDriver(previousMeta);
    const latestOverlay = extractAllocationOverlay(task);
    const latestThemeCore = meta?.theme_core || '';
    const latestThemeSupport = meta?.theme_support || '';
    const latestTopCompressedAsset = latestOverlay?.compressed_assets?.[0] || '';

    let trendLabel = '保持观察';
    let trendSummary = '最近没有检测到显著的叙事切换。';
    if (previousDriver?.key && currentDriver?.key && previousDriver.key !== currentDriver.key) {
      trendLabel = '主导切换';
      trendSummary = `主导驱动从 ${formatDriverLabel(previousDriver)} 切换到 ${formatDriverLabel(currentDriver)}`;
    } else if (currentDriver?.value && previousDriver?.value && Number(currentDriver.value) > Number(previousDriver.value)) {
      trendLabel = '驱动增强';
      trendSummary = `${formatDriverLabel(currentDriver)} 持续增强`;
    } else if (currentDriver?.value && previousDriver?.value && Number(currentDriver.value) < Number(previousDriver.value)) {
      trendLabel = '驱动走弱';
      trendSummary = `${formatDriverLabel(currentDriver)} 较前期走弱`;
    }

    accumulator[templateId] = {
      trendLabel,
      trendSummary,
      latestThemeCore,
      latestThemeSupport,
      latestTopCompressedAsset,
    };
    return accumulator;
  }, {});
};

export const buildHunterModel = ({ snapshot = {}, overview = {}, status = {}, researchTasks = [] }) => {
  const alerts = [];
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  Object.entries(refreshStatus).forEach(([name, info]) => {
    if (['degraded', 'error'].includes(info.status)) {
      alerts.push({
        key: `provider-${name}`,
        title: `${name} 数据状态 ${info.status}`,
        severity: info.status === 'error' ? 'high' : 'medium',
        description: info.error || '继续使用最近成功快照',
        action: ACTION_MAP.observe,
      });
    }
  });

  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  supplyAlerts.forEach((item, index) => {
    const symbol = COMPANY_SYMBOL_MAP[item.company] || null;
    alerts.push({
      key: `supply-${index}`,
      title: `${item.company || '未知公司'} 人才结构预警`,
      severity: 'high',
      description: item.message || `dilution ratio ${item.dilution_ratio || 0}`,
      action: symbol
        ? buildPricingAction(symbol, 'alert_hunter', item.message || '人才结构预警')
        : buildCrossMarketAction('defensive_beta_hedge', 'alert_hunter', item.message || '人才结构预警'),
    });
  });

  (overview?.factors || [])
    .filter((item) => item.signal !== 0)
    .forEach((factor) => {
      alerts.push({
        key: `factor-${factor.name}`,
        title: `${formatFactorName(factor.name)} 出现偏移`,
        severity: Math.abs(Number(factor.z_score || 0)) > 1 ? 'high' : 'medium',
        description: `value=${Number(factor.value || 0).toFixed(3)} z=${Number(factor.z_score || 0).toFixed(3)}`,
        action:
          factor.signal === 1
            ? buildCrossMarketAction(
                FACTOR_TEMPLATE_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看跨市场模板`
              )
            : buildPricingAction(
                FACTOR_SYMBOL_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看单标的定价研究`
              ),
      });
    });

  const resonance = overview?.resonance_summary || {};
  const resonanceFactors = [
    ...(resonance.positive_cluster || []),
    ...(resonance.negative_cluster || []),
    ...(resonance.reversed_factors || []),
    ...(resonance.precursor || []),
    ...(resonance.weakening || []),
  ];
  if (resonance.label && resonance.label !== 'mixed' && resonanceFactors.length) {
    const primaryFactor = resonanceFactors[0];
    const clusterFactors = Array.from(new Set(resonanceFactors))
      .slice(0, 3)
      .map((name) => formatFactorName(name))
      .join('、');
    const severity =
      resonance.label === 'reversal_cluster'
        ? 'high'
        : resonance.label === 'precursor_cluster' || resonance.label === 'fading_cluster'
          ? 'medium'
          : 'high';

    alerts.push({
      key: `resonance-${resonance.label}`,
      title: `宏观因子共振 ${resonance.label}`,
      severity,
      description: `${resonance.reason} · ${clusterFactors}`,
      action: buildCrossMarketAction(
        FACTOR_TEMPLATE_MAP[primaryFactor],
        'alert_hunter',
        `${clusterFactors} 正在形成宏观共振，建议打开跨市场剧本复核当前模板。`
      ),
    });
  }

  alerts.push(...buildNarrativeShiftAlerts(researchTasks));

  const refreshSignals = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot });
  const taskById = Object.fromEntries((researchTasks || []).map((task) => [task.id, task]));
  refreshSignals.prioritized
    .filter((item) => item.severity !== 'low')
    .slice(0, 3)
    .forEach((item) => {
      const recentComparisonLead = extractRecentComparisonLead(taskById[item.taskId]);
      const runStateSummary =
        item.selectionQualityRunState?.active && item.selectionQualityRunState?.label
          ? `降级运行 ${item.selectionQualityRunState.label}${
              item.selectionQualityRunState.reason ? `，${item.selectionQualityRunState.reason}` : ''
            }`
          : '';
      alerts.push({
        key: `refresh-${item.taskId}`,
        title: `${item.title || formatTemplateName(item.templateId)} ${item.refreshLabel}`,
        severity: item.severity,
        description: [
          item.summary,
          recentComparisonLead ? `最近两版：${recentComparisonLead}` : '',
          item.reviewContextDriven && item.reviewContextShift?.lead ? item.reviewContextShift.lead : '',
          item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
            ? `输入可靠度 ${item.inputReliabilityShift.savedLabel}→${item.inputReliabilityShift.currentLabel}，${item.inputReliabilityShift.currentLead}`
            : '',
          runStateSummary
            ? `${runStateSummary}，当前结果已在降级强度下运行，应优先重看`
            : '',
          item.selectionQualityDriven && item.selectionQualityShift?.currentLabel
            ? `自动降级 ${item.selectionQualityShift.currentLabel}`
            : '',
          item.biasCompressionDriven && item.biasCompressionShift?.topCompressedAsset
            ? `压缩焦点 ${item.biasCompressionShift.topCompressedAsset}`
            : '',
        ].filter(Boolean).join(' · '),
        action:
          item.severity === 'high'
            ? buildWorkbenchAction(
                item.taskId,
                'alert_hunter',
                runStateSummary
                  ? `${item.title || formatTemplateName(item.templateId)} 当前结果已在降级强度下运行，建议优先直接打开对应任务重看判断。`
                  : item.reviewContextDriven && item.reviewContextShift?.actionHint
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.reviewContextShift.actionHint}`
                  : item.inputReliabilityDriven && item.inputReliabilityShift?.actionHint
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.inputReliabilityShift.actionHint}`
                  : item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.inputReliabilityShift.currentLead}`
                  : `${item.title || formatTemplateName(item.templateId)} 当前研究输入已经变化，建议直接打开对应任务更新判断。`,
                item.priorityReason || '',
                item.selectionQualityRunState?.active
                  ? '优先重看任务'
                  : item.reviewContextDriven
                    ? getReviewContextActionLabel(item.reviewContextShift)
                    : item.inputReliabilityDriven
                      ? getInputReliabilityActionLabel(item.inputReliabilityShift)
                      : '打开任务'
              )
            : buildCrossMarketAction(
                item.templateId,
                'alert_hunter',
                runStateSummary
                  ? `${item.title || formatTemplateName(item.templateId)} 当前结果已在降级强度下运行，建议重新打开跨市场剧本优先重看。`
                  : item.reviewContextDriven && item.reviewContextShift?.actionHint
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.reviewContextShift.actionHint}`
                  : item.inputReliabilityDriven && item.inputReliabilityShift?.actionHint
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.inputReliabilityShift.actionHint}`
                  : item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
                    ? `${item.title || formatTemplateName(item.templateId)} ${item.inputReliabilityShift.currentLead}`
                    : `${item.title || formatTemplateName(item.templateId)} 当前研究输入已经变化，建议重新打开跨市场剧本更新判断。`
              ),
      });
    });

  alerts.sort((a, b) => {
    const priority = { high: 0, medium: 1, low: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return alerts.slice(0, 8);
};

export const buildCrossMarketCards = (
  payload = {},
  overview = {},
  snapshot = {},
  researchTasks = [],
) => {
  const trendLookup = buildNarrativeTrendLookup(researchTasks);
  const refreshLookup = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot }).byTemplateId;
  const taskLookup = Object.fromEntries(
    (researchTasks || [])
      .filter((task) => task?.type === 'cross_market' && task?.status !== 'archived')
      .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))
      .map((task) => [extractTemplateIdentity(task, extractTemplateMeta(task)), task])
      .filter(([templateId]) => Boolean(templateId))
  );

  return buildScoredCrossMarketCards(
    payload,
    overview,
    snapshot,
    (templateId, note) => buildCrossMarketAction(templateId, 'cross_market_overview', note)
  )
    .map((card) => {
      const trendMeta = trendLookup[card.id] || {};
      const refreshMeta = refreshLookup[card.id] || null;
      const recentComparisonLead = extractRecentComparisonLead(taskLookup[card.id]);
      const rankingPenalty = refreshMeta?.biasCompressionShift?.coreLegAffected
        ? 0.45
        : refreshMeta?.selectionQualityRunState?.active
          ? 0.3
          : refreshMeta?.reviewContextDriven
            ? 0.24
            : refreshMeta?.inputReliabilityDriven
              ? 0.16
              : refreshMeta?.selectionQualityDriven
                ? 0.2
                : 0;
      const adjustedScore = Number(Math.max(0, Number(card.recommendationScore || 0) - rankingPenalty).toFixed(2));

      return {
        ...card,
        baseRecommendationScore: card.recommendationScore,
        baseRecommendationTier: card.recommendationTier,
        rankingPenalty,
        rankingPenaltyReason: rankingPenalty
          ? refreshMeta?.biasCompressionShift?.coreLegAffected
            ? `核心腿 ${refreshMeta?.biasCompressionShift?.topCompressedAsset || ''} 已进入偏置收缩焦点，模板排序自动降级`
            : refreshMeta?.selectionQualityRunState?.active
              ? `当前结果已按 ${refreshMeta?.selectionQualityRunState?.label || 'degraded'} 强度运行，模板排序进一步下调`
              : refreshMeta?.reviewContextDriven
                ? `复核语境切换：${refreshMeta?.reviewContextShift?.lead || '最近两版已发生复核语境切换，模板排序谨慎下调'}`
                : refreshMeta?.inputReliabilityDriven
                  ? `输入可靠度变化：${refreshMeta?.inputReliabilityShift?.currentLead || '整体输入可靠度下降，模板排序适度下调'}`
                  : `当前主题已进入自动降级处理，模板排序谨慎下调`
          : '',
        recommendationScore: adjustedScore,
        recommendationTier: buildDisplayTier(adjustedScore),
        recommendationTone: buildDisplayTone(adjustedScore),
        ...trendMeta,
        ...(refreshMeta
          ? {
              taskRefreshTaskId: refreshMeta.taskId,
              taskRefreshSeverity: refreshMeta.severity,
              taskRefreshLabel: refreshMeta.refreshLabel,
              taskRefreshTone: refreshMeta.refreshTone,
              taskRefreshSummary: refreshMeta.summary,
              taskRefreshResonanceDriven: refreshMeta.resonanceDriven,
              taskRefreshPolicySourceDriven: refreshMeta.policySourceDriven,
              taskRefreshInputReliabilityDriven: refreshMeta.inputReliabilityDriven,
              taskRefreshBiasCompressionDriven: refreshMeta.biasCompressionDriven,
              taskRefreshSelectionQualityDriven: refreshMeta.selectionQualityDriven,
              taskRefreshSelectionQualityShift: refreshMeta.selectionQualityShift,
              taskRefreshSelectionQualityRunState: refreshMeta.selectionQualityRunState,
              taskRefreshSelectionQualityActive: refreshMeta.selectionQualityRunState?.active || false,
              taskRefreshReviewContextDriven: refreshMeta.reviewContextDriven,
              taskRefreshReviewContextShift: refreshMeta.reviewContextShift,
              taskRefreshBiasCompressionShift: refreshMeta.biasCompressionShift,
              taskRefreshBiasCompressionCore: refreshMeta.biasCompressionShift?.coreLegAffected || false,
              taskRefreshTopCompressedAsset: refreshMeta.biasCompressionShift?.topCompressedAsset || '',
              taskRefreshPolicySourceShift: refreshMeta.policySourceShift,
              taskRefreshInputReliabilityShift: refreshMeta.inputReliabilityShift,
              taskRecentComparisonLead: recentComparisonLead,
              taskAction:
                refreshMeta.severity === 'high'
                  ? buildWorkbenchAction(
                      refreshMeta.taskId,
                      'cross_market_overview',
                      refreshMeta.selectionQualityRunState?.active
                        ? `${card.name} 当前结果已在降级强度下运行，更适合直接打开对应任务优先重看。`
                        : refreshMeta.reviewContextDriven
                          ? `${card.name} 最近两版已发生复核语境切换，更适合直接打开对应任务优先重看。`
                          : refreshMeta.inputReliabilityDriven && refreshMeta.inputReliabilityShift?.actionHint
                            ? `${card.name} ${refreshMeta.inputReliabilityShift.actionHint}`
                            : refreshMeta.inputReliabilityDriven
                              ? `${card.name} 当前整体输入可靠度已经变化，更适合直接打开对应任务优先复核。`
                              : `${card.name} 当前更适合直接打开对应任务处理。`,
                      refreshMeta.priorityReason || '',
                      refreshMeta.selectionQualityRunState?.active
                        ? '优先重看任务'
                        : refreshMeta.reviewContextDriven
                          ? getReviewContextActionLabel(refreshMeta.reviewContextShift)
                          : refreshMeta.inputReliabilityDriven
                            ? getInputReliabilityActionLabel(refreshMeta.inputReliabilityShift)
                            : '打开任务'
                    )
                  : null,
            }
          : {}),
      };
    });
};
