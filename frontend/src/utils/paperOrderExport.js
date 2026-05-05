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
