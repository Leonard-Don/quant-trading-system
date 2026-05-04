/**
 * String → string formatters and small score → tier/tone resolvers used
 * by the cross-market backtest panel. Pure helpers, easy to unit-test.
 */

import { CONSTRUCTION_MODE_LABELS } from './crossMarketDefaults';

export const formatConstructionMode = (value) =>
    CONSTRUCTION_MODE_LABELS[value] || value || '未设置';

export const buildDisplayTier = (score) => {
    if (score >= 2.6) return '优先部署';
    if (score >= 1.4) return '重点跟踪';
    return '候选模板';
};

export const buildDisplayTone = (score) => {
    if (score >= 2.6) return 'volcano';
    if (score >= 1.4) return 'gold';
    return 'blue';
};

export const formatTradeAction = (value) => {
    const action = String(value || '').toUpperCase();
    if (!action) return '-';
    return action
        .replace('OPEN', '开仓')
        .replace('CLOSE', '平仓')
        .replace('LONG', '多头')
        .replace('SHORT', '空头')
        .replaceAll('_', ' ');
};

const EXECUTION_CHANNEL_LABELS = {
    cash_equity: '现货股票',
    futures: '期货通道',
};

export const formatExecutionChannel = (value = '') =>
    EXECUTION_CHANNEL_LABELS[value] || value || '-';

const VENUE_LABELS = {
    US_EQUITY: '美股主板',
    US_ETF: '美股 ETF',
    COMEX_CME: 'CME / COMEX',
};

export const formatVenue = (value = '') =>
    VENUE_LABELS[value] || value || '-';
