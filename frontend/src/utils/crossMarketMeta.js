/**
 * Level / band → display meta resolvers for the cross-market backtest
 * panel. Each helper takes a string label and returns
 * `{ color, label }` (or for selection quality, `{ type, title }`).
 *
 * Resolvers fall back to a sensible "未评估" / "-" label when the
 * incoming value isn't in their mapping table.
 */

const fallback = (level, label) => ({ color: 'default', label: level || label });

const buildResolver = (mapping, fallbackLabel = '-') => (level = '') =>
    mapping[level] || fallback(level, fallbackLabel);

export const getConcentrationMeta = buildResolver(
    {
        high: { color: 'red', label: '高集中' },
        moderate: { color: 'orange', label: '中等集中' },
        balanced: { color: 'green', label: '相对均衡' },
    },
    '未评估',
);

export const getCapacityMeta = buildResolver({
    light: { color: 'green', label: '轻量' },
    moderate: { color: 'orange', label: '中等' },
    heavy: { color: 'red', label: '偏重' },
});

export const getLiquidityMeta = buildResolver({
    comfortable: { color: 'green', label: '流动性舒适' },
    watch: { color: 'orange', label: '需要留意' },
    stretched: { color: 'red', label: '流动性偏紧' },
    unknown: { color: 'default', label: '流动性未知' },
});

export const getMarginMeta = buildResolver({
    manageable: { color: 'green', label: '保证金可控' },
    elevated: { color: 'orange', label: '保证金偏高' },
    aggressive: { color: 'red', label: '保证金激进' },
});

export const getBetaMeta = buildResolver({
    balanced: { color: 'green', label: 'Beta 较中性' },
    watch: { color: 'orange', label: 'Beta 需留意' },
    stretched: { color: 'red', label: 'Beta 偏离较大' },
    unknown: { color: 'default', label: 'Beta 未知' },
});

export const getCointegrationMeta = buildResolver({
    strong: { color: 'green', label: '协整较强' },
    watch: { color: 'orange', label: '协整待确认' },
    weak: { color: 'red', label: '协整偏弱' },
    unknown: { color: 'default', label: '协整未知' },
});

export const getCalendarMeta = buildResolver({
    aligned: { color: 'green', label: '日历较对齐' },
    watch: { color: 'orange', label: '日历有错位' },
    stretched: { color: 'red', label: '日历错位明显' },
});

const SELECTION_QUALITY_META = {
    original: { type: 'info', title: '本次回测沿用原始推荐强度运行' },
    softened: { type: 'warning', title: '本次回测生成复核型结果：基于收缩后的推荐强度运行' },
    auto_downgraded: { type: 'warning', title: '本次回测生成复核型结果：基于自动降级后的推荐强度运行' },
};

export const getSelectionQualityMeta = (label = '') =>
    SELECTION_QUALITY_META[label] || SELECTION_QUALITY_META.original;
