import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Polyfill matchMedia — JSDOM doesn't ship it, and antd's Statistic / Row / Col
// transitively call useBreakpoint which assumes it exists.
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

import PaperTradingPanel from '../components/PaperTradingPanel';

const mockGetAccount = jest.fn();
const mockListOrders = jest.fn();
const mockSubmitOrder = jest.fn();
const mockResetAccount = jest.fn();
const mockGetMultipleQuotes = jest.fn();

jest.mock('../services/api', () => ({
    getPaperAccount: (...args) => mockGetAccount(...args),
    listPaperOrders: (...args) => mockListOrders(...args),
    submitPaperOrder: (...args) => mockSubmitOrder(...args),
    resetPaperAccount: (...args) => mockResetAccount(...args),
    getMultipleQuotes: (...args) => mockGetMultipleQuotes(...args),
}));

const renderWithApp = (node) => render(<AntdApp>{node}</AntdApp>);

const ACCOUNT_WITH_POSITION = {
    profile_id: 'default',
    initial_capital: 10000,
    cash: 8500,
    positions: [
        {
            symbol: 'AAPL',
            quantity: 10,
            avg_cost: 150,
            opened_at: '2026-05-01T08:00:00+00:00',
            updated_at: '2026-05-01T08:00:00+00:00',
        },
    ],
    orders_count: 1,
    created_at: '2026-05-01T08:00:00+00:00',
    updated_at: '2026-05-01T08:00:00+00:00',
};

const ORDERS_HISTORY = {
    orders: [
        {
            id: 'ord-1',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 10,
            fill_price: 150,
            commission: 0,
            submitted_at: '2026-05-01T08:00:00+00:00',
            note: '',
        },
    ],
    limit: 50,
};

describe('PaperTradingPanel', () => {
    beforeEach(() => {
        mockGetAccount.mockReset();
        mockListOrders.mockReset();
        mockSubmitOrder.mockReset();
        mockResetAccount.mockReset();
        mockGetMultipleQuotes.mockReset();
        mockGetMultipleQuotes.mockResolvedValue({
            success: true,
            data: { quotes: { AAPL: { price: 165 } } },
        });
        mockGetAccount.mockResolvedValue({ success: true, data: ACCOUNT_WITH_POSITION });
        mockListOrders.mockResolvedValue({ success: true, data: ORDERS_HISTORY });
    });

    it('renders account chips and existing positions table', async () => {
        renderWithApp(<PaperTradingPanel />);

        // Chip strip values are deterministic markers of "data loaded"
        await waitFor(() => {
            expect(screen.getByText('持仓 1')).toBeInTheDocument();
        });
        expect(screen.getByText('订单 1')).toBeInTheDocument();
        // Positions table shows the symbol; orders table also shows it,
        // so getAllByText is the right query.
        expect(screen.getAllByText('AAPL').length).toBeGreaterThanOrEqual(1);
    });

    it('submits an order through the API and refreshes the account view', async () => {
        mockSubmitOrder.mockResolvedValue({
            success: true,
            data: { account: ACCOUNT_WITH_POSITION },
        });

        renderWithApp(<PaperTradingPanel />);
        // Wait for the data to arrive so the form is wired up
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());
        const initialAccountCalls = mockGetAccount.mock.calls.length;

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'msft' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '5' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '210' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const sent = mockSubmitOrder.mock.calls[0][0];
        expect(sent).toMatchObject({
            symbol: 'MSFT',
            side: 'BUY',
            quantity: 5,
            fill_price: 210,
        });
        // The success branch triggers refresh(), which re-fetches the account
        await waitFor(() =>
            expect(mockGetAccount.mock.calls.length).toBeGreaterThan(initialAccountCalls)
        );
    });

    it('surfaces submit errors via the message channel', async () => {
        mockSubmitOrder.mockRejectedValue({
            response: { data: { error: { message: 'insufficient cash' } } },
        });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'aapl' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '1000' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '200' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        await waitFor(() => {
            expect(screen.getByText('insufficient cash')).toBeInTheDocument();
        });
    });
});
