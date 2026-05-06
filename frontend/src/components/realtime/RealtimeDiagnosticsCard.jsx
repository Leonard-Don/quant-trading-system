import React from 'react';
import { Card, Button, Space, Typography } from 'antd';
import { DownOutlined, RightOutlined } from '@ant-design/icons';

const { Text } = Typography;

const RealtimeDiagnosticsCard = ({
  diagnosticsCache,
  diagnosticsFetch,
  diagnosticsLastLoadedAt,
  diagnosticsLoading,
  diagnosticsQuality,
  diagnosticsSummary,
  formatQuoteTime,
  formatTransportDecision,
  isExpanded,
  onRefresh,
  onDisable,
  onToggleExpanded,
  transportDecisions,
  weakestFields,
  weakestSymbols,
}) => (
  <Card
    className="realtime-diagnostics-card"
    style={{
      borderRadius: 24,
      border: '1px dashed color-mix(in srgb, var(--accent-primary) 32%, var(--border-color) 68%)',
      background: 'color-mix(in srgb, var(--bg-secondary) 86%, white 14%)',
      boxShadow: '0 12px 28px rgba(15, 23, 42, 0.05)',
    }}
  >
    <div className="realtime-board-head" style={{ marginBottom: 12 }}>
      <div
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10 }}
        onClick={onToggleExpanded}
      >
        <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
          {isExpanded ? <DownOutlined /> : <RightOutlined />}
        </span>
        <div>
          <div className="realtime-block-title">开发诊断</div>
          <div className="realtime-block-subtitle">
            实时链路摘要，判断当前命中 bundle cache、走 WebSocket snapshot 还是退回 REST。
          </div>
        </div>
      </div>
      <Space>
        <Text type="secondary" style={{ fontSize: '12px' }}>
          最近拉取：{formatQuoteTime(diagnosticsLastLoadedAt)}
        </Text>
        <Button size="small" onClick={onDisable}>
          隐藏诊断
        </Button>
        <Button size="small" onClick={onRefresh} loading={diagnosticsLoading}>
          刷新诊断
        </Button>
      </Space>
    </div>

    {isExpanded && (
      <>
        <div className="realtime-hero__meta" style={{ marginBottom: 14 }}>
          <div className="realtime-hero__chip">WS 连接 {diagnosticsSummary?.websocket?.connections ?? '--'}</div>
          <div className="realtime-hero__chip">活跃 symbols {diagnosticsSummary?.websocket?.active_symbols ?? '--'}</div>
          <div className="realtime-hero__chip">bundle 命中 {diagnosticsCache.bundle_cache_hits ?? '--'}</div>
          <div className="realtime-hero__chip">bundle miss {diagnosticsCache.bundle_cache_misses ?? '--'}</div>
          <div className="realtime-hero__chip">bundle 写入 {diagnosticsCache.bundle_cache_writes ?? '--'}</div>
          <div className="realtime-hero__chip">预热次数 {diagnosticsCache.bundle_prewarm_calls ?? '--'}</div>
        </div>

        <div className="realtime-quote-card__metrics">
          <div className="realtime-quote-card__metric">
            <span>最近抓取</span>
            <strong>
              req {diagnosticsFetch.requested ?? '--'} / hit {diagnosticsFetch.cache_hits ?? '--'} / fetch {diagnosticsFetch.fetched ?? '--'}
            </strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>最近耗时</span>
            <strong>{diagnosticsFetch.duration_ms ?? '--'} ms</strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>最近 bundle key</span>
            <strong>
              {Array.isArray(diagnosticsCache.last_bundle_cache_key) && diagnosticsCache.last_bundle_cache_key.length > 0
                ? diagnosticsCache.last_bundle_cache_key.join(', ')
                : '--'}
            </strong>
          </div>
        </div>

        <div className="realtime-quote-card__metrics" style={{ marginTop: 12 }}>
          <div className="realtime-quote-card__metric">
            <span>活跃质量样本</span>
            <strong>{diagnosticsQuality.active_quote_count ?? '--'}</strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>最弱字段</span>
            <strong>
              {weakestFields.length > 0
                ? weakestFields.map((item) => `${item.field} ${Math.round((item.coverage_ratio || 0) * 100)}%`).join(' / ')
                : '--'}
            </strong>
          </div>
          <div className="realtime-quote-card__metric">
            <span>最缺字段标的</span>
            <strong>
              {weakestSymbols.length > 0
                ? weakestSymbols.map((item) => `${item.symbol}(${item.missing_count})`).join(' / ')
                : '--'}
            </strong>
          </div>
        </div>

        <div style={{ marginTop: 14 }}>
          <div className="realtime-block-subtitle" style={{ marginBottom: 8 }}>
            最近决策轨迹
          </div>
          {transportDecisions.length === 0 ? (
            <Text type="secondary" style={{ fontSize: '12px' }}>
              暂无链路决策记录
            </Text>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {transportDecisions.slice(0, 3).map((decision) => (
                <div
                  key={decision.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    padding: '10px 12px',
                    borderRadius: 14,
                    background: 'rgba(15, 23, 42, 0.04)',
                  }}
                >
                  <Text style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
                    {formatTransportDecision(decision)}
                  </Text>
                  <Text type="secondary" style={{ fontSize: '12px', whiteSpace: 'nowrap' }}>
                    {formatQuoteTime(decision.timestamp)}
                  </Text>
                </div>
              ))}
            </div>
          )}
        </div>
      </>
    )}
  </Card>
);

export default RealtimeDiagnosticsCard;
