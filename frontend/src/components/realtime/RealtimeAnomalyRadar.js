import React from 'react';
import { Card, Button, Space, Tag, Typography } from 'antd';
import { BellOutlined } from '@ant-design/icons';

const { Text } = Typography;

const RealtimeAnomalyRadar = ({
  anomalyFeed,
  buildAlertDraftFromAnomaly,
  buildTradePlanDraftFromAnomaly,
  formatQuoteTime,
  getDisplayName,
  handleOpenAlerts,
  handleOpenTrade,
  handleShowDetail,
  isExpanded,
  onToggleExpanded,
  quotes,
}) => {
  const featuredAnomaly = anomalyFeed[0] || null;
  const remainingCount = Math.max(0, anomalyFeed.length - 1);

  return (
    <Card
    className="realtime-board-card"
    style={{
      borderRadius: 24,
      border: '1px solid var(--border-color)',
      boxShadow: '0 16px 34px rgba(15, 23, 42, 0.06)',
    }}
  >
    <div className="realtime-board-head" style={{ marginBottom: isExpanded ? 14 : 0 }}>
      <div>
        <div className="realtime-block-title">异动雷达</div>
        <div className="realtime-block-subtitle">
          基于当前分组的实时报价，自动识别涨跌异常、振幅扩张、放量和逼近日高/日低的标的。
        </div>
      </div>
      <Space>
        <div className="realtime-board-summary">
          <span>当前异动</span>
          <strong>{anomalyFeed.length}</strong>
        </div>
        <Button size="small" onClick={onToggleExpanded}>
          {isExpanded ? '收起异动雷达' : '展开异动'}
        </Button>
      </Space>
    </div>

    {!isExpanded && featuredAnomaly ? (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 14,
          padding: '12px 14px',
          borderRadius: 16,
          background: `linear-gradient(180deg, ${featuredAnomaly.background || 'color-mix(in srgb, var(--bg-secondary) 90%, white 10%)'} 0%, color-mix(in srgb, var(--bg-secondary) 94%, white 6%) 100%)`,
          border: `1px solid ${featuredAnomaly.color || 'var(--border-color)'}`,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'grid', gap: 4 }}>
          <Space wrap>
            <Tag
              style={{
                margin: 0,
                borderRadius: 999,
                paddingInline: 10,
                color: featuredAnomaly.color,
                background: featuredAnomaly.background,
                borderColor: 'transparent',
                fontWeight: 700,
              }}
            >
              {featuredAnomaly.label}
            </Tag>
            <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>{featuredAnomaly.symbol}</Tag>
            {remainingCount > 0 ? (
              <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                另有 {remainingCount} 条
              </Tag>
            ) : null}
          </Space>
          <Text style={{ color: 'var(--text-primary)', fontWeight: 700 }}>
            {featuredAnomaly.title} · {getDisplayName(featuredAnomaly.symbol)}
          </Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {featuredAnomaly.description}
          </Text>
        </div>
        <Button type="primary" size="small" onClick={onToggleExpanded}>
          查看全部异动
        </Button>
      </div>
    ) : null}

    {isExpanded && (
      anomalyFeed.length === 0 ? (
        <Text type="secondary">当前分组暂无显著异动，等待下一笔明显变化。</Text>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {anomalyFeed.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 14,
                padding: '14px 16px',
                borderRadius: 18,
                background: `linear-gradient(180deg, ${item.background || 'color-mix(in srgb, var(--bg-secondary) 90%, white 10%)'} 0%, color-mix(in srgb, var(--bg-secondary) 94%, white 6%) 100%)`,
                border: `1px solid ${item.color || 'var(--border-color)'}`,
                alignItems: 'center',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ display: 'grid', gap: 6 }}>
                <Space wrap>
                  <Tag color="magenta" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>{item.title}</Tag>
                  <Tag
                    style={{
                      margin: 0,
                      borderRadius: 999,
                      paddingInline: 10,
                      color: item.color,
                      background: item.background,
                      borderColor: 'transparent',
                      fontWeight: 700,
                    }}
                  >
                    {item.label}
                  </Tag>
                  <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>{item.symbol}</Tag>
                </Space>
                <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                  {getDisplayName(item.symbol)}
                </Text>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  {item.description}
                </Text>
              </div>

              <Space wrap>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  {formatQuoteTime(item.timestamp)}
                </Text>
                <Button
                  size="small"
                  onClick={() => handleOpenTrade(
                    item.symbol,
                    buildTradePlanDraftFromAnomaly(item, quotes[item.symbol])
                  )}
                >
                  计划
                </Button>
                <Button
                  size="small"
                  onClick={() => handleOpenAlerts(
                    item.symbol,
                    buildAlertDraftFromAnomaly(item, quotes[item.symbol], quotes)
                  )}
                  icon={<BellOutlined />}
                >
                  提醒
                </Button>
                <Button type="primary" size="small" onClick={() => handleShowDetail(item.symbol)}>
                  详情
                </Button>
              </Space>
            </div>
          ))}
        </div>
      )
    )}
  </Card>
  );
};

export default RealtimeAnomalyRadar;
