import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

// Mock Recharts BEFORE importing the component. The real BarChart needs
// width/height from ResponsiveContainer (which uses ResizeObserver under
// jsdom and silently renders zero bars). The mock turns the chart into a
// flat list of <div data-testid="recharts-cell-${i}">, which lets us assert
// the bar count + cell colour without dragging in chart geometry.
vi.mock('recharts', () => {
  const passthrough = ({ children }) => <div>{children}</div>;
  const Bar = ({ children }) => <div data-testid="recharts-bar">{children}</div>;
  const Cell = ({ fill, ...rest }) => (
    <div
      data-testid="recharts-cell"
      data-fill={fill}
      data-bar-key={rest['data-testid']}
    />
  );
  return {
    ResponsiveContainer: passthrough,
    BarChart: ({ children }) => <div data-testid="recharts-barchart">{children}</div>,
    Bar,
    Cell,
    CartesianGrid: passthrough,
    ReferenceLine: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

import EtfPolicyFactorAttributionPanel from '../components/EtfPolicyFactorAttributionPanel';

// Shape lifted straight from docs/sample_attribution_report.md — synthetic
// seed=2026 report with five rebalances, hit rate 100%, +0.6807% net.
const buildSampleReport = (overrides = {}) => ({
  period_start: '2026-04-17T07:22:48+00:00',
  period_end: '2026-05-17T07:22:48+00:00',
  n_factor_on_rebalances: 5,
  factor_on_return_pct: 4.5741,
  factor_off_return_pct: 3.8934,
  factor_contribution_pct: 0.6807,
  hit_rate_pct: 100.0,
  per_rebalance_attribution: [
    {
      run_at: '2026-04-18T02:00:00+00:00',
      factor_on_return_pct: -0.0679,
      factor_off_return_pct: -0.1136,
      factor_contribution_pct: 0.0457,
    },
    {
      run_at: '2026-04-23T02:00:00+00:00',
      factor_on_return_pct: 2.3702,
      factor_off_return_pct: 2.2994,
      factor_contribution_pct: 0.0708,
    },
    {
      run_at: '2026-04-28T02:00:00+00:00',
      factor_on_return_pct: 1.0116,
      factor_off_return_pct: 0.9111,
      factor_contribution_pct: 0.1005,
    },
    {
      run_at: '2026-05-03T02:00:00+00:00',
      factor_on_return_pct: 0.1575,
      factor_off_return_pct: 0.0762,
      factor_contribution_pct: 0.0814,
    },
    {
      run_at: '2026-05-08T02:00:00+00:00',
      factor_on_return_pct: 1.0393,
      factor_off_return_pct: 0.6790,
      factor_contribution_pct: 0.3603,
    },
  ],
  top_winner_etfs: [
    { code: '515030', contribution_pct: 0.3470, n_rebalances: 4 },
    { code: '512400', contribution_pct: 0.3117, n_rebalances: 5 },
  ],
  top_loser_etfs: [],
  ...overrides,
});

const buildEmptyReport = (overrides = {}) => ({
  period_start: '2026-04-17T07:22:48+00:00',
  period_end: '2026-05-17T07:22:48+00:00',
  n_factor_on_rebalances: 0,
  factor_on_return_pct: 0,
  factor_off_return_pct: 0,
  factor_contribution_pct: 0,
  hit_rate_pct: 0,
  per_rebalance_attribution: [],
  top_winner_etfs: [],
  top_loser_etfs: [],
  ...overrides,
});

const makeFetcher = (report) => vi.fn().mockResolvedValue({ success: true, data: report });

const expandPanel = async (user) => {
  // The Collapse collapses by default; click the section header to expand
  // the body so the chart + tables are queryable.
  const header = await screen.findByTestId('etf-policy-factor-attribution-header');
  await user.click(header);
};

beforeAll(() => {
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

describe('EtfPolicyFactorAttributionPanel', () => {
  it('renders when policy_signal_factor is on, hides when off', () => {
    const fetcher = makeFetcher(buildSampleReport());

    const { rerender, queryByTestId } = render(
      <EtfPolicyFactorAttributionPanel visible={false} fetchAttribution={fetcher} />,
    );

    expect(queryByTestId('etf-policy-factor-attribution-panel')).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();

    rerender(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={fetcher} />,
    );

    expect(queryByTestId('etf-policy-factor-attribution-panel')).toBeInTheDocument();
  });

  it('shows a green +0.68% tag for positive contribution and red for negative', async () => {
    const positiveFetcher = makeFetcher(buildSampleReport());

    const { rerender } = render(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={positiveFetcher} />,
    );

    let tag;
    await waitFor(async () => {
      tag = await screen.findByTestId('etf-policy-factor-attribution-tag');
      expect(tag.textContent).toContain('+0.6807%');
    });
    // AntD applies a `ant-tag-green` class for green tags; assert the
    // contribution sign maps to green when contribution > 0.
    expect(tag.className).toMatch(/green/);

    const negativeFetcher = makeFetcher(buildSampleReport({
      factor_contribution_pct: -0.4521,
    }));

    rerender(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={negativeFetcher} />,
    );

    await waitFor(async () => {
      const negTag = await screen.findByTestId('etf-policy-factor-attribution-tag');
      expect(negTag.textContent).toContain('-0.4521%');
      expect(negTag.className).toMatch(/red/);
    });
  });

  it('renders one chart bar per rebalance and a winners table', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={fetcher} />,
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    await expandPanel(user);

    const chart = await screen.findByTestId('etf-policy-factor-attribution-chart');
    expect(chart).toBeInTheDocument();

    // 5 rebalances → 5 bar cells under the mocked Recharts.
    const cells = await screen.findAllByTestId('recharts-cell');
    expect(cells).toHaveLength(5);

    // All sample contributions are positive → every cell is green.
    cells.forEach((cell) => {
      expect(cell.getAttribute('data-fill')).toBe('#52c41a');
    });

    const winners = await screen.findByTestId('etf-policy-factor-attribution-winners');
    expect(within(winners).getByText('515030')).toBeInTheDocument();
    expect(within(winners).getByText('512400')).toBeInTheDocument();
  });

  it('refresh button triggers a re-fetch with refresh=true', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={fetcher} />,
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher).toHaveBeenLastCalledWith({ periodDays: 30, refresh: false });

    await user.click(screen.getByTestId('etf-policy-factor-attribution-refresh'));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher).toHaveBeenLastCalledWith({ periodDays: 30, refresh: true });
  });

  it('period selector switching triggers a re-fetch with the new period_days', async () => {
    // AntD Radio.Button's hidden <input> carries `pointer-events: none`, so
    // we tell user-event to skip its CSS check and just fire the click —
    // matches what a real user does (clicks the visible label, AntD bubbles
    // the change up to the hidden input).
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const fetcher = makeFetcher(buildSampleReport());

    render(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={fetcher} />,
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher).toHaveBeenLastCalledWith({ periodDays: 30, refresh: false });

    // Switch to the 7-day window — should fire a fresh fetch with the new
    // period and DON'T pass refresh=true (cache is still valuable across
    // period changes).
    await user.click(screen.getByTestId('etf-policy-factor-attribution-period-7'));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher).toHaveBeenLastCalledWith({ periodDays: 7, refresh: false });

    // Switch to 90d → third fetch.
    await user.click(screen.getByTestId('etf-policy-factor-attribution-period-90'));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    expect(fetcher).toHaveBeenLastCalledWith({ periodDays: 90, refresh: false });
  });

  it('renders empty state when no factor-enabled rebalances are in the window', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildEmptyReport());

    render(
      <EtfPolicyFactorAttributionPanel visible fetchAttribution={fetcher} />,
    );

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    await expandPanel(user);

    expect(
      await screen.findByTestId('etf-policy-factor-attribution-empty'),
    ).toBeInTheDocument();
    // No chart, no winners table.
    expect(screen.queryByTestId('etf-policy-factor-attribution-chart')).toBeNull();
    expect(screen.queryByTestId('etf-policy-factor-attribution-winners')).toBeNull();
  });
});
