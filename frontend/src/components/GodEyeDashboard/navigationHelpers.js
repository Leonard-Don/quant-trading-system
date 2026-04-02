import {
  buildCrossMarketLink,
  buildPricingLink,
  buildWorkbenchLink,
  navigateToAppUrl,
} from '../../utils/researchContext';

const REFRESH_PRIORITY = [
  { flag: 'taskRefreshResonanceDriven', reason: 'resonance', highOnly: true },
  { flag: 'taskRefreshBiasCompressionCore', reason: 'bias_quality_core', highOnly: true },
  { flag: 'taskRefreshSelectionQualityActive', reason: 'selection_quality_active', highOnly: true },
  { flag: 'taskRefreshReviewContextDriven', reason: 'review_context', highOnly: true },
  { flag: 'taskRefreshInputReliabilityDriven', reason: 'input_reliability', highOnly: true },
  { flag: 'taskRefreshSelectionQualityDriven', reason: 'selection_quality', highOnly: true },
  { flag: 'taskRefreshBiasCompressionDriven', reason: 'bias_quality', highOnly: true },
  { flag: 'taskRefreshPolicySourceDriven', reason: 'policy_source', highOnly: true },
  { flag: 'taskRefreshResonanceDriven', reason: 'resonance' },
  { flag: 'taskRefreshBiasCompressionCore', reason: 'bias_quality_core' },
  { flag: 'taskRefreshSelectionQualityActive', reason: 'selection_quality_active' },
  { flag: 'taskRefreshReviewContextDriven', reason: 'review_context' },
  { flag: 'taskRefreshInputReliabilityDriven', reason: 'input_reliability' },
  { flag: 'taskRefreshSelectionQualityDriven', reason: 'selection_quality' },
  { flag: 'taskRefreshBiasCompressionDriven', reason: 'bias_quality' },
  { flag: 'taskRefreshPolicySourceDriven', reason: 'policy_source' },
];

const findPreferredWorkbenchTarget = (crossMarketCards = []) => {
  for (const item of REFRESH_PRIORITY) {
    const match = crossMarketCards.find((card) =>
      Boolean(card?.[item.flag]) && (!item.highOnly || card?.taskRefreshSeverity === 'high')
    );
    if (match) {
      return {
        reason: item.reason,
        taskId: match.taskRefreshTaskId || '',
      };
    }
  }

  const fallback =
    crossMarketCards.find((card) => card.taskRefreshSeverity === 'high')
    || crossMarketCards.find((card) => card.taskRefreshLabel === '建议复核');

  return {
    reason: '',
    taskId: fallback?.taskRefreshTaskId || '',
  };
};

export const buildRefreshCounts = (crossMarketCards = []) => ({
  high: crossMarketCards.filter((card) => card.taskRefreshLabel === '建议更新').length,
  medium: crossMarketCards.filter((card) => card.taskRefreshLabel === '建议复核').length,
  resonance: crossMarketCards.filter((card) => card.taskRefreshResonanceDriven).length,
  biasQualityCore: crossMarketCards.filter((card) => card.taskRefreshBiasCompressionCore).length,
  selectionQuality: crossMarketCards.filter((card) => card.taskRefreshSelectionQualityDriven).length,
  selectionQualityActive: crossMarketCards.filter((card) => card.taskRefreshSelectionQualityActive).length,
  reviewContext: crossMarketCards.filter((card) => card.taskRefreshReviewContextDriven).length,
  inputReliability: crossMarketCards.filter((card) => card.taskRefreshInputReliabilityDriven).length,
  policySource: crossMarketCards.filter((card) => card.taskRefreshPolicySourceDriven).length,
  biasQuality: crossMarketCards.filter((card) => card.taskRefreshBiasCompressionDriven).length,
});

export const navigateDashboardAction = (actionOrTarget, { crossMarketCards = [], search = '' } = {}) => {
  if (!actionOrTarget) return;

  if (typeof actionOrTarget === 'string') {
    if (actionOrTarget === 'pricing') {
      navigateToAppUrl(buildPricingLink('', 'godeye', '来自 GodEye 的研究入口'));
      return;
    }
    if (actionOrTarget === 'cross-market') {
      navigateToAppUrl(buildCrossMarketLink('', 'godeye', '来自 GodEye 的跨市场入口'));
      return;
    }
    if (actionOrTarget === 'workbench-refresh') {
      const preferredTarget = findPreferredWorkbenchTarget(crossMarketCards);
      navigateToAppUrl(
        buildWorkbenchLink(
          {
            refresh: 'high',
            type: 'cross_market',
            sourceFilter: '',
            reason: preferredTarget.reason,
            taskId: preferredTarget.taskId,
          },
          search
        )
      );
    }
    return;
  }

  if (actionOrTarget.target === 'pricing') {
    navigateToAppUrl(
      buildPricingLink(
        actionOrTarget.symbol,
        actionOrTarget.source || 'godeye',
        actionOrTarget.note || ''
      )
    );
    return;
  }

  if (actionOrTarget.target === 'cross-market') {
    navigateToAppUrl(
      buildCrossMarketLink(
        actionOrTarget.template,
        actionOrTarget.source || 'godeye',
        actionOrTarget.note || ''
      )
    );
    return;
  }

  if (actionOrTarget.target === 'workbench') {
    navigateToAppUrl(
      buildWorkbenchLink(
        {
          refresh: actionOrTarget.refresh || '',
          type: actionOrTarget.type || '',
          sourceFilter: actionOrTarget.sourceFilter || '',
          reason: actionOrTarget.reason || '',
          taskId: actionOrTarget.taskId || '',
        },
        search
      )
    );
  }
};
