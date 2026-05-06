import React, { useState, useEffect, useCallback, useMemo, Suspense } from 'react';
import { App as AntdApp, Layout, Typography, Menu, Space, Button, Tooltip, Spin, Grid } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  LineChartOutlined,
  MenuOutlined,
  SunOutlined,
  MoonOutlined,
  FireOutlined,
  FundOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import ErrorBoundary from './components/ErrorBoundary';
import {
  getStrategies,
  runBacktest,
  createResearchJournalEntry,
  getRealtimeQuote,
  submitPaperOrder,
} from './services/api';
import { buildBacktestJournalEntry } from './utils/backtestJournalEntry';
import {
  buildPrefillFromBacktest,
  canAutoExecutePrefill,
  setPaperPrefill,
} from './utils/paperTradingPrefill';
import { useTheme } from './contexts/ThemeContext';
import { APP_VERSION } from './generated/version';
import { useAppUrlState } from './hooks/useAppUrlState';
import { replaceAppUrl } from './utils/appUrlState';
import lazyWithRetry from './utils/lazyWithRetry';
import { buildViewUrlForCurrentState, navigateToAppUrl } from './utils/researchContext';

// 懒加载非核心组件，减少初始包大小

const RealTimePanel = lazyWithRetry(() => import('./components/RealTimePanel'));
const IndustryDashboard = lazyWithRetry(() => import('./components/IndustryDashboard'));
const BacktestDashboard = lazyWithRetry(() => import('./components/BacktestDashboard'));
const TodayResearchDashboard = lazyWithRetry(() => import('./components/TodayResearchDashboard'));
const PaperTradingPanel = lazyWithRetry(() => import('./components/PaperTradingPanel'));

// 懒加载占位组件
const LazyLoadFallback = () => (
  <div style={{
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    height: '300px'
  }}>
    <Spin size="large" />
    <div style={{ marginTop: 12, color: '#8c8c8c' }}>加载中...</div>
  </div>
);

const { Header, Content, Sider } = Layout;
const { Title } = Typography;
const { useBreakpoint } = Grid;
const VIEW_QUERY_KEY = 'view';
const VALID_VIEWS = new Set(['today', 'backtest', 'realtime', 'industry', 'paper']);
const WIDE_VIEW_SET = new Set(['today', 'backtest', 'industry', 'paper']);
const FULL_VIEW_SET = new Set(['realtime']);
const readViewStateFromLocation = (search = window.location.search, revision = 0) => {
  const params = new URLSearchParams(search);
  const requestedView = params.get(VIEW_QUERY_KEY);

  if (requestedView === 'alerts') {
    return {
      currentView: 'realtime',
      realtimeAuxIntent: `alerts:${revision}`,
    };
  }

  if (requestedView && VALID_VIEWS.has(requestedView)) {
    return {
      currentView: requestedView,
      realtimeAuxIntent: null,
    };
  }

  return {
    currentView: 'backtest',
    realtimeAuxIntent: null,
  };
};

