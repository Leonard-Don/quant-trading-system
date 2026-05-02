export const BACKTEST_WORKSPACE_DRAFT_KEY = 'backtest_workspace_draft';
export const ADVANCED_EXPERIMENT_INTENT_KEY = 'advanced_experiment_intent';
export const BACKTEST_WORKSPACE_DRAFT_EVENT = 'backtest-workspace-draft-updated';
export const BACKTEST_RESEARCH_SNAPSHOTS_KEY = 'backtest_research_snapshots';
export const BACKTEST_RESEARCH_SNAPSHOT_EVENT = 'backtest-research-snapshot-updated';

const MAX_RESEARCH_SNAPSHOTS = 12;

const readJsonStorage = (key, fallback = null) => {
  if (typeof window === 'undefined') {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw);
  } catch (error) {
    return fallback;
  }
};

const writeJsonStorage = (key, value) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // Ignore localStorage failures so the main workflow is never blocked.
  }
};

export const saveBacktestWorkspaceDraft = (draft) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    writeJsonStorage(BACKTEST_WORKSPACE_DRAFT_KEY, draft);
    window.dispatchEvent(new CustomEvent(BACKTEST_WORKSPACE_DRAFT_EVENT, { detail: draft }));
  } catch (error) {
    // Ignore localStorage failures so the main workflow is never blocked.
  }
};

export const loadBacktestWorkspaceDraft = () => {
  return readJsonStorage(BACKTEST_WORKSPACE_DRAFT_KEY, null);
};

export const saveAdvancedExperimentIntent = (intent) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    writeJsonStorage(ADVANCED_EXPERIMENT_INTENT_KEY, intent);
  } catch (error) {
    // Ignore localStorage failures so navigation still works.
  }
};

export const consumeAdvancedExperimentIntent = () => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const parsed = readJsonStorage(ADVANCED_EXPERIMENT_INTENT_KEY, null);
    window.localStorage.removeItem(ADVANCED_EXPERIMENT_INTENT_KEY);
    return parsed;
  } catch (error) {
    window.localStorage.removeItem(ADVANCED_EXPERIMENT_INTENT_KEY);
    return null;
  }
};

export const loadBacktestResearchSnapshots = () => {
  const snapshots = readJsonStorage(BACKTEST_RESEARCH_SNAPSHOTS_KEY, []);
  return Array.isArray(snapshots)
    ? snapshots
      .filter((item) => item && typeof item === 'object' && item.id)
      .sort((left, right) => (
        new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime()
      ))
    : [];
};

export const buildBacktestResearchSnapshot = ({
  result = {},
  note = '',
  source = 'results_display',
  marketRegimeResult = null,
} = {}) => {
  const createdAt = new Date().toISOString();
  const symbol = String(result.symbol || '').trim().toUpperCase();
  const strategy = String(result.strategy || '').trim();

  return {
    id: `research_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    created_at: createdAt,
    source,
    symbol,
    strategy,
    note: String(note || '').trim(),
    history_record_id: result.history_record_id || '',
    date_range: {
      start_date: result.start_date || '',
      end_date: result.end_date || '',
    },
    metrics: {
      total_return: Number(result.total_return || 0),
      annualized_return: Number(result.annualized_return || 0),
      max_drawdown: Number(result.max_drawdown || 0),
      sharpe_ratio: Number(result.sharpe_ratio || 0),
      num_trades: Number(result.num_trades || result.total_trades || 0),
      final_value: Number(result.final_value || 0),
    },
    execution: {
      execution_lag: result.execution_diagnostics?.execution_lag ?? null,
      market_impact_bps: result.execution_diagnostics?.market_impact_bps ?? 0,
      market_impact_model: result.execution_diagnostics?.market_impact_model || '',
      estimated_market_impact_cost: result.execution_costs?.estimated_market_impact_cost ?? 0,
      estimated_total_slippage_cost: result.execution_costs?.estimated_total_slippage_cost ?? 0,
    },
    market_regime: marketRegimeResult?.summary ? {
      strongest_regime: marketRegimeResult.summary.strongest_regime?.regime || '',
      weakest_regime: marketRegimeResult.summary.weakest_regime?.regime || '',
      positive_regimes: Number(marketRegimeResult.summary.positive_regimes || 0),
      regime_count: Number(marketRegimeResult.summary.regime_count || 0),
    } : null,
  };
};

export const saveBacktestResearchSnapshot = (snapshot) => {
  if (!snapshot || typeof snapshot !== 'object') {
    return null;
  }

  const existing = loadBacktestResearchSnapshots();
  const nextSnapshot = {
    ...snapshot,
    id: snapshot.id || `research_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    created_at: snapshot.created_at || new Date().toISOString(),
  };
  const filtered = existing.filter((item) => item.id !== nextSnapshot.id);
  const nextSnapshots = [nextSnapshot, ...filtered].slice(0, MAX_RESEARCH_SNAPSHOTS);
  writeJsonStorage(BACKTEST_RESEARCH_SNAPSHOTS_KEY, nextSnapshots);

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(BACKTEST_RESEARCH_SNAPSHOT_EVENT, { detail: nextSnapshot }));
  }

  return nextSnapshot;
};

export const deleteBacktestResearchSnapshot = (snapshotId) => {
  const nextSnapshots = loadBacktestResearchSnapshots().filter((item) => item.id !== snapshotId);
  writeJsonStorage(BACKTEST_RESEARCH_SNAPSHOTS_KEY, nextSnapshots);
  return nextSnapshots;
};
