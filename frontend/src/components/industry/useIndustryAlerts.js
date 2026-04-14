import { useEffect, useMemo, useState } from 'react';
import { publishQuantAlertEvent } from '../../services/api';

import {
    DEFAULT_INDUSTRY_ALERT_THRESHOLDS,
    INDUSTRY_ALERT_BADGE_EVENT,
    INDUSTRY_ALERT_BADGE_STORAGE_KEY,
    buildIndustryActionPosture,
    formatIndustryAlertMoneyFlow,
    formatIndustryAlertSeenLabel,
    getAlertSubscriptionBucket,
    getIndustryAlertSeverity,
    pruneIndustryAlertHistory,
} from './industryShared';

export default function useIndustryAlerts({
    heatmapIndustries,
    hotIndustries,
    heatmapSummary,
    industryAlertThresholds,
    industryAlertHistory,
    setIndustryAlertHistory,
    industryAlertSubscription,
    desktopAlertNotifications,
    watchlistIndustries,
    selectedIndustry,
}) {
    const [industryAlertRule, setIndustryAlertRule] = useState('all');
    const [industryAlertRecency, setIndustryAlertRecency] = useState('15');

    const focusIndustrySuggestions = useMemo(() => {
        const merged = [
            ...(heatmapSummary?.topInflow || []),
            ...(heatmapSummary?.topTurnover || []),
            ...(heatmapSummary?.topOutflow || []),
        ];
        const seen = new Set();
        return merged
            .map((item) => item?.name)
            .filter((name) => {
                if (!name || seen.has(name)) return false;
                seen.add(name);
                return true;
            })
            .slice(0, 5);
    }, [heatmapSummary]);

    const industryAlertSnapshots = useMemo(() => {
        const snapshots = new Map();

        (heatmapIndustries || []).forEach((item) => {
            if (!item?.name) return;
            snapshots.set(item.name, {
                industry_name: item.name,
                score: item.total_score ?? null,
                change_pct: item.value ?? null,
                money_flow: item.moneyFlow ?? null,
                industryVolatility: item.industryVolatility ?? null,
                turnoverRate: item.turnoverRate ?? null,
                stock_count: item.stockCount ?? null,
                marketCapSource: item.marketCapSource ?? 'unknown',
            });
        });

        (hotIndustries || []).forEach((item) => {
            if (!item?.industry_name) return;
            const current = snapshots.get(item.industry_name) || { industry_name: item.industry_name };
            snapshots.set(item.industry_name, {
                ...current,
                score: item.score ?? current.score ?? null,
                change_pct: item.change_pct ?? current.change_pct ?? null,
                money_flow: item.money_flow ?? current.money_flow ?? null,
                industryVolatility: item.industryVolatility ?? current.industryVolatility ?? null,
                stock_count: item.stock_count ?? current.stock_count ?? null,
                marketCapSource: item.marketCapSource ?? current.marketCapSource ?? 'unknown',
            });
        });

        return Array.from(snapshots.values());
    }, [heatmapIndustries, hotIndustries]);

    const rawIndustryAlerts = useMemo(() => {
        const bestByIndustry = new Map();
        const upsertAlert = (alert) => {
            if (!alert?.industry_name) return;
            const existing = bestByIndustry.get(alert.industry_name);
            if (!existing || alert.priority > existing.priority) {
                bestByIndustry.set(alert.industry_name, alert);
            }
        };

        industryAlertSnapshots.forEach((item) => {
            const name = item.industry_name;
            const score = Number(item.score || 0);
            const change = Number(item.change_pct || 0);
            const moneyFlow = Number(item.money_flow || 0);
            const volatility = Number(item.industryVolatility || 0);
            const turnoverRate = Number(item.turnoverRate || 0);
            const resonanceScore = Number(industryAlertThresholds.resonance_score || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.resonance_score);
            const resonanceChange = Number(industryAlertThresholds.resonance_change_pct || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.resonance_change_pct);
            const resonanceFlow = Number(industryAlertThresholds.resonance_money_flow_yi || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.resonance_money_flow_yi) * 1e8;
            const capitalInflow = Number(industryAlertThresholds.capital_inflow_yi || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.capital_inflow_yi) * 1e8;
            const capitalChange = Number(industryAlertThresholds.capital_inflow_change_pct || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.capital_inflow_change_pct);
            const riskOutflow = Number(industryAlertThresholds.risk_release_outflow_yi || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.risk_release_outflow_yi) * 1e8;
            const riskChange = Number(industryAlertThresholds.risk_release_change_pct || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.risk_release_change_pct);
            const highVolatilityThreshold = Number(industryAlertThresholds.high_volatility_threshold || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.high_volatility_threshold);
            const highVolatilityChange = Number(industryAlertThresholds.high_volatility_change_pct || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.high_volatility_change_pct);
            const rotationTurnover = Number(industryAlertThresholds.rotation_turnover_threshold || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.rotation_turnover_threshold);
            const rotationChange = Number(industryAlertThresholds.rotation_change_pct || DEFAULT_INDUSTRY_ALERT_THRESHOLDS.rotation_change_pct);

            if (score >= resonanceScore && change >= resonanceChange && moneyFlow >= resonanceFlow) {
                upsertAlert({
                    industry_name: name,
                    kind: 'resonance',
                    title: '强势共振',
                    color: 'red',
                    accent: '#ff7875',
                    summary: `综合得分 ${score.toFixed(1)}，涨幅 ${change.toFixed(2)}%，资金 ${formatIndustryAlertMoneyFlow(moneyFlow)}。`,
                    reason: '热度、价格和资金都在同向增强，适合先看龙头承接。',
                    priority: 120 + score + change + Math.min(moneyFlow / 1e8, 20),
                });
                return;
            }

            if (moneyFlow >= capitalInflow && change >= capitalChange) {
                upsertAlert({
                    industry_name: name,
                    kind: 'capital_inflow',
                    title: '资金突入',
                    color: 'volcano',
                    accent: '#ff9c6e',
                    summary: `主力净流入 ${formatIndustryAlertMoneyFlow(moneyFlow)}，价格同步转强。`,
                    reason: '短线关注度在升温，适合顺着热点扩散继续看。',
                    priority: 100 + Math.min(moneyFlow / 1e8, 24) + change,
                });
            }

            if (moneyFlow <= -riskOutflow && change <= -riskChange) {
                upsertAlert({
                    industry_name: name,
                    kind: 'risk_release',
                    title: '风险释放',
                    color: 'green',
                    accent: '#95de64',
                    summary: `主力净流出 ${formatIndustryAlertMoneyFlow(moneyFlow)}，价格承压 ${Math.abs(change).toFixed(2)}%。`,
                    reason: '更适合先看承接与止跌信号，而不是直接追击。',
                    priority: 98 + Math.min(Math.abs(moneyFlow) / 1e8, 24) + Math.abs(change),
                });
            }

            if (volatility >= highVolatilityThreshold && Math.abs(change) >= highVolatilityChange) {
                upsertAlert({
                    industry_name: name,
                    kind: 'high_volatility',
                    title: '高波动博弈',
                    color: 'gold',
                    accent: '#ffd666',
                    summary: `波动率 ${volatility.toFixed(1)}%，价格振幅已经明显放大。`,
                    reason: '更适合盯节奏和分化，不适合只看静态排行。',
                    priority: 92 + volatility + Math.abs(change),
                });
            }

            if (turnoverRate >= rotationTurnover && Math.abs(change) >= rotationChange) {
                upsertAlert({
                    industry_name: name,
                    kind: 'rotation_heatup',
                    title: '轮动升温',
                    color: 'blue',
                    accent: '#69c0ff',
                    summary: `换手率 ${turnoverRate.toFixed(1)}%，板块活跃度在抬升。`,
                    reason: '适合直接加入轮动对比，看是不是新一轮资金切换。',
                    priority: 88 + turnoverRate + Math.abs(change),
                });
            }
        });

        return Array.from(bestByIndustry.values())
            .sort((a, b) => b.priority - a.priority)
            .slice(0, 6);
    }, [industryAlertSnapshots, industryAlertThresholds]);

    useEffect(() => {
        if (rawIndustryAlerts.length === 0) return;

        const seenAt = Date.now();
        setIndustryAlertHistory((current) => {
            const next = { ...current };
            let changed = false;

            rawIndustryAlerts.forEach((alert) => {
                const key = `${alert.industry_name}:${alert.kind}`;
                const existing = current[key];
                const subscriptionBucket = getAlertSubscriptionBucket(alert.kind);
                if (!existing) {
                    next[key] = {
                        industry_name: alert.industry_name,
                        kind: alert.kind,
                        title: alert.title,
                        color: alert.color,
                        accent: alert.accent,
                        summary: alert.summary,
                        reason: alert.reason,
                        priority: alert.priority,
                        subscriptionBucket,
                        firstSeenAt: seenAt,
                        lastSeenAt: seenAt,
                        hitCount: 1,
                    };
                    changed = true;
                    return;
                }

                if (existing.lastSeenAt !== seenAt) {
                    next[key] = {
                        ...existing,
                        industry_name: alert.industry_name,
                        kind: alert.kind,
                        title: alert.title,
                        color: alert.color,
                        accent: alert.accent,
                        summary: alert.summary,
                        reason: alert.reason,
                        priority: alert.priority,
                        subscriptionBucket,
                        lastSeenAt: seenAt,
                        hitCount: (existing.hitCount || 1) + 1,
                    };
                    changed = true;
                }
            });

            return changed ? next : current;
        });
    }, [rawIndustryAlerts, setIndustryAlertHistory]);

    const subscribedIndustryAlerts = useMemo(() => {
        const recencyMs = industryAlertRecency === 'session' ? Number.POSITIVE_INFINITY : Number(industryAlertRecency || 15) * 60 * 1000;
        return rawIndustryAlerts
            .map((alert) => {
                const historyKey = `${alert.industry_name}:${alert.kind}`;
                const history = industryAlertHistory[historyKey];
                const firstSeenAt = history?.firstSeenAt || null;
                const isNew = firstSeenAt ? (Date.now() - firstSeenAt) <= recencyMs : false;
                return {
                    ...alert,
                    firstSeenAt,
                    isNew,
                    seenLabel: formatIndustryAlertSeenLabel(firstSeenAt),
                    subscriptionBucket: getAlertSubscriptionBucket(alert.kind),
                };
            })
            .filter((alert) => {
                const scopePass = industryAlertSubscription.scope !== 'watchlist'
                    || watchlistIndustries.includes(alert.industry_name);
                const kindPass = industryAlertSubscription.kinds.includes(alert.subscriptionBucket);
                return scopePass && kindPass;
            });
    }, [industryAlertHistory, industryAlertRecency, industryAlertSubscription, rawIndustryAlerts, watchlistIndustries]);

    const subscribedAlertNewCount = useMemo(
        () => subscribedIndustryAlerts.filter((alert) => alert.isNew).length,
        [subscribedIndustryAlerts]
    );

    const alertTimelineEntries = useMemo(() => {
        const recencyMs = industryAlertRecency === 'session'
            ? Number.POSITIVE_INFINITY
            : Number(industryAlertRecency || 15) * 60 * 1000;

        return Object.values(pruneIndustryAlertHistory(industryAlertHistory))
            .map((entry) => {
                const firstSeenAt = Number(entry?.firstSeenAt || 0) || null;
                const lastSeenAt = Number(entry?.lastSeenAt || firstSeenAt || 0) || null;
                const isNew = firstSeenAt ? (Date.now() - firstSeenAt) <= recencyMs : false;
                const severity = getIndustryAlertSeverity(entry);
                return {
                    ...entry,
                    firstSeenAt,
                    lastSeenAt,
                    isNew,
                    seenLabel: formatIndustryAlertSeenLabel(lastSeenAt),
                    subscriptionBucket: entry?.subscriptionBucket || getAlertSubscriptionBucket(entry?.kind),
                    severity,
                };
            })
            .filter((entry) => {
                const scopePass = industryAlertSubscription.scope !== 'watchlist'
                    || watchlistIndustries.includes(entry.industry_name);
                const kindPass = industryAlertSubscription.kinds.includes(entry.subscriptionBucket);
                if (!scopePass || !kindPass) return false;
                if (industryAlertRule === 'new') return entry.isNew;
                if (industryAlertRule === 'capital') return entry.subscriptionBucket === 'capital';
                if (industryAlertRule === 'risk') return entry.subscriptionBucket === 'risk';
                if (industryAlertRule === 'rotation') return entry.subscriptionBucket === 'rotation';
                return true;
            })
            .sort((a, b) => (b.lastSeenAt || 0) - (a.lastSeenAt || 0))
            .slice(0, 6);
    }, [
        industryAlertHistory,
        industryAlertRecency,
        industryAlertRule,
        industryAlertSubscription,
        watchlistIndustries,
    ]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(INDUSTRY_ALERT_BADGE_STORAGE_KEY, String(subscribedAlertNewCount || 0));
        window.dispatchEvent(new CustomEvent(INDUSTRY_ALERT_BADGE_EVENT, {
            detail: { count: subscribedAlertNewCount || 0 },
        }));
    }, [subscribedAlertNewCount]);

    const industryAlerts = useMemo(() => {
        const filteredAlerts = subscribedIndustryAlerts.filter((alert) => {
            if (industryAlertRule === 'new') return alert.isNew;
            if (industryAlertRule === 'capital') return ['capital_inflow', 'resonance'].includes(alert.kind);
            if (industryAlertRule === 'risk') return alert.kind === 'risk_release';
            if (industryAlertRule === 'rotation') return ['rotation_heatup', 'high_volatility'].includes(alert.kind);
            return true;
        });

        if (filteredAlerts.length > 0) {
            return filteredAlerts
                .sort((a, b) => Number(b.isNew) - Number(a.isNew) || b.priority - a.priority)
                .slice(0, 4);
        }

        if (rawIndustryAlerts.length > 0) {
            return [];
        }

        return focusIndustrySuggestions.slice(0, 3).map((industry, index) => ({
            industry_name: industry,
            kind: 'watchlist_seed',
            title: index === 0 ? '优先观察' : '关注备选',
            color: 'processing',
            accent: '#69c0ff',
            summary: `${industry} 当前处在热度聚合视野里，适合先加入观察列表。`,
            reason: '可以先看研究焦点、龙头股和行业详情三条链路。',
            priority: 60 - index,
            firstSeenAt: null,
            isNew: false,
            seenLabel: '等待下一次异动',
        }));
    }, [focusIndustrySuggestions, industryAlertRule, rawIndustryAlerts, subscribedIndustryAlerts]);

    const industryAlertsWithSeverity = useMemo(
        () => industryAlerts.map((alert) => ({ ...alert, severity: getIndustryAlertSeverity(alert) })),
        [industryAlerts]
    );

    const industryActionPosture = useMemo(
        () => buildIndustryActionPosture({
            alerts: industryAlertsWithSeverity,
            newCount: subscribedAlertNewCount,
            focusIndustrySuggestions,
            watchlistIndustries,
            selectedIndustry,
        }),
        [focusIndustrySuggestions, industryAlertsWithSeverity, selectedIndustry, subscribedAlertNewCount, watchlistIndustries]
    );

    useEffect(() => {
        if (!desktopAlertNotifications || typeof window === 'undefined' || typeof Notification === 'undefined') {
            return;
        }
        if (Notification.permission !== 'granted') {
            return;
        }
        industryAlertsWithSeverity
            .filter((alert) => alert.isNew && alert.severity?.level !== 'low')
            .slice(0, 2)
            .forEach((alert) => {
                const notifyKey = `industry-alert-notified:${alert.industry_name}:${alert.kind}:${alert.firstSeenAt || 'na'}`;
                if (window.sessionStorage.getItem(notifyKey)) {
                    return;
                }
                window.sessionStorage.setItem(notifyKey, 'true');
                new Notification(`行业异动: ${alert.industry_name}`, {
                    body: `${alert.title} · ${alert.summary}`,
                });
            });
    }, [desktopAlertNotifications, industryAlertsWithSeverity]);

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }

        industryAlertsWithSeverity
            .filter((alert) => alert.isNew)
            .filter((alert) => ['high', 'medium'].includes(alert.severity?.level))
            .slice(0, 4)
            .forEach((alert) => {
                const publishKey = `industry-alert-bus-published:${alert.industry_name}:${alert.kind}:${alert.firstSeenAt || 'na'}`;
                if (window.sessionStorage.getItem(publishKey)) {
                    return;
                }
                window.sessionStorage.setItem(publishKey, 'true');
                void publishQuantAlertEvent({
                    source_module: 'industry',
                    rule_name: `${alert.title} · ${alert.industry_name}`,
                    symbol: alert.industry_name,
                    severity: alert.severity?.level === 'high' ? 'critical' : 'warning',
                    message: `${alert.summary} ${alert.reason}`,
                    condition_summary: `industry:${alert.kind}`,
                    trigger_value: Number(alert.priority || 0),
                    notify_channels: [],
                    create_workbench_task: alert.severity?.level === 'high',
                    workbench_task_type: 'cross_market',
                    persist_event_record: true,
                    cascade_actions: [
                        { type: 'persist_record', record_type: 'industry_alert_hit' },
                    ],
                }).catch((error) => {
                    console.warn('Failed to publish industry alert to unified bus:', error);
                    window.sessionStorage.removeItem(publishKey);
                });
            });
    }, [industryAlertsWithSeverity]);

    return {
        alertTimelineEntries,
        focusIndustrySuggestions,
        industryAlertRecency,
        industryAlertRule,
        industryAlertsWithSeverity,
        industryActionPosture,
        rawIndustryAlerts,
        setIndustryAlertRecency,
        setIndustryAlertRule,
        subscribedAlertNewCount,
    };
}
