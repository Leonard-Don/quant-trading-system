import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
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
import TradePanel from './TradePanel';
import webSocketService from '../services/websocket';
import { STOCK_DATABASE } from '../constants/stocks';
import StockDetailModal from './StockDetailModal';

const { Text } = Typography;

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
    };
  }, [messageApi]);


  // 管理自动更新和连接
  useEffect(() => {
    if (isAutoUpdate) {
      webSocketService.connect().catch(err => {
        console.error("Failed to connect WS:", err);
        messageApi.error('无法建立实时数据连接');
      });
    } else {
      webSocketService.disconnect();
      setIsConnected(false);
    }
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

  // 获取实时报价
  const fetchQuotes = async () => {
    if (!subscribedSymbols.length) return;

    setLoading(true);
    try {
      // 这里的 API 此时应该是支持批量获取的
      const response = await api.get('/realtime/quotes', {
        params: { symbols: subscribedSymbols.join(',') }
      });

      if (response.data.success) {
        setQuotes(prev => ({ ...prev, ...response.data.data }));
      }
    } catch (error) {
      console.error('获取初始数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 添加新股票
  const addSymbol = (symbol) => {
    if (!symbol) return;
    const newSymbol = symbol.toUpperCase();
    if (subscribedSymbols.includes(newSymbol)) return;

    subscribeSymbol(newSymbol);
    setSearchSymbol('');
  };

  // 组件挂载时初始化
  useEffect(() => {
    if (isInitializedRef.current) return;
    isInitializedRef.current = true;
    fetchQuotes();

    // 如果已经连接，需要重新订阅（确保服务器端知道我们仍然订阅这些）
    return () => {
      // 保持连接，只清理组件内的监听器
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatPrice = (price) => {
    if (price === undefined || price === null || isNaN(price)) return '0.00';
    return typeof price === 'number' ? price.toFixed(2) : parseFloat(price).toFixed(2);
  };

  const formatPercent = (percent) => {
    if (percent === undefined || percent === null || isNaN(percent)) return '0.00%';
    return typeof percent === 'number' ? percent.toFixed(2) + '%' : parseFloat(percent).toFixed(2) + '%';
  };

  const formatVolume = (volume) => {
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

  const handleShowDetail = useCallback((symbol) => {
    setDetailSymbol(symbol);
    setIsDetailModalVisible(true);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setIsDetailModalVisible(false);
    // Don't clear detailSymbol here to prevent content flashing during close animation
    // setDetailSymbol(null); 
  }, []);

  const handleAfterClose = useCallback(() => {
    setDetailSymbol(null);
  }, []);



  const getDisplayName = (symbol) => {
    const info = STOCK_DATABASE[symbol];
    if (info) {
      return info.cn || info.en || symbol;
    }
    return symbol;
  };

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

  const renderQuoteCard = (symbol, quote) => {
    const isPositive = quote.change >= 0;
    const changeColor = isPositive ? 'var(--accent-success)' : 'var(--accent-danger)';
    const changeIcon = isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
    const info = STOCK_DATABASE[symbol];
    const isMarketIndex = info?.type === 'index';

    return (
      <Card
        key={symbol}
        size="small"
        style={{
          marginBottom: 8,
          borderLeft: `4px solid ${changeColor}`,
          backgroundColor: isMarketIndex ? 'rgba(56, 189, 248, 0.05)' : undefined
        }}
        styles={{ body: { padding: '12px' } }}
      >
        <div style={{ cursor: 'pointer' }} onClick={() => handleShowDetail(symbol)}>
          <Row align="middle" justify="space-between">
            <Col span={8}>
              <Space direction="vertical" size={0}>
                <Space>
                  {isMarketIndex && (
                    <Tag color="geekblue" style={{ margin: 0 }}>指数</Tag>
                  )}
                  {info?.type === 'crypto' && (
                    <Tag color="gold" style={{ margin: 0 }}>Crypto</Tag>
                  )}
                  <Text strong style={{ fontSize: '16px' }}>
                    {getDisplayName(symbol)}
                  </Text>
                </Space>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  {symbol} {new Date(quote.timestamp).toLocaleTimeString()}
                </Text>
              </Space>
            </Col>

            <Col span={8} style={{ textAlign: 'center' }}>
              <Space direction="vertical" size={0}>
                <Text strong style={{ fontSize: '18px' }}>
                  {formatPrice(quote.price)}
                </Text>
                <Space gutter={8}>
                  <Text style={{ color: changeColor, fontSize: '14px' }}>
                    {changeIcon} {formatPrice(Math.abs(quote.change))}
                  </Text>
                  <Text style={{ color: changeColor, fontSize: '14px' }}>
                    ({formatPercent(quote.change_percent)})
                  </Text>
                </Space>
                <Space gutter={8} style={{ fontSize: '12px', color: '#888', marginTop: 4 }}>
                  <span>高: {formatPrice(quote.high)}</span>
                  <span>低: {formatPrice(quote.low)}</span>
                </Space>
              </Space>
            </Col>

            <Col span={8} style={{ textAlign: 'right' }}>
              <Space>
                {!isMarketIndex && info?.type !== 'bond' && (
                  <Button
                    type="primary"
                    size="small"
                    onClick={(e) => { e.stopPropagation(); handleOpenTrade(symbol); }}
                    icon={<DollarOutlined />}
                    ghost
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
              <div style={{ marginTop: 4 }}>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  Vol: {formatVolume(quote.volume)}
                </Text>
              </div>
            </Col>
          </Row>
        </div>
      </Card>
    );
  };

  const getSymbolsByCategory = (category) => {
    return subscribedSymbols.filter(symbol => {
      const info = STOCK_DATABASE[symbol];
      if (!info) return category === 'us'; // Default unknown to US stock
      return info.type === category;
    });
  };

  const renderTabItem = (key, label, icon) => {
    const symbols = getSymbolsByCategory(key);
    return {
      key,
      label: <span>{icon} {label}</span>,
      children: symbols.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Text type="secondary">暂无{label}数据，请添加</Text>
        </div>
      ) : (
        <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
          {symbols.map(symbol => {
            const quote = quotes[symbol];
            return quote ? renderQuoteCard(symbol, quote) : (
              <Card key={symbol} loading style={{ marginBottom: 8 }} />
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
    <div style={{ padding: '16px' }}>
      {messageContextHolder}
      {/* 控制面板 */}
      <Card style={{ marginBottom: 16 }}>
        <Row align="middle" justify="space-between">
          <Col>
            <Space>
              <Badge status={isConnected ? "processing" : "error"} />
              <Text strong style={{ fontSize: '18px' }}>实时行情数据</Text>
              <Tag color={isConnected ? "success" : "error"}>
                {isConnected ? "已连接" : "未连接"}
              </Tag>
            </Space>
          </Col>

          <Col>
            <Space>
              <Text>自动更新</Text>
              <Switch
                checked={isAutoUpdate}
                onChange={toggleAutoUpdate}
                checkedChildren={<PlayCircleOutlined />}
                unCheckedChildren={<PauseCircleOutlined />}
              />

              <Button
                type="primary"
                icon={<SyncOutlined spin={loading} />}
                onClick={fetchQuotes}
                loading={loading}
              >
                刷新
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 添加股票 */}
      <Card style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: '100%' }}>
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
            />
          </AutoComplete>
          <Button type="primary" size="large" onClick={() => handleSearch(searchSymbol) && handleSelect(searchSymbol)}>
            添加
          </Button>
        </Space.Compact>
      </Card>

      {/* 市场概览统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small">
            <Statistic title="监控总数" value={subscribedSymbols.length} prefix={<RiseOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="上涨"
              value={Object.values(quotes).filter(q => q.change > 0).length}
              valueStyle={{ color: 'var(--accent-success)' }}
              prefix={<ArrowUpOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="下跌"
              value={Object.values(quotes).filter(q => q.change < 0).length}
              valueStyle={{ color: 'var(--accent-danger)' }}
              prefix={<ArrowDownOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 分类展示 */}
      <div className="card-container">
        <Tabs
          type="card"
          activeKey={activeTab}
          onChange={setActiveTab}
          size="large"
          className="market-tabs"
          items={tabs.map(t => renderTabItem(t.key, t.label, t.icon))}
        />
      </div>

      <TradePanel
        visible={isTradeModalVisible}
        defaultSymbol={selectedSymbol}
        onClose={handleCloseTrade}
        onSuccess={() => {
          messageApi.success('交易已记录');
        }}
      />

      {/* 详情模态框 */}
      <StockDetailModal
        visible={isDetailModalVisible}
        symbol={detailSymbol}
        onClose={handleCloseDetail}
        afterClose={handleAfterClose}
      />

      <style>{`
        .market-tabs .ant-tabs-nav {
          margin-bottom: 16px;
        }
      `}</style>
    </div>
  );
};

export default RealTimePanel;
