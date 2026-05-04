/**
 * Component-level test for the "送到纸面账户" action on backtest-typed
 * entries inside TodayResearchDashboard (Feature G).
 */

import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
const mockNavigate = jest.fn();
const mockSetPaperPrefill = jest.fn();

jest.mock('../services/api', () => ({
    getResearchJournalSnapshot: (...args) => mockGetSnapshot(...args),
    updateResearchJournalSnapshot: (...args) => mockUpdateSnapshot(...args),
    updateResearchJournalEntryStatus: (...args) => mockUpdateStatus(...args),
    createResearchJournalEntry: (...args) => mockCreateEntry(...args),
}));

jest.mock('../utils/researchContext', () => {
    const actual = jest.requireActual('../utils/researchContext');
    return {
        ...actual,
        navigateToAppUrl: (...args) => mockNavigate(...args),
    };
});

jest.mock('../utils/paperTradingPrefill', () => {
    const actual = jest.requireActual('../utils/paperTradingPrefill');
    return {
        ...actual,
        setPaperPrefill: (...args) => mockSetPaperPrefill(...args),
    };
});

const renderWithApp = (node) => render(<AntdApp>{node}</AntdApp>);

const buildSnapshot = (entries) => ({
    success: true,
    data: {
        entries,
        source_state: {},
        generated_at: '2026-05-04T08:00:00+00:00',
        updated_at: '2026-05-04T08:00:00+00:00',
        summary: { total_entries: entries.length },
    },
});

const BACKTEST_ENTRY = {
    id: 'bt-1',
    type: 'backtest',
    status: 'open',
    priority: 'medium',
    title: 'AAPL · MovingAverageCrossover',
    summary: '收益 12.34% Sharpe 1.20',
    symbol: 'AAPL',
    industry: '',
    source: 'backtest_auto',
    source_label: '自动归档',
    created_at: '2026-05-03T08:00:00+00:00',
    updated_at: '2026-05-03T08:00:00+00:00',
    tags: ['auto', 'MovingAverageCrossover'],
    metrics: { total_return: 0.12, sharpe_ratio: 1.2 },
    raw: {
        strategy: 'MovingAverageCrossover',
        last_trade: { side: 'BUY', quantity: 10, price: 150, date: '2024-12-01' },
    },
};

const MANUAL_ENTRY = {
    id: 'manual-1',
    type: 'manual',
    status: 'open',
    priority: 'medium',
    title: '半导体跟踪',
    symbol: '688981',
    raw: {},
    source: 'manual_entry',
    source_label: '手动记录',
    created_at: '2026-05-03T09:00:00+00:00',
    updated_at: '2026-05-03T09:00:00+00:00',
};

describe('TodayResearchDashboard send-to-paper', () => {
    beforeEach(() => {
        mockGetSnapshot.mockReset();
        mockUpdateSnapshot.mockReset();
        mockUpdateStatus.mockReset();
        mockCreateEntry.mockReset();
        mockNavigate.mockReset();
        mockSetPaperPrefill.mockReset();
        try { window.localStorage.clear(); } catch (_e) { /* noop */ }
    });

    it('renders the send-to-paper button on backtest entries with a symbol', async () => {
        mockGetSnapshot.mockResolvedValue(buildSnapshot([BACKTEST_ENTRY]));
        mockUpdateSnapshot.mockResolvedValue(buildSnapshot([BACKTEST_ENTRY]));

        renderWithApp(<TodayResearchDashboard />);

        await waitFor(() => {
            expect(screen.getByTestId('today-entry-send-to-paper')).toBeInTheDocument();
        });
    });

    it('does not render the send-to-paper button on non-backtest entries', async () => {
        mockGetSnapshot.mockResolvedValue(buildSnapshot([MANUAL_ENTRY]));
        mockUpdateSnapshot.mockResolvedValue(buildSnapshot([MANUAL_ENTRY]));

        renderWithApp(<TodayResearchDashboard />);

        // Wait for the entry itself to be in the DOM
        await waitFor(() => {
            expect(screen.getByText('半导体跟踪')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('today-entry-send-to-paper')).not.toBeInTheDocument();
    });

    it('does not render the send-to-paper button when symbol is missing', async () => {
        const entry = { ...BACKTEST_ENTRY, id: 'bt-no-sym', symbol: '' };
        mockGetSnapshot.mockResolvedValue(buildSnapshot([entry]));
        mockUpdateSnapshot.mockResolvedValue(buildSnapshot([entry]));

        renderWithApp(<TodayResearchDashboard />);

        await waitFor(() => {
            expect(screen.getByText('AAPL · MovingAverageCrossover')).toBeInTheDocument();
        });
        expect(screen.queryByTestId('today-entry-send-to-paper')).not.toBeInTheDocument();
    });

    it('clicking the button stages a paper prefill and navigates to ?view=paper', async () => {
        mockGetSnapshot.mockResolvedValue(buildSnapshot([BACKTEST_ENTRY]));
        mockUpdateSnapshot.mockResolvedValue(buildSnapshot([BACKTEST_ENTRY]));

        renderWithApp(<TodayResearchDashboard />);

        const btn = await screen.findByTestId('today-entry-send-to-paper');
        fireEvent.click(btn);

        await waitFor(() => expect(mockSetPaperPrefill).toHaveBeenCalledTimes(1));
        const prefill = mockSetPaperPrefill.mock.calls[0][0];
        expect(prefill).toMatchObject({
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 10,
            sourceLabel: '由 MovingAverageCrossover · 档案带入',
        });

        expect(mockNavigate).toHaveBeenCalledTimes(1);
        const targetUrl = mockNavigate.mock.calls[0][0];
        expect(targetUrl).toContain('view=paper');
    });
});
