import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

// Mock Recharts before importing the component. The real BarChart needs
// width/height from ResponsiveContainer (which uses ResizeObserver under
// jsdom and silently renders zero bars). The mock turns the chart into a
// flat list of <div data-testid="recharts-cell"> with `data-fill` so we
// can assert bar count + colour without depending on chart geometry.
vi.mock('recharts', () => {
  const passthrough = ({ children }) => <div>{children}</div>;
  const Bar = ({ children }) => <div data-testid="recharts-bar">{children}</div>;
  const Cell = ({ fill, ...rest }) => (
    <div
      data-testid="recharts-cell"
      data-fill={fill}
      data-bar-key={rest['data-testid']}
      data-sign={rest['data-sign']}
    />
  );
  return {
    ResponsiveContainer: passthrough,
    BarChart: ({ children }) => <div data-testid="recharts-barchart">{children}</div>,
    Bar,
    Cell,
    CartesianGrid: passthrough,
    ReferenceLine: ({ y, label }) => (
      <div
        data-testid="recharts-reference-line"
        data-y={y}
        data-label={typeof label === 'object' ? label?.value : label}
      />
    ),
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

import EtfWalkforwardPanel from '../components/EtfWalkforwardPanel';

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

// Sample lifted from docs/sample_walkforward_report.md — the real
// 2024-01 → 2025-04 / 14-window run. We keep 4 windows here (one of
// which is negative) so the bar-colour and table assertions stay tight.
const buildSampleReport = (overrides = {}) => ({
  period_start: '2024-01-01',
  period_end: '2025-04-30',
  window_months: 3,
  step_months: 1,
  n_windows: 4,
  rebalance_freq_days: 5,
  initial_capital: 100000,
  policy_signal_factor_enabled: false,
  windows: [
    {
      period_start: '2024-01-02',
      period_end: '2024-03-29',
      total_return_pct: 5.65,
      sharpe_ratio: 3.61,
      max_drawdown_pct: 2.07,
      comparable_buy_hold_return_pct: 3.40,
      win_rate: 0.636,
    },
    {
      period_start: '2024-02-01',
      period_end: '2024-04-30',
      total_return_pct: 7.08,
      sharpe_ratio: 3.13,
      max_drawdown_pct: 3.36,
      comparable_buy_hold_return_pct: 16.27,
      win_rate: 0.636,
    },
    {
      period_start: '2024-04-01',
      period_end: '2024-06-28',
      total_return_pct: -0.34,
      sharpe_ratio: -0.07,
      max_drawdown_pct: 5.76,
      comparable_buy_hold_return_pct: -1.01,
      win_rate: 0.545,
    },
    {
      period_start: '2024-05-06',
      period_end: '2024-07-31',
      total_return_pct: -3.18,
      sharpe_ratio: -1.54,
      max_drawdown_pct: 6.65,
      comparable_buy_hold_return_pct: -6.44,
      win_rate: 0.417,
    },
  ],
  aggregate_return_pct: 8.97,
  mean_window_return_pct: 2.30,
  median_window_return_pct: 2.66,
  return_std_pct: 4.45,
  pct_positive_windows: 0.5,
  mean_sharpe: 1.28,
  median_sharpe: 1.53,
  mean_max_dd_pct: 4.46,
  worst_window_dd_pct: 6.65,
  mean_buy_hold_return_pct: 3.06,
  consistency_score: 0.213,
  caveats: ['walkforward_overlapping_windows_double_count_overlap'],
  ...overrides,
});

const makeFetcher = (report, { cached = false } = {}) => vi.fn().mockResolvedValue({
  success: true,
  data: report,
  cached,
  cache_age_seconds: cached ? 12.5 : 0,
});

describe('EtfWalkforwardPanel', () => {
  it('renders header + controls in the collapsed/initial state without auto-running', () => {
    const fetcher = makeFetcher(buildSampleReport());

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    expect(screen.getByTestId('etf-walkforward-panel')).toBeInTheDocument();
    // Header + scope-distinguishing tooltip tag.
    expect(screen.getByText('历史回测（滚动窗口）')).toBeInTheDocument();
    // Controls visible.
    expect(screen.getByTestId('etf-walkforward-range-picker')).toBeInTheDocument();
    expect(screen.getByTestId('etf-walkforward-window-months')).toBeInTheDocument();
    expect(screen.getByTestId('etf-walkforward-step-months')).toBeInTheDocument();
    expect(screen.getByTestId('etf-walkforward-policy-switch')).toBeInTheDocument();
    expect(screen.getByTestId('etf-walkforward-cache-checkbox')).toBeInTheDocument();
    expect(screen.getByTestId('etf-walkforward-run-button')).toBeInTheDocument();
    // Empty state shown until the user clicks Run — button-driven UX.
    expect(screen.getByTestId('etf-walkforward-empty')).toBeInTheDocument();
    // No auto-run on mount.
    expect(fetcher).not.toHaveBeenCalled();
    // Summary tag is hidden until results land.
    expect(screen.queryByTestId('etf-walkforward-summary-tag')).toBeNull();
  });

  it('clicking 运行回测 triggers POST with default params and renders results', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    // Default params: 2024-01-01 → 2025-04-30, 3 month window, 1 month step,
    // policy factor OFF.
    expect(fetcher).toHaveBeenLastCalledWith({
      periodStart: '2024-01-01',
      periodEnd: '2025-04-30',
      windowMonths: 3,
      stepMonths: 1,
      enablePolicySignalFactor: false,
      refresh: false,
    });

    // Summary + chart + table all render after the response lands.
    const summaryTag = await screen.findByTestId('etf-walkforward-summary-tag');
    expect(summaryTag.textContent).toContain('50%');
    expect(summaryTag.textContent).toContain('median');

    expect(await screen.findByTestId('etf-walkforward-summary-tile')).toBeInTheDocument();
    expect(screen.getByText('median 窗口收益')).toBeInTheDocument();
    expect(screen.getByText('mean 窗口收益')).toBeInTheDocument();
    expect(screen.getByText('std (pp)')).toBeInTheDocument();
    expect(screen.getByText('% 正收益窗口')).toBeInTheDocument();
    expect(screen.getByText('consistency')).toBeInTheDocument();
    expect(screen.getByText('mean buy-hold/窗口')).toBeInTheDocument();
    expect(await screen.findByTestId('etf-walkforward-chart')).toBeInTheDocument();
    expect(await screen.findByTestId('etf-walkforward-table')).toBeInTheDocument();
  });

  it('renders a successful empty-window report as a degraded empty state', async () => {
    const user = userEvent.setup();
    const emptyReport = buildSampleReport({
      n_windows: 0,
      windows: [],
      aggregate_return_pct: 0,
      mean_window_return_pct: 0,
      median_window_return_pct: 0,
      return_std_pct: 0,
      pct_positive_windows: 0,
      mean_sharpe: 0,
      median_sharpe: 0,
      mean_max_dd_pct: 0,
      worst_window_dd_pct: 0,
      mean_buy_hold_return_pct: 0,
      consistency_score: 0,
      caveats: ['empty_report:no_windows_generated'],
    });
    const fetcher = makeFetcher(emptyReport);

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    const summaryTag = await screen.findByTestId('etf-walkforward-summary-tag');
    expect(summaryTag.textContent).toContain('0%');
    expect(summaryTag.textContent).toContain('median +0.00%');

    const noWindows = await screen.findByTestId('etf-walkforward-no-windows');
    expect(noWindows).toHaveTextContent('没有可用窗口');
    expect(screen.queryByTestId('etf-walkforward-summary-tile')).toBeNull();
    expect(screen.queryByTestId('etf-walkforward-chart')).toBeNull();
    expect(screen.queryByTestId('etf-walkforward-table')).toBeNull();
    expect(screen.queryByTestId('etf-walkforward-error')).toBeNull();
  });

  it('shows the loading state with the "约 30 秒 / 14 个窗口" hint while POST is in flight', async () => {
    const user = userEvent.setup();
    // Resolve manually so we can observe the loading state mid-flight.
    let resolveFetch;
    const fetcher = vi.fn().mockImplementation(() => new Promise((resolve) => {
      resolveFetch = resolve;
    }));

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));

    // The loading card should appear with the progress hint while
    // pending — both the spinner card and the antd button spinner.
    const loadingCard = await screen.findByTestId('etf-walkforward-loading');
    expect(loadingCard.textContent).toMatch(/30 秒/);
    expect(loadingCard.textContent).toMatch(/14 个窗口/);

    // Resolve so userEvent's act() cleanup doesn't warn.
    resolveFetch({
      success: true,
      data: buildSampleReport(),
      cached: false,
      cache_age_seconds: 0,
    });

    await waitFor(() => {
      expect(screen.queryByTestId('etf-walkforward-loading')).toBeNull();
    });
  });

  it('renders one bar per window with the correct positive/negative colour', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    const cells = await screen.findAllByTestId('recharts-cell');
    // 4 windows → 4 bars.
    expect(cells).toHaveLength(4);

    // Per sample data: 2 positive (+5.65 / +7.08), 2 negative (-0.34 / -3.18).
    expect(cells[0].getAttribute('data-fill')).toBe('#52c41a');
    expect(cells[1].getAttribute('data-fill')).toBe('#52c41a');
    expect(cells[2].getAttribute('data-fill')).toBe('#ff4d4f');
    expect(cells[3].getAttribute('data-fill')).toBe('#ff4d4f');
    expect(cells[2].getAttribute('data-sign')).toBe('negative');
    expect(cells[3].getAttribute('data-sign')).toBe('negative');

    // Table renders one row per window — the antd Table renders the
    // window labels (#1 / #2 / …) we can grep on.
    const table = screen.getByTestId('etf-walkforward-table');
    expect(within(table).getByText('#1')).toBeInTheDocument();
    expect(within(table).getByText('#4')).toBeInTheDocument();
  });

  it('overlays a mean-buy-hold reference line at +3.06% per the sample report', async () => {
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    // Two ReferenceLine elements: zero baseline + mean buy-hold overlay.
    const refLines = await screen.findAllByTestId('recharts-reference-line');
    expect(refLines.length).toBeGreaterThanOrEqual(2);
    const buyHold = refLines.find((el) => Number(el.getAttribute('data-y')) === 3.06);
    expect(buyHold).toBeTruthy();
    expect(buyHold.getAttribute('data-label')).toMatch(/3\.06%/);
  });

  it('changing controls and re-running fires a new POST with the updated payload', async () => {
    // AntD's RangePicker is heavy under jsdom; rather than driving the
    // calendar UI we update the window-months input to prove the controls
    // round-trip through the POST. The range-picker default values are
    // covered by the prior "default params" test. This case asserts that
    // a control change between runs *does* reach the request payload.
    const user = userEvent.setup();
    const fetcher = makeFetcher(buildSampleReport());

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    // Run once with defaults.
    await user.click(screen.getByTestId('etf-walkforward-run-button'));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({
      windowMonths: 3,
      stepMonths: 1,
      refresh: false,
    }));

    // Bump window_months 3 → 6 via the InputNumber spinner. AntD's
    // InputNumber renders an inner <input>; we type into it and re-run.
    const windowInputWrapper = screen.getByTestId('etf-walkforward-window-months');
    const windowInput = windowInputWrapper.querySelector('input');
    expect(windowInput).toBeTruthy();
    await user.clear(windowInput);
    await user.type(windowInput, '6');

    // Toggle policy factor ON so we also assert the boolean flips through.
    await user.click(screen.getByTestId('etf-walkforward-policy-switch'));
    await user.click(screen.getByTestId('etf-walkforward-cache-checkbox'));

    // After clicking Run a 2nd time, the new params should reach the API.
    await user.click(screen.getByTestId('etf-walkforward-run-button'));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({
      windowMonths: 6,
      enablePolicySignalFactor: true,
      refresh: true,
    }));
  });

  it('surfaces an Alert when the POST fails', async () => {
    const user = userEvent.setup();
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'));

    render(<EtfWalkforwardPanel postWalkforward={fetcher} />);

    await user.click(screen.getByTestId('etf-walkforward-run-button'));

    const alert = await screen.findByTestId('etf-walkforward-error');
    expect(alert.textContent).toContain('boom');
  });
});
