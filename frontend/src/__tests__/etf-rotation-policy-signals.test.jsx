import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import EtfRotationDashboard from '../components/EtfRotationDashboard';
import {
  getEtfRotationLiveTarget,
  getPolicyRadarSignal,
} from '../services/api';

// All API functions referenced from EtfRotationDashboard must be mocked here;
// only `getEtfRotationLiveTarget` (for the initial plan) and
// `getPolicyRadarSignal` (the panel under test) actually need bodies.
vi.mock('../services/api', () => ({
  getEtfRotationAnalytics: vi.fn(),
  getEtfRotationAuditLog: vi.fn(),
  getEtfRotationDailySignal: vi.fn(),
  getEtfRotationLiveTarget: vi.fn(),
  getPolicyRadarSignal: vi.fn(),
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

const basePlanFixture = {
  manual_only: true,
  auto_ordering: false,
  banner: 'Manual trade plan — review and execute manually.',
  total_asset: 32000,
  current_weights: { '512400': 0.3, CASH: 0.7 },
  target_weights: { '512400': 0.3, CASH: 0.7 },
  adjusted_weights: { '512400': 0.3, CASH: 0.7 },
  quote_source: 'live',
  live_quote_status: { requested: 1, resolved: 1 },
  quote_snapshot: { '512400': { current_price: 2.0, source: 'realtime_manager' } },
  suggestions: [],
  risk_reasons: [],
  source_health: [],
};

const liveTargetEnvelope = {
  data: {
    plan: basePlanFixture,
    refreshed_at: '2026-05-16T02:00:00+00:00',
    quote_source: 'live',
    debounced: false,
    debounce_max_delta: null,
    reasons: [],
  },
};

const THREE_INDUSTRY_SIGNAL = {
  industry_signals: {
    '新能源汽车': { avg_impact: -0.35, mentions: 4, signal: 'bearish' },
    '半导体': { avg_impact: 0.5, mentions: 6, signal: 'bullish' },
    '光伏': { avg_impact: 0.12, mentions: 2, signal: 'neutral' },
  },
  policy_count: 12,
  source_health: { ndrc: { level: 'healthy', record_count: 4, full_text_ratio: 0.9 } },
  // A recent timestamp so the stale warning should NOT fire.
  last_refresh: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  available: true,
};

const expandPolicyPanel = async (user) => {
  const panel = await screen.findByTestId('etf-policy-signals-panel');
  // Antd v5 renders the collapsible header role="button" inside the panel.
  const header = within(panel).getByRole('button', { name: /政策信号/ });
  await user.click(header);
};

describe('EtfRotationDashboard — policy_radar signals panel', () => {
  test('renders 3 industry rows sorted by |avg_impact| once expanded', async () => {
    getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);
    getPolicyRadarSignal.mockResolvedValue({ success: true, data: THREE_INDUSTRY_SIGNAL });

    render(<EtfRotationDashboard />);
    await waitFor(() => expect(screen.getByTestId('etf-rotation-dashboard')).toBeInTheDocument());

    // Panel exists, but the rows are not rendered until expanded — they are
    // gated by the lazy-load Collapse-onChange handler.
    expect(screen.queryByTestId('etf-policy-signal-row-半导体')).not.toBeInTheDocument();

    const user = userEvent.setup();
    await expandPolicyPanel(user);

    await waitFor(() => expect(getPolicyRadarSignal).toHaveBeenCalledTimes(1));

    // All 3 industries rendered with their signal tag + impact value.
    const semi = await screen.findByTestId('etf-policy-signal-row-半导体');
    expect(within(semi).getByText('偏多')).toBeInTheDocument();
    expect(within(semi).getByText(/\+0\.50/)).toBeInTheDocument();
    expect(within(semi).getByText(/· 提及 6/)).toBeInTheDocument();

    const evCar = screen.getByTestId('etf-policy-signal-row-新能源汽车');
    expect(within(evCar).getByText('偏空')).toBeInTheDocument();
    expect(within(evCar).getByText(/-0\.35/)).toBeInTheDocument();

    const solar = screen.getByTestId('etf-policy-signal-row-光伏');
    expect(within(solar).getByText('中性')).toBeInTheDocument();

    // Sort order: |0.5| > |-0.35| > |0.12| — DOM order must match.
    const rows = screen.getAllByTestId(/^etf-policy-signal-row-/);
    expect(rows.map((node) => node.getAttribute('data-testid'))).toEqual([
      'etf-policy-signal-row-半导体',
      'etf-policy-signal-row-新能源汽车',
      'etf-policy-signal-row-光伏',
    ]);

    // No stale warning when last_refresh is recent.
    expect(screen.queryByTestId('etf-policy-signals-stale-warning')).not.toBeInTheDocument();
  });

  test('available:false renders the empty placeholder, not the rows', async () => {
    getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);
    getPolicyRadarSignal.mockResolvedValue({
      success: true,
      data: {
        industry_signals: {},
        policy_count: 0,
        source_health: {},
        last_refresh: null,
        available: false,
      },
    });

    render(<EtfRotationDashboard />);
    await waitFor(() => expect(screen.getByTestId('etf-rotation-dashboard')).toBeInTheDocument());

    const user = userEvent.setup();
    await expandPolicyPanel(user);

    await waitFor(() => expect(getPolicyRadarSignal).toHaveBeenCalledTimes(1));

    expect(await screen.findByText(/政策数据未就绪/)).toBeInTheDocument();
    expect(screen.queryByTestId(/^etf-policy-signal-row-/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('etf-policy-signals-stale-warning')).not.toBeInTheDocument();
  });

  test('expanding the panel triggers a lazy fetch (not called on mount)', async () => {
    getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);
    getPolicyRadarSignal.mockResolvedValue({ success: true, data: THREE_INDUSTRY_SIGNAL });

    render(<EtfRotationDashboard />);
    await waitFor(() => expect(screen.getByTestId('etf-rotation-dashboard')).toBeInTheDocument());

    // Before any user interaction the lazy fetcher must not have fired.
    expect(getPolicyRadarSignal).not.toHaveBeenCalled();

    const user = userEvent.setup();
    await expandPolicyPanel(user);

    await waitFor(() => expect(getPolicyRadarSignal).toHaveBeenCalledTimes(1));
  });

  test('shows the stale warning when last_refresh is older than 24h', async () => {
    getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);
    const staleTimestamp = new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString();
    getPolicyRadarSignal.mockResolvedValue({
      success: true,
      data: {
        ...THREE_INDUSTRY_SIGNAL,
        last_refresh: staleTimestamp,
      },
    });

    render(<EtfRotationDashboard />);
    await waitFor(() => expect(screen.getByTestId('etf-rotation-dashboard')).toBeInTheDocument());

    const user = userEvent.setup();
    await expandPolicyPanel(user);

    expect(await screen.findByTestId('etf-policy-signals-stale-warning')).toBeInTheDocument();
    expect(screen.getByText(/已过期/)).toBeInTheDocument();
  });
});
