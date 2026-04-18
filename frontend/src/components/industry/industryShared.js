export const INDUSTRY_ALERT_RECENCY_OPTIONS = [
    { value: '15', label: '近15分钟新增' },
    { value: '30', label: '近30分钟新增' },
    { value: 'session', label: '本次会话' },
];

export const INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY = 'industry_alert_subscription_v1';
export const INDUSTRY_ALERT_HISTORY_STORAGE_KEY = 'industry_alert_history_v1';
export const INDUSTRY_ALERT_BADGE_STORAGE_KEY = 'industry_alert_badge_count_v1';
export const INDUSTRY_ALERT_BADGE_EVENT = 'industry-alert-badge-update';
export const INDUSTRY_ALERT_HISTORY_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
export const INDUSTRY_ALERT_KIND_OPTIONS = [
    { value: 'capital', label: '资金' },
    { value: 'risk', label: '风险' },
    { value: 'rotation', label: '轮动' },
];
export const INDUSTRY_ALERT_DESKTOP_STORAGE_KEY = 'industry_alert_desktop_notifications_v1';
export const INDUSTRY_WATCHLIST_STORAGE_KEY = 'industry_watchlist_v1';
export const INDUSTRY_SAVED_VIEWS_STORAGE_KEY = 'industry_saved_views_v1';
export const DEFAULT_INDUSTRY_ALERT_THRESHOLDS = {
    resonance_score: 80,
    resonance_change_pct: 2,
    resonance_money_flow_yi: 0,
    capital_inflow_yi: 8,
    capital_inflow_change_pct: 0.5,
    risk_release_outflow_yi: 8,
    risk_release_change_pct: -1,
    high_volatility_threshold: 4.5,
    high_volatility_change_pct: 2,
    rotation_turnover_threshold: 3.5,
    rotation_change_pct: 1,
};

export const scheduleDeferredTask = (task, delayMs = 1600) => {
    if (typeof window === 'undefined') {
        task();
        return () => {};
    }
    const timeoutId = window.setTimeout(task, delayMs);
    return () => window.clearTimeout(timeoutId);
};

export const getMarketCapBadgeMeta = (source) => {
    const normalized = String(source || 'unknown');
    if (normalized.startsWith('snapshot_')) {
        return { label: '快照', color: 'blue', filter: 'snapshot' };
    }
    if (normalized === 'sina_proxy_stock_sum') {
        return { label: '代理', color: 'cyan', filter: 'proxy' };
    }
    if (normalized === 'unknown' || normalized.startsWith('estimated') || normalized === 'constant_fallback') {
        return { label: '估算', color: 'gold', filter: 'estimated' };
    }
    return { label: '实时', color: 'green', filter: 'live' };
};

export const normalizeIndustryAlertThresholds = (thresholds = {}) => ({
    ...DEFAULT_INDUSTRY_ALERT_THRESHOLDS,
    ...(thresholds || {}),
});

export const formatIndustryAlertMoneyFlow = (value) => {
    const numericValue = Number(value || 0);
    if (!numericValue) return '0';
    const yi = numericValue / 1e8;
    if (Math.abs(yi) >= 1) return `${yi >= 0 ? '+' : ''}${yi.toFixed(1)}亿`;
    const wan = numericValue / 1e4;
    return `${wan >= 0 ? '+' : ''}${wan.toFixed(0)}万`;
};

export const getIndustryScoreTone = (score) => {
    const numericScore = Number(score || 0);
    if (numericScore >= 70) return '#52c41a';
    if (numericScore >= 50) return '#faad14';
    return '#ff4d4f';
};

export const formatIndustryAlertSeenLabel = (timestamp) => {
    if (!timestamp) return '刚刚出现';
    const diffMs = Math.max(0, Date.now() - timestamp);
    const diffMinutes = Math.floor(diffMs / 60000);
    if (diffMinutes < 1) return '刚刚出现';
    if (diffMinutes < 60) return `${diffMinutes} 分钟前出现`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} 小时前出现`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} 天前出现`;
};

export const clampNumeric = (value, min = 0, max = 100) => {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return min;
    }
    return Math.min(max, Math.max(min, numericValue));
};

export const activateOnEnterOrSpace = (event, callback) => {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        callback();
    }
};

