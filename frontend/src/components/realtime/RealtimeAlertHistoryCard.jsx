import React from 'react';
import { Card, Button, Space, Statistic, Tag, Typography } from 'antd';
import { BellOutlined } from '@ant-design/icons';

const { Text } = Typography;

const RealtimeAlertHistoryCard = ({
  currentTabAlertFollowThrough,
  currentTabAlertHitSummary,
  formatQuoteTime,
  handleOpenAlerts,
  handleShowDetail,
  isExpanded,
  onToggleExpanded,
}) => (
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
        <div className="realtime-block-title">提醒命中历史</div>
        <div className="realtime-block-subtitle">
          记录当前分组里已经触发过的提醒，帮助你判断哪些规则更常命中、哪些标的值得继续追踪。
        </div>
      </div>
      <Space>
        <div className="realtime-board-summary">
          <span>当前命中</span>
          <strong>{currentTabAlertHitSummary.totalHits}</strong>
        </div>
        <Button size="small" onClick={onToggleExpanded}>
          {isExpanded ? '收起提醒命中历史' : '展开提醒命中历史'}
        </Button>
      </Space>
    </div>

    {isExpanded ? (
      <>
        <div className="realtime-stats-grid" style={{ marginBottom: 14 }}>
          <Card className="realtime-stat-card">
            <Statistic title="命中次数" value={currentTabAlertHitSummary.totalHits} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--focus">
            <Statistic title="涉及标的" value={currentTabAlertHitSummary.uniqueSymbols} />
          </Card>
          <Card className="realtime-stat-card">
            <Statistic title="高频标的" value={currentTabAlertHitSummary.topSymbol} />
          </Card>
          <Card className="realtime-stat-card">
            <Statistic title="高频条件" value={currentTabAlertHitSummary.topCondition} />
          </Card>
        </div>

        <div className="realtime-stats-grid" style={{ marginBottom: 14 }}>
          <Card className="realtime-stat-card realtime-stat-card--positive">
            <Statistic title="命中后延续" value={currentTabAlertFollowThrough.continued} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--negative">
            <Statistic title="命中后反转" value={currentTabAlertFollowThrough.reversed} />
          </Card>
          <Card className="realtime-stat-card">
            <Statistic title="待继续观察" value={currentTabAlertFollowThrough.pending} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--focus">
            <Statistic
              title="后效概览"
              value={`${currentTabAlertFollowThrough.continued}/${currentTabAlertHitSummary.totalHits || 0}`}
              formatter={() => `${currentTabAlertFollowThrough.continued} 延续 / ${currentTabAlertFollowThrough.reversed} 反转`}
            />
          </Card>
        </div>

        {currentTabAlertHitSummary.recentHits.length === 0 ? (
          <Text type="secondary">当前分组还没有提醒命中记录，触发后会自动沉淀到这里，并同步进入详情页时间线。</Text>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {currentTabAlertHitSummary.recentHits.slice(0, 4).map((entry) => (
              <div
                key={entry.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 14,
                  padding: '14px 16px',
                  borderRadius: 18,
                  background: 'color-mix(in srgb, var(--bg-secondary) 90%, white 10%)',
                  border: '1px solid var(--border-color)',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ display: 'grid', gap: 6 }}>
                  <Space wrap>
                    <Tag color="processing" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                      {entry.symbol}
                    </Tag>
                    <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                      {entry.conditionLabel}
                    </Tag>
                    <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                      {formatQuoteTime(entry.triggerTime)}
                    </Tag>
                  </Space>
                  <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                    {entry.message}
                  </Text>
                </div>

                <Space wrap>
                  <Button size="small" onClick={() => handleShowDetail(entry.symbol)}>
                    详情
                  </Button>
                  <Button size="small" icon={<BellOutlined />} onClick={() => handleOpenAlerts(entry.symbol)}>
                    打开提醒
                  </Button>
                </Space>
              </div>
            ))}
          </div>
        )}
      </>
    ) : (
      <Text type="secondary">默认收起提醒命中历史，避免主看盘面板被挤到页面下方。</Text>
    )}
  </Card>
);

export default RealtimeAlertHistoryCard;