function App() {
  const { message } = AntdApp.useApp();
  const screens = useBreakpoint();
  const isMobile = !screens.lg;
  const locationState = useAppUrlState();
  // Theme
  const { isDarkMode, toggleTheme } = useTheme();
  // ... (existing state)
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [strategiesLoaded, setStrategiesLoaded] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const viewState = useMemo(
    () => readViewStateFromLocation(locationState.search, locationState.revision),
    [locationState.revision, locationState.search],
  );
  const { currentView, realtimeAuxIntent } = viewState;
  const primaryNavigationId = 'app-primary-navigation';
  const mobileMenuLabel = mobileMenuOpen ? '收起导航菜单' : '展开导航菜单';
  const themeToggleLabel = isDarkMode ? '切换到浅色主题' : '切换到深色主题';
  const viewFrameClassName = FULL_VIEW_SET.has(currentView)
    ? 'app-view-frame app-view-frame--full'
    : WIDE_VIEW_SET.has(currentView)
      ? 'app-view-frame app-view-frame--wide'
      : 'app-view-frame app-view-frame--focused';

  const loadStrategies = useCallback(async () => {
    if (strategiesLoaded) {
      return;
    }
    try {
      const data = await getStrategies();
      setStrategies(data);
      setStrategiesLoaded(true);
    } catch (error) {
      message.error('加载策略失败: ' + error.message);
    }
  }, [message, strategiesLoaded]);

  useEffect(() => {
    if (currentView === 'backtest' && !strategiesLoaded) {
      loadStrategies();
    }
  }, [currentView, strategiesLoaded, loadStrategies]);

  useEffect(() => {
    const nextUrl = buildViewUrlForCurrentState(
      currentView,
      locationState.search,
      locationState.pathname,
    );

    if (nextUrl !== locationState.href) {
      replaceAppUrl(nextUrl);
    }
  }, [currentView, locationState.href, locationState.pathname, locationState.search]);

  useEffect(() => {
    if (!isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile]);

  const handleBacktest = async (formData) => {
    setLoading(true);

    try {
      message.loading('正在运行回测...', 0);
      const result = await runBacktest(formData);
      message.destroy();

      if (result.success) {
        setResults(result.data);
        message.success({
          content: '回测完成！',
          duration: 3,
        });
        // Auto-archive to research journal. Best-effort: a journal failure must
        // never disturb the visible backtest result, which is the primary user
        // outcome here.
        const journalEntry = buildBacktestJournalEntry(formData, result.data);
        if (journalEntry) {
          createResearchJournalEntry(journalEntry).catch((archiveError) => {
            console.warn('Auto-archive to research journal failed:', archiveError);
          });
        }
      } else {
        message.error({
          content: '回测失败: ' + result.error,
          duration: 5,
        });
      }
    } catch (error) {
      message.destroy();
      console.error('Backtest error:', error);
      message.error({
        content: '回测失败: ' + (error.message || '未知错误'),
        duration: 5,
      });
    } finally {
      setLoading(false);
    }
  };

  const menuItems = [
    {
      key: 'today',
      icon: <FundOutlined />,
      label: '今日研究',
    },
    {
      key: 'backtest',
      icon: <BarChartOutlined />,
      label: '策略回测',
    },
    {
      key: 'realtime',
      icon: <LineChartOutlined />,
      label: '实时行情',
    },

    {
      key: 'industry',
      icon: <FireOutlined />,
      label: '行业热度',
    },
    {
      key: 'paper',
      icon: <ThunderboltOutlined />,
      label: '纸面账户',
    }
  ];

  const setCurrentView = useCallback((nextView) => {
    const nextUrl = buildViewUrlForCurrentState(
      nextView,
      locationState.search,
      locationState.pathname,
    );
    navigateToAppUrl(nextUrl);
    if (isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile, locationState.pathname, locationState.search]);

  const handleSendBacktestToPaper = useCallback((backtestResult) => {
    const prefill = buildPrefillFromBacktest(backtestResult);
    if (!prefill) {
      message.warning('当前回测结果不足以预填纸面订单（缺少标的或成交记录）');
      return;
    }
    setPaperPrefill(prefill);
    setCurrentView('paper');
  }, [message, setCurrentView]);

  const handleAutoExecuteBacktestToPaper = useCallback(async (backtestResult) => {
    const prefill = buildPrefillFromBacktest(backtestResult);
    if (!canAutoExecutePrefill(prefill)) {
      message.warning('当前回测结果缺少有效成交信息，无法直接下单');
      return;
    }

    // Best-effort: any failure (quote unavailable, order rejected) falls
    // back to the F path so the user lands in the paper workspace with a
    // prefilled form rather than a dead end.
    try {
      const quoteResp = await getRealtimeQuote(prefill.symbol);
      const quotePayload = quoteResp?.data || quoteResp || {};
      const price = Number(quotePayload.price ?? quotePayload.last_price ?? quotePayload.close);
      if (!Number.isFinite(price) || price <= 0) {
        message.warning('行情不可用，已切到手填模式');
        setPaperPrefill(prefill);
        setCurrentView('paper');
        return;
      }
      await submitPaperOrder({
        symbol: prefill.symbol,
        side: prefill.side,
        quantity: prefill.quantity,
        fill_price: price,
        commission: 0,
        slippage_bps: 0,
      });
      message.success(
        `已按市价 $${price.toFixed(2)} 下单 ${prefill.side} ${prefill.quantity} ${prefill.symbol}`,
      );
      setCurrentView('paper');
    } catch (error) {
      const detail = error?.response?.data?.error?.message
        || error?.response?.data?.detail
        || error?.message
        || '下单失败';
      message.error(`直接下单失败：${detail}（已切到手填模式）`);
      setPaperPrefill(prefill);
      setCurrentView('paper');
    }
  }, [message, setCurrentView]);

  const renderContent = () => {
    switch (currentView) {
      case 'today':
        return <Suspense fallback={<LazyLoadFallback />}><TodayResearchDashboard /></Suspense>;

      case 'realtime':
        return <Suspense fallback={<LazyLoadFallback />}><RealTimePanel openAlertsSignal={realtimeAuxIntent} /></Suspense>;

      case 'industry':
        return <Suspense fallback={<LazyLoadFallback />}><IndustryDashboard /></Suspense>;

      case 'paper':
        return <Suspense fallback={<LazyLoadFallback />}><PaperTradingPanel /></Suspense>;
      case 'backtest':
      default:
        return (
          <Suspense fallback={<LazyLoadFallback />}>
            <BacktestDashboard
              strategies={strategies}
              onSubmit={handleBacktest}
              loading={loading}
              results={results}
              onSendToPaperTrading={handleSendBacktestToPaper}
              onAutoExecuteToPaperTrading={handleAutoExecuteBacktestToPaper}
            />
          </Suspense>
        );
    }
  };

  return (
    <ErrorBoundary>
      <Layout className="app-root-layout">
        <Header className="app-main-header">
          <div className="app-brand">
            {isMobile ? (
              <Button
                className="app-main-header__menu-trigger"
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setMobileMenuOpen((open) => !open)}
                aria-label={mobileMenuLabel}
                aria-controls={primaryNavigationId}
                aria-expanded={mobileMenuOpen}
                style={{
                  color: 'var(--text-primary)',
                  fontSize: '16px',
                }}
              />
            ) : null}
            <DashboardOutlined className="app-brand__mark" style={{
              fontSize: '22px',
              color: 'var(--accent-primary)'
            }} />
            <div className="app-brand__identity">
              <Title className="app-brand__title" level={4} style={{
                margin: 0,
                fontWeight: 700,
                letterSpacing: '0.5px',
                color: 'var(--text-primary)',
                fontSize: '18px',
                lineHeight: '1'
              }}>
                量化交易系统
              </Title>
              <span className="app-brand__version" style={{
                fontSize: '10px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'var(--accent-primary-soft)',
                color: 'var(--accent-primary)',
                fontWeight: 500,
                lineHeight: '1.4'
              }}>{`v${APP_VERSION}`}</span>
            </div>
          </div>
          <Space className="app-main-header__actions" size={16}>
            <Tooltip title={themeToggleLabel}>
              <Button
                className="app-main-header__theme-toggle"
                type="text"
                icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggleTheme}
                aria-label={themeToggleLabel}
                aria-pressed={isDarkMode}
                style={{
                  color: 'var(--text-primary)',
                  fontSize: '16px'
                }}
              />
            </Tooltip>
          </Space>
        </Header>
        <Layout className="app-main-shell">
          <Sider
            id={primaryNavigationId}
            aria-label="主导航"
            className="app-main-sider"
            width={220}
            collapsible
            trigger={null}
            collapsed={isMobile ? !mobileMenuOpen : false}
            collapsedWidth={isMobile ? 0 : 64}
          >
            <Menu
              className="app-main-menu"
              mode="inline"
              selectedKeys={[currentView]}
              items={menuItems}
              onClick={({ key }) => {
                setCurrentView(key);
              }}
            />
          </Sider>
          <Layout className="app-main-body">
            <Content className="app-main-content">
              <div className={viewFrameClassName}>
                {renderContent()}
              </div>
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </ErrorBoundary>
  );
}

export default App;
