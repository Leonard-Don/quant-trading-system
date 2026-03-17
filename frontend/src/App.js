import React, { useState, useEffect, lazy, Suspense } from 'react';
import { Layout, Typography, message, Menu, Space, Button, Tooltip, Spin } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  LineChartOutlined,
  SunOutlined,
  MoonOutlined,
  BellOutlined,
  FireOutlined,
  FundOutlined,
  RadarChartOutlined
} from '@ant-design/icons';

import ErrorBoundary from './components/ErrorBoundary';
import { getStrategies, runBacktest } from './services/api';
import { useTheme } from './contexts/ThemeContext';

// 懒加载非核心组件，减少初始包大小


const AlertCenter = lazy(() => import('./components/AlertCenter'));
const RealTimePanel = lazy(() => import('./components/RealTimePanel'));


const PriceAlerts = lazy(() => import('./components/PriceAlerts'));
const IndustryDashboard = lazy(() => import('./components/IndustryDashboard'));
const BacktestDashboard = lazy(() => import('./components/BacktestDashboard'));
const PricingResearch = lazy(() => import('./components/PricingResearch'));
const GodEyeDashboard = lazy(() => import('./components/GodEyeDashboard'));

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
const VIEW_QUERY_KEY = 'view';
const VALID_VIEWS = new Set(['backtest', 'realtime', 'industry', 'alerts', 'pricing', 'godsEye']);

function App() {
  // Theme
  const { isDarkMode, toggleTheme } = useTheme();
  // ... (existing state)
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [currentView, setCurrentView] = useState('backtest');

  useEffect(() => {
    loadStrategies();
  }, []);

  useEffect(() => {
    const applyViewFromUrl = () => {
      const params = new URLSearchParams(window.location.search);
      const nextView = params.get(VIEW_QUERY_KEY);
      if (nextView && VALID_VIEWS.has(nextView)) {
        setCurrentView(nextView);
      }
    };

    applyViewFromUrl();
    window.addEventListener('popstate', applyViewFromUrl);
    return () => window.removeEventListener('popstate', applyViewFromUrl);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (currentView === 'backtest') {
      params.delete(VIEW_QUERY_KEY);
    } else {
      params.set(VIEW_QUERY_KEY, currentView);
    }
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
    window.history.replaceState(null, '', nextUrl);
  }, [currentView]);

  const loadStrategies = async () => {
    try {
      const data = await getStrategies();
      setStrategies(data);
    } catch (error) {
      message.error('加载策略失败: ' + error.message);
    }
  };

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
      label: '行业热度',
    },

    {
      key: 'alerts',
      icon: <BellOutlined />,
      label: '价格提醒',
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
    }
  ];

  const renderContent = () => {
    switch (currentView) {

      case 'realtime':
        return <Suspense fallback={<LazyLoadFallback />}><RealTimePanel /></Suspense>;

      case 'industry':
        return <Suspense fallback={<LazyLoadFallback />}><IndustryDashboard /></Suspense>;

      case 'alerts':
        return <Suspense fallback={<LazyLoadFallback />}><PriceAlerts /></Suspense>;

      case 'pricing':
        return <Suspense fallback={<LazyLoadFallback />}><PricingResearch /></Suspense>;
      case 'godsEye':
        return <Suspense fallback={<LazyLoadFallback />}><GodEyeDashboard /></Suspense>;
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
            }}>v3.3.0</span>
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
            <AlertCenter />
          </Space>
        </Header>
        <Layout>
          <Sider
            width={220}
            breakpoint={null}
            collapsedWidth={64}
          >
            <Menu
              mode="inline"
              selectedKeys={[currentView]}
              items={menuItems}
              onClick={({ key }) => setCurrentView(key)}
              style={{
                height: '100%',
                borderRight: 0,
                padding: '16px 0'
              }}
            />
          </Sider>
          <Layout style={{ padding: '0' }}>
            <Content style={{
              padding: '24px',
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
