import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { App as AntdApp, Layout, Typography, Menu, Space, Button, Tooltip, Spin, Badge, Grid } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  LineChartOutlined,
  MenuOutlined,
  SunOutlined,
  MoonOutlined,
  FireOutlined,
  FundOutlined,
  RadarChartOutlined,
  FolderOutlined,
} from '@ant-design/icons';

import ErrorBoundary from './components/ErrorBoundary';
import { getStrategies, runBacktest } from './services/api';
import { useTheme } from './contexts/ThemeContext';
import { APP_VERSION } from './generated/version';
import { buildViewUrlForCurrentState } from './utils/researchContext';

// 懒加载非核心组件，减少初始包大小


const AlertCenter = lazy(() => import('./components/AlertCenter'));
const RealTimePanel = lazy(() => import('./components/RealTimePanel'));
const IndustryDashboard = lazy(() => import('./components/IndustryDashboard'));
const BacktestDashboard = lazy(() => import('./components/BacktestDashboard'));
const PricingResearch = lazy(() => import('./components/PricingResearch'));
const GodEyeDashboard = lazy(() => import('./components/GodEyeDashboard'));
const ResearchWorkbench = lazy(() => import('./components/ResearchWorkbench'));
const QuantLab = lazy(() => import('./components/QuantLab'));

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
const VALID_VIEWS = new Set(['backtest', 'realtime', 'industry', 'pricing', 'godsEye', 'godeye', 'workbench', 'quantlab']);
const INDUSTRY_ALERT_BADGE_STORAGE_KEY = 'industry_alert_badge_count_v1';
const INDUSTRY_ALERT_BADGE_EVENT = 'industry-alert-badge-update';

