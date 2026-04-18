import { useEffect, useRef, useState } from 'react';

import api from '../services/api';

export const REALTIME_SYMBOLS_STORAGE_KEY = 'realtime-panel:symbols';
export const REALTIME_ACTIVE_TAB_STORAGE_KEY = 'realtime-panel:active-tab';
export const REALTIME_SYMBOL_CATEGORIES_STORAGE_KEY = 'realtime-panel:symbol-categories';
export const REALTIME_WATCH_GROUPS_STORAGE_KEY = 'realtime-panel:watch-groups';
const REALTIME_PROFILE_STORAGE_KEY = 'realtime-panel:profile-id';
const REALTIME_TAB_QUERY_KEY = 'tab';
export const REALTIME_PREFERENCES_DEBOUNCE_MS = 500;

const normalizeAllowedTabs = (validActiveTabs = []) => (
  Array.isArray(validActiveTabs) ? validActiveTabs.filter((tab) => typeof tab === 'string' && tab.trim()) : []
);

const isAllowedTab = (value, validActiveTabs = []) => {
  if (typeof value !== 'string' || !value.trim()) {
    return false;
  }
  const allowedTabs = normalizeAllowedTabs(validActiveTabs);
  return allowedTabs.length === 0 || allowedTabs.includes(value);
};

export const readRealtimeTabFromUrl = (validActiveTabs = [], search = window.location.search) => {
  if (typeof window === 'undefined') {
    return null;
  }

  const params = new URLSearchParams(search);
  const queryTab = params.get(REALTIME_TAB_QUERY_KEY);
  return isAllowedTab(queryTab, validActiveTabs) ? queryTab : null;
};

