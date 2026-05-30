import { Card, Button, Space, Input, Tag, Empty } from 'antd';
import { FolderOutlined, DeleteOutlined } from '@ant-design/icons';

const RealtimeWatchGroupMonitor = ({
  watchGroupName,
  onWatchGroupNameChange,
  watchGroupSymbols,
  onWatchGroupSymbolsChange,
  watchGroupCapital,
  onWatchGroupCapitalChange,
  watchGroupWeights,
  onWatchGroupWeightsChange,
  watchGroupSummaries,
  onAddWatchGroup,
  onRemoveWatchGroup,
  formatPercent,
  formatCompactCurrency,
  getDisplayName,
}) => (
  <div className="app-page-section-block">
    <div className="app-page-section-kicker">组合监控与敞口</div>
    <Card
      style={{
        borderRadius: 24,
        border: '1px solid var(--border-color)',
        boxShadow: '0 14px 34px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div className="realtime-block-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <FolderOutlined />
        自选组合监控
      </div>
      <div className="realtime-block-subtitle">
        把多个标的组织成“科技重仓”“对冲腿”等组合，实时观察组合级涨跌、宽度和最强驱动。
      </div>
      <Space.Compact style={{ width: '100%', marginTop: 16 }}>
        <Input
          style={{ maxWidth: 220 }}
          aria-label="自选组合名称"
          name="watch_group_name"
          autoComplete="off"
          value={watchGroupName}
          onChange={(event) => onWatchGroupNameChange(event.target.value)}
          placeholder="组合名称"
        />
        <Input
          aria-label="自选组合标的列表"
          name="watch_group_symbols"
          autoComplete="off"
          value={watchGroupSymbols}
          onChange={(event) => onWatchGroupSymbolsChange(event.target.value)}
          placeholder="标的列表，逗号分隔，如 600519.SS, 000858.SZ, AAPL"
          onPressEnter={onAddWatchGroup}
        />
        <Button className="realtime-watch-group-add" type="primary" onClick={onAddWatchGroup}>添加组合</Button>
      </Space.Compact>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'minmax(180px, 220px) minmax(260px, 1fr)', marginTop: 12 }}>
        <Input
          aria-label="自选组合资金"
          name="watch_group_capital"
          autoComplete="off"
          inputMode="decimal"
          value={watchGroupCapital}
          onChange={(event) => onWatchGroupCapitalChange(event.target.value)}
          placeholder="组合资金，可选，如 100000"
        />
        <Input
          aria-label="自选组合权重"
          name="watch_group_weights"
          autoComplete="off"
          value={watchGroupWeights}
          onChange={(event) => onWatchGroupWeightsChange(event.target.value)}
          placeholder="权重/对冲腿，可选，如 600519:0.5 000858:0.3 AAPL:-0.2"
        />
      </div>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', marginTop: 18 }}>
        {watchGroupSummaries.length ? watchGroupSummaries.map((group) => (
          <div
            key={group.id}
            style={{
              borderRadius: 16,
              padding: 16,
              border: '1px solid rgba(148, 163, 184, 0.18)',
              background: 'rgba(15, 23, 42, 0.02)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{group.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {group.trackedCount} 个标的 · 实时覆盖 {group.liveCount}/{group.trackedCount}
                </div>
              </div>
              <Button
                type="text"
                icon={<DeleteOutlined />}
                aria-label={`删除组合 ${group.name}`}
                onClick={() => onRemoveWatchGroup(group.id)}
              />
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
              <Tag color={Number(group.avgChange || 0) >= 0 ? 'green' : 'red'}>
                组合均值 {group.avgChange === null ? '--' : formatPercent(group.avgChange)}
              </Tag>
              <Tag color={Number(group.weightedChange || 0) >= 0 ? 'green' : 'red'}>
                加权收益 {group.weightedChange === null ? '--' : formatPercent(group.weightedChange)}
              </Tag>
              <Tag color="blue">
                上涨宽度 {group.breadth === null ? '--' : `${Math.round(group.breadth * 100)}%`}
              </Tag>
              <Tag color="purple">
                估算 P&L {group.estimatedPnl === null ? '--' : formatCompactCurrency(group.estimatedPnl)}
              </Tag>
            </div>
            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
              {group.strongest
                ? `最强驱动：${getDisplayName(group.strongest.symbol)} ${formatPercent(group.strongest.quote?.change_percent)}`
                : '等待实时行情覆盖后显示组合驱动。'}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              {`净暴露 ${group.netWeight.toFixed(2)}x · 总暴露 ${group.grossWeight.toFixed(2)}x · 最大单名权重 ${(group.concentration * 100).toFixed(0)}%`}
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {group.topExposures.length
                ? group.topExposures.map((item) => (
                  <Tag key={`${group.id}-${item.category}`} color="geekblue">
                    {`${item.label} 暴露 ${(item.weight * 100).toFixed(0)}%`}
                  </Tag>
                ))
                : <Tag>等待暴露计算</Tag>}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              {group.weakest
                ? `最弱标的：${getDisplayName(group.weakest.symbol)} ${formatPercent(group.weakest.quote?.change_percent)}`
                : '暂无最弱标的。'}
            </div>
            <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {(group.symbols || []).slice(0, 6).map((symbol) => (
                <Tag key={`${group.id}-${symbol}`}>{`${symbol} ${Number(group.weightMap?.[symbol] || 0).toFixed(2)}x`}</Tag>
              ))}
            </div>
          </div>
        )) : (
          <Empty description="还没有组合。可以把当前关注的标的组织成研究篮子。" />
        )}
      </div>
    </Card>
  </div>
);

export default RealtimeWatchGroupMonitor;
