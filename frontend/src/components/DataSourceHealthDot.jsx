import { useState, useEffect, useCallback, useRef } from 'react';
import { Tooltip } from 'antd';

import { getDataSourceHealth } from '../services/api';

// Poll lightly: the server caches the Tushare health probe ~60s, so a 3-minute
// client poll is plenty and adds no rate-limit pressure.
const POLL_INTERVAL_MS = 180000;

// Map the classified Tushare reason to a dot color + human label. Green = OK,
// amber = degraded/fallback active (data may be slower/incomplete), red =
// down/token bad. Grey = not yet loaded / unreachable backend.
const REASON_LABELS = {
  ok: 'Tushare 正常',
  token_missing: 'Tushare token 缺失',
  token_invalid: 'Tushare token 无效',
  rate_limited: 'Tushare 触发限流',
  init_error: 'Tushare 初始化失败',
  error: 'Tushare 连接异常',
  unknown: '数据源状态未知',
};

const RED_REASONS = new Set(['token_missing', 'token_invalid', 'init_error']);

export function resolveHealthVisual(health) {
  if (!health) {
    return { color: '#8c8c8c', state: 'loading', label: '数据源状态加载中…' };
  }
  const tushare = health.tushare || {};
  const reason = tushare.reason || 'unknown';
  const reasonLabel = REASON_LABELS[reason] || REASON_LABELS.unknown;

  if (tushare.ok && !health.degraded) {
    return {
      color: '#52c41a',
      state: 'ok',
      label: `数据源正常 · ${reasonLabel}`,
    };
  }

  // Token/credential failures are the hard-down case (red); rate limits and
  // other transient degradations are amber (fallback chain still serves data,
  // just slower/incomplete).
  const isDown = RED_REASONS.has(reason);
  return {
    color: isDown ? '#ff4d4f' : '#faad14',
    state: isDown ? 'down' : 'degraded',
    label: isDown
      ? `数据源故障 · ${reasonLabel}。A 股数据可能不可用。`
      : `数据源降级 · ${reasonLabel}。已切换备用源，A 股数据可能更慢或不完整。`,
  };
}

function DataSourceHealthDot() {
  const [health, setHealth] = useState(null);
  const mountedRef = useRef(true);

  const fetchHealth = useCallback(async () => {
    try {
      const data = await getDataSourceHealth();
      if (mountedRef.current) {
        setHealth(data);
      }
    } catch {
      // Backend unreachable — show a degraded (amber) signal rather than crash.
      if (mountedRef.current) {
        setHealth({
          tushare: { ok: false, reason: 'error', detail: 'status unreachable' },
          primary_source: 'tushare',
          degraded: true,
        });
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchHealth();
    const interval = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchHealth]);

  const visual = resolveHealthVisual(health);

  return (
    <Tooltip title={visual.label} placement="bottomRight">
      <span
        role="status"
        aria-label={visual.label}
        data-testid="datasource-health-dot"
        data-state={visual.state}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 16,
          height: 16,
          cursor: 'default',
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: visual.color,
            boxShadow: `0 0 0 3px ${visual.color}22`,
            transition: 'background 0.2s ease',
          }}
        />
      </span>
    </Tooltip>
  );
}

export default DataSourceHealthDot;