const readViewStateFromLocation = (search = window.location.search) => {
  const params = new URLSearchParams(search);
  const requestedView = params.get(VIEW_QUERY_KEY);

  if (requestedView === 'alerts') {
    return {
      currentView: 'realtime',
      realtimeAuxIntent: `alerts:${Date.now()}`,
    };
  }

  if (requestedView && VALID_VIEWS.has(requestedView)) {
    return {
      currentView: requestedView === 'godeye' ? 'godsEye' : requestedView,
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
  // Theme
  const { isDarkMode, toggleTheme } = useTheme();
  // ... (existing state)
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [viewState, setViewState] = useState(() => readViewStateFromLocation());
  const [strategiesLoaded, setStrategiesLoaded] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [industryAlertBadgeCount, setIndustryAlertBadgeCount] = useState(() => {
    const value = window.localStorage.getItem(INDUSTRY_ALERT_BADGE_STORAGE_KEY);
    const numericValue = Number(value || 0);
    return Number.isFinite(numericValue) ? Math.max(0, numericValue) : 0;
  });
  const { currentView, realtimeAuxIntent } = viewState;

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
    const applyViewFromUrl = () => {
      setViewState(readViewStateFromLocation());
    };

    applyViewFromUrl();
    window.addEventListener('popstate', applyViewFromUrl);
    return () => window.removeEventListener('popstate', applyViewFromUrl);
  }, []);

  useEffect(() => {
    const syncIndustryAlertBadge = () => {
      const value = window.localStorage.getItem(INDUSTRY_ALERT_BADGE_STORAGE_KEY);
      const numericValue = Number(value || 0);
      setIndustryAlertBadgeCount(Number.isFinite(numericValue) ? Math.max(0, numericValue) : 0);
    };

    syncIndustryAlertBadge();
    window.addEventListener(INDUSTRY_ALERT_BADGE_EVENT, syncIndustryAlertBadge);
    window.addEventListener('storage', syncIndustryAlertBadge);
    return () => {
      window.removeEventListener(INDUSTRY_ALERT_BADGE_EVENT, syncIndustryAlertBadge);
      window.removeEventListener('storage', syncIndustryAlertBadge);
    };
  }, []);

  useEffect(() => {
    const nextUrl = buildViewUrlForCurrentState(currentView);
    window.history.replaceState(null, '', nextUrl);
  }, [currentView]);

  useEffect(() => {
    if (!isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile]);

  const handleBacktest = async (formData) => {
    setLoading(true);
    setResults(null);

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
      label: (
        <Badge
          count={industryAlertBadgeCount}
          size="small"
          overflowCount={99}
          offset={[10, 0]}
          styles={{ indicator: { boxShadow: 'none' } }}
        >
          <span style={{ paddingRight: industryAlertBadgeCount > 0 ? 16 : 0 }}>行业热度</span>
        </Badge>
      ),
    },
    {
      key: 'pricing',
      icon: <FundOutlined />,
      label: '定价研究',
    },
    {
      key: 'godsEye',
      icon: <RadarChartOutlined />,
      label: '上帝视角',
    },
    {
      key: 'workbench',
      icon: <FolderOutlined />,
      label: '研究工作台',
    },
    {
      key: 'quantlab',
      icon: <DashboardOutlined />,
      label: 'Quant Lab',
    }
  ];

  const setCurrentView = useCallback((nextView) => {
    setViewState((prev) => ({
      ...prev,
      currentView: nextView,
      realtimeAuxIntent: nextView === 'realtime' ? prev.realtimeAuxIntent : null,
    }));
    if (isMobile) {
      setMobileMenuOpen(false);
    }
  }, [isMobile]);

  const renderContent = () => {
    switch (currentView) {

      case 'realtime':
        return <Suspense fallback={<LazyLoadFallback />}><RealTimePanel openAlertsSignal={realtimeAuxIntent} /></Suspense>;

      case 'industry':
        return <Suspense fallback={<LazyLoadFallback />}><IndustryDashboard /></Suspense>;

      case 'pricing':
        return <Suspense fallback={<LazyLoadFallback />}><PricingResearch /></Suspense>;
      case 'godsEye':
      case 'godeye':
        return <Suspense fallback={<LazyLoadFallback />}><GodEyeDashboard /></Suspense>;
      case 'workbench':
        return <Suspense fallback={<LazyLoadFallback />}><ResearchWorkbench /></Suspense>;
      case 'quantlab':
        return <Suspense fallback={<LazyLoadFallback />}><QuantLab /></Suspense>;
      case 'backtest':
      default:
        return (
          <Suspense fallback={<LazyLoadFallback />}>
            <BacktestDashboard
              strategies={strategies}
              onSubmit={handleBacktest}
              loading={loading}
              results={results}
            />
          </Suspense>
        );
    }
  };

  return (
    <ErrorBoundary>
      <Layout style={{ height: '100vh' }}>
        <Header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {isMobile ? (
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setMobileMenuOpen((open) => !open)}
                aria-label="切换导航菜单"
                style={{
                  color: 'var(--text-primary)',
                  fontSize: '16px',
                }}
              />
            ) : null}
            <DashboardOutlined style={{
              fontSize: '22px',
              color: 'var(--accent-primary)'
            }} />
            <Title level={4} style={{
              margin: 0,
              fontWeight: 700,
              letterSpacing: '0.5px',
              color: 'var(--text-primary)',
              fontSize: '18px',
              lineHeight: '1'
            }}>
              量化交易系统
            </Title>
            <span style={{
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '4px',
              background: 'var(--accent-primary-soft)',
              color: 'var(--accent-primary)',
              fontWeight: 500,
              lineHeight: '1.4'
            }}>{`v${APP_VERSION}`}</span>
          </div>
          <Space size={16}>
            <Tooltip title={isDarkMode ? '切换到浅色主题' : '切换到深色主题'}>
              <Button
                type="text"
                icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggleTheme}
                style={{
                  color: 'var(--text-primary)',
                  fontSize: '16px'
                }}
              />
            </Tooltip>
            <Suspense fallback={null}>
              <AlertCenter />
            </Suspense>
          </Space>
        </Header>
        <Layout>
          <Sider
            width={220}
            collapsible
            trigger={null}
            collapsed={isMobile ? !mobileMenuOpen : false}
            collapsedWidth={isMobile ? 0 : 64}
            style={isMobile ? {
              position: 'fixed',
              left: 0,
              top: 64,
              bottom: 0,
              zIndex: 1000,
            } : undefined}
          >
            <Menu
              mode="inline"
              selectedKeys={[currentView]}
              items={menuItems}
              onClick={({ key }) => {
                setCurrentView(key);
              }}
              style={{
                height: '100%',
                borderRight: 0,
                padding: '16px 0'
              }}
            />
          </Sider>
          <Layout style={{ padding: '0' }}>
            <Content style={{
              padding: isMobile ? '16px' : '24px',
              margin: 0,
              minHeight: '280px',
              overflow: 'auto'
            }}>
              <div style={{ maxWidth: '1600px', margin: '0 auto' }}>
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
