import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
    getIndustryPreferences,
    importIndustryPreferences,
    updateIndustryPreferences,
} from '../../services/api';
import {
    DEFAULT_INDUSTRY_ALERT_THRESHOLDS,
    INDUSTRY_ALERT_DESKTOP_STORAGE_KEY,
    INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
    INDUSTRY_ALERT_KIND_OPTIONS,
    INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY,
    INDUSTRY_SAVED_VIEWS_STORAGE_KEY,
    INDUSTRY_WATCHLIST_STORAGE_KEY,
    normalizeIndustryAlertThresholds,
    pruneIndustryAlertHistory,
    scheduleDeferredTask,
} from './industryShared';

export default function useIndustryPreferences({
    heatmapIndustriesLength,
    maxWatchlistIndustries,
    message,
}) {
    const [industryAlertHistory, setIndustryAlertHistory] = useState({});
    const [industryAlertSubscription, setIndustryAlertSubscription] = useState({
        scope: 'all',
        kinds: INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value),
    });
    const [industryAlertSubscriptionHydrated, setIndustryAlertSubscriptionHydrated] = useState(false);
    const [desktopAlertNotifications, setDesktopAlertNotifications] = useState(false);
    const [watchlistIndustries, setWatchlistIndustries] = useState([]);
    const [watchlistHydrated, setWatchlistHydrated] = useState(false);
    const [industryAlertThresholds, setIndustryAlertThresholds] = useState(DEFAULT_INDUSTRY_ALERT_THRESHOLDS);
    const [savedViewDraftName, setSavedViewDraftName] = useState('');
    const [savedIndustryViews, setSavedIndustryViews] = useState([]);

    const savedViewImportInputRef = useRef(null);
    const industryPreferencesHydratedRef = useRef(false);
    const industryPreferencesFetchStartedRef = useRef(false);
    const lastSyncedIndustryPreferencesSignatureRef = useRef('');

    const handleExportSavedViews = useCallback(() => {
        try {
            const payload = {
                watchlist_industries: watchlistIndustries,
                saved_views: savedIndustryViews,
                alert_thresholds: industryAlertThresholds,
                exported_at: new Date().toISOString(),
                version: 1,
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
            const url = window.URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = `industry-preferences-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            window.URL.revokeObjectURL(url);
            message.success('已导出行业视图与提醒配置');
        } catch (error) {
            console.error('Failed to export industry preferences:', error);
            message.error('导出行业配置失败');
        }
    }, [industryAlertThresholds, message, savedIndustryViews, watchlistIndustries]);

    const handleImportSavedViewsClick = useCallback(() => {
        savedViewImportInputRef.current?.click();
    }, []);

    const handleImportSavedViews = useCallback(async (event) => {
        const file = event?.target?.files?.[0];
        if (!file) return;
        try {
            const text = await file.text();
            const payload = JSON.parse(text);
            const normalizedWatchlist = Array.isArray(payload?.watchlist_industries)
                ? payload.watchlist_industries.filter((item) => typeof item === 'string' && item.trim()).slice(0, maxWatchlistIndustries)
                : [];
            const normalizedViews = Array.isArray(payload?.saved_views)
                ? payload.saved_views.filter((item) => item?.id && item?.state)
                : [];
            const normalizedThresholds = normalizeIndustryAlertThresholds(payload?.alert_thresholds || {});
            const syncPayload = {
                watchlist_industries: normalizedWatchlist,
                saved_views: normalizedViews,
                alert_thresholds: normalizedThresholds,
            };

            setWatchlistIndustries(normalizedWatchlist);
            setSavedIndustryViews(normalizedViews);
            setIndustryAlertThresholds(normalizedThresholds);
            await importIndustryPreferences(syncPayload);
            lastSyncedIndustryPreferencesSignatureRef.current = JSON.stringify(syncPayload);
            message.success('已导入行业视图与提醒配置');
        } catch (error) {
            console.error('Failed to import industry preferences:', error);
            message.error('导入配置失败，请检查文件格式');
        } finally {
            if (event?.target) {
                event.target.value = '';
            }
        }
    }, [maxWatchlistIndustries, message]);

    const toggleWatchlistIndustry = useCallback((industryName) => {
        if (!industryName) return;
        const persistWatchlistSnapshot = (nextWatchlist) => {
            try {
                window.localStorage.setItem(INDUSTRY_WATCHLIST_STORAGE_KEY, JSON.stringify(nextWatchlist));
            } catch (error) {
                console.warn('Failed to persist industry watchlist immediately:', error);
            }
        };

        const alreadyWatched = watchlistIndustries.includes(industryName);
        if (alreadyWatched) {
            setWatchlistIndustries((current) => {
                const nextWatchlist = current.filter((item) => item !== industryName);
                persistWatchlistSnapshot(nextWatchlist);
                return nextWatchlist;
            });
            message.success(`${industryName} 已移出观察列表`);
            return;
        }
        if (watchlistIndustries.length >= maxWatchlistIndustries) {
            message.warning(`观察列表最多保留 ${maxWatchlistIndustries} 个行业`);
            return;
        }
        setWatchlistIndustries((current) => {
            const nextWatchlist = [industryName, ...current];
            persistWatchlistSnapshot(nextWatchlist);
            return nextWatchlist;
        });
        message.success(`${industryName} 已加入观察列表`);
    }, [maxWatchlistIndustries, message, watchlistIndustries]);

    const requestDesktopAlertPermission = useCallback(async () => {
        if (typeof window === 'undefined' || typeof Notification === 'undefined') {
            message.warning('当前浏览器不支持桌面通知');
            return;
        }
        try {
            const permission = await Notification.requestPermission();
            const granted = permission === 'granted';
            setDesktopAlertNotifications(granted);
            if (granted) {
                new Notification('行业异动提醒已启用', {
                    body: '后续会优先推送高严重等级的新增行业提醒。',
                });
                message.success('桌面通知已开启');
            } else {
                message.warning('桌面通知未开启');
            }
        } catch (error) {
            console.warn('Failed to request industry alert notification permission:', error);
            message.warning('无法开启桌面通知');
        }
    }, [message]);

    useEffect(() => {
        try {
            const storedWatchlist = window.localStorage.getItem(INDUSTRY_WATCHLIST_STORAGE_KEY);
            const storedSavedViews = window.localStorage.getItem(INDUSTRY_SAVED_VIEWS_STORAGE_KEY);
            const localWatchlist = storedWatchlist ? JSON.parse(storedWatchlist) : [];
            const localViews = storedSavedViews ? JSON.parse(storedSavedViews) : [];
            setWatchlistIndustries(
                (Array.isArray(localWatchlist) ? localWatchlist : [])
                    .filter((item) => typeof item === 'string' && item.trim())
                    .slice(0, maxWatchlistIndustries)
            );
            setSavedIndustryViews(
                (Array.isArray(localViews) ? localViews : []).filter((item) => item?.id && item?.state)
            );
        } catch (error) {
            console.warn('Failed to hydrate local industry preferences:', error);
        } finally {
            setWatchlistHydrated(true);
        }
    }, [maxWatchlistIndustries]);

    useEffect(() => {
        if (industryPreferencesFetchStartedRef.current) return undefined;
        if (!heatmapIndustriesLength) return undefined;

        industryPreferencesFetchStartedRef.current = true;
        let isActive = true;

        const cancelIdleTask = scheduleDeferredTask(async () => {
            try {
                const backendPreferences = await getIndustryPreferences().catch(() => null);
                if (!isActive || !backendPreferences) return;

                setWatchlistIndustries((current) => Array.from(new Set([
                    ...((backendPreferences?.watchlist_industries || []).filter((item) => typeof item === 'string' && item.trim())),
                    ...(current.filter((item) => typeof item === 'string' && item.trim())),
                ])).slice(0, maxWatchlistIndustries));

                setSavedIndustryViews((current) => {
                    const mergedViewsMap = new Map();
                    [...((backendPreferences?.saved_views || []).filter((item) => item?.id && item?.state)), ...current]
                        .forEach((item) => mergedViewsMap.set(item.id, item));
                    return Array.from(mergedViewsMap.values());
                });

                setIndustryAlertThresholds((current) => ({
                    ...normalizeIndustryAlertThresholds(backendPreferences?.alert_thresholds || {}),
                    ...normalizeIndustryAlertThresholds(current),
                }));
            } catch (error) {
                console.warn('Failed to hydrate industry preferences from backend:', error);
            } finally {
                if (isActive) {
                    industryPreferencesHydratedRef.current = true;
                }
            }
        }, 2400);

        return () => {
            isActive = false;
            cancelIdleTask();
        };
    }, [heatmapIndustriesLength, maxWatchlistIndustries]);

    useEffect(() => {
        try {
            const storedSubscription = window.localStorage.getItem(INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY);
            if (!storedSubscription) return;
            const parsedSubscription = JSON.parse(storedSubscription);
            const nextKinds = Array.isArray(parsedSubscription?.kinds)
                ? parsedSubscription.kinds.filter((item) => INDUSTRY_ALERT_KIND_OPTIONS.some((option) => option.value === item))
                : INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value);
            setIndustryAlertSubscription({
                scope: parsedSubscription?.scope === 'watchlist' ? 'watchlist' : 'all',
                kinds: nextKinds.length > 0 ? nextKinds : INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value),
            });
        } catch (error) {
            console.warn('Failed to hydrate industry alert subscription:', error);
        } finally {
            setIndustryAlertSubscriptionHydrated(true);
        }
    }, []);

    useEffect(() => {
        try {
            const storedDesktopNotifications = window.localStorage.getItem(INDUSTRY_ALERT_DESKTOP_STORAGE_KEY);
            if (storedDesktopNotifications == null) {
                setDesktopAlertNotifications(typeof Notification !== 'undefined' && Notification.permission === 'granted');
                return;
            }
            setDesktopAlertNotifications(storedDesktopNotifications === 'true');
        } catch (error) {
            console.warn('Failed to hydrate industry desktop notifications:', error);
        }
    }, []);

    useEffect(() => {
        try {
            const storedHistory = window.localStorage.getItem(INDUSTRY_ALERT_HISTORY_STORAGE_KEY);
            if (!storedHistory) return;
            const parsedHistory = JSON.parse(storedHistory);
            if (parsedHistory && typeof parsedHistory === 'object') {
                setIndustryAlertHistory(pruneIndustryAlertHistory(parsedHistory));
            }
        } catch (error) {
            console.warn('Failed to hydrate industry alert history:', error);
        }
    }, []);

    useEffect(() => {
        if (!watchlistHydrated) return;
        try {
            window.localStorage.setItem(INDUSTRY_WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistIndustries));
        } catch (error) {
            console.warn('Failed to persist industry watchlist:', error);
        }
    }, [watchlistHydrated, watchlistIndustries]);

    useEffect(() => {
        if (!industryAlertSubscriptionHydrated) return;
        try {
            window.localStorage.setItem(INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY, JSON.stringify(industryAlertSubscription));
        } catch (error) {
            console.warn('Failed to persist industry alert subscription:', error);
        }
    }, [industryAlertSubscription, industryAlertSubscriptionHydrated]);

    useEffect(() => {
        try {
            window.localStorage.setItem(
                INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
                JSON.stringify(pruneIndustryAlertHistory(industryAlertHistory))
            );
        } catch (error) {
            console.warn('Failed to persist industry alert history:', error);
        }
    }, [industryAlertHistory]);

    useEffect(() => {
        try {
            window.localStorage.setItem(INDUSTRY_ALERT_DESKTOP_STORAGE_KEY, desktopAlertNotifications ? 'true' : 'false');
        } catch (error) {
            console.warn('Failed to persist industry desktop notifications:', error);
        }
    }, [desktopAlertNotifications]);

    useEffect(() => {
        try {
            window.localStorage.setItem(INDUSTRY_SAVED_VIEWS_STORAGE_KEY, JSON.stringify(savedIndustryViews));
        } catch (error) {
            console.warn('Failed to persist industry saved views:', error);
        }
    }, [savedIndustryViews]);

    const industryPreferencesSyncPayload = useMemo(() => ({
        watchlist_industries: watchlistIndustries,
        saved_views: savedIndustryViews,
        alert_thresholds: normalizeIndustryAlertThresholds(industryAlertThresholds),
    }), [industryAlertThresholds, savedIndustryViews, watchlistIndustries]);

    const industryPreferencesSyncSignature = useMemo(
        () => JSON.stringify(industryPreferencesSyncPayload),
        [industryPreferencesSyncPayload]
    );

    useEffect(() => {
        if (!industryPreferencesHydratedRef.current) return undefined;
        if (industryPreferencesSyncSignature === lastSyncedIndustryPreferencesSignatureRef.current) {
            return undefined;
        }
        const timeoutId = window.setTimeout(() => {
            updateIndustryPreferences(industryPreferencesSyncPayload)
                .then(() => {
                    lastSyncedIndustryPreferencesSignatureRef.current = industryPreferencesSyncSignature;
                })
                .catch((error) => {
                    console.warn('Failed to sync industry preferences:', error);
                });
        }, 450);
        return () => window.clearTimeout(timeoutId);
    }, [industryPreferencesSyncPayload, industryPreferencesSyncSignature]);

    return {
        desktopAlertNotifications,
        handleExportSavedViews,
        handleImportSavedViews,
        handleImportSavedViewsClick,
        industryAlertHistory,
        industryAlertSubscription,
        industryAlertThresholds,
        requestDesktopAlertPermission,
        savedIndustryViews,
        savedViewDraftName,
        savedViewImportInputRef,
        setDesktopAlertNotifications,
        setIndustryAlertHistory,
        setIndustryAlertSubscription,
        setIndustryAlertThresholds,
        setSavedIndustryViews,
        setSavedViewDraftName,
        toggleWatchlistIndustry,
        watchlistIndustries,
    };
}
