export const BACKTEST_WORKSPACE_DRAFT_KEY = 'backtest_workspace_draft';
export const ADVANCED_EXPERIMENT_INTENT_KEY = 'advanced_experiment_intent';
export const BACKTEST_WORKSPACE_DRAFT_EVENT = 'backtest-workspace-draft-updated';

export const saveBacktestWorkspaceDraft = (draft) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(BACKTEST_WORKSPACE_DRAFT_KEY, JSON.stringify(draft));
    window.dispatchEvent(new CustomEvent(BACKTEST_WORKSPACE_DRAFT_EVENT, { detail: draft }));
  } catch (error) {
    // Ignore localStorage failures so the main workflow is never blocked.
  }
};

export const loadBacktestWorkspaceDraft = () => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(BACKTEST_WORKSPACE_DRAFT_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
};

export const saveAdvancedExperimentIntent = (intent) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(ADVANCED_EXPERIMENT_INTENT_KEY, JSON.stringify(intent));
  } catch (error) {
    // Ignore localStorage failures so navigation still works.
  }
};

export const consumeAdvancedExperimentIntent = () => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(ADVANCED_EXPERIMENT_INTENT_KEY);
    if (!raw) {
      return null;
    }
    window.localStorage.removeItem(ADVANCED_EXPERIMENT_INTENT_KEY);
    return JSON.parse(raw);
  } catch (error) {
    window.localStorage.removeItem(ADVANCED_EXPERIMENT_INTENT_KEY);
    return null;
  }
};
