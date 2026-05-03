import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Spin, Tag } from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { checkIndustryHealth, getProviderRuntimeStatus } from '../services/api';

const SOURCE_STATUS_META = {
  connected: { label: '已连接', color: 'success' },
  blocked: { label: '被拦截', color: 'warning' },
  error: { label: '错误', color: 'error' },
  empty: { label: '空数据', color: 'warning' },
  not_installed: { label: '未安装', color: 'default' },
  unavailable: { label: '不可用', color: 'default' },
  unknown: { label: '未知', color: 'default' },
};

const BREAKER_STATUS_META = {
  closed: { label: '闭合', color: 'success' },
  open: { label: '熔断', color: 'error' },
  half_open: { label: '半开探测', color: 'processing' },
  unknown: { label: '未知', color: 'default' },
};

const getSourceStatusMeta = (status) => (
  SOURCE_STATUS_META[status] || SOURCE_STATUS_META.unknown
);

const getBreakerStatusMeta = (status) => (
  BREAKER_STATUS_META[String(status || 'unknown').toLowerCase()] || BREAKER_STATUS_META.unknown
);

const normalizeProviderEntries = (runtimeData = {}) => (
  Object.entries(runtimeData.providers || {}).map(([key, providerStatus]) => {
    const provider = providerStatus?.provider || {};
    const breakers = Object.entries(providerStatus?.circuit_breakers || {}).map(
      ([breakerKey, breaker]) => ({
        key: breakerKey,
        name: breaker?.name || breakerKey,
        state: String(breaker?.state || 'unknown').toLowerCase(),
        failureCount: Number(breaker?.failure_count || 0),
        failureThreshold: Number(breaker?.failure_threshold || 0),
        nextAttemptAt: breaker?.next_attempt_at || null,
      })
    );
    const openCount = breakers.filter((breaker) => breaker.state === 'open').length;
    const halfOpenCount = breakers.filter((breaker) => breaker.state === 'half_open').length;

    return {
      key,
      name: provider.name || key,
      description: provider.description || provider.type || '',
      breakers,
      breakerCount: breakers.length,
      openCount,
      halfOpenCount,
      failureCount: breakers.reduce((total, breaker) => total + breaker.failureCount, 0),
    };
  })
);

export const summarizeBacktestDataHealth = (healthData = {}) => {
  const sources = Object.entries(healthData.data_sources || {});
  const connectedSources = sources.filter(([, source]) => source?.status === 'connected');
  const warningSources = sources.filter(([, source]) => (
    source?.status && source.status !== 'connected' && source.status !== 'unknown'
  ));
  const totalSources = sources.length;
  const connectedCount = connectedSources.length;
  const activeProvider = healthData.active_provider?.name || '未识别';

  return {
    activeProvider,
    connectedCount,
    totalSources,
    warningCount: warningSources.length,
    contributingSources: healthData.data_sources_contributing || [],
    mode: healthData.data_source_mode || 'unknown',
    status: healthData.status || 'unknown',
  };
};

export const summarizeProviderRuntimeStatus = (runtimeData = {}) => {
  const providers = normalizeProviderEntries(runtimeData);
  const breakerCount = providers.reduce((total, provider) => total + provider.breakerCount, 0);
  const openBreakerCount = providers.reduce((total, provider) => total + provider.openCount, 0);
  const halfOpenBreakerCount = providers.reduce((total, provider) => total + provider.halfOpenCount, 0);
  const failureCount = providers.reduce((total, provider) => total + provider.failureCount, 0);

  return {
    providers,
    providerCount: providers.length,
    breakerCount,
    openBreakerCount,
    halfOpenBreakerCount,
    failureCount,
    status: openBreakerCount > 0 ? 'degraded' : 'healthy',
  };
};

