import React, { useState, useEffect } from 'react';
import {
  Badge,
  Drawer,
  List,
  Tag,
  Button,
  Empty,
  Typography,
  Space,
  Divider,
  Alert as AntAlert
} from 'antd';
import {
  BellOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  CloseCircleOutlined,
  CheckOutlined
} from '@ant-design/icons';
import * as api from '../services/api';

const { Text, Title } = Typography;
const EMPTY_ALERT_SUMMARY = {
  activeAlerts: 0,
  recentAlerts: [],
  alertsByLevel: {},
  backendUnavailable: false,
};

const normalizeAlertSummary = (payload) => {
  if (payload?.success && payload?.data) {
    const baseAlerts = Array.isArray(payload.data.alerts) ? payload.data.alerts : [];
    return {
      activeAlerts: Number(payload.data.count || 0),
      recentAlerts: baseAlerts,
      alertsByLevel: {},
      backendUnavailable: true,
    };
  }

  return {
    activeAlerts: Number(payload?.active_alerts || 0),
    recentAlerts: Array.isArray(payload?.recent_alerts) ? payload.recent_alerts : [],
    alertsByLevel: payload?.alerts_by_level || {},
    backendUnavailable: false,
  };
};

const AlertCenter = () => {
  const [visible, setVisible] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(EMPTY_ALERT_SUMMARY);

  // 告警级别配置
  const alertConfig = {
    info: {
      color: 'blue',
      icon: <InfoCircleOutlined />,
      label: '信息'
    },
    warning: {
      color: 'orange',
      icon: <WarningOutlined />,
      label: '警告'
    },
    error: {
      color: 'red',
      icon: <CloseCircleOutlined />,
      label: '错误'
    },
    critical: {
      color: 'volcano',
      icon: <ExclamationCircleOutlined />,
      label: '严重'
    }
  };

  // 获取告警数据
  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const data = await api.getAlertSummary();
      const nextSummary = normalizeAlertSummary(data);
      setSummary(nextSummary);
      setAlerts(nextSummary.recentAlerts);
    } catch (error) {
      console.error('获取告警数据失败:', error);
      setSummary(EMPTY_ALERT_SUMMARY);
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  };

  // 解决告警
  const resolveAlert = async (alertIndex) => {
    try {
      await api.resolveAlert(alertIndex);
      await fetchAlerts(); // 刷新数据
    } catch (error) {
      console.error('解决告警失败:', error);
    }
  };

  // 组件挂载时获取数据
  useEffect(() => {
    fetchAlerts();

    // 每30秒刷新一次告警数据
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  // 渲染告警项
  const renderAlertItem = (alert, index) => {
    const config = alertConfig[alert.level] || alertConfig.info;
    const isResolved = alert.resolved;

    return (
      <List.Item
        key={index}
        actions={[
          !isResolved && (
            <Button
              size="small"
              type="link"
              icon={<CheckOutlined />}
              onClick={() => resolveAlert(index)}
            >
              解决
            </Button>
          )
        ].filter(Boolean)}
        style={{
          opacity: isResolved ? 0.6 : 1,
          backgroundColor: isResolved ? '#f5f5f5' : 'white'
        }}
      >
        <List.Item.Meta
          avatar={
            <Tag
              color={config.color}
              icon={config.icon}
              style={{ marginRight: 12 }}
            >
              {config.label}
            </Tag>
          }
          title={
            <Space>
              <Text strong={!isResolved} delete={isResolved}>
                {alert.title}
              </Text>
              {isResolved && <Tag color="green">已解决</Tag>}
            </Space>
          }
          description={
            <div>
              <Text type={isResolved ? 'secondary' : 'default'}>
                {alert.message}
              </Text>
              <br />
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {new Date(alert.timestamp).toLocaleString('zh-CN')}
              </Text>
            </div>
          }
        />
      </List.Item>
    );
  };

  // 获取告警统计信息
  const getAlertStats = () => {
    const stats = summary.alertsByLevel || {};
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Title level={5}>告警统计</Title>
        <Space wrap>
          {Object.entries(alertConfig).map(([level, config]) => (
            <Tag
              key={level}
              color={config.color}
              icon={config.icon}
            >
              {config.label}: {stats[level] || 0}
            </Tag>
          ))}
        </Space>
      </Space>
    );
  };

  return (
    <>
      {/* 告警铃铛按钮 */}
      <Badge count={summary.activeAlerts} size="small">
        <Button
          type="text"
          icon={<BellOutlined />}
          onClick={() => setVisible(true)}
          style={{
            color: summary.activeAlerts > 0 ? '#ff4d4f' : undefined
          }}
        />
      </Badge>

      {/* 告警抽屉 */}
      <Drawer
        title="系统告警中心"
        placement="right"
        width={480}
        onClose={() => setVisible(false)}
        open={visible}
        extra={
          <Button
            type="primary"
            size="small"
            onClick={fetchAlerts}
            loading={loading}
          >
            刷新
          </Button>
        }
      >
        {/* 总体告警状态 */}
        {summary.backendUnavailable ? (
          <AntAlert
            message="告警系统暂未启用"
            description="当前后端仅保留占位接口，页面会优雅降级显示为空状态。"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        ) : summary.activeAlerts > 0 ? (
          <AntAlert
            message={`当前有 ${summary.activeAlerts} 个活跃告警`}
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
        ) : (
          <AntAlert
            message="系统运行正常，无活跃告警"
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {/* 告警统计 */}
        {getAlertStats()}

        <Divider />

        {/* 告警列表 */}
        <Title level={5}>最近告警</Title>
        {alerts.length === 0 ? (
          <Empty
            description="暂无告警记录"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <List
            dataSource={alerts}
            renderItem={renderAlertItem}
            loading={loading}
            style={{ maxHeight: '60vh', overflowY: 'auto' }}
          />
        )}
      </Drawer>
    </>
  );
};

export default AlertCenter;
