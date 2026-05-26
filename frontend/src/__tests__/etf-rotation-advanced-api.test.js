import api, {
  API_TIMEOUT_PROFILES,
  postEtfRotationBacktest,
  postEtfRotationOptimizeParameters,
  postEtfRotationStrategyComparison,
} from '../services/api';

describe('ETF rotation advanced research API helpers', () => {
  beforeEach(() => {
    vi.spyOn(api, 'post').mockResolvedValue({ data: { success: true, data: { ok: true } } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts the single-window backtest payload to the backend engine with the long timeout profile', async () => {
    const payload = {
      period_start: '2024-01-01',
      period_end: '2024-03-31',
      enable_policy_signal_factor: true,
    };

    await expect(postEtfRotationBacktest(payload)).resolves.toEqual({ success: true, data: { ok: true } });

    expect(api.post).toHaveBeenCalledWith(
      '/etf-rotation/backtest',
      payload,
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.long }),
    );
  });

  it('posts the strategy-comparison payload through the frontend service barrel', async () => {
    const payload = {
      period_start: '2024-01-01',
      period_end: '2024-06-30',
      strategies: ['rotation', 'mean_reversion', 'blend'],
      refresh: true,
    };

    await postEtfRotationStrategyComparison(payload);

    expect(api.post).toHaveBeenCalledWith(
      '/etf-rotation/strategy-comparison',
      payload,
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.long }),
    );
  });

  it('posts optimizer jobs to the parameter optimizer endpoint with long-running request handling', async () => {
    const payload = {
      period_start: '2024-01-01',
      period_end: '2024-06-30',
      parameter_grid: { min_score_to_hold: [20, 30] },
      metric: 'sharpe_ratio',
    };

    await postEtfRotationOptimizeParameters(payload);

    expect(api.post).toHaveBeenCalledWith(
      '/etf-rotation/optimize-parameters',
      payload,
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.long }),
    );
  });
});
