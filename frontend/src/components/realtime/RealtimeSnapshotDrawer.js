import React from 'react';
import { Drawer, Card, Button, Space, Tag, Input, Typography } from 'antd';

const { Text } = Typography;

const RealtimeSnapshotDrawer = ({
  filteredReviewSnapshots,
  formatQuoteTime,
  formatReviewSnapshotMarkdown,
  getCategoryLabel,
  getSnapshotOutcomeMeta,
  isOpen,
  onClose,
  onCopyText,
  onOpenSnapshotFocus,
  onOpenSnapshotShareCard,
  onRestoreSnapshot,
  onUpdateReviewSnapshot,
}) => (
  <Drawer
    title="复盘快照"
    placement="right"
    width={720}
    onClose={onClose}
    open={isOpen}
  >
    <div style={{ display: 'grid', gap: 12 }}>
      {filteredReviewSnapshots.length === 0 ? (
        <Text type="secondary">暂无复盘快照，先在实时页保存一笔当前状态吧。</Text>
      ) : filteredReviewSnapshots.map((snapshot) => {
        const outcomeMeta = getSnapshotOutcomeMeta(snapshot.outcome);
        return (
          <Card key={snapshot.id} style={{ borderRadius: 18 }}>
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
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
                  <div style={{ marginTop: 8, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {snapshot.spotlightName || '未记录焦点标的'}
                    {snapshot.spotlightSymbol ? ` · ${snapshot.spotlightSymbol}` : ''}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                    {snapshot.transportModeLabel}
                  </div>
                </div>
                <Space wrap>
                  <Button
                    size="small"
                    onClick={() => onCopyText(
                      formatReviewSnapshotMarkdown(snapshot),
                      '复盘快照摘要已复制'
                    )}
                  >
                    复制 Markdown
                  </Button>
                  <Button size="small" onClick={() => onOpenSnapshotShareCard(snapshot)}>
                    分享卡片
                  </Button>
                  <Button onClick={() => onRestoreSnapshot(snapshot)}>恢复分组</Button>
                  {snapshot.spotlightSymbol ? (
                    <Button type="primary" onClick={() => onOpenSnapshotFocus(snapshot)}>
                      打开焦点详情
                    </Button>
                  ) : null}
                </Space>
              </div>

              <div>
                <div className="realtime-block-subtitle" style={{ marginBottom: 8 }}>复盘结论</div>
                <Space wrap style={{ marginBottom: 10 }}>
                  <Button size="small" onClick={() => onUpdateReviewSnapshot(snapshot.id, { outcome: 'watching' })}>
                    继续观察
                  </Button>
                  <Button size="small" onClick={() => onUpdateReviewSnapshot(snapshot.id, { outcome: 'validated' })}>
                    标记有效
                  </Button>
                  <Button size="small" danger onClick={() => onUpdateReviewSnapshot(snapshot.id, { outcome: 'invalidated' })}>
                    标记失效
                  </Button>
                </Space>
                <Input
                  value={snapshot.note || ''}
                  placeholder="写下这笔快照后来的判断、复盘结论或后续动作"
                  onChange={(event) => onUpdateReviewSnapshot(snapshot.id, { note: event.target.value })}
                />
              </div>

              <div className="realtime-quote-card__metrics">
                <div className="realtime-quote-card__metric">
                  <span>分组覆盖</span>
                  <strong>{snapshot.loadedCount}/{snapshot.totalCount}</strong>
                </div>
                <div className="realtime-quote-card__metric">
                  <span>异动数量</span>
                  <strong>{snapshot.anomalyCount}</strong>
                </div>
                <div className="realtime-quote-card__metric">
                  <span>新鲜 / 变旧 / 延迟</span>
                  <strong>
                    {snapshot.freshnessSummary?.fresh ?? 0} / {snapshot.freshnessSummary?.aging ?? 0} / {snapshot.freshnessSummary?.delayed ?? 0}
                  </strong>
                </div>
              </div>

              <div>
                <div className="realtime-block-subtitle" style={{ marginBottom: 8 }}>当时跟踪标的</div>
                <Space wrap>
                  {(snapshot.watchedSymbols || []).map((item) => (
                    <Tag key={`${snapshot.id}-${item}`} style={{ borderRadius: 999, paddingInline: 10 }}>{item}</Tag>
                  ))}
                </Space>
              </div>

              <div>
                <div className="realtime-block-subtitle" style={{ marginBottom: 8 }}>当时价格快照</div>
                {snapshot.quoteSnapshots?.length ? (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {snapshot.quoteSnapshots.map((item) => (
                      <div key={`${snapshot.id}-${item.symbol}`} style={{ padding: '10px 12px', borderRadius: 14, background: 'rgba(15, 23, 42, 0.04)' }}>
                        <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{item.symbol}</Text>
                        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: '12px' }}>
                          价格 {item.price} · 涨跌幅 {item.changePercent} · 成交量 {item.volume}
                        </Text>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Text type="secondary" style={{ fontSize: '12px' }}>这笔快照没有保存价格快照。</Text>
                )}
              </div>

              <div>
                <div className="realtime-block-subtitle" style={{ marginBottom: 8 }}>当时异动</div>
                {snapshot.anomalies?.length ? (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {snapshot.anomalies.map((item, index) => (
                      <div key={`${snapshot.id}-${item.symbol}-${index}`} style={{ padding: '10px 12px', borderRadius: 14, background: 'rgba(15, 23, 42, 0.04)' }}>
                        <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{item.title} · {item.symbol}</Text>
                        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: '12px' }}>{item.description}</Text>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Text type="secondary" style={{ fontSize: '12px' }}>这笔快照保存时没有显著异动。</Text>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  </Drawer>
);

export default RealtimeSnapshotDrawer;
