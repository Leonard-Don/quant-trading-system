const VIEW_QUERY_KEY = 'view';
const TAB_QUERY_KEY = 'tab';

const RESEARCH_KEYS = ['symbol', 'symbols', 'template', 'action', 'source', 'note'];
const PRICING_KEYS = ['symbol', 'symbols', 'action', 'source', 'note', 'period'];
const CROSS_MARKET_KEYS = ['template', 'action', 'source', 'note'];
const WORKBENCH_KEYS = ['workbench_refresh', 'workbench_type', 'workbench_source', 'workbench_reason', 'task'];

export const readResearchContext = (search = window.location.search) => {
  const params = new URLSearchParams(search);
  return {
    view: params.get(VIEW_QUERY_KEY) || 'backtest',
    tab: params.get(TAB_QUERY_KEY) || '',
    symbol: params.get('symbol') || '',
    symbols: params.get('symbols') || '',
    template: params.get('template') || '',
    action: params.get('action') || '',
    source: params.get('source') || '',
    note: params.get('note') || '',
    period: params.get('period') || '',
    record: params.get('record') || '',
    historySymbol: params.get('history_symbol') || '',
    historyStrategy: params.get('history_strategy') || '',
    workbenchRefresh: params.get('workbench_refresh') || '',
    workbenchType: params.get('workbench_type') || '',
    workbenchSource: params.get('workbench_source') || '',
    workbenchReason: params.get('workbench_reason') || '',
    task: params.get('task') || '',
  };
};

const setParam = (params, key, value) => {
  if (value === undefined || value === null || value === '') {
    params.delete(key);
  } else {
    params.set(key, value);
  }
};

export const sanitizeParamsForView = (params, view) => {
  if (view === 'pricing') {
    params.delete(TAB_QUERY_KEY);
    params.delete('record');
    params.delete('history_symbol');
    params.delete('history_strategy');
    RESEARCH_KEYS.forEach((key) => {
      if (!PRICING_KEYS.includes(key)) params.delete(key);
    });
    return params;
  }

  if (view === 'backtest') {
    params.delete('period');
    const activeTab = params.get(TAB_QUERY_KEY) || 'new';
    if (activeTab !== 'history') {
      params.delete('record');
      params.delete('history_symbol');
      params.delete('history_strategy');
    }
    if (activeTab === 'cross-market') {
      RESEARCH_KEYS.forEach((key) => {
        if (!CROSS_MARKET_KEYS.includes(key)) params.delete(key);
      });
    } else {
      RESEARCH_KEYS.forEach((key) => params.delete(key));
    }
    return params;
  }

  if (view === 'workbench') {
    params.delete(TAB_QUERY_KEY);
    params.delete('period');
    params.delete('record');
    params.delete('history_symbol');
    params.delete('history_strategy');
    RESEARCH_KEYS.forEach((key) => params.delete(key));
    return params;
  }

  params.delete(TAB_QUERY_KEY);
  params.delete('period');
  params.delete('record');
  params.delete('history_symbol');
  params.delete('history_strategy');
  RESEARCH_KEYS.forEach((key) => params.delete(key));
  WORKBENCH_KEYS.forEach((key) => params.delete(key));
  return params;
};

export const buildAppUrl = ({
  pathname = window.location.pathname,
  currentSearch = window.location.search,
  view = 'backtest',
  tab = undefined,
  symbol = undefined,
  symbols = undefined,
  template = undefined,
  action = undefined,
  source = undefined,
  note = undefined,
  period = undefined,
  record = undefined,
  historySymbol = undefined,
  historyStrategy = undefined,
  workbenchRefresh = undefined,
  workbenchType = undefined,
  workbenchSource = undefined,
  workbenchReason = undefined,
  task = undefined,
} = {}) => {
  const params = new URLSearchParams(currentSearch);
  if (view === 'backtest') {
    params.delete(VIEW_QUERY_KEY);
  } else {
    params.set(VIEW_QUERY_KEY, view);
  }

  if (view !== 'backtest') {
    params.delete(TAB_QUERY_KEY);
  } else {
    setParam(params, TAB_QUERY_KEY, tab);
  }

  setParam(params, 'symbol', symbol);
  setParam(params, 'symbols', symbols);
  setParam(params, 'template', template);
  setParam(params, 'action', action);
  setParam(params, 'source', source);
  setParam(params, 'note', note);
  setParam(params, 'period', period);
  setParam(params, 'record', record);
  setParam(params, 'history_symbol', historySymbol);
  setParam(params, 'history_strategy', historyStrategy);
  setParam(params, 'workbench_refresh', workbenchRefresh);
  setParam(params, 'workbench_type', workbenchType);
  setParam(params, 'workbench_source', workbenchSource);
  setParam(params, 'workbench_reason', workbenchReason);
  setParam(params, 'task', task);

  sanitizeParamsForView(params, view);

  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
};