export const getAlertSubscriptionBucket = (kind) => {
    if (['capital_inflow', 'resonance'].includes(kind)) return 'capital';
    if (kind === 'risk_release') return 'risk';
    if (['rotation_heatup', 'high_volatility'].includes(kind)) return 'rotation';
    return 'capital';
};

export const pruneIndustryAlertHistory = (history = {}) => {
    const now = Date.now();
    return Object.entries(history || {}).reduce((acc, [key, item]) => {
        const lastSeenAt = Number(item?.lastSeenAt || item?.firstSeenAt || 0);
        if (!lastSeenAt || Number.isNaN(lastSeenAt)) {
            return acc;
        }
        if ((now - lastSeenAt) > INDUSTRY_ALERT_HISTORY_RETENTION_MS) {
            return acc;
        }
        acc[key] = {
            ...item,
            firstSeenAt: Number(item?.firstSeenAt || lastSeenAt),
            lastSeenAt,
            hitCount: Math.max(1, Number(item?.hitCount || 1)),
        };
        return acc;
    }, {});
};

export const getIndustryAlertSeverity = (alert) => {
    const priority = Number(alert?.priority || 0);
    const kind = String(alert?.kind || '');
    if (priority >= 118 || kind === 'resonance') {
        return { level: 'high', label: '高', color: 'red' };
    }
    if (priority >= 96 || kind === 'risk_release' || kind === 'capital_inflow') {
        return { level: 'medium', label: '中', color: 'orange' };
    }
    return { level: 'low', label: '低', color: 'blue' };
};

export const buildSavedIndustryViewLabel = (view) => {
    const tabMap = {
        heatmap: '热力图',
        ranking: '排行榜',
        clusters: '聚类',
        rotation: '轮动',
    };
    const tabLabel = tabMap[view?.state?.activeTab] || '行业热度';
    return `${view?.name || '未命名视图'} · ${tabLabel}`;
};

export const buildIndustryActionPosture = ({
    alerts = [],
    newCount = 0,
    focusIndustrySuggestions = [],
    watchlistIndustries = [],
    selectedIndustry = '',
} = {}) => {
    const highSeverityCount = (alerts || []).filter((item) => item?.severity?.level === 'high').length;
    const mediumSeverityCount = (alerts || []).filter((item) => item?.severity?.level === 'medium').length;
    const topAlert = (alerts || [])[0] || null;

    if (highSeverityCount > 0 || newCount >= 2) {
        return {
            level: 'warning',
            label: 'priority_review',
            title: '先处理新增高优先级行业提醒',
            posture: '优先处理高优先级提醒',
            actionHint: topAlert
                ? `建议先从 ${topAlert.industry_name} 开始，确认资金、风险或轮动提醒是否需要升级到行业详情或对比视图。`
                : '建议先从新增高优先级提醒入手，快速确认是否需要升级到行业详情或对比视图。',
            reason: `当前有 ${highSeverityCount} 条高严重度提醒，新增 ${newCount} 条，适合先看提醒而不是只扫热力图。`,
        };
    }

    if (mediumSeverityCount > 0 || watchlistIndustries.length > 0) {
        return {
            level: 'info',
            label: 'watchlist_follow',
            title: '继续跟进观察列表与中等级别提醒',
            posture: '先跟进观察名单',
            actionHint: selectedIndustry
                ? `可以先围绕 ${selectedIndustry} 补看行业详情、龙头股和研究焦点。`
                : '可以优先从观察列表和中等级别提醒里挑 1-2 个行业继续跟进。',
            reason: `当前有 ${mediumSeverityCount} 条中等级别提醒，观察列表 ${watchlistIndustries.length} 个行业。`,
        };
    }

    const seedIndustry = (focusIndustrySuggestions || [])[0] || '';
    return {
        level: 'default',
        label: 'observe',
        title: '当前更适合扩展观察名单',
        posture: '继续观察',
        actionHint: seedIndustry
            ? `可以先把 ${seedIndustry} 作为观察候选，等待下一次资金或轮动异动再升级处理。`
            : '当前没有明显需要立刻升级处理的行业提醒，更适合继续观察热力图与轮动变化。',
        reason: `当前提醒强度较温和，适合先维持观察节奏而不是立即切到高强度研究模式。`,
    };
};
