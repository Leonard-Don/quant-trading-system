import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
const mockCreateJournalEntry = jest.fn();
const mockCancelPaperOrder = jest.fn();

jest.mock('../services/api', () => ({
    getPaperAccount: (...args) => mockGetAccount(...args),
    listPaperOrders: (...args) => mockListOrders(...args),
    submitPaperOrder: (...args) => mockSubmitOrder(...args),
    resetPaperAccount: (...args) => mockResetAccount(...args),
    getMultipleQuotes: (...args) => mockGetMultipleQuotes(...args),
    createResearchJournalEntry: (...args) => mockCreateJournalEntry(...args),
    cancelPaperOrder: (...args) => mockCancelPaperOrder(...args),
}));

const mockExportToCSV = jest.fn();
jest.mock('../utils/export', () => ({
    exportToCSV: (...args) => mockExportToCSV(...args),
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
        mockCreateJournalEntry.mockReset();
        mockCancelPaperOrder.mockReset();
        mockExportToCSV.mockReset();
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

    it('forwards slippage_bps in the order payload when the user fills it', async () => {
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'aapl' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '5' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '120' } });
        fireEvent.change(screen.getByPlaceholderText('如 5'), { target: { value: '8' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const sent = mockSubmitOrder.mock.calls[0][0];
        expect(sent).toMatchObject({
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 5,
            fill_price: 120,
            slippage_bps: 8,
        });
    });

    it('defaults slippage_bps to 0 when the user leaves the field blank', async () => {
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'aapl' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '1' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '100' } });
        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        expect(mockSubmitOrder.mock.calls[0][0].slippage_bps).toBe(0);
    });

    it('forwards stop_loss_pct (converted from percent to ratio) on a BUY order', async () => {
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'aapl' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '5' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '120' } });
        // Use the dedicated stop-loss testid; both slippage and stop-loss have placeholder "如 5"
        const stopLossInput = screen.getByTestId('paper-stop-loss-input');
        fireEvent.change(stopLossInput, { target: { value: '5' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const sent = mockSubmitOrder.mock.calls[0][0];
        // 5% → 0.05
        expect(sent.stop_loss_pct).toBeCloseTo(0.05);
    });

    it('renders stop_loss_price and the trigger-distance label on positions that have one', async () => {
        const positionWithStopLoss = {
            ...ACCOUNT_WITH_POSITION.positions[0],
            stop_loss_pct: 0.05,
            stop_loss_price: 142.5,
        };
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [positionWithStopLoss] },
        });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => {
            expect(screen.getByTestId('paper-position-stop-loss-AAPL')).toBeInTheDocument();
        });
        // The cell should show the formatted stop-loss price
        const cell = screen.getByTestId('paper-position-stop-loss-AAPL');
        expect(cell.textContent).toContain('$142.50');
        // And the distance label (165 quote / 142.5 stop → ~13.64% above)
        expect(cell.textContent).toContain('距触发');
    });

    it('auto-submits a SELL when a quote crosses below stop_loss_price', async () => {
        const positionWithStopLoss = {
            ...ACCOUNT_WITH_POSITION.positions[0],
            stop_loss_pct: 0.05,
            stop_loss_price: 200, // higher than the mocked quote (165)
        };
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [positionWithStopLoss] },
        });
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(mockSubmitOrder).toHaveBeenCalledTimes(1);
        });
        const autoSell = mockSubmitOrder.mock.calls[0][0];
        expect(autoSell).toMatchObject({
            symbol: 'AAPL',
            side: 'SELL',
            quantity: 10,
            note: 'stop_loss_triggered',
            slippage_bps: 10,
        });
    });

    it('forwards take_profit_pct (converted from percent to ratio) on a BUY order', async () => {
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'aapl' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '5' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '120' } });
        fireEvent.change(screen.getByTestId('paper-take-profit-input'), { target: { value: '15' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const sent = mockSubmitOrder.mock.calls[0][0];
        // 15% → 0.15
        expect(sent.take_profit_pct).toBeCloseTo(0.15);
    });

    it('renders take_profit_price and the trigger-distance label on positions that have one', async () => {
        const positionWithTakeProfit = {
            ...ACCOUNT_WITH_POSITION.positions[0],
            take_profit_pct: 0.15,
            take_profit_price: 172.5,
        };
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [positionWithTakeProfit] },
        });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => {
            expect(screen.getByTestId('paper-position-take-profit-AAPL')).toBeInTheDocument();
        });
        const cell = screen.getByTestId('paper-position-take-profit-AAPL');
        expect(cell.textContent).toContain('$172.50');
        expect(cell.textContent).toContain('距触发');
    });

    it('auto-submits a SELL when a quote crosses above take_profit_price', async () => {
        const positionWithTakeProfit = {
            ...ACCOUNT_WITH_POSITION.positions[0],
            take_profit_pct: 0.10,
            take_profit_price: 160, // lower than the mocked quote (165)
        };
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [positionWithTakeProfit] },
        });
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: ACCOUNT_WITH_POSITION } });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(mockSubmitOrder).toHaveBeenCalledTimes(1);
        });
        const autoSell = mockSubmitOrder.mock.calls[0][0];
        expect(autoSell).toMatchObject({
            symbol: 'AAPL',
            side: 'SELL',
            quantity: 10,
            note: 'take_profit_triggered',
            slippage_bps: 10,
        });
    });

    it('forwards order_type=LIMIT and limit_price when the limit order_type is selected', async () => {
        mockSubmitOrder.mockResolvedValue({
            success: true,
            data: { account: ACCOUNT_WITH_POSITION, order: { id: 'ord-pending-x' } },
        });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        // Click the LIMIT segment via Segmented (clicks on labelled radio)
        // Antd's Segmented renders a radio group internally — the simplest
        // accessible click is on the label "限价单".
        fireEvent.click(screen.getByText('限价单'));

        fireEvent.change(screen.getByPlaceholderText('如 AAPL'), { target: { value: 'msft' } });
        fireEvent.change(screen.getByPlaceholderText('如 10'), { target: { value: '5' } });
        fireEvent.change(screen.getByPlaceholderText('如 150.0'), { target: { value: '95' } });

        fireEvent.click(screen.getByRole('button', { name: '提交订单' }));

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const sent = mockSubmitOrder.mock.calls[0][0];
        expect(sent).toMatchObject({
            symbol: 'MSFT',
            side: 'BUY',
            quantity: 5,
            order_type: 'LIMIT',
            limit_price: 95,
            fill_price: 95,
        });
    });

    it('renders pending orders and the cancel button calls cancelPaperOrder', async () => {
        const accountWithPending = {
            ...ACCOUNT_WITH_POSITION,
            pending_orders: [
                {
                    id: 'ord-pending-abc',
                    symbol: 'GOOG',
                    side: 'BUY',
                    quantity: 3,
                    limit_price: 110,
                    submitted_at: '2026-05-05T08:00:00+00:00',
                    order_type: 'LIMIT',
                },
            ],
        };
        mockGetAccount.mockResolvedValue({ success: true, data: accountWithPending });
        mockCancelPaperOrder.mockResolvedValue({ success: true });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(screen.getByTestId('paper-cancel-pending-ord-pending-abc')).toBeInTheDocument();
        });
        // Pending order shows symbol + limit price
        expect(screen.getByText('GOOG')).toBeInTheDocument();
        expect(screen.getByText('$110.00')).toBeInTheDocument();

        // Trigger the Popconfirm flow
        fireEvent.click(screen.getByTestId('paper-cancel-pending-ord-pending-abc'));
        const overlay = document.querySelector('.ant-popover');
        expect(overlay).not.toBeNull();
        fireEvent.click(within(overlay).getByRole('button', { name: '取消挂单' }));

        await waitFor(() => expect(mockCancelPaperOrder).toHaveBeenCalledWith('ord-pending-abc'));
    });

    it('auto-fires the LIMIT trigger when a quote crosses the limit price', async () => {
        const accountWithPending = {
            ...ACCOUNT_WITH_POSITION,
            pending_orders: [
                {
                    id: 'ord-pending-trig',
                    symbol: 'AAPL',     // matches the mock quote (price=165)
                    side: 'SELL',
                    quantity: 10,
                    limit_price: 160,    // SELL triggers when last >= limit; 165 ≥ 160
                    submitted_at: '2026-05-05T08:00:00+00:00',
                    order_type: 'LIMIT',
                },
            ],
        };
        mockGetAccount.mockResolvedValue({ success: true, data: accountWithPending });
        mockSubmitOrder.mockResolvedValue({ success: true, data: { account: accountWithPending } });
        mockCancelPaperOrder.mockResolvedValue({ success: true });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => expect(mockSubmitOrder).toHaveBeenCalledTimes(1));
        const fired = mockSubmitOrder.mock.calls[0][0];
        expect(fired).toMatchObject({
            symbol: 'AAPL',
            side: 'SELL',
            quantity: 10,
            note: 'limit_triggered',
            fill_price: 160,
        });
        // Cancel chain should also fire to remove the pending order.
        await waitFor(() => expect(mockCancelPaperOrder).toHaveBeenCalledWith('ord-pending-trig'));
    });

    it('exports orders to CSV when the button is clicked', async () => {
        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        const exportBtn = screen.getByTestId('paper-export-orders-csv');
        expect(exportBtn).not.toBeDisabled(); // ORDERS_HISTORY has 1 order

        fireEvent.click(exportBtn);

        await waitFor(() => expect(mockExportToCSV).toHaveBeenCalledTimes(1));
        const args = mockExportToCSV.mock.calls[0];
        // 1st arg: rows (built via buildPaperOrderRows)
        expect(args[0]).toHaveLength(1);
        expect(args[0][0].symbol).toBe('AAPL');
        // 2nd arg: filename starts with paper_orders_
        expect(args[1]).toMatch(/^paper_orders_\d{8}_\d{4}$/);
        // 3rd arg: column definitions
        expect(args[2]).toEqual(expect.arrayContaining([
            expect.objectContaining({ key: 'symbol' }),
            expect.objectContaining({ key: 'effective_fill_price' }),
        ]));
    });

    it('disables the CSV export button when there are no orders', async () => {
        mockListOrders.mockResolvedValue({ success: true, data: { orders: [], limit: 50 } });
        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());
        expect(screen.getByTestId('paper-export-orders-csv')).toBeDisabled();
    });

    it('exports current positions to CSV when its button is clicked', async () => {
        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        const positionsBtn = screen.getByTestId('paper-export-positions-csv');
        expect(positionsBtn).not.toBeDisabled(); // 1 position present
        fireEvent.click(positionsBtn);

        await waitFor(() => expect(mockExportToCSV).toHaveBeenCalledTimes(1));
        const args = mockExportToCSV.mock.calls[0];
        // 1 row for AAPL position
        expect(args[0]).toHaveLength(1);
        expect(args[0][0].symbol).toBe('AAPL');
        // Filename starts with paper_positions_
        expect(args[1]).toMatch(/^paper_positions_\d{8}_\d{4}$/);
        // Column list includes the position-specific cols
        expect(args[2]).toEqual(expect.arrayContaining([
            expect.objectContaining({ key: 'avg_cost' }),
            expect.objectContaining({ key: 'stop_loss_price' }),
        ]));
    });

    it('disables the positions CSV button when there are no positions', async () => {
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [] },
        });
        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 0')).toBeInTheDocument());
        expect(screen.getByTestId('paper-export-positions-csv')).toBeDisabled();
    });

    it('labels auto-triggered orders in the 触发来源 column', async () => {
        const stopLossOrder = {
            id: 'ord-sl', symbol: 'AAPL', side: 'SELL', quantity: 10,
            fill_price: 95, effective_fill_price: 94.91, slippage_bps: 10,
            commission: 0, submitted_at: '2026-05-05T11:00:00+00:00',
            note: 'stop_loss_triggered',
        };
        const takeProfitOrder = {
            id: 'ord-tp', symbol: 'AAPL', side: 'SELL', quantity: 10,
            fill_price: 130, effective_fill_price: 129.87, slippage_bps: 10,
            commission: 0, submitted_at: '2026-05-05T12:00:00+00:00',
            note: 'take_profit_triggered',
        };
        const limitOrder = {
            id: 'ord-lim', symbol: 'AAPL', side: 'BUY', quantity: 5,
            fill_price: 95, effective_fill_price: 95, slippage_bps: 0,
            commission: 0, submitted_at: '2026-05-05T13:00:00+00:00',
            note: 'limit_triggered',
        };
        const manualOrder = {
            id: 'ord-man', symbol: 'AAPL', side: 'BUY', quantity: 1,
            fill_price: 100, effective_fill_price: 100, slippage_bps: 0,
            commission: 0, submitted_at: '2026-05-05T14:00:00+00:00',
            note: '',
        };
        mockListOrders.mockResolvedValue({
            success: true,
            data: { orders: [stopLossOrder, takeProfitOrder, limitOrder, manualOrder], limit: 50 },
        });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(screen.getByTestId('paper-order-source-ord-sl')).toBeInTheDocument();
        });
        expect(screen.getByTestId('paper-order-source-ord-sl').textContent).toBe('止损自动');
        expect(screen.getByTestId('paper-order-source-ord-tp').textContent).toBe('止盈自动');
        expect(screen.getByTestId('paper-order-source-ord-lim').textContent).toBe('限价触发');
        // Manual orders show "手动" plain text, no tag testid
        expect(screen.queryByTestId('paper-order-source-ord-man')).not.toBeInTheDocument();
        expect(screen.getByText('手动')).toBeInTheDocument();
    });

    it('shows effective_fill_price and a slippage tag in the order history', async () => {
        const orderWithSlippage = {
            id: 'ord-slip',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 10,
            fill_price: 100,
            effective_fill_price: 100.05, // 5 bps
            slippage_bps: 5,
            commission: 0,
            submitted_at: '2026-05-05T10:00:00+00:00',
            note: '',
        };
        mockListOrders.mockResolvedValue({
            success: true,
            data: { orders: [orderWithSlippage], limit: 50 },
        });

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(screen.getByTestId('paper-order-effective-ord-slip')).toBeInTheDocument();
        });
        const cell = screen.getByTestId('paper-order-effective-ord-slip');
        // Effective price is shown
        expect(cell.textContent).toContain('$100.05');
        // Slippage tag is visible
        expect(cell.textContent).toContain('5bps');
    });

    it('falls back to fill_price for orders without effective_fill_price (pre-C2)', async () => {
        const legacyOrder = {
            id: 'ord-legacy',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 5,
            fill_price: 150,
            // No effective_fill_price / slippage_bps — older order shape
            commission: 0,
            submitted_at: '2026-05-01T10:00:00+00:00',
            note: '',
        };
        mockListOrders.mockResolvedValue({
            success: true,
            data: { orders: [legacyOrder], limit: 50 },
        });

        renderWithApp(<PaperTradingPanel />);

        // ACCOUNT_WITH_POSITION's positions table also renders $150.00
        // (avg_cost), so wait on the legacy order's specific marker:
        // its absence of the effective-price testid (we don't render the
        // tag wrapper unless slippage > 0).
        await waitFor(() => expect(mockListOrders).toHaveBeenCalled());
        // Wait for the orders table to render the legacy order. The
        // orders table column displays $150.00 plain text, so getAllByText
        // is the right query.
        const cells = await screen.findAllByText('$150.00');
        expect(cells.length).toBeGreaterThan(0);
        expect(screen.queryByTestId('paper-order-effective-ord-legacy')).not.toBeInTheDocument();
    });

    it('archives current positions to the research journal on demand', async () => {
        mockCreateJournalEntry.mockResolvedValue({ success: true });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 1')).toBeInTheDocument());

        const btn = screen.getByTestId('paper-snapshot-positions');
        expect(btn).not.toBeDisabled();
        fireEvent.click(btn);

        await waitFor(() => expect(mockCreateJournalEntry).toHaveBeenCalledTimes(1));
        const archived = mockCreateJournalEntry.mock.calls[0][0];
        expect(archived).toMatchObject({
            id: 'paper-position:AAPL',
            type: 'trade_plan',
            symbol: 'AAPL',
        });
        expect(archived.title).toContain('AAPL 纸面持仓');
    });

    it('disables the archive button when there are no positions', async () => {
        mockGetAccount.mockResolvedValue({
            success: true,
            data: { ...ACCOUNT_WITH_POSITION, positions: [], orders_count: 0 },
        });
        mockListOrders.mockResolvedValue({ success: true, data: { orders: [], limit: 50 } });

        renderWithApp(<PaperTradingPanel />);
        await waitFor(() => expect(screen.getByText('持仓 0')).toBeInTheDocument());
        expect(screen.getByTestId('paper-snapshot-positions')).toBeDisabled();
    });

    it('consumes a backtest prefill from sessionStorage and prefills the order form', async () => {
        // Stage the prefill before mounting (mirrors the flow App.js drives)
        window.sessionStorage.setItem(
            'paper-trading-prefill',
            JSON.stringify({
                symbol: 'MSFT',
                side: 'SELL',
                quantity: 7,
                sourceLabel: '由 BollingerBands · 回测带入',
                writtenAt: Date.now(),
            }),
        );

        renderWithApp(<PaperTradingPanel />);

        await waitFor(() => {
            expect(screen.getByTestId('paper-prefill-tag')).toBeInTheDocument();
        });
        expect(screen.getByText(/由 BollingerBands · 回测带入/)).toBeInTheDocument();
        // The form's symbol input should now hold the prefilled symbol
        expect(screen.getByPlaceholderText('如 AAPL')).toHaveValue('MSFT');
        // sessionStorage entry must be drained after consumption so a refresh
        // doesn't re-apply a stale prefill
        expect(window.sessionStorage.getItem('paper-trading-prefill')).toBeNull();
    });
});
