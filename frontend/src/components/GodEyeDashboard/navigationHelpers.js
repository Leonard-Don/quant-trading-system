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
  { flag: 'taskRefreshStructuralDecayDriven', reason: 'structural_decay', highOnly: true },
  { flag: 'taskRefreshTradeThesisDriven', reason: 'trade_thesis', highOnly: true },
  { flag: 'taskRefreshPeopleLayerDriven', reason: 'people_layer', highOnly: true },
  { flag: 'taskRefreshDepartmentChaosDriven', reason: 'department_chaos', highOnly: true },
  { flag: 'taskRefreshInputReliabilityDriven', reason: 'input_reliability', highOnly: true },
  { flag: 'taskRefreshSelectionQualityDriven', reason: 'selection_quality', highOnly: true },
  { flag: 'taskRefreshBiasCompressionDriven', reason: 'bias_quality', highOnly: true },
  { flag: 'taskRefreshPolicySourceDriven', reason: 'policy_source', highOnly: true },
  { flag: 'taskRefreshResonanceDriven', reason: 'resonance' },
  { flag: 'taskRefreshBiasCompressionCore', reason: 'bias_quality_core' },
  { flag: 'taskRefreshSelectionQualityActive', reason: 'selection_quality_active' },
  { flag: 'taskRefreshReviewContextDriven', reason: 'review_context' },
  { flag: 'taskRefreshStructuralDecayDriven', reason: 'structural_decay' },
  { flag: 'taskRefreshTradeThesisDriven', reason: 'trade_thesis' },
  { flag: 'taskRefreshPeopleLayerDriven', reason: 'people_layer' },
  { flag: 'taskRefreshDepartmentChaosDriven', reason: 'department_chaos' },
  { flag: 'taskRefreshInputReliabilityDriven', reason: 'input_reliability' },
  { flag: 'taskRefreshSelectionQualityDriven', reason: 'selection_quality' },
  { flag: 'taskRefreshBiasCompressionDriven', reason: 'bias_quality' },
  { flag: 'taskRefreshPolicySourceDriven', reason: 'policy_source' },
];

const findPreferredWorkbenchTarget = (crossMarketCards = [], refreshSignals = []) => {
  const prioritizedSignal = (refreshSignals || []).find((item) => item?.severity === 'high')
    || (refreshSignals || []).find((item) => item?.severity === 'medium');
  if (prioritizedSignal) {
    return {
      reason: prioritizedSignal.priorityReason || '',
      taskId: prioritizedSignal.taskId || '',
      type: prioritizedSignal.taskType || '',
    };
  }

  for (const item of REFRESH_PRIORITY) {
    const match = crossMarketCards.find((card) =>
      Boolean(card?.[item.flag]) && (!item.highOnly || card?.taskRefreshSeverity === 'high')
    );
    if (match) {
      return {
        reason: item.reason,
        taskId: match.taskRefreshTaskId || '',
        type: 'cross_market',
      };
    }
  }

  const fallback =
    crossMarketCards.find((card) => card.taskRefreshSeverity === 'high')
    || crossMarketCards.find((card) => card.taskRefreshLabel === '建议复核');

  return {
    reason: '',
    taskId: fallback?.taskRefreshTaskId || '',
    type: 'cross_market',
  };
};

export const buildRefreshCounts = (refreshSignals = []) => ({
  high: refreshSignals.filter((item) => item.severity === 'high').length,
  medium: refreshSignals.filter((item) => item.severity === 'medium').length,
  resonance: refreshSignals.filter((item) => item.resonanceDriven).length,
  biasQualityCore: refreshSignals.filter((item) => item.biasCompressionShift?.coreLegAffected).length,
  selectionQuality: refreshSignals.filter((item) => item.selectionQualityDriven).length,
  selectionQualityActive: refreshSignals.filter((item) => item.selectionQualityRunState?.active).length,
  reviewContext: refreshSignals.filter((item) => item.reviewContextDriven).length,
  structuralDecay: refreshSignals.filter((item) => item.structuralDecayDriven).length,
  tradeThesis: refreshSignals.filter((item) => item.tradeThesisDriven).length,
  peopleLayer: refreshSignals.filter((item) => item.peopleLayerDriven).length,
  departmentChaos: refreshSignals.filter((item) => item.departmentChaosDriven).length,
  inputReliability: refreshSignals.filter((item) => item.inputReliabilityDriven).length,
  policySource: refreshSignals.filter((item) => item.policySourceDriven).length,
  biasQuality: refreshSignals.filter((item) => item.biasCompressionDriven).length,
});

export const navigateDashboardAction = (actionOrTarget, { crossMarketCards = [], refreshSignals = [], search = '' } = {}) => {
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
      const preferredTarget = findPreferredWorkbenchTarget(crossMarketCards, refreshSignals);
      navigateToAppUrl(
        buildWorkbenchLink(
          {
            refresh: 'high',
            type: preferredTarget.type || '',
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