const generateRealtimeProfileId = () => {
  if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
    return `rtp-${window.crypto.randomUUID()}`;
  }

  return `rtp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};

const normalizeWatchGroup = (group, index = 0) => {
  const symbols = Array.isArray(group?.symbols)
    ? group.symbols
        .filter((symbol) => typeof symbol === 'string')
        .map((symbol) => symbol.trim().toUpperCase())
        .filter(Boolean)
    : [];
  const weights = group?.weights && typeof group.weights === 'object' && !Array.isArray(group.weights)
    ? Object.entries(group.weights).reduce((result, [rawSymbol, rawWeight]) => {
        const symbol = String(rawSymbol || '').trim().toUpperCase();
        const numericWeight = Number(rawWeight);
        if (symbol && symbols.includes(symbol) && Number.isFinite(numericWeight)) {
          result[symbol] = numericWeight;
        }
        return result;
      }, {})
    : {};
  const capital = Number(group?.capital);

  return {
    id: String(group?.id || `group-${index + 1}`),
    name: String(group?.name || '').trim(),
    symbols,
    notes: String(group?.notes || '').trim(),
    capital: Number.isFinite(capital) ? Math.max(capital, 0) : 0,
    weights,
  };
};

export const loadRealtimeProfileId = () => {
  if (typeof window === 'undefined') {
    return 'rtp-default';
  }

  const existing = window.localStorage.getItem(REALTIME_PROFILE_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const nextId = generateRealtimeProfileId();
  window.localStorage.setItem(REALTIME_PROFILE_STORAGE_KEY, nextId);
  return nextId;
};

export const loadPersistedSymbols = (defaultSymbols) => {
  if (typeof window === 'undefined') {
    return defaultSymbols;
  }

  try {
    const raw = window.localStorage.getItem(REALTIME_SYMBOLS_STORAGE_KEY);
    if (!raw) {
      return defaultSymbols;
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return defaultSymbols;
    }

    const normalized = parsed
      .filter((symbol) => typeof symbol === 'string')
      .map((symbol) => symbol.trim().toUpperCase())
      .filter(Boolean);

    return normalized.length > 0 ? Array.from(new Set(normalized)) : defaultSymbols;
  } catch (error) {
    return defaultSymbols;
  }
};

export const loadPersistedActiveTab = (defaultTab, validActiveTabs = []) => {
  if (typeof window === 'undefined') {
    return defaultTab;
  }

  const tabFromUrl = readRealtimeTabFromUrl(validActiveTabs);
  if (tabFromUrl) {
    return tabFromUrl;
  }

  const persisted = window.localStorage.getItem(REALTIME_ACTIVE_TAB_STORAGE_KEY);
  return isAllowedTab(persisted, validActiveTabs) ? persisted : defaultTab;
};

export const loadPersistedSymbolCategories = () => {
  if (typeof window === 'undefined') {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(REALTIME_SYMBOL_CATEGORIES_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }

    return Object.entries(parsed).reduce((result, [rawSymbol, rawCategory]) => {
      if (typeof rawSymbol !== 'string' || typeof rawCategory !== 'string') {
        return result;
      }
      const symbol = rawSymbol.trim().toUpperCase();
      const category = rawCategory.trim();
      if (symbol && category) {
        result[symbol] = category;
      }
      return result;
    }, {});
  } catch (error) {
    return {};
  }
};

export const loadPersistedWatchGroups = () => {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(REALTIME_WATCH_GROUPS_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .filter((group) => group && typeof group === 'object')
      .map((group, index) => normalizeWatchGroup(group, index))
      .filter((group) => group.name);
  } catch (error) {
    return [];
  }
};

export const useRealtimePreferences = ({
  defaultSymbols,
  defaultActiveTab = 'index',
  validActiveTabs = [],
}) => {
  const [subscribedSymbols, setSubscribedSymbols] = useState(() => loadPersistedSymbols(defaultSymbols));
  const [activeTab, setActiveTab] = useState(() => loadPersistedActiveTab(defaultActiveTab, validActiveTabs));
  const [symbolCategoryOverrides, setSymbolCategoryOverrides] = useState(() => loadPersistedSymbolCategories());
  const [watchGroups, setWatchGroups] = useState(() => loadPersistedWatchGroups());
  const [isPreferencesHydrated, setIsPreferencesHydrated] = useState(false);

  const lastSyncedPreferencesRef = useRef('');
  const preferencesSaveTimerRef = useRef(null);
  const latestPreferencesRef = useRef('');
  const realtimeProfileIdRef = useRef(loadRealtimeProfileId());

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(REALTIME_SYMBOLS_STORAGE_KEY, JSON.stringify(subscribedSymbols));
  }, [subscribedSymbols]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(REALTIME_ACTIVE_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('view') !== 'realtime') {
      return;
    }

    if (activeTab) {
      params.set(REALTIME_TAB_QUERY_KEY, activeTab);
    } else {
      params.delete(REALTIME_TAB_QUERY_KEY);
    }

    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash || ''}`;
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash || ''}`;

    if (nextUrl !== currentUrl) {
      window.history.replaceState(null, '', nextUrl);
    }
  }, [activeTab]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      REALTIME_SYMBOL_CATEGORIES_STORAGE_KEY,
      JSON.stringify(symbolCategoryOverrides)
    );
  }, [symbolCategoryOverrides]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      REALTIME_WATCH_GROUPS_STORAGE_KEY,
      JSON.stringify(watchGroups)
    );
  }, [watchGroups]);

  useEffect(() => {
    latestPreferencesRef.current = JSON.stringify({
      symbols: subscribedSymbols,
      active_tab: activeTab,
      symbol_categories: symbolCategoryOverrides,
      watch_groups: watchGroups,
    });
  }, [activeTab, subscribedSymbols, symbolCategoryOverrides, watchGroups]);

  useEffect(() => {
    let isCancelled = false;
    const initialPreferencesSnapshot = JSON.stringify({
      symbols: subscribedSymbols,
      active_tab: activeTab,
      symbol_categories: symbolCategoryOverrides,
      watch_groups: watchGroups,
    });

    const hydratePreferences = async () => {
      try {
        const response = await api.get('/realtime/preferences', {
          headers: {
            'X-Realtime-Profile': realtimeProfileIdRef.current,
          },
        });
        if (!response.data?.success || isCancelled) {
          return;
        }

        const currentPreferencesSnapshot = latestPreferencesRef.current || initialPreferencesSnapshot;
        const userChangedPreferencesDuringHydration = currentPreferencesSnapshot !== initialPreferencesSnapshot;
        const urlActiveTab = readRealtimeTabFromUrl(validActiveTabs);
        const nextSymbols = Array.isArray(response.data.data?.symbols)
          ? response.data.data.symbols
              .filter((symbol) => typeof symbol === 'string')
              .map((symbol) => symbol.trim().toUpperCase())
              .filter(Boolean)
          : [];
        const nextTab = isAllowedTab(response.data.data?.active_tab, validActiveTabs)
          ? response.data.data.active_tab
          : null;
        const nextCategories = response.data.data?.symbol_categories
          && typeof response.data.data.symbol_categories === 'object'
          && !Array.isArray(response.data.data.symbol_categories)
          ? Object.entries(response.data.data.symbol_categories).reduce((result, [rawSymbol, rawCategory]) => {
            if (typeof rawSymbol !== 'string' || typeof rawCategory !== 'string') {
              return result;
            }
            const symbol = rawSymbol.trim().toUpperCase();
            const category = rawCategory.trim();
            if (symbol && category) {
              result[symbol] = category;
            }
            return result;
          }, {})
          : {};
        const nextWatchGroups = Array.isArray(response.data.data?.watch_groups)
          ? response.data.data.watch_groups
              .filter((group) => group && typeof group === 'object')
              .map((group, index) => normalizeWatchGroup(group, index))
              .filter((group) => group.name)
          : [];

        if (!userChangedPreferencesDuringHydration) {
          if (nextSymbols.length > 0) {
            setSubscribedSymbols(Array.from(new Set(nextSymbols)));
          }
          if (nextTab && !urlActiveTab) {
            setActiveTab(nextTab);
          }
          setSymbolCategoryOverrides(nextCategories);
          setWatchGroups(nextWatchGroups);

          lastSyncedPreferencesRef.current = JSON.stringify({
            symbols: nextSymbols.length > 0 ? Array.from(new Set(nextSymbols)) : subscribedSymbols,
            active_tab: nextTab || activeTab,
            symbol_categories: nextCategories,
            watch_groups: nextWatchGroups,
          });
        }
      } catch (error) {
        console.warn('Failed to load realtime preferences from backend, falling back to local cache:', error);
      } finally {
        if (!isCancelled) {
          setIsPreferencesHydrated(true);
        }
      }
    };

    hydratePreferences();

    return () => {
      isCancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isPreferencesHydrated) {
      return undefined;
    }

    const payload = {
      symbols: subscribedSymbols,
      active_tab: activeTab,
      symbol_categories: symbolCategoryOverrides,
      watch_groups: watchGroups,
    };
    const serializedPayload = JSON.stringify(payload);
    if (serializedPayload === lastSyncedPreferencesRef.current) {
      return undefined;
    }

    if (preferencesSaveTimerRef.current) {
      clearTimeout(preferencesSaveTimerRef.current);
    }

    preferencesSaveTimerRef.current = setTimeout(async () => {
      try {
        await api.put('/realtime/preferences', payload, {
          headers: {
            'X-Realtime-Profile': realtimeProfileIdRef.current,
          },
        });
        lastSyncedPreferencesRef.current = serializedPayload;
      } catch (error) {
        console.warn('Failed to sync realtime preferences to backend, keeping local cache only:', error);
      }
    }, REALTIME_PREFERENCES_DEBOUNCE_MS);

    return () => {
      if (preferencesSaveTimerRef.current) {
        clearTimeout(preferencesSaveTimerRef.current);
        preferencesSaveTimerRef.current = null;
      }
    };
  }, [activeTab, isPreferencesHydrated, subscribedSymbols, symbolCategoryOverrides, watchGroups]);

  return {
    activeTab,
    realtimeProfileId: realtimeProfileIdRef.current,
    setActiveTab,
    setSymbolCategoryOverrides,
    setSubscribedSymbols,
    subscribedSymbols,
    symbolCategoryOverrides,
    watchGroups,
    setWatchGroups,
  };
};
