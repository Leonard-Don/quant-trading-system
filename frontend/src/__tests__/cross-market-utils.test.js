import {
    ASSET_CLASS_LABELS,
    ASSET_CLASS_OPTIONS,
    CONSTRUCTION_MODE_LABELS,
    DEFAULT_CONSTRAINTS,
    DEFAULT_PARAMETERS,
    DEFAULT_QUALITY,
    createAsset,
    normalizeAssets,
} from '../utils/crossMarketDefaults';
import {
    buildDisplayTier,
    buildDisplayTone,
    formatConstructionMode,
    formatExecutionChannel,
    formatTradeAction,
    formatVenue,
} from '../utils/crossMarketFormatters';
import {
    getBetaMeta,
    getCalendarMeta,
    getCapacityMeta,
    getCointegrationMeta,
    getConcentrationMeta,
    getLiquidityMeta,
    getMarginMeta,
    getSelectionQualityMeta,
} from '../utils/crossMarketMeta';

describe('crossMarketDefaults', () => {
    it('asset class labels are derived from the option list', () => {
        expect(ASSET_CLASS_OPTIONS.length).toBe(3);
        ASSET_CLASS_OPTIONS.forEach((option) => {
            expect(ASSET_CLASS_LABELS[option.value]).toBe(option.label);
        });
    });

    it('default parameter / quality / constraint shapes are stable', () => {
        expect(DEFAULT_PARAMETERS).toMatchObject({
            lookback: 20,
            entry_threshold: 1.5,
            exit_threshold: 0.5,
        });
        expect(DEFAULT_QUALITY).toMatchObject({ construction_mode: 'equal_weight' });
        expect(DEFAULT_CONSTRAINTS).toMatchObject({
            max_single_weight: null,
            min_single_weight: null,
        });
        expect(CONSTRUCTION_MODE_LABELS.equal_weight).toBe('等权配置');
        expect(CONSTRUCTION_MODE_LABELS.ols_hedge).toBe('滚动 OLS 对冲');
    });

    it('createAsset produces a side/index keyed seed', () => {
        const asset = createAsset('long', 0);
        expect(asset.side).toBe('long');
        expect(asset.symbol).toBe('');
        expect(asset.asset_class).toBe('ETF');
        expect(asset.weight).toBeNull();
        expect(asset.key.startsWith('long-0-')).toBe(true);
    });

    it('normalizeAssets filters by side and uppercases symbols', () => {
        const input = [
            { side: 'long', symbol: ' aapl ', asset_class: 'US_STOCK' },
            { side: 'short', symbol: 'msft', asset_class: 'US_STOCK' },
            { side: 'long', symbol: 'tsla', asset_class: 'US_STOCK' },
        ];
        const result = normalizeAssets(input, 'long');
        expect(result).toHaveLength(2);
        expect(result.map((a) => a.symbol)).toEqual(['AAPL', 'TSLA']);
    });
});

describe('crossMarketFormatters', () => {
    it('formatConstructionMode resolves known modes and falls back', () => {
        expect(formatConstructionMode('equal_weight')).toBe('等权配置');
        expect(formatConstructionMode('ols_hedge')).toBe('滚动 OLS 对冲');
        expect(formatConstructionMode('unknown_mode')).toBe('unknown_mode');
        expect(formatConstructionMode(undefined)).toBe('未设置');
    });

    it('buildDisplayTier classifies score bands', () => {
        expect(buildDisplayTier(3.0)).toBe('优先部署');
        expect(buildDisplayTier(2.6)).toBe('优先部署');
        expect(buildDisplayTier(2.0)).toBe('重点跟踪');
        expect(buildDisplayTier(1.4)).toBe('重点跟踪');
        expect(buildDisplayTier(0.8)).toBe('候选模板');
    });

    it('buildDisplayTone matches buildDisplayTier bands', () => {
        expect(buildDisplayTone(3.0)).toBe('volcano');
        expect(buildDisplayTone(2.0)).toBe('gold');
        expect(buildDisplayTone(0.8)).toBe('blue');
    });

    it('formatTradeAction translates action verbs', () => {
        expect(formatTradeAction('open_long')).toBe('开仓 多头');
        expect(formatTradeAction('CLOSE_SHORT')).toBe('平仓 空头');
        expect(formatTradeAction('')).toBe('-');
        expect(formatTradeAction(null)).toBe('-');
        // Unmapped tokens pass through as upper-case spaced strings
        expect(formatTradeAction('rebalance')).toBe('REBALANCE');
    });

    it('formatExecutionChannel + formatVenue resolve known codes', () => {
        expect(formatExecutionChannel('cash_equity')).toBe('现货股票');
        expect(formatExecutionChannel('futures')).toBe('期货通道');
        expect(formatExecutionChannel('rfq')).toBe('rfq');
        expect(formatExecutionChannel()).toBe('-');

        expect(formatVenue('US_EQUITY')).toBe('美股主板');
        expect(formatVenue('US_ETF')).toBe('美股 ETF');
        expect(formatVenue('COMEX_CME')).toBe('CME / COMEX');
        expect(formatVenue('OTHER')).toBe('OTHER');
        expect(formatVenue()).toBe('-');
    });
});

describe('crossMarketMeta resolvers', () => {
    it.each([
        [getConcentrationMeta, 'high', 'red'],
        [getConcentrationMeta, 'balanced', 'green'],
        [getCapacityMeta, 'light', 'green'],
        [getCapacityMeta, 'heavy', 'red'],
        [getLiquidityMeta, 'comfortable', 'green'],
        [getLiquidityMeta, 'stretched', 'red'],
        [getMarginMeta, 'manageable', 'green'],
        [getBetaMeta, 'balanced', 'green'],
        [getCointegrationMeta, 'strong', 'green'],
        [getCalendarMeta, 'aligned', 'green'],
    ])('%p → %p maps to color %p', (resolver, level, expectedColor) => {
        const meta = resolver(level);
        expect(meta.color).toBe(expectedColor);
        expect(typeof meta.label).toBe('string');
    });

    it('falls back gracefully on unknown levels', () => {
        expect(getConcentrationMeta('')).toEqual({ color: 'default', label: '未评估' });
        expect(getCapacityMeta('')).toEqual({ color: 'default', label: '-' });
        expect(getCapacityMeta('foreign')).toEqual({ color: 'default', label: 'foreign' });
    });

    it('getSelectionQualityMeta maps known labels and defaults to original', () => {
        expect(getSelectionQualityMeta('softened').type).toBe('warning');
        expect(getSelectionQualityMeta('auto_downgraded').type).toBe('warning');
        expect(getSelectionQualityMeta('original').type).toBe('info');
        expect(getSelectionQualityMeta('unknown_label').type).toBe('info');
    });
});
