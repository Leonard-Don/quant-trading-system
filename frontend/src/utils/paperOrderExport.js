/**
 * Shape and column definitions for exporting paper-trading orders to CSV.
 *
 * Pure helpers — no React, no DOM. The actual file download is delegated
 * to utils/export.js so the same CSV machinery (BOM + escaping) is shared
 * across the project.
 */

export const PAPER_ORDER_CSV_COLUMNS = [
    { key: 'submitted_at', title: '提交时间' },
    { key: 'order_type', title: '类型' },
    { key: 'symbol', title: '标的' },
    { key: 'side', title: '方向' },
    { key: 'quantity', title: '数量' },
    { key: 'fill_price', title: '报价价' },
    { key: 'effective_fill_price', title: '实际成交价' },
    { key: 'slippage_bps', title: '滑点(bps)' },
    { key: 'commission', title: '手续费' },
    { key: 'note', title: '备注' },
];

const safeNumber = (value) => {
    if (value == null) return null;
    const num = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(num) ? num : null;
};

/**
 * Map an order record to the row shape exportToCSV expects.
 * - order_type defaults to MARKET (older orders predate C5)
 * - effective_fill_price falls back to fill_price (older orders predate C2)
 * - empty strings are intentional rather than null so the CSV cell is blank
 *   rather than the literal "null"
 */
export const buildPaperOrderRows = (orders = []) => {
    const list = Array.isArray(orders) ? orders : [];
    return list.map((order) => {
        const fillPrice = safeNumber(order?.fill_price);
        const effectiveCandidate = order?.effective_fill_price ?? order?.fill_price;
        const effectivePrice = safeNumber(effectiveCandidate);
        const slippage = safeNumber(order?.slippage_bps);
        const commission = safeNumber(order?.commission);
        return {
            submitted_at: order?.submitted_at || '',
            order_type: order?.order_type || 'MARKET',
            symbol: order?.symbol || '',
            side: order?.side || '',
            quantity: safeNumber(order?.quantity) ?? '',
            fill_price: fillPrice ?? '',
            effective_fill_price: effectivePrice ?? '',
            slippage_bps: slippage ?? 0,
            commission: commission ?? 0,
            note: order?.note || '',
        };
    });
};

const pad2 = (value) => String(value).padStart(2, '0');

/**
 * Filename helper: paper_orders_YYYYMMDD_HHmm.csv. Stable for tests via
 * an injected `now` Date.
 */
export const buildPaperOrderCsvFilename = (now = new Date()) => {
    const year = now.getFullYear();
    const month = pad2(now.getMonth() + 1);
    const day = pad2(now.getDate());
    const hour = pad2(now.getHours());
    const minute = pad2(now.getMinutes());
    return `paper_orders_${year}${month}${day}_${hour}${minute}`;
};

// ---------------------------------------------------------------------------
// Positions export
// ---------------------------------------------------------------------------

export const PAPER_POSITION_CSV_COLUMNS = [
    { key: 'symbol', title: '标的' },
    { key: 'quantity', title: '数量' },
    { key: 'avg_cost', title: '均价' },
    { key: 'last_price', title: '现价' },
    { key: 'market_value', title: '市值' },
    { key: 'unrealized_pnl', title: '浮动盈亏' },
    { key: 'stop_loss_price', title: '止损价' },
    { key: 'take_profit_price', title: '止盈价' },
    { key: 'opened_at', title: '开仓时间' },
    { key: 'updated_at', title: '更新时间' },
];

/**
 * Map a position list (the same enriched shape PaperTradingPanel renders
 * in the positions table) into CSV rows. Defensive against missing
 * mark-to-market fields — last_price / market_value / unrealized_pnl
 * are blank when the realtime quote hasn't arrived yet.
 */
export const buildPaperPositionRows = (positions = []) => {
    const list = Array.isArray(positions) ? positions : [];
    return list.map((position) => {
        const quantity = safeNumber(position?.quantity);
        const avgCost = safeNumber(position?.avg_cost);
        const lastPrice = safeNumber(position?.last_price);
        const marketValue = safeNumber(position?.market_value);
        const unrealized = safeNumber(position?.unrealized_pnl);
        const stopLoss = safeNumber(position?.stop_loss_price);
        const takeProfit = safeNumber(position?.take_profit_price);
        return {
            symbol: position?.symbol || '',
            quantity: quantity ?? '',
            avg_cost: avgCost ?? '',
            last_price: lastPrice ?? '',
            market_value: marketValue ?? '',
            unrealized_pnl: unrealized ?? '',
            stop_loss_price: stopLoss ?? '',
            take_profit_price: takeProfit ?? '',
            opened_at: position?.opened_at || '',
            updated_at: position?.updated_at || '',
        };
    });
};

export const buildPaperPositionCsvFilename = (now = new Date()) => {
    const year = now.getFullYear();
    const month = pad2(now.getMonth() + 1);
    const day = pad2(now.getDate());
    const hour = pad2(now.getHours());
    const minute = pad2(now.getMinutes());
    return `paper_positions_${year}${month}${day}_${hour}${minute}`;
};
