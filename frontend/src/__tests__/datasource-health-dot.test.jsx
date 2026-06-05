import { cleanup, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import DataSourceHealthDot, { resolveHealthVisual } from '../components/DataSourceHealthDot';
import { getDataSourceHealth } from '../services/api';

vi.mock('../services/api', () => ({
  getDataSourceHealth: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('resolveHealthVisual', () => {
  test('green when tushare ok and not degraded', () => {
    const v = resolveHealthVisual({
      tushare: { ok: true, reason: 'ok', detail: 'reachable' },
      degraded: false,
    });
    expect(v.state).toBe('ok');
    expect(v.color).toBe('#52c41a');
  });

  test('amber when rate limited (fallback active, not hard down)', () => {
    const v = resolveHealthVisual({
      tushare: { ok: false, reason: 'rate_limited', detail: '每分钟最多访问' },
      degraded: true,
    });
    expect(v.state).toBe('degraded');
    expect(v.color).toBe('#faad14');
    expect(v.label).toMatch(/更慢|不完整/);
  });

  test('red when token invalid', () => {
    const v = resolveHealthVisual({
      tushare: { ok: false, reason: 'token_invalid', detail: '您的token不对' },
      degraded: true,
    });
    expect(v.state).toBe('down');
    expect(v.color).toBe('#ff4d4f');
  });

  test('red when token missing', () => {
    const v = resolveHealthVisual({
      tushare: { ok: false, reason: 'token_missing', detail: 'not configured' },
      degraded: true,
    });
    expect(v.state).toBe('down');
    expect(v.color).toBe('#ff4d4f');
  });

  test('grey loading state when no health yet', () => {
    const v = resolveHealthVisual(null);
    expect(v.state).toBe('loading');
    expect(v.color).toBe('#8c8c8c');
  });
});

describe('<DataSourceHealthDot />', () => {
  test('renders a healthy (green) dot on mount', async () => {
    getDataSourceHealth.mockResolvedValue({
      tushare: { ok: true, reason: 'ok', detail: 'reachable' },
      primary_source: 'tushare',
      degraded: false,
    });

    render(<DataSourceHealthDot />);

    await waitFor(() => {
      const dot = screen.getByTestId('datasource-health-dot');
      expect(dot).toHaveAttribute('data-state', 'ok');
    });
    expect(getDataSourceHealth).toHaveBeenCalledTimes(1);
  });

  test('reflects a degraded (amber) state', async () => {
    getDataSourceHealth.mockResolvedValue({
      tushare: { ok: false, reason: 'rate_limited', detail: '限流' },
      primary_source: 'tushare',
      degraded: true,
    });

    render(<DataSourceHealthDot />);

    await waitFor(() => {
      expect(screen.getByTestId('datasource-health-dot')).toHaveAttribute('data-state', 'degraded');
    });
  });

  test('shows a degraded dot when the backend is unreachable', async () => {
    getDataSourceHealth.mockRejectedValue(new Error('network down'));

    render(<DataSourceHealthDot />);

    await waitFor(() => {
      const dot = screen.getByTestId('datasource-health-dot');
      // error path => amber degraded, never crashes
      expect(['degraded', 'down']).toContain(dot.getAttribute('data-state'));
    });
  });
});
