import React, { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react';
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
import api from '../services/api';
import webSocketService from '../services/websocket';
import { STOCK_DATABASE } from '../constants/stocks';

const { Text } = Typography;
const DEFAULT_PRICE_TEXT = '0.00';
const EMPTY_NUMERIC_TEXT = '--';
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

const RealTimePanel = () => {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [quotes, setQuotes] = useState({});
  // 默认订阅初始列表
  const [subscribedSymbols, setSubscribedSymbols] = useState([
    // 指数
    '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
    // 美股
    'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
    // A股
    '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
    // 加密
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
    // 债券
    '^TNX', '^TYX', 'TLT',
    // 期货
    'GC=F', 'CL=F', 'SI=F',
    // 期权
    'SPY', 'QQQ', 'UVXY'
  ]);
  const [isConnected, setIsConnected] = useState(false);
  const [isAutoUpdate, setIsAutoUpdate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [searchSymbol, setSearchSymbol] = useState('');
  const [activeTab, setActiveTab] = useState('index');

  // Trade Modal State
  const [isTradeModalVisible, setIsTradeModalVisible] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  // Detail Modal State
  const [isDetailModalVisible, setIsDetailModalVisible] = useState(false);
  const [detailSymbol, setDetailSymbol] = useState(null);

  const isInitializedRef = useRef(false);  // 追踪是否已初始化，防止StrictMode重复执行
  const shownMessagesRef = useRef(new Set());  // 追踪已显示的消息
  const previousSubscribedSymbolsRef = useRef(new Set());
  const connectTimerRef = useRef(null);

  // 初始化WebSocket监听器
  useEffect(() => {
    // 注册连接状态监听
    const removeConnectionListener = webSocketService.addListener('connection', (data) => {
      setIsConnected(data.status === 'connected');
      if (data.status === 'connected') {
        setLoading(false);
        if (!shownMessagesRef.current.has('connected')) {
          shownMessagesRef.current.add('connected');
          messageApi.success('实时数据连接已建立');
        }
      }
    });

    // 注册实时报价监听
    const removeQuoteListener = webSocketService.addListener('quote', (data) => {
      const { symbol, data: quoteData } = data;
      setQuotes(prev => ({
        ...prev,
        [symbol]: quoteData
      }));
    });

    // 注册错误监听
    const removeErrorListener = webSocketService.addListener('error', (data) => {
      console.error('WebSocket Error:', data.error);
      setIsConnected(false);
    });

    return () => {
      removeConnectionListener();
      removeQuoteListener();
      removeErrorListener();
      webSocketService.disconnect({ resetSubscriptions: true });
    };
  }, [messageApi]);


  // 管理自动更新和连接
  useEffect(() => {
    if (isAutoUpdate) {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
      }

      // React StrictMode 下首轮 mount/unmount 会非常快，延迟一点再连可以避免假性 WS 警告。
      connectTimerRef.current = setTimeout(() => {
        webSocketService.connect().catch(err => {
          console.error("Failed to connect WS:", err);
          messageApi.error('无法建立实时数据连接');
        });
      }, 80);
    } else {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
        connectTimerRef.current = null;
      }
      webSocketService.disconnect();
      setIsConnected(false);
    }

    return () => {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
        connectTimerRef.current = null;
      }
    };
  }, [isAutoUpdate, messageApi]);

  // 监听订阅列表变化，只同步增量订阅
  useEffect(() => {
    const previousSymbols = previousSubscribedSymbolsRef.current;
    const nextSymbols = new Set(subscribedSymbols);

    const addedSymbols = subscribedSymbols.filter(symbol => !previousSymbols.has(symbol));
    const removedSymbols = Array.from(previousSymbols).filter(symbol => !nextSymbols.has(symbol));

    if (addedSymbols.length > 0) {
      webSocketService.subscribe(addedSymbols);
    }

    if (removedSymbols.length > 0) {
      webSocketService.unsubscribe(removedSymbols);
    }

    previousSubscribedSymbolsRef.current = nextSymbols;
  }, [subscribedSymbols]);


  // 订阅股票
  const subscribeSymbol = (symbol) => {
    if (!subscribedSymbols.includes(symbol)) {
      const newSymbols = [...subscribedSymbols, symbol];
      setSubscribedSymbols(newSymbols);

        const msgKey = `subscribed_${symbol}`;
      if (!shownMessagesRef.current.has(msgKey)) {
        shownMessagesRef.current.add(msgKey);
        messageApi.success(`已订阅 ${symbol} 的实时数据`);
      }
    }
  };

  // 移除股票
  const removeSymbol = (symbol) => {
    setSubscribedSymbols(prev => prev.filter(s => s !== symbol));
    setQuotes(prev => {
      const next = { ...prev };
      delete next[symbol];
      return next;
    });
  };

  // 切换自动更新
  const toggleAutoUpdate = (checked) => {
    setIsAutoUpdate(checked);
  };

  const getSymbolsByCategory = useCallback((category) => {
    return subscribedSymbols.filter(symbol => {
      const info = STOCK_DATABASE[symbol];
      if (!info) return category === 'us';
      return info.type === category;
    });
  }, [subscribedSymbols]);

  // 获取实时报价
  const fetchQuotes = useCallback(async (symbols = subscribedSymbols) => {
    const targetSymbols = Array.isArray(symbols) ? symbols.filter(Boolean) : [symbols].filter(Boolean);
    if (!targetSymbols.length) return;

    setLoading(true);
    try {
      const response = await api.get('/realtime/quotes', {
        params: { symbols: targetSymbols.join(',') }
      });

      if (response.data.success) {
        setQuotes(prev => ({ ...prev, ...response.data.data }));
      }
    } catch (error) {
      console.error('获取初始数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [subscribedSymbols]);

  // 添加新股票
  const addSymbol = (symbol) => {
    if (!symbol) return;
    const newSymbol = symbol.trim().toUpperCase();
    if (subscribedSymbols.includes(newSymbol)) return;

    subscribeSymbol(newSymbol);
    const nextCategory = STOCK_DATABASE[newSymbol]?.type;
    if (nextCategory) {
      setActiveTab(nextCategory);
    }
    fetchQuotes([newSymbol]);
    setSearchSymbol('');
    setAutoCompleteOptions([]);
  };

  // 组件挂载时初始化
  useEffect(() => {
    if (isInitializedRef.current) return;
    isInitializedRef.current = true;
    fetchQuotes(getSymbolsByCategory(activeTab));

    // 如果已经连接，需要重新订阅（确保服务器端知道我们仍然订阅这些）
    return () => {
      // 保持连接，只清理组件内的监听器
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const missingSymbols = getSymbolsByCategory(activeTab).filter(symbol => !quotes[symbol]);
    if (missingSymbols.length > 0) {
      fetchQuotes(missingSymbols);
    }
  }, [activeTab, fetchQuotes, getSymbolsByCategory, quotes]);

  const formatPrice = (price, fallback = DEFAULT_PRICE_TEXT) => {
    if (price === undefined || price === null || isNaN(price)) return fallback;
    return typeof price === 'number' ? price.toFixed(2) : parseFloat(price).toFixed(2);
  };

  const formatPercent = (percent) => {
    if (percent === undefined || percent === null || isNaN(percent)) return '0.00%';
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

  const [autoCompleteOptions, setAutoCompleteOptions] = useState([]);

  const risingCount = Object.values(quotes).filter(q => q?.change > 0).length;
  const fallingCount = Object.values(quotes).filter(q => q?.change < 0).length;
  const currentTabSymbols = getSymbolsByCategory(activeTab);
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

  const renderQuoteCard = (symbol, quote) => {
    const isPositive = Number(quote.change ?? 0) >= 0;
    const changeColor = isPositive ? 'var(--accent-success)' : 'var(--accent-danger)';
    const changeIcon = isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
    const info = STOCK_DATABASE[symbol];
    const categoryTheme = getCategoryTheme(info?.type);
    const isMarketIndex = info?.type === 'index';

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
                    background: isPositive ? 'rgba(34, 197, 94, 0.14)' : 'rgba(239, 68, 68, 0.14)',
                    fontWeight: 700,
                  }}
                >
                  {formatPercent(quote.change_percent)}
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
                {changeIcon} {formatPrice(Math.abs(quote.change))} · {formatPercent(quote.change_percent)}
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
              {!isMarketIndex && info?.type !== 'bond' && (
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
              {spotlightSymbol && (
                <div className="realtime-hero__chip">
                  焦点：{getDisplayName(spotlightSymbol)} {formatPercent(quotes[spotlightSymbol]?.change_percent)}
                </div>
              )}
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
              onClick={fetchQuotes}
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
