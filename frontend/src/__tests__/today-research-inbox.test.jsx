import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';

if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

import { App as AntdApp } from 'antd';

import TodayResearchDashboard from '../components/TodayResearchDashboard';

const mockGetSnapshot = jest.fn();
const mockUpdateSnapshot = jest.fn();
const mockUpdateStatus = jest.fn();
const mockCreateEntry = jest.fn();

vi.mock('../services/api', () => ({
  getResearchJournalSnapshot: (...args) => mockGetSnapshot(...args),
  updateResearchJournalSnapshot: (...args) => mockUpdateSnapshot(...args),
  updateResearchJournalEntryStatus: (...args) => mockUpdateStatus(...args),
  createResearchJournalEntry: (...args) => mockCreateEntry(...args),
}));

const renderWithApp = (node) => render(<AntdApp>{node}</AntdApp>);

const buildSnapshot = (entries) => ({
  success: true,
  data: {
    entries,
    source_state: {},
    generated_at: '2026-05-12T10:00:00.000Z',
    updated_at: '2026-05-12T10:00:00.000Z',
    summary: { total_entries: entries.length },
  },
});

describe('TodayResearchDashboard research inbox', () => {
  beforeEach(() => {
    mockGetSnapshot.mockReset();
    mockUpdateSnapshot.mockReset();
    mockUpdateStatus.mockReset();
    mockCreateEntry.mockReset();
    window.localStorage.clear();
  });

  it('renders inbox and research actions sections with prioritized safe labels', async () => {
    const entries = [
      {
        id: 'fresh-alert',
        type: 'realtime_alert',
        title: 'BTC 提醒命中',
        summary: '价格提醒刚触发',
        status: 'watching',
        priority: 'medium',
        source: 'realtime_alert_hit_history',
        source_label: '实时提醒',
        updated_at: '2026-05-12T09:30:00.000Z',
        tags: [false, null, 7, 'alert'],
        action: { view: 'realtime', label: '打开实时看盘' },
      },
      {
        id: 'watch-industry',
        type: 'industry_watch',
        title: '半导体观察',
        summary: '继续看热力图',
        status: 'watching',
        priority: 'medium',
        source: 'industry_watchlist',
        source_label: '行业观察',
        updated_at: '2026-05-12T08:00:00.000Z',
        tags: ['观察'],
        action: { view: 'industry', label: '打开行业热度' },
      },
    ];
    mockGetSnapshot.mockResolvedValue(buildSnapshot(entries));
    mockUpdateSnapshot.mockResolvedValue(buildSnapshot(entries));

    renderWithApp(<TodayResearchDashboard />);

    const inbox = await screen.findByTestId('today-research-inbox');
    await waitFor(() => expect(within(inbox).getByText('研究收件箱')).toBeInTheDocument());

    const inboxText = inbox.textContent;
    expect(inboxText.indexOf('BTC 提醒命中')).toBeLessThan(inboxText.indexOf('半导体观察'));
    expect(within(inbox).getAllByText('需处理').length).toBeGreaterThan(0);
    expect(within(inbox).getAllByText('继续观察').length).toBeGreaterThan(0);
    expect(within(inbox).getByText('7')).toBeInTheDocument();
    expect(within(inbox).queryByText('false')).not.toBeInTheDocument();

    const actions = await screen.findByTestId('today-research-actions');
    expect(within(actions).getByText('研究行动')).toBeInTheDocument();
    expect(within(actions).getByText('复核提醒')).toBeInTheDocument();
    expect(within(actions).getByText('跟进行业观察')).toBeInTheDocument();
    expect(actions.textContent.indexOf('BTC 提醒命中')).toBeLessThan(actions.textContent.indexOf('半导体观察'));
    expect(within(actions).queryByText('false')).not.toBeInTheDocument();
  });
});
