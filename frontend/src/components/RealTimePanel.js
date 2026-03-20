import React, { useState, useCallback, lazy, Suspense } from 'react';
import {
  Card,
  Statistic,
  Tag,
  Input,
  Button,
  Space,
  Typography,
  Badge,
  Switch,
  message,
  AutoComplete,
  Tabs
} from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  SearchOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  RiseOutlined,
  DollarOutlined,
  StockOutlined,
  PropertySafetyOutlined,
  BankOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  FundOutlined
} from '@ant-design/icons';
import { STOCK_DATABASE } from '../constants/stocks';
import { useRealtimeFeed } from '../hooks/useRealtimeFeed';
import { useRealtimePreferences } from '../hooks/useRealtimePreferences';

const { Text } = Typography;
const DEFAULT_PRICE_TEXT = '--';
const EMPTY_NUMERIC_TEXT = '--';
const QUOTE_FRESH_MS = 45 * 1000;
const QUOTE_DELAYED_MS = 3 * 60 * 1000;
const DEFAULT_SUBSCRIBED_SYMBOLS = [
  '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
  'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
  '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
  'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
  '^TNX', '^TYX', 'TLT',
  'GC=F', 'CL=F', 'SI=F',
  'SPY', 'QQQ', 'UVXY'
];
const CATEGORY_THEMES = {
  index: { label: '指数', accent: '#0ea5e9', soft: 'rgba(14, 165, 233, 0.12)' },
  us: { label: '美股', accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.12)' },
  cn: { label: 'A股', accent: '#f97316', soft: 'rgba(249, 115, 22, 0.12)' },
  crypto: { label: '加密', accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' },
  bond: { label: '债券', accent: '#6366f1', soft: 'rgba(99, 102, 241, 0.12)' },
  future: { label: '期货', accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' },
  option: { label: '期权', accent: '#a855f7', soft: 'rgba(168, 85, 247, 0.12)' },
  other: { label: '其他', accent: '#64748b', soft: 'rgba(100, 116, 139, 0.12)' },
};
const TradePanel = lazy(() => import('./TradePanel'));
const RealtimeStockDetailModal = lazy(() => import('./RealtimeStockDetailModal'));

const hasNumericValue = (value) => value !== undefined && value !== null && !Number.isNaN(Number(value));

const inferSymbolCategory = (symbol) => {
  const type = STOCK_DATABASE[symbol]?.type;
  if (type) {
    return type;
  }

  if (/^\d{6}\.(SS|SZ|BJ)$/i.test(symbol)) {
    return 'cn';
  }

  if (/^-?[A-Z0-9]+-USD$/i.test(symbol)) {
    return 'crypto';
  }

  if (/=F$/i.test(symbol)) {
    return 'future';
  }

  if (symbol.startsWith('^')) {
    return /^(?:\^TNX|\^TYX|\^FVX|\^IRX)$/i.test(symbol) ? 'bond' : 'index';
  }

  return 'us';
};

const RealTimePanel = () => {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [searchSymbol, setSearchSymbol] = useState('');

  // Trade Modal State
  const [isTradeModalVisible, setIsTradeModalVisible] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  // Detail Modal State
  const [isDetailModalVisible, setIsDetailModalVisible] = useState(false);
  const [detailSymbol, setDetailSymbol] = useState(null);
  const [autoCompleteOptions, setAutoCompleteOptions] = useState([]);

  const {
    activeTab,
    setActiveTab,
    setSubscribedSymbols,
    subscribedSymbols,
  } = useRealtimePreferences({
    defaultSymbols: DEFAULT_SUBSCRIBED_SYMBOLS,
  });

  const getSymbolsByCategory = useCallback((category) => {
    return subscribedSymbols.filter(symbol => {
      return inferSymbolCategory(symbol) === category;
    });
  }, [subscribedSymbols]);

  const {
    clearMissingQuoteRequests,
    fetchQuotes,
    freshnessNow,
    hasEverConnected,
    hasExperiencedFallback,
    isAutoUpdate,
    isConnected,
    lastConnectionIssue,
    lastMarketUpdateAt,
    loading,
    quotes,
    reconnectAttempts,
    refreshCurrentTab,
    removeQuote,
    setIsAutoUpdate,
  } = useRealtimeFeed({
    activeTab,
    messageApi,
    resolveSymbolsByCategory: getSymbolsByCategory,
    subscribedSymbols,
  });

  const subscribeSymbol = useCallback((symbol) => {
    if (subscribedSymbols.includes(symbol)) {
      return false;
    }

    setSubscribedSymbols(prev => [...prev, symbol]);
    messageApi.success(`已订阅 ${symbol} 的实时数据`);
    return true;
  }, [messageApi, setSubscribedSymbols, subscribedSymbols]);

  const removeSymbol = useCallback((symbol) => {
    setSubscribedSymbols(prev => prev.filter(s => s !== symbol));
    removeQuote(symbol);
  }, [removeQuote, setSubscribedSymbols]);

  const toggleAutoUpdate = useCallback((checked) => {
    setIsAutoUpdate(checked);
  }, [setIsAutoUpdate]);

  // 添加新股票
  const addSymbol = (symbol) => {
    if (!symbol) return;
    const newSymbol = symbol.trim().toUpperCase();
    if (subscribedSymbols.includes(newSymbol)) return;

    const added = subscribeSymbol(newSymbol);
    if (!added) {
      return;
    }
    const nextCategory = inferSymbolCategory(newSymbol);
    if (nextCategory) {
      setActiveTab(nextCategory);
    }
    clearMissingQuoteRequests([newSymbol]);
    fetchQuotes([newSymbol]);
    setSearchSymbol('');
    setAutoCompleteOptions([]);
  };

  const formatPrice = (price, fallback = DEFAULT_PRICE_TEXT) => {
    if (!hasNumericValue(price)) return fallback;
    return typeof price === 'number' ? price.toFixed(2) : parseFloat(price).toFixed(2);
  };

  const formatPercent = (percent, fallback = EMPTY_NUMERIC_TEXT) => {
    if (!hasNumericValue(percent)) return fallback;
    return typeof percent === 'number' ? percent.toFixed(2) + '%' : parseFloat(percent).toFixed(2) + '%';
  };

  const formatVolume = (volume) => {
    if (volume === undefined || volume === null || Number.isNaN(Number(volume))) {
      return EMPTY_NUMERIC_TEXT;
    }

    if (volume >= 1000000) {
      return (volume / 1000000).toFixed(1) + 'M';
    } else if (volume >= 1000) {
      return (volume / 1000).toFixed(1) + 'K';
    }
    return volume.toString();
  };

  const handleOpenTrade = useCallback((symbol) => {
    setSelectedSymbol(symbol);
    setIsTradeModalVisible(true);
  }, []);

  const handleCloseTrade = useCallback(() => {
    setIsTradeModalVisible(false);
    setSelectedSymbol(null);
  }, []);

  const getDisplayName = useCallback((symbol) => {
    const info = STOCK_DATABASE[symbol];
    if (info) {
      return info.cn || info.en || symbol;
    }
    return symbol;
  }, []);

  const handleShowDetail = useCallback((symbol) => {
    setDetailSymbol(symbol);
    setIsDetailModalVisible(true);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setIsDetailModalVisible(false);
    setDetailSymbol(null);
  }, []);

  const findMatchingSymbols = (input) => {
    if (!input || input.trim() === '') return [];

    const query = input.toLowerCase().trim();
    const results = [];

    Object.entries(STOCK_DATABASE).forEach(([code, info]) => {
      if (subscribedSymbols.includes(code)) return;

      if (code.toLowerCase().includes(query)) {
        results.push({ code, info, matchType: 'code', priority: code.toLowerCase() === query ? 0 : 1 });
        return;
      }
      if (info.en.toLowerCase().includes(query)) {
        results.push({ code, info, matchType: 'en', priority: 2 });
        return;
      }
      if (info.cn.includes(query)) {
        results.push({ code, info, matchType: 'cn', priority: 2 });
        return;
      }
    });

    return results.sort((a, b) => a.priority - b.priority).slice(0, 10);
  };

  const risingCount = Object.values(quotes).filter(q => q?.change > 0).length;
  const fallingCount = Object.values(quotes).filter(q => q?.change < 0).length;
  const currentTabSymbols = getSymbolsByCategory(activeTab);
  const currentTabQuotes = currentTabSymbols.map(symbol => quotes[symbol]).filter(Boolean);
  const loadedQuotesCount = Object.values(quotes).filter(Boolean).length;
  const spotlightSymbol = currentTabSymbols
    .filter(symbol => quotes[symbol])
    .sort((left, right) => Math.abs(Number(quotes[right]?.change_percent || 0)) - Math.abs(Number(quotes[left]?.change_percent || 0)))[0] || null;

  const handleSearch = (value) => {
    setSearchSymbol(value);
    if (!value || value.trim() === '') {
      setAutoCompleteOptions([]);
      return;
    }

    const results = findMatchingSymbols(value);
    const options = results.map(({ code, info }) => ({
      value: code,
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
          <span>
            <Text strong style={{ fontSize: '14px' }}>{code}</Text>
            <Text type="secondary" style={{ marginLeft: 10 }}>{info.cn}</Text>
            <Text type="secondary" style={{ marginLeft: 6, fontSize: '12px' }}>({info.en})</Text>
          </span>
          <Tag color="blue" style={{ margin: 0 }}>
            {getCategoryLabel(info.type)}
          </Tag>
        </div>
      )
    }));
    setAutoCompleteOptions(options);
  };

  const handleSelect = (value) => {
    addSymbol(value);
    setAutoCompleteOptions([]);
  };

  const getCategoryLabel = (type) => {
    switch (type) {
      case 'index': return '指数';
      case 'us': return '美股';
      case 'cn': return 'A股';
      case 'crypto': return '加密货币';
      case 'bond': return '债券';
      case 'future': return '期货';
      case 'option': return '期权';
      default: return '其他';
    }
  };

  const getCategoryTheme = (type) => CATEGORY_THEMES[type] || CATEGORY_THEMES.other;

  const formatQuoteTime = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getQuoteFreshness = useCallback((quote) => {
    if (!quote?._clientReceivedAt) {
      return {
        state: 'pending',
        label: '待补数',
        tone: {
          color: '#64748b',
          background: 'rgba(100, 116, 139, 0.12)',
        },
      };
    }

    const ageMs = Math.max(0, freshnessNow - quote._clientReceivedAt);
    if (ageMs <= QUOTE_FRESH_MS) {
      return {
        state: 'fresh',
        label: '刚刚更新',
        tone: {
          color: '#15803d',
          background: 'rgba(34, 197, 94, 0.14)',
        },
      };
    }

    if (ageMs <= QUOTE_DELAYED_MS) {
      return {
        state: 'aging',
        label: `${Math.max(1, Math.floor(ageMs / 1000))} 秒前更新`,
        tone: {
          color: '#b45309',
          background: 'rgba(245, 158, 11, 0.16)',
        },
      };
    }

    return {
      state: 'delayed',
      label: `延迟 ${Math.max(1, Math.floor(ageMs / 60000))} 分钟`,
      tone: {
        color: '#b91c1c',
        background: 'rgba(239, 68, 68, 0.14)',
      },
    };
  }, [freshnessNow]);

  const freshnessSummary = currentTabQuotes.reduce((summary, quote) => {
    const freshness = getQuoteFreshness(quote);
    if (freshness.state === 'fresh') summary.fresh += 1;
    else if (freshness.state === 'aging') summary.aging += 1;
    else if (freshness.state === 'delayed') summary.delayed += 1;
    else summary.pending += 1;
    return summary;
  }, { fresh: 0, aging: 0, delayed: 0, pending: 0 });
  const transportModeLabel = !isAutoUpdate
    ? '手动刷新'
    : isConnected
      ? 'WebSocket 实时'
      : reconnectAttempts > 0
        ? '重连中 / REST 补数'
        : '连接中 / REST 补数';
  const lastMarketUpdateLabel = lastMarketUpdateAt ? formatQuoteTime(lastMarketUpdateAt) : '--';
  const transportBanner = !isAutoUpdate
    ? {
        tone: 'manual',
        title: '自动更新已关闭',
        description: '当前只会在你手动点击刷新时拉取最新行情，适合临时暂停实时更新。',
      }
    : isConnected
      ? {
          tone: 'healthy',
          title: hasExperiencedFallback ? '实时推送已恢复' : '实时推送正常',
          description: hasExperiencedFallback
            ? 'WebSocket 已重新接管实时更新，列表会继续自动推进。'
            : '当前由 WebSocket 持续推送最新行情，REST 只在首屏和补数时兜底。',
        }
      : reconnectAttempts > 0
        ? {
            tone: 'fallback',
            title: '正在重连实时推送',
            description: `当前已切到 REST 补数，第 ${reconnectAttempts} 次重连进行中。${lastConnectionIssue ? ` 最近异常：${lastConnectionIssue}` : ''}`,
          }
      : {
          tone: 'fallback',
          title: hasEverConnected ? '已降级到 REST 补数' : '正在建立实时连接',
          description: hasEverConnected
            ? `实时推送暂时不可用，页面会先用 REST 补数维持更新，连接恢复后会自动切回实时模式。${lastConnectionIssue ? ` 最近异常：${lastConnectionIssue}` : ''}`
            : '在 WebSocket 建立前，页面会先通过 REST 拉取当前分组行情，避免首屏空白。',
        };
  const transportBannerStyle = transportBanner.tone === 'healthy'
    ? {
        color: '#166534',
        background: 'rgba(34, 197, 94, 0.14)',
        borderColor: 'rgba(34, 197, 94, 0.24)',
      }
    : transportBanner.tone === 'manual'
      ? {
          color: '#1d4ed8',
          background: 'rgba(59, 130, 246, 0.12)',
          borderColor: 'rgba(59, 130, 246, 0.2)',
        }
      : {
          color: '#b45309',
          background: 'rgba(245, 158, 11, 0.14)',
          borderColor: 'rgba(245, 158, 11, 0.26)',
        };

  const renderQuoteCard = (symbol, quote) => {
    const hasChange = hasNumericValue(quote.change);
    const isPositive = hasChange ? Number(quote.change) >= 0 : null;
    const changeColor = isPositive === null
      ? 'var(--text-secondary)'
      : isPositive
        ? 'var(--accent-success)'
        : 'var(--accent-danger)';
    const changeIcon = isPositive === null ? null : (isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />);
    const categoryType = inferSymbolCategory(symbol);
    const categoryTheme = getCategoryTheme(categoryType);
    const isMarketIndex = categoryType === 'index';
    const changePercentText = formatPercent(quote.change_percent);
    const changeTagBackground = isPositive === null
      ? 'rgba(100, 116, 139, 0.12)'
      : isPositive
        ? 'rgba(34, 197, 94, 0.14)'
        : 'rgba(239, 68, 68, 0.14)';
    const freshness = getQuoteFreshness(quote);

    return (
      <Card
        key={symbol}
        className="realtime-quote-card"
        style={{
          border: `1px solid color-mix(in srgb, ${categoryTheme.accent} 28%, var(--border-color) 72%)`,
          background: `linear-gradient(180deg, ${categoryTheme.soft} 0%, color-mix(in srgb, var(--bg-secondary) 92%, white 8%) 100%)`,
          boxShadow: '0 14px 34px rgba(15, 23, 42, 0.08)',
          overflow: 'hidden',
        }}
        styles={{ body: { padding: 0 } }}
      >
        <div
          className="realtime-quote-card__surface"
          onClick={() => handleShowDetail(symbol)}
          style={{ cursor: 'pointer', padding: 18 }}
        >
          <div className="realtime-quote-card__header">
            <div>
              <div className="realtime-quote-card__tags">
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    color: categoryTheme.accent,
                    background: categoryTheme.soft,
                    borderColor: 'transparent',
                    fontWeight: 700,
                  }}
                >
                  {categoryTheme.label}
                </Tag>
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    borderColor: 'transparent',
                    color: changeColor,
                    background: changeTagBackground,
                    fontWeight: 700,
                  }}
                >
                  {changePercentText}
                </Tag>
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    borderColor: 'transparent',
                    color: freshness.tone.color,
                    background: freshness.tone.background,
                    fontWeight: 700,
                  }}
                >
                  {freshness.label}
                </Tag>
              </div>
              <div className="realtime-quote-card__name">
                <Text strong style={{ fontSize: '17px', color: 'var(--text-primary)' }}>
                  {getDisplayName(symbol)}
                </Text>
              </div>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {symbol} · {formatQuoteTime(quote.timestamp)}
              </Text>
            </div>

            <div className="realtime-quote-card__source">
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', opacity: 0.72 }}>
                Source
              </div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                {quote.source || '--'}
              </div>
            </div>
          </div>

          <div className="realtime-quote-card__price-row">
            <div>
              <div className="realtime-quote-card__price">{formatPrice(quote.price)}</div>
              <div className="realtime-quote-card__delta" style={{ color: changeColor }}>
                {changeIcon ? <>{changeIcon} </> : null}
                {hasChange ? formatPrice(Math.abs(Number(quote.change))) : EMPTY_NUMERIC_TEXT} · {changePercentText}
              </div>
            </div>
            <div className="realtime-quote-card__focus">
              <div className="realtime-quote-card__focus-label">点击卡片</div>
              <div className="realtime-quote-card__focus-value">查看深度详情</div>
            </div>
          </div>

          <div className="realtime-quote-card__metrics">
            <div className="realtime-quote-card__metric">
              <span>日内区间</span>
              <strong>{formatPrice(quote.low, EMPTY_NUMERIC_TEXT)} - {formatPrice(quote.high, EMPTY_NUMERIC_TEXT)}</strong>
            </div>
            <div className="realtime-quote-card__metric">
              <span>开盘 / 昨收</span>
              <strong>{formatPrice(quote.open, EMPTY_NUMERIC_TEXT)} / {formatPrice(quote.previous_close, EMPTY_NUMERIC_TEXT)}</strong>
            </div>
            <div className="realtime-quote-card__metric">
              <span>成交量</span>
              <strong>{formatVolume(quote.volume)}</strong>
            </div>
          </div>

          <div className="realtime-quote-card__footer">
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {isMarketIndex ? '指数详情与分析面板联动' : '支持查看实时快照、分析与交易入口'}
            </Text>
            <Space>
              {!isMarketIndex && categoryType !== 'bond' && (
                <Button
                  type="primary"
                  size="small"
                  onClick={(e) => { e.stopPropagation(); handleOpenTrade(symbol); }}
                  icon={<DollarOutlined />}
                >
                  交易
                </Button>
              )}
              <Button
                type="text"
                size="small"
                danger
                onClick={(e) => { e.stopPropagation(); removeSymbol(symbol); }}
              >
                ×
              </Button>
            </Space>
          </div>
        </div>
      </Card>
    );
  };

  const renderTabItem = (key, label, icon) => {
    const symbols = getSymbolsByCategory(key);
    return {
      key,
      label: <span>{icon} {label}</span>,
      children: symbols.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '56px 20px' }}>
          <Text type="secondary">暂无{label}数据，请添加</Text>
        </div>
      ) : (
        <div className="realtime-quote-grid">
          {symbols.map(symbol => {
            const quote = quotes[symbol];
            return quote ? renderQuoteCard(symbol, quote) : (
              <Card
                key={symbol}
                loading
                style={{
                  minHeight: 220,
                  borderRadius: 22,
                  border: '1px solid var(--border-color)',
                }}
              />
            );
          })}
        </div>
      )
    };
  };

  const tabs = [
    { key: 'index', label: '指数', icon: <BarChartOutlined /> },
    { key: 'us', label: '美股', icon: <StockOutlined /> },
    { key: 'cn', label: 'A股', icon: <StockOutlined /> },
    { key: 'crypto', label: '加密', icon: <ThunderboltOutlined /> },
    { key: 'bond', label: '债券', icon: <BankOutlined /> },
    { key: 'future', label: '期货', icon: <PropertySafetyOutlined /> },
    { key: 'option', label: '期权', icon: <FundOutlined /> },
  ];

  return (
    <div className="realtime-panel-shell">
      {messageContextHolder}
      <Card
        className="realtime-hero-card"
        style={{
          marginBottom: 18,
          borderRadius: 28,
          overflow: 'hidden',
          border: '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)',
          boxShadow: '0 24px 60px rgba(15, 23, 42, 0.10)',
        }}
        styles={{ body: { padding: 0 } }}
      >
        <div className="realtime-hero">
          <div className="realtime-hero__copy">
            <div className="realtime-hero__eyebrow">Realtime Radar</div>
            <div className="realtime-hero__title-row">
              <Space>
                <Badge status={isConnected ? 'processing' : 'error'} />
                <Text strong style={{ fontSize: '22px', color: 'var(--text-primary)' }}>实时行情数据</Text>
              </Space>
              <Tag
                color={isConnected ? 'success' : 'error'}
                style={{ margin: 0, borderRadius: 999, paddingInline: 12, fontWeight: 700 }}
              >
                {isConnected ? '已连接' : '未连接'}
              </Tag>
            </div>
            <div className="realtime-hero__subtitle">
              把指数、美股、A股、加密、债券、期货和期权放进同一个实时工作台里，列表看盘，卡片直达深度详情。
            </div>
            <div className="realtime-hero__meta">
              <div className="realtime-hero__chip">已加载 {loadedQuotesCount}/{subscribedSymbols.length} 个标的</div>
              <div className="realtime-hero__chip">当前分组：{getCategoryLabel(activeTab)}</div>
              <div className="realtime-hero__chip">链路模式：{transportModeLabel}</div>
              <div className="realtime-hero__chip">最近成功刷新：{lastMarketUpdateLabel}</div>
              {reconnectAttempts > 0 && (
                <div className="realtime-hero__chip">重连次数：{reconnectAttempts}</div>
              )}
              <div className="realtime-hero__chip">新鲜 {freshnessSummary.fresh}/{currentTabSymbols.length}</div>
              {freshnessSummary.aging > 0 && (
                <div className="realtime-hero__chip">变旧 {freshnessSummary.aging}</div>
              )}
              {freshnessSummary.delayed > 0 && (
                <div className="realtime-hero__chip">延迟 {freshnessSummary.delayed}</div>
              )}
              {spotlightSymbol && (
                <div className="realtime-hero__chip">
                  焦点：{getDisplayName(spotlightSymbol)} {formatPercent(quotes[spotlightSymbol]?.change_percent)}
                </div>
              )}
            </div>
            <div
              style={{
                marginTop: 16,
                padding: '12px 14px',
                borderRadius: 16,
                border: `1px solid ${transportBannerStyle.borderColor}`,
                background: transportBannerStyle.background,
                color: transportBannerStyle.color,
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 13 }}>{transportBanner.title}</div>
              <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.6 }}>{transportBanner.description}</div>
            </div>
          </div>

          <div className="realtime-hero__actions">
            <div className="realtime-hero__toggle">
              <Text style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>自动更新</Text>
              <Switch
                checked={isAutoUpdate}
                onChange={toggleAutoUpdate}
                checkedChildren={<PlayCircleOutlined />}
                unCheckedChildren={<PauseCircleOutlined />}
              />
            </div>

            <Button
              type="primary"
              icon={<SyncOutlined spin={loading} />}
              onClick={refreshCurrentTab}
              loading={loading}
              size="large"
            >
              刷新
            </Button>
          </div>
        </div>
      </Card>

      <div className="realtime-toolbar-grid">
        <Card
          className="realtime-search-card"
          style={{
            borderRadius: 24,
            border: '1px solid var(--border-color)',
            boxShadow: '0 14px 34px rgba(15, 23, 42, 0.06)',
          }}
        >
          <div className="realtime-block-title">添加跟踪标的</div>
          <div className="realtime-block-subtitle">支持按代码、英文名和中文名搜索，添加后会自动进入对应分组。</div>
          <Space.Compact style={{ width: '100%', marginTop: 16 }}>
            <AutoComplete
              style={{ flex: 1 }}
              options={autoCompleteOptions}
              value={searchSymbol}
              onChange={handleSearch}
              onSelect={handleSelect}
            >
              <Input
                placeholder="搜索... (支持指数、美股、A股、加密货币、债券等)"
                prefix={<SearchOutlined />}
                allowClear
                size="large"
                onPressEnter={() => addSymbol(searchSymbol)}
              />
            </AutoComplete>
            <Button type="primary" size="large" onClick={() => addSymbol(searchSymbol)}>
              添加
            </Button>
          </Space.Compact>
        </Card>

        <div className="realtime-stats-grid">
          <Card className="realtime-stat-card realtime-stat-card--primary">
            <Statistic title="监控总数" value={subscribedSymbols.length} prefix={<RiseOutlined />} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--positive">
            <Statistic
              title="上涨"
              value={risingCount}
              valueStyle={{ color: 'var(--accent-success)' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--negative">
            <Statistic
              title="下跌"
              value={fallingCount}
              valueStyle={{ color: 'var(--accent-danger)' }}
              prefix={<ArrowDownOutlined />}
            />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--focus">
            <Statistic
              title="当前分组"
              value={currentTabSymbols.length}
              formatter={() => getCategoryLabel(activeTab)}
              prefix={tabs.find(tab => tab.key === activeTab)?.icon}
            />
          </Card>
        </div>
      </div>

      <Card
        className="realtime-board-card"
        style={{
          borderRadius: 28,
          border: '1px solid var(--border-color)',
          boxShadow: '0 18px 42px rgba(15, 23, 42, 0.07)',
        }}
      >
        <div className="realtime-board-head">
          <div>
            <div className="realtime-block-title">多市场看盘面板</div>
            <div className="realtime-block-subtitle">
              选中不同市场后按卡片浏览，点开即可进入完整的实时快照与全维分析详情。
            </div>
          </div>
          <div className="realtime-board-summary">
            <span>当前 {getCategoryLabel(activeTab)}</span>
            <strong>{currentTabSymbols.length}</strong>
          </div>
        </div>

        <Tabs
          type="card"
          activeKey={activeTab}
          onChange={setActiveTab}
          size="large"
          className="market-tabs"
          items={tabs.map(t => renderTabItem(t.key, t.label, t.icon))}
        />
      </Card>

      <Suspense fallback={null}>
        <TradePanel
          visible={isTradeModalVisible}
          defaultSymbol={selectedSymbol}
          onClose={handleCloseTrade}
          onSuccess={() => {
            messageApi.success('交易已记录');
          }}
        />
      </Suspense>

      {/* 详情模态框 */}
      <Suspense fallback={null}>
        <RealtimeStockDetailModal
          open={isDetailModalVisible}
          onCancel={handleCloseDetail}
          symbol={detailSymbol}
          quote={detailSymbol ? quotes[detailSymbol] || null : null}
        />
      </Suspense>

      <style>{`
        .realtime-panel-shell {
          padding: 16px;
          display: grid;
          gap: 18px;
          background:
            radial-gradient(circle at top left, color-mix(in srgb, var(--accent-primary) 10%, transparent 90%), transparent 34%),
            radial-gradient(circle at top right, color-mix(in srgb, var(--accent-secondary) 12%, transparent 88%), transparent 30%);
        }

        .realtime-hero {
          display: grid;
          grid-template-columns: minmax(0, 1.8fr) minmax(280px, 0.9fr);
          gap: 24px;
          padding: 28px;
          background:
            linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 14%, var(--bg-secondary) 86%) 0%, color-mix(in srgb, var(--accent-secondary) 12%, var(--bg-secondary) 88%) 100%);
        }

        .realtime-hero__eyebrow {
          font-size: 11px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--text-secondary);
          margin-bottom: 10px;
          font-weight: 700;
        }

        .realtime-hero__title-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }

        .realtime-hero__subtitle {
          margin-top: 14px;
          max-width: 720px;
          color: var(--text-secondary);
          line-height: 1.7;
          font-size: 14px;
        }

        .realtime-hero__meta {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 18px;
        }

        .realtime-hero__chip {
          padding: 8px 12px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
          font-size: 12px;
          color: var(--text-secondary);
        }

        .realtime-hero__actions {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 14px;
          padding: 18px;
          border-radius: 20px;
          background: color-mix(in srgb, var(--bg-secondary) 88%, white 12%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 18%, var(--border-color) 82%);
        }

        .realtime-hero__toggle {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }

        .realtime-toolbar-grid {
          display: grid;
          grid-template-columns: minmax(320px, 1.25fr) minmax(0, 1fr);
          gap: 18px;
        }

        .realtime-stats-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 14px;
        }

        .realtime-stat-card {
          border-radius: 22px;
          border: 1px solid var(--border-color);
          box-shadow: 0 12px 26px rgba(15, 23, 42, 0.06);
        }

        .realtime-stat-card--primary {
          background: linear-gradient(135deg, rgba(14, 165, 233, 0.14), rgba(56, 189, 248, 0.04));
        }

        .realtime-stat-card--positive {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.14), rgba(34, 197, 94, 0.04));
        }

        .realtime-stat-card--negative {
          background: linear-gradient(135deg, rgba(239, 68, 68, 0.14), rgba(239, 68, 68, 0.04));
        }

        .realtime-stat-card--focus {
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.14), rgba(168, 85, 247, 0.04));
        }

        .realtime-block-title {
          font-size: 18px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-block-subtitle {
          margin-top: 6px;
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.65;
        }

        .realtime-board-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 18px;
          flex-wrap: wrap;
        }

        .realtime-board-summary {
          display: inline-flex;
          align-items: baseline;
          gap: 10px;
          padding: 10px 14px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
          border: 1px solid var(--border-color);
          color: var(--text-secondary);
        }

        .realtime-board-summary strong {
          font-size: 22px;
          color: var(--text-primary);
        }

        .market-tabs .ant-tabs-nav {
          margin-bottom: 20px;
        }

        .market-tabs .ant-tabs-tab {
          border-radius: 999px !important;
          padding-inline: 16px !important;
        }

        .realtime-quote-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 16px;
          align-items: stretch;
        }

        .realtime-quote-card__surface {
          min-height: 100%;
          display: grid;
          gap: 16px;
        }

        .realtime-quote-card__header,
        .realtime-quote-card__price-row,
        .realtime-quote-card__footer {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .realtime-quote-card__tags {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
          flex-wrap: wrap;
        }

        .realtime-quote-card__name {
          margin-bottom: 4px;
        }

        .realtime-quote-card__source {
          text-align: right;
          min-width: 76px;
          padding: 10px 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--border-color) 80%, white 20%);
          color: var(--text-secondary);
        }

        .realtime-quote-card__price {
          font-size: 32px;
          line-height: 1;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: -0.03em;
        }

        .realtime-quote-card__delta {
          margin-top: 8px;
          font-size: 14px;
          font-weight: 700;
        }

        .realtime-quote-card__focus {
          min-width: 120px;
          text-align: right;
          padding: 10px 12px;
          border-radius: 16px;
          background: rgba(15, 23, 42, 0.04);
        }

        .realtime-quote-card__focus-label {
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__focus-value {
          margin-top: 6px;
          font-size: 13px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-quote-card__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }

        .realtime-quote-card__metric {
          padding: 12px;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.52);
          border: 1px solid rgba(148, 163, 184, 0.16);
          display: grid;
          gap: 8px;
        }

        .realtime-quote-card__metric span {
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__metric strong {
          font-size: 13px;
          line-height: 1.45;
          color: var(--text-primary);
          word-break: break-word;
        }

        .realtime-quote-card__footer {
          align-items: center;
          padding-top: 4px;
        }

        @media (max-width: 1180px) {
          .realtime-toolbar-grid,
          .realtime-hero {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 900px) {
          .realtime-stats-grid,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr 1fr;
          }
        }

        @media (max-width: 640px) {
          .realtime-panel-shell {
            padding: 12px;
          }

          .realtime-hero {
            padding: 18px;
          }

          .realtime-quote-grid,
          .realtime-stats-grid,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr;
          }

          .realtime-quote-card__header,
          .realtime-quote-card__price-row,
          .realtime-quote-card__footer {
            flex-direction: column;
            align-items: stretch;
          }

          .realtime-quote-card__source,
          .realtime-quote-card__focus {
            text-align: left;
          }
        }
      `}</style>
    </div>
  );
};

export default RealTimePanel;