function BacktestDataHealthPanel() {
  const [healthData, setHealthData] = useState(null);
  const [providerRuntimeData, setProviderRuntimeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [providerErrorMessage, setProviderErrorMessage] = useState('');

  const applySnapshotResults = useCallback((healthResult, providerResult) => {
    if (healthResult.status === 'fulfilled') {
      setHealthData(healthResult.value);
      setErrorMessage('');
    } else {
      const error = healthResult.reason || {};
      setErrorMessage(error.userMessage || error.message || '数据源健康检查失败');
    }

    if (providerResult.status === 'fulfilled' && providerResult.value?.success !== false) {
      setProviderRuntimeData(providerResult.value);
      setProviderErrorMessage('');
    } else {
      const error = providerResult.status === 'fulfilled'
        ? { message: providerResult.value?.error }
        : providerResult.reason || {};
      setProviderErrorMessage(error.userMessage || error.message || 'Provider 运行状态检查失败');
    }
  }, []);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    setProviderErrorMessage('');
    try {
      const [healthResult, providerResult] = await Promise.allSettled([
        checkIndustryHealth(),
        getProviderRuntimeStatus(),
      ]);
      applySnapshotResults(healthResult, providerResult);
    } catch (error) {
      setErrorMessage(error.userMessage || error.message || '数据源健康检查失败');
    } finally {
      setLoading(false);
    }
  }, [applySnapshotResults]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setErrorMessage('');
      setProviderErrorMessage('');
      try {
        const [healthResult, providerResult] = await Promise.allSettled([
          checkIndustryHealth(),
          getProviderRuntimeStatus(),
        ]);
        if (mounted) {
          applySnapshotResults(healthResult, providerResult);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      mounted = false;
    };
  }, [applySnapshotResults]);

  const summary = useMemo(
    () => summarizeBacktestDataHealth(healthData || {}),
    [healthData]
  );
  const providerSummary = useMemo(
    () => summarizeProviderRuntimeStatus(providerRuntimeData || {}),
    [providerRuntimeData]
  );
  const sources = Object.entries(healthData?.data_sources || {});
  const isHealthy = summary.status === 'healthy' && summary.connectedCount > 0;
  const providerRuntimeHealthy = providerSummary.openBreakerCount === 0;
  const providerRuntimeTag = providerErrorMessage
    ? { color: 'warning', label: '状态待确认' }
    : {
      color: providerRuntimeHealthy ? 'success' : 'error',
      label: providerRuntimeHealthy ? '未发现熔断' : `${providerSummary.openBreakerCount} 个熔断`,
    };

  return (
    <div className="workspace-section backtest-data-health-panel">
      <div className="workspace-section__header">
        <div>
          <div className="workspace-section__title">
            <ApiOutlined /> 数据源健康
          </div>
          <div className="workspace-section__description">
            回测前先确认行业、资金流和市值来源是否处在可用状态。
          </div>
        </div>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={fetchHealth}
        >
          刷新
        </Button>
      </div>

      {loading && !healthData ? (
        <div className="backtest-main-stage__loading-state" style={{ minHeight: 120 }}>
          <Spin />
          <div className="backtest-main-stage__loading-copy">正在检查数据源状态</div>
        </div>
      ) : null}

      {errorMessage ? (
        <Alert
          type="warning"
          showIcon
          message="数据源状态暂不可用"
          description={errorMessage}
        />
      ) : null}

      {healthData ? (
        <>
          <div className="summary-strip summary-strip--compact backtest-data-health-panel__summary">
            <div className="summary-strip__item">
              <span className="summary-strip__label">当前 Provider</span>
              <span className="summary-strip__value">{summary.activeProvider}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">可用数据源</span>
              <span className="summary-strip__value">{`${summary.connectedCount}/${summary.totalSources}`}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">运行模式</span>
              <span className="summary-strip__value">{summary.mode}</span>
            </div>
          </div>

          <div className="backtest-data-health-panel__sources">
            {sources.map(([key, source]) => {
              const statusMeta = getSourceStatusMeta(source?.status);
              return (
                <Tag
                  key={key}
                  color={statusMeta.color}
                  icon={source?.status === 'connected' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                  className="backtest-data-health-panel__source-tag"
                >
                  {source?.name || key}: {statusMeta.label}
                </Tag>
              );
            })}
          </div>

          <Alert
            className="backtest-data-health-panel__alert"
            type={isHealthy ? 'success' : 'warning'}
            showIcon
            message={isHealthy ? '数据源可以支撑当前研究流' : '部分数据源需要关注'}
            description={
              summary.contributingSources.length
                ? `当前贡献来源：${summary.contributingSources.join(' + ').toUpperCase()}。`
                : '当前没有识别到明确贡献来源，建议刷新或等待后端恢复。'
            }
          />

          <div className="backtest-data-health-panel__runtime">
            <div className="backtest-data-health-panel__runtime-header">
              <div className="backtest-data-health-panel__runtime-title">
                <SafetyCertificateOutlined /> Provider 熔断状态
              </div>
              <Tag color={providerRuntimeTag.color}>{providerRuntimeTag.label}</Tag>
            </div>

            {providerErrorMessage ? (
              <Alert
                className="backtest-data-health-panel__runtime-alert"
                type="warning"
                showIcon
                message="Provider 状态暂不可用"
                description={providerErrorMessage}
              />
            ) : null}

            {providerRuntimeData ? (
              <>
                <div className="summary-strip summary-strip--compact backtest-data-health-panel__runtime-summary">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">已注册 Provider</span>
                    <span className="summary-strip__value">{providerSummary.providerCount}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">熔断器数量</span>
                    <span className="summary-strip__value">{providerSummary.breakerCount}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">累计失败</span>
                    <span className="summary-strip__value">{providerSummary.failureCount}</span>
                  </div>
                </div>

                <div className="backtest-data-health-panel__provider-list">
                  {providerSummary.providers.map((provider) => (
                    <div className="backtest-data-health-panel__provider-row" key={provider.key}>
                      <div className="backtest-data-health-panel__provider-main">
                        <span className="backtest-data-health-panel__provider-name">{provider.name}</span>
                        {provider.description ? (
                          <span className="backtest-data-health-panel__provider-description">
                            {provider.description}
                          </span>
                        ) : null}
                      </div>
                      <div className="backtest-data-health-panel__breaker-tags">
                        {provider.breakers.length ? provider.breakers.map((breaker) => {
                          const statusMeta = getBreakerStatusMeta(breaker.state);
                          const failureText = breaker.failureCount > 0
                            ? ` · ${breaker.failureCount}/${breaker.failureThreshold || '-'}`
                            : '';

                          return (
                            <Tag key={breaker.key} color={statusMeta.color}>
                              {breaker.name}: {statusMeta.label}{failureText}
                            </Tag>
                          );
                        }) : (
                          <Tag color="success">未触发熔断器</Tag>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

export default BacktestDataHealthPanel;
