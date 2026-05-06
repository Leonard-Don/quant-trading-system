import React from 'react';
import { Card, Button, Space, Statistic, Tag, Typography } from 'antd';

const { Text } = Typography;

const RealtimeReviewSummaryCard = ({
  REVIEW_SCOPE_OPTIONS,
  copyTextToClipboard,
  exportReviewSnapshots,
  filteredReviewSnapshots,
  formatQuoteTime,
  formatReviewSnapshotMarkdown,
  formatReviewSummaryMarkdown,
  getCategoryLabel,
  getSnapshotOutcomeMeta,
  isExpanded,
  latestSnapshots,
  onOpenSnapshotShareCard,
  onOpenReviewSummaryShareCard,
  onRestoreSnapshot,
  onSetReviewScope,
  onToggleExpanded,
  onTriggerSnapshotImport,
  onOpenSnapshotFocus,
  resolvedSnapshotCount,
  reviewAttribution,
  reviewOutcomeSummary,
  reviewScope,
  reviewScopeLabel,
  validationRate,
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
        <div className="realtime-block-title">复盘快照</div>
        <div className="realtime-block-subtitle">
          保存当前分组、焦点标的、异动、价格快照和链路状态，方便盘后回看更完整的市场切片。
        </div>
      </div>
      <Space>
        <div className="realtime-board-summary">
          <span>当前样本</span>
          <strong>{filteredReviewSnapshots.length}</strong>
        </div>
        <Button size="small" onClick={onToggleExpanded}>
          {isExpanded ? '收起复盘快照' : '展开复盘快照'}
        </Button>
      </Space>
    </div>

    {isExpanded ? (
      <>
        <Space wrap style={{ marginBottom: 14 }}>
          {REVIEW_SCOPE_OPTIONS.map((option) => (
            <Button
              key={option.key}
              size="small"
              type={reviewScope === option.key ? 'primary' : 'default'}
              onClick={() => onSetReviewScope(option.key)}
            >
              {option.label}
            </Button>
          ))}
          <Button
            size="small"
            onClick={() => copyTextToClipboard(
              formatReviewSummaryMarkdown({
                scopeLabel: reviewScopeLabel,
                filteredReviewSnapshots,
                reviewOutcomeSummary,
                validationRate,
                reviewAttribution,
              }),
              '复盘统计摘要已复制'
            )}
          >
            复制统计摘要
          </Button>
          <Button size="small" onClick={onOpenReviewSummaryShareCard}>
            分享统计卡片
          </Button>
          <Button size="small" onClick={exportReviewSnapshots}>
            导出 JSON
          </Button>
          <Button size="small" onClick={onTriggerSnapshotImport}>
            导入 JSON
          </Button>
        </Space>

        <div className="realtime-stats-grid" style={{ marginBottom: 14 }}>
          <Card className="realtime-stat-card">
            <Statistic title="已复盘" value={`${resolvedSnapshotCount}/${filteredReviewSnapshots.length}`} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--positive">
            <Statistic title="验证有效" value={reviewOutcomeSummary.validated} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--negative">
            <Statistic title="观察失效" value={reviewOutcomeSummary.invalidated} />
          </Card>
          <Card className="realtime-stat-card realtime-stat-card--focus">
            <Statistic title="有效率" value={validationRate} />
          </Card>
        </div>

        <div className="realtime-quote-card__metrics" style={{ marginBottom: 14 }}>
          <div className="realtime-quote-card__metric">
            <span>最强分组</span>
            <strong>{reviewAttribution.topValidatedMarket}</strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>常失效异动</span>
            <strong>{reviewAttribution.topInvalidatedSignal}</strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>高频焦点</span>
            <strong>{reviewAttribution.topSpotlightSymbol}</strong>
          </div>
        </div>

        {latestSnapshots.length === 0 ? (
          <Text type="secondary">还没有保存过复盘快照，盘中发现机会时可以先记一笔，盘后更容易回看判断过程。</Text>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {latestSnapshots.map((snapshot) => {
              const outcomeMeta = getSnapshotOutcomeMeta(snapshot.outcome);
              return (
                <div
                  key={snapshot.id}
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
                      <Tag color="cyan" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                        {snapshot.activeTabLabel || getCategoryLabel(snapshot.activeTab)}
                      </Tag>
                      {outcomeMeta ? (
                        <Tag color={outcomeMeta.color} style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                          {outcomeMeta.label}
                        </Tag>
                      ) : null}
                      <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
                        {formatQuoteTime(snapshot.createdAt)}
                      </Tag>
                    </Space>
                    <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                      {snapshot.spotlightName || '未记录焦点标的'}
                      {snapshot.spotlightSymbol ? ` · ${snapshot.spotlightSymbol}` : ''}
                    </Text>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                      {snapshot.transportModeLabel} · 异动 {snapshot.anomalyCount} · 已加载 {snapshot.loadedCount}/{snapshot.totalCount}
                    </Text>
                    {snapshot.note ? (
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        备注：{snapshot.note}
                      </Text>
                    ) : null}
                  </div>

                  <Space wrap>
                    <Button
                      size="small"
                      onClick={() => copyTextToClipboard(
                        formatReviewSnapshotMarkdown(snapshot),
                        '复盘快照摘要已复制'
                      )}
                    >
                      复制摘要
                    </Button>
                    <Button size="small" onClick={() => onOpenSnapshotShareCard(snapshot)}>
                      分享卡片
                    </Button>
                    <Button size="small" onClick={() => onRestoreSnapshot(snapshot)}>
                      恢复分组
                    </Button>
                    {snapshot.spotlightSymbol ? (
                      <Button size="small" type="primary" onClick={() => onOpenSnapshotFocus(snapshot)}>
                        焦点详情
                      </Button>
                    ) : null}
                  </Space>
                </div>
              );
            })}
          </div>
        )}
      </>
    ) : (
      <Text type="secondary">默认收起复盘快照，把主看盘区域留在更靠前的位置，需要回看时再展开。</Text>
    )}
  </Card>
);

export default RealtimeReviewSummaryCard;
