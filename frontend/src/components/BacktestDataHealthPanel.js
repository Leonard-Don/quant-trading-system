import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Spin, Tag } from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { checkIndustryHealth } from '../services/api';

const SOURCE_STATUS_META = {
  connected: { label: '已连接', color: 'success' },
  blocked: { label: '被拦截', color: 'warning' },
  error: { label: '错误', color: 'error' },
  empty: { label: '空数据', color: 'warning' },
  not_installed: { label: '未安装', color: 'default' },
  unavailable: { label: '不可用', color: 'default' },
  unknown: { label: '未知', color: 'default' },
};

const getSourceStatusMeta = (status) => (
  SOURCE_STATUS_META[status] || SOURCE_STATUS_META.unknown
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

function BacktestDataHealthPanel() {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const data = await checkIndustryHealth();
      setHealthData(data);
    } catch (error) {
      setErrorMessage(error.userMessage || error.message || '数据源健康检查失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setErrorMessage('');
      try {
        const data = await checkIndustryHealth();
        if (mounted) {
          setHealthData(data);
        }
      } catch (error) {
        if (mounted) {
          setErrorMessage(error.userMessage || error.message || '数据源健康检查失败');
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
  }, []);

  const summary = useMemo(
    () => summarizeBacktestDataHealth(healthData || {}),
    [healthData]
  );
  const sources = Object.entries(healthData?.data_sources || {});
  const isHealthy = summary.status === 'healthy' && summary.connectedCount > 0;

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
        </>
      ) : null}
    </div>
  );
}

export default BacktestDataHealthPanel;
