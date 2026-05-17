import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import EtfRotationDashboard from '../components/EtfRotationDashboard';
import {
  getEtfRotationDailySignal,
  getEtfRotationLiveTarget,
  getEtfRotationPreferences,
  postEtfRotationPreferences,
} from '../services/api';

// Mock the entire api module so the dashboard runs offline. Every API
// function the dashboard imports must be listed here, otherwise the
// component will read ``undefined`` and crash.
vi.mock('../services/api', () => ({
  getEtfRotationAnalytics: vi.fn(),
  getEtfRotationAuditLog: vi.fn(),
  getEtfRotationDailySignal: vi.fn(),
  getEtfRotationLiveTarget: vi.fn(),
  getEtfRotationPreferences: vi.fn(),
  getPolicyRadarSignal: vi.fn(),
  postEtfRotationPreferences: vi.fn(),
  postEtfRotationRefresh: vi.fn(),
  postEtfRotationReloadConfig: vi.fn(),
}));

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = () => ({
      matches: false,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }
  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

afterEach(() => {
  vi.clearAllMocks();
});

// Minimal viable plan — the toggle row + Δ panel are gated by fields
// inside the plan envelope, so we keep this fixture deliberately small
// and override only the policy-related slice in each test.
const buildPlan = ({
  policyEnabled = false,
  source = 'config',
  scoreBreakdown = {},
  appliedCount = 0,
  boosted = [],
  penalised = [],
} = {}) => ({
  manual_only: true,
  auto_ordering: false,
  banner: 'Manual trade plan',
  total_asset: 10000,
  current_weights: { '512400': 0.3, CASH: 0.7 },
  target_weights: { '512400': 0.3, CASH: 0.7 },
  adjusted_weights: { '512400': 0.3, CASH: 0.7 },
  quote_source: 'live',
  live_quote_status: { requested: 1, resolved: 1 },
  quote_snapshot: {},
  suggestions: [],
  risk_reasons: [],
  source_health: [],
  score_breakdown: scoreBreakdown,
  // The top-level shortcut the API stamps after the precedence
  // resolution; the toggle binds to this field.
  policy_signal_factor_enabled: policyEnabled,
  policy_signal_factor: {
    enabled: policyEnabled,
    source,
    applied_count: appliedCount,
    boosted,
    penalised,
    industry_signals_count: 0,
    last_refresh: null,
  },
});

const wrapInLiveTargetEnvelope = (plan) => ({
  data: {
    plan,
    refreshed_at: '2026-05-16T02:00:00+00:00',
    quote_source: 'live',
    debounced: false,
    debounce_max_delta: null,
    reasons: [],
  },
  refresh: { is_trading_hours: false },
});

const PREF_RESPONSE_OFF = {
  success: true,
  data: {
    preference: { policy_signal_factor_enabled: null },
    effective: { policy_signal_factor_enabled: false, source: 'config' },
    config_default: { policy_signal_factor_enabled: false },
  },
};

describe('EtfRotationDashboard — policy_signal_factor toggle', () => {
  test('renders the toggle row and shows it in the OFF state by default', async () => {
    getEtfRotationPreferences.mockResolvedValue(PREF_RESPONSE_OFF);
    getEtfRotationLiveTarget.mockResolvedValue(
      wrapInLiveTargetEnvelope(buildPlan({ policyEnabled: false })),
    );

    render(<EtfRotationDashboard />);

    const toggle = await screen.findByTestId('etf-policy-factor-toggle');
    expect(toggle).toBeInTheDocument();
    // Antd's Switch reflects state through ``aria-checked``.
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    // The visible state badge mirrors the boolean for sighted users.
    expect(screen.getByTestId('etf-policy-factor-state-tag')).toHaveTextContent('已关闭');
    // No Δ panel when off.
    expect(screen.queryByTestId('etf-policy-factor-delta-panel')).not.toBeInTheDocument();
  });

  test('clicking the toggle posts the preference and re-fetches the plan', async () => {
    getEtfRotationPreferences.mockResolvedValue(PREF_RESPONSE_OFF);
    getEtfRotationLiveTarget
      // Initial mount: factor off.
      .mockResolvedValueOnce(wrapInLiveTargetEnvelope(buildPlan({ policyEnabled: false })))
      // After the toggle click, the re-fetch returns the same shape but
      // with the factor flipped on. The dashboard binds its rendered
      // state to this response (not to optimistic local state) so this
      // is the source of truth.
      .mockResolvedValueOnce(wrapInLiveTargetEnvelope(buildPlan({
        policyEnabled: true,
        source: 'preference',
        appliedCount: 1,
        boosted: ['512400'],
      })));
    postEtfRotationPreferences.mockResolvedValue({
      success: true,
      data: {
        preference: { policy_signal_factor_enabled: true },
        effective: { policy_signal_factor_enabled: true, source: 'preference' },
        config_default: { policy_signal_factor_enabled: false },
      },
    });

    render(<EtfRotationDashboard />);
    const toggle = await screen.findByTestId('etf-policy-factor-toggle');
    expect(toggle.getAttribute('aria-checked')).toBe('false');

    const user = userEvent.setup();
    await user.click(toggle);

    // Preference POST happened with the new value …
    await waitFor(() => {
      expect(postEtfRotationPreferences).toHaveBeenCalledWith({
        policySignalFactorEnabled: true,
      });
    });
    // … followed by the live-target re-fetch that surfaces the new state.
    await waitFor(() => {
      expect(getEtfRotationLiveTarget).toHaveBeenCalledWith({ triggerRefresh: true });
    });
    // The toggle reconciles to ON once the new plan lands.
    await waitFor(() => {
      expect(screen.getByTestId('etf-policy-factor-toggle').getAttribute('aria-checked')).toBe('true');
    });
    expect(screen.getByTestId('etf-policy-factor-state-tag')).toHaveTextContent('已启用');
  });

  test('when the factor is on, the Δ panel lists every applied policy_adjustment', async () => {
    getEtfRotationPreferences.mockResolvedValue({
      success: true,
      data: {
        preference: { policy_signal_factor_enabled: true },
        effective: { policy_signal_factor_enabled: true, source: 'preference' },
        config_default: { policy_signal_factor_enabled: false },
      },
    });
    const scoreBreakdown = {
      '512400': {
        score: 60,
        trend_score: 0, momentum_score: 0, risk_score: 0, premium_score: 0,
        raw_target_weight: 0.22, latest_price: 2.0, ma20: 0, ma60: 0,
        ma200: null, trend_long_strength: null,
        return5: 0, return20: 0, return60: 0, drawdown60: 0, volatility60: 0,
        policy_adjustment: {
          applied: true,
          industry: 'metals',
          signal: 'bullish',
          avg_impact: 0.4,
          delta_weight: 0.06,
        },
      },
      '159985': {
        score: 50,
        trend_score: 0, momentum_score: 0, risk_score: 0, premium_score: 0,
        raw_target_weight: 0.04, latest_price: 1.0, ma20: 0, ma60: 0,
        ma200: null, trend_long_strength: null,
        return5: 0, return20: 0, return60: 0, drawdown60: 0, volatility60: 0,
        policy_adjustment: {
          applied: true,
          industry: '新能源汽车',
          signal: 'bearish',
          avg_impact: -0.35,
          delta_weight: -0.08,
        },
      },
      '510300': {
        score: 70,
        trend_score: 0, momentum_score: 0, risk_score: 0, premium_score: 0,
        raw_target_weight: 0.28, latest_price: 5.0, ma20: 0, ma60: 0,
        ma200: null, trend_long_strength: null,
        return5: 0, return20: 0, return60: 0, drawdown60: 0, volatility60: 0,
        // Not applied → must NOT appear in the delta list.
        policy_adjustment: {
          applied: false,
          industry: 'broad_market',
          signal: 'neutral',
          avg_impact: 0.0,
          delta_weight: 0.0,
        },
      },
    };
    getEtfRotationLiveTarget.mockResolvedValue(
      wrapInLiveTargetEnvelope(
        buildPlan({
          policyEnabled: true,
          source: 'preference',
          scoreBreakdown,
          appliedCount: 2,
          boosted: ['512400'],
          penalised: ['159985'],
        }),
      ),
    );

    render(<EtfRotationDashboard />);

    const panel = await screen.findByTestId('etf-policy-factor-delta-panel');
    const list = within(panel).getByTestId('etf-policy-factor-delta-list');
    // Two applied rows (one boost, one penalty). The neutral/non-applied
    // 510300 must NOT appear.
    expect(within(list).getByTestId('etf-policy-factor-delta-512400')).toBeInTheDocument();
    expect(within(list).getByTestId('etf-policy-factor-delta-159985')).toBeInTheDocument();
    expect(within(list).queryByTestId('etf-policy-factor-delta-510300')).not.toBeInTheDocument();
    // The deltas surface as percentages with a sign — boost is +, penalty is -.
    expect(within(panel).getByText(/\+6\.0% policy boost/)).toBeInTheDocument();
    expect(within(panel).getByText(/-8\.0% policy penalty/)).toBeInTheDocument();
  });

  test('Δ panel disappears when the toggle is flipped back off', async () => {
    getEtfRotationPreferences.mockResolvedValue(PREF_RESPONSE_OFF);
    const onPlan = buildPlan({
      policyEnabled: true,
      source: 'preference',
      scoreBreakdown: {
        '512400': {
          score: 60,
          trend_score: 0, momentum_score: 0, risk_score: 0, premium_score: 0,
          raw_target_weight: 0.22, latest_price: 2.0, ma20: 0, ma60: 0,
          ma200: null, trend_long_strength: null,
          return5: 0, return20: 0, return60: 0, drawdown60: 0, volatility60: 0,
          policy_adjustment: {
            applied: true, industry: 'metals', signal: 'bullish',
            avg_impact: 0.4, delta_weight: 0.06,
          },
        },
      },
      appliedCount: 1, boosted: ['512400'],
    });
    const offPlan = buildPlan({ policyEnabled: false });

    getEtfRotationLiveTarget
      .mockResolvedValueOnce(wrapInLiveTargetEnvelope(onPlan))
      .mockResolvedValueOnce(wrapInLiveTargetEnvelope(offPlan));
    postEtfRotationPreferences.mockResolvedValue({
      success: true,
      data: {
        preference: { policy_signal_factor_enabled: false },
        effective: { policy_signal_factor_enabled: false, source: 'preference' },
        config_default: { policy_signal_factor_enabled: false },
      },
    });

    render(<EtfRotationDashboard />);
    // Initial render: Δ panel visible because the factor is on.
    await screen.findByTestId('etf-policy-factor-delta-panel');

    const toggle = screen.getByTestId('etf-policy-factor-toggle');
    expect(toggle.getAttribute('aria-checked')).toBe('true');

    const user = userEvent.setup();
    await user.click(toggle);

    await waitFor(() => {
      expect(postEtfRotationPreferences).toHaveBeenCalledWith({
        policySignalFactorEnabled: false,
      });
    });
    // After the re-fetch, the toggle is off and the Δ panel is gone.
    await waitFor(() => {
      expect(screen.getByTestId('etf-policy-factor-toggle').getAttribute('aria-checked')).toBe('false');
    });
    expect(screen.queryByTestId('etf-policy-factor-delta-panel')).not.toBeInTheDocument();
  });

  test('the source tag explains who won (preference vs config vs query)', async () => {
    getEtfRotationPreferences.mockResolvedValue({
      success: true,
      data: {
        preference: { policy_signal_factor_enabled: true },
        effective: { policy_signal_factor_enabled: true, source: 'preference' },
        config_default: { policy_signal_factor_enabled: false },
      },
    });
    getEtfRotationLiveTarget.mockResolvedValue(
      wrapInLiveTargetEnvelope(
        buildPlan({ policyEnabled: true, source: 'preference', appliedCount: 0 }),
      ),
    );

    render(<EtfRotationDashboard />);

    // The component renders ``来源：<source>`` as a Tag — assert by full text.
    expect(await screen.findByText(/来源：preference/)).toBeInTheDocument();
  });

  // Bonus: even before the daily-signal response arrives, the dashboard
  // calls /etf-rotation/preferences. This is a soft contract — the
  // pre-warm exists so the toggle's first render is *eventually*
  // consistent with the stored state when the daily-signal mock isn't
  // wired (e.g. in degraded environments). We assert that the call goes
  // out so the contract doesn't silently regress.
  test('mounts call /etf-rotation/preferences exactly once to pre-warm', async () => {
    getEtfRotationPreferences.mockResolvedValue(PREF_RESPONSE_OFF);
    // Force the daily-signal path to fall through so neither side rejects.
    const error503 = new Error('Service Unavailable');
    error503.response = { status: 503 };
    getEtfRotationLiveTarget.mockRejectedValue(error503);
    getEtfRotationDailySignal.mockResolvedValue({
      data: buildPlan({ policyEnabled: false }),
    });

    render(<EtfRotationDashboard />);

    await waitFor(() => expect(getEtfRotationPreferences).toHaveBeenCalledTimes(1));
  });
});
