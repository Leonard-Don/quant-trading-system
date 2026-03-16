import React, { useState, useEffect, useCallback } from 'react';
import { Popover, Tag, Badge, Space, Tooltip, Spin } from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  CloudServerOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { checkIndustryHealth } from '../services/api';

const STATUS_MAP = {
  connected: { color: '#52c41a', icon: <CheckCircleOutlined />, text: '已连接' },
  blocked: { color: '#faad14', icon: <ExclamationCircleOutlined />, text: '被拦截' },
  error: { color: '#ff4d4f', icon: <CloseCircleOutlined />, text: '错误' },
  empty: { color: '#faad14', icon: <ExclamationCircleOutlined />, text: '空数据' },
  not_installed: { color: '#8c8c8c', icon: <CloseCircleOutlined />, text: '未安装' },
  unavailable: { color: '#8c8c8c', icon: <CloseCircleOutlined />, text: '不可用' },
  unknown: { color: '#8c8c8c', icon: <SyncOutlined spin />, text: '未知' },
};

const CAPABILITY_LABELS = {
  has_market_cap: '市值数据',
  has_multi_day: '多日涨跌',
  has_real_money_flow: '真实资金流',
};

function ApiStatusIndicator() {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastChecked, setLastChecked] = useState(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await checkIndustryHealth();
      setHealthData(data);
      setLastChecked(new Date());
    } catch (e) {
      setHealthData({
        status: 'unhealthy',
        active_provider: { name: '连接失败', type: 'none' },
        data_sources: {},
        message: '无法连接后端服务',
      });
      setLastChecked(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 120000); // 每2分钟刷新
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (!healthData) {
    return <Spin size="small" aria-label="数据源状态加载中" />;
  }

  const activeType = healthData.active_provider?.type || 'none';
  const isHealthy = healthData.status === 'healthy';
  const badgeColor = isHealthy ? '#52c41a' : '#faad14';

  const renderSourceCard = (key, source) => {
    const status = STATUS_MAP[source.status] || STATUS_MAP.unknown;
    const isActive = activeType === key;

    return (
      <div
        key={key}
        style={{
          padding: '12px 16px',
          borderRadius: '8px',
          background: isActive
            ? 'rgba(56, 189, 248, 0.08)'
            : 'rgba(255,255,255,0.03)',
          border: isActive
            ? '1px solid rgba(56, 189, 248, 0.3)'
            : '1px solid rgba(255,255,255,0.06)',
          marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <Space size={6}>
            <CloudServerOutlined style={{ color: isActive ? '#38bdf8' : '#8c8c8c' }} />
            <span style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 13 }}>
              {source.name}
            </span>
            {isActive && (
              <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                当前使用
              </Tag>
            )}
          </Space>
          <Tag
            icon={status.icon}
            color={source.status === 'connected' ? 'success' : source.status === 'blocked' ? 'warning' : 'default'}
            style={{ fontSize: 11, margin: 0 }}
          >
            {status.text}
          </Tag>
        </div>

        {source.status_detail && (
          <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 6, paddingLeft: 20 }}>
            {source.status_detail}
          </div>
        )}

        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', paddingLeft: 20 }}>
          {Object.entries(CAPABILITY_LABELS).map(([cap, label]) => (
            <Tag
              key={cap}
              style={{
                fontSize: 10,
                lineHeight: '16px',
                padding: '0 4px',
                margin: 0,
                borderColor: source[cap] ? 'rgba(82, 196, 26, 0.3)' : 'rgba(255,255,255,0.1)',
                color: source[cap] ? '#52c41a' : '#64748b',
                background: source[cap] ? 'rgba(82, 196, 26, 0.06)' : 'transparent',
              }}
            >
              {source[cap] ? '✓' : '✗'} {label}
            </Tag>
          ))}
        </div>
      </div>
    );
  };

  const popoverContent = (
    <div style={{ width: 320 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.06)'
      }}>
        <span style={{ fontWeight: 700, color: '#f1f5f9', fontSize: 14 }}>
          数据源状态
        </span>
        <Tooltip title="刷新状态">
          <ReloadOutlined
            spin={loading}
            style={{ color: '#38bdf8', cursor: 'pointer', fontSize: 13 }}
            onClick={(e) => { e.stopPropagation(); fetchStatus(); }}
          />
        </Tooltip>
      </div>

      {healthData.data_sources && Object.entries(healthData.data_sources).map(([key, src]) =>
        renderSourceCard(key, src)
      )}

      {healthData.sina_fallback_active && (
        <div style={{
          fontSize: 11, color: '#38bdf8', marginTop: 4, padding: '4px 8px',
          background: 'rgba(56, 189, 248, 0.06)', borderRadius: 4,
        }}>
          ⚡ Sina + THS 混合运行时已激活
        </div>
      )}
      {healthData.data_sources_contributing && healthData.data_sources_contributing.length > 0 && (
        <div style={{
          fontSize: 10, color: '#94a3b8', marginTop: 4, padding: '4px 8px',
          background: 'rgba(255,255,255,0.02)', borderRadius: 4,
        }}>
          数据来源: {healthData.data_sources_contributing.join(' + ').toUpperCase()}
          {healthData.data_source_mode === 'sina_fallback' && ' (兜底)'}
        </div>
      )}

      {lastChecked && (
        <div style={{ fontSize: 10, color: '#64748b', marginTop: 8, textAlign: 'right' }}>
          上次检查: {lastChecked.toLocaleTimeString()}
        </div>
      )}
    </div>
  );

  return (
    <Popover
      content={popoverContent}
      title={null}
      trigger="click"
      placement="bottomRight"
      overlayStyle={{ maxWidth: 360 }}
      styles={{
        body: {
          background: '#1e293b',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 12,
          padding: 16,
        }
      }}
    >
      <div
        aria-label={healthData.message || '点击查看数据源状态'}
        title={healthData.message || '点击查看数据源状态'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          cursor: 'pointer',
          padding: '2px 8px',
          borderRadius: 4,
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.05)',
          transition: 'all 0.2s',
          marginTop: 2,
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.08)';
          e.currentTarget.style.borderColor = 'rgba(56, 189, 248, 0.3)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.02)';
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)';
        }}
      >
        <Badge dot color={badgeColor} offset={[0, 0]}>
          <ApiOutlined style={{ fontSize: 13, color: '#94a3b8' }} />
        </Badge>
        <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 'normal' }}>
          {activeType === 'sina' ? '数据源: 新浪 + 同花顺' : activeType === 'akshare' ? '数据源: 东方财富' : '数据源: 未知'}
        </span>
      </div>
    </Popover>
  );
}

export default ApiStatusIndicator;