export const buildViewUrlForCurrentState = (
  view,
  currentSearch = window.location.search,
  pathname = window.location.pathname,
) => {
  const params = new URLSearchParams(currentSearch);
  sanitizeParamsForView(params, view);

  return buildAppUrl({
    pathname,
    currentSearch: `?${params.toString()}`,
    view,
    tab: view === 'backtest' ? params.get(TAB_QUERY_KEY) : undefined,
    symbol: params.get('symbol'),
    symbols: params.get('symbols'),
    template: params.get('template'),
    action: params.get('action'),
    source: params.get('source'),
    note: params.get('note'),
    period: params.get('period'),
    record: params.get('record'),
    historySymbol: params.get('history_symbol'),
    historyStrategy: params.get('history_strategy'),
    workbenchRefresh: params.get('workbench_refresh'),
    workbenchType: params.get('workbench_type'),
    workbenchSource: params.get('workbench_source'),
    workbenchReason: params.get('workbench_reason'),
    task: params.get('task'),
  });
};

export const buildPricingLink = (
  symbol,
  source = 'godeye',
  note = '',
  currentSearch = window.location.search,
  period = undefined,
) => {
  const params = new URLSearchParams(currentSearch);
  const resolvedPeriod = period ?? params.get('period') ?? undefined;
  return buildAppUrl({
    currentSearch,
    view: 'pricing',
    symbol,
    source,
    action: 'pricing',
    note,
    period: resolvedPeriod,
  });
};

export const buildCrossMarketLink = (templateId, source = 'godeye', note = '', currentSearch = window.location.search) =>
  buildAppUrl({
    currentSearch,
    view: 'backtest',
    tab: 'cross-market',
    template: templateId,
    source,
    action: 'cross_market',
    note,
  });

export const buildGodEyeLink = (currentSearch = window.location.search) =>
  buildAppUrl({
    currentSearch,
    view: 'godsEye',
  });

export const buildWorkbenchLink = (
  {
    refresh = '',
    type = '',
    sourceFilter = '',
    reason = '',
    taskId = '',
  } = {},
  currentSearch = window.location.search,
) =>
  buildAppUrl({
    currentSearch,
    view: 'workbench',
    workbenchRefresh: refresh,
    workbenchType: type,
    workbenchSource: sourceFilter,
    workbenchReason: reason,
    task: taskId,
  });

export const navigateToAppUrl = (url) => {
  window.history.pushState(null, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

export const navigateByResearchAction = (action, currentSearch = window.location.search) => {
  if (!action?.target || action.target === 'observe') {
    return;
  }

  if (action.target === 'pricing') {
    navigateToAppUrl(
      buildPricingLink(action.symbol, action.source || 'playbook', action.note || '', currentSearch, action.period)
    );
    return;
  }

  if (action.target === 'cross-market') {
    navigateToAppUrl(
      buildCrossMarketLink(action.template, action.source || 'playbook', action.note || '', currentSearch)
    );
    return;
  }

  if (action.target === 'godsEye') {
    navigateToAppUrl(buildGodEyeLink(currentSearch));
    return;
  }

  if (action.target === 'workbench') {
    navigateToAppUrl(
      buildWorkbenchLink(
        {
          refresh: action.refresh,
          type: action.type,
          sourceFilter: action.sourceFilter,
          reason: action.reason,
          taskId: action.taskId,
        },
        currentSearch
      )
    );
  }
};

export const formatResearchSource = (source = '') => {
  const mapping = {
    godeye: 'GodEye',
    alert_hunter: 'Alert Hunter',
    policy_timeline: 'Policy Timeline',
    factor_panel: 'Macro Factor Panel',
    risk_radar: 'Risk Premium Radar',
    cross_market_overview: 'Cross-Market Overview',
    cross_market_panel: 'Cross-Market Panel',
    pricing_playbook: 'Pricing Playbook',
    cross_market_playbook: 'Cross-Market Playbook',
  };
  return mapping[source] || source;
};
