import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import {
  ApartmentOutlined,
  BarChartOutlined,
  CodeOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  FundOutlined,
  LineChartOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import {
  bootstrapInfrastructurePersistence,
  cancelInfrastructureTask,
  compareStrategySignificance,
  createInfrastructureTask,
  createInfrastructureToken,
  queueBacktestMonteCarlo,
  queueMarketImpactAnalysis,
  queueMultiPeriodBacktest,
  queueStrategySignificance,
  deleteNotificationChannel,
  diffConfigVersions,
  getAltSignalDiagnostics,
  getApiAuthToken,
  getApiRefreshToken,
  getInfrastructureAuthUsers,
  getInfrastructureAuthProviders,
  getInfrastructurePersistenceDiagnostics,
  getInfrastructurePersistenceMigrationPreview,
  getInfrastructureRecords,
  getRealtimeAnomalyDiagnostics,
  getConfigVersions,
  getIndustryIntelligence,
  getIndustryNetwork,
  getMacroFactorBacktest,
  getQuantAlertOrchestration,
  getQuantDataQuality,
  getQuantTradingJournal,
  publishQuantAlertEvent,
  getRealtimeOrderbook,
  getRealtimeReplay,
  getRiskCenterAnalysis,
  getStrategies,
  getInfrastructureStatus,
  getInfrastructureTasks,
  getInfrastructureTimeseries,
  runBacktestMonteCarlo,
  runMarketImpactAnalysis,
  runMultiPeriodBacktest,
  runQuantIndustryRotationLab,
  runQuantFactorExpression,
  runQuantValuationLab,
  runStrategyOptimizer,
  queueQuantIndustryRotationLab,
  queueQuantFactorExpressionTask,
  queueQuantRiskCenterTask,
  queueQuantValuationLab,
  queueStrategyOptimizerTask,
  restoreConfigVersion,
  revokeInfrastructureAuthSession,
  saveConfigVersion,
  setApiAuthToken,
  setApiRefreshToken,
  saveInfrastructureAuthUser,
  saveInfrastructureRecord,
  saveInfrastructureTimeseries,
  saveNotificationChannel,
  testNotificationChannel,
  loginInfrastructureUser,
  runInfrastructurePersistenceMigration,
  exchangeInfrastructureOAuthProvider,
  getInfrastructureAuthProviderDiagnostics,
  updateInfrastructureRateLimits,
  updateInfrastructureAuthPolicy,
  updateQuantAlertOrchestration,
  updateQuantTradingJournal,
  saveInfrastructureAuthProvider,
  startInfrastructureOAuthProvider,
  syncInfrastructureAuthProvidersFromEnv,
} from '../services/api';

const { Title, Paragraph, Text } = Typography;

const PERIOD_OPTIONS = [
  { value: '6mo', label: '6个月' },
  { value: '1y', label: '1年' },
  { value: '2y', label: '2年' },
  { value: '3y', label: '3年' },
];

const JOURNAL_STAGE_OPTIONS = [
  { value: 'discovered', label: '发现' },
  { value: 'backtesting', label: '回测' },
  { value: 'optimizing', label: '优化' },
  { value: 'paper', label: '模拟' },
  { value: 'live', label: '实盘' },
  { value: 'retired', label: '停用' },
];

const JOURNAL_STATUS_OPTIONS = [
  { value: 'active', label: '进行中' },
  { value: 'watching', label: '观察中' },
  { value: 'blocked', label: '阻塞' },
  { value: 'closed', label: '已关闭' },
];

const formatPct = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
const formatSignedPct = (value) => `${Number(value || 0).toFixed(2)}%`;
const formatMoney = (value) => `$${Number(value || 0).toFixed(2)}`;
const formatDateTime = (value) => String(value || '').slice(0, 19).replace('T', ' ');
const lifecycleStageColor = (value) => ({
  discovered: 'blue',
  backtesting: 'geekblue',
  optimizing: 'purple',
  paper: 'gold',
  live: 'green',
  retired: 'default',
}[value] || 'default');
const lifecycleStatusColor = (value) => ({
  active: 'cyan',
  watching: 'gold',
  blocked: 'red',
  closed: 'default',
}[value] || 'default');

const HeatmapGrid = ({ heatmap }) => {
  const cells = Array.isArray(heatmap?.cells) ? heatmap.cells : [];
  if (!cells.length) {
    return <Empty description="暂无参数热力图数据" />;
  }

  const values = cells
    .map((item) => Number(item.value))
    .filter((item) => Number.isFinite(item));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const colorForValue = (value) => {
    if (!Number.isFinite(Number(value))) {
      return 'rgba(148, 163, 184, 0.12)';
    }
    const ratio = max === min ? 0.5 : (Number(value) - min) / (max - min);
    const alpha = 0.18 + (ratio * 0.55);
    const positive = ratio >= 0.5;
    return positive ? `rgba(34, 197, 94, ${alpha})` : `rgba(239, 68, 68, ${alpha})`;
  };

  return (
    <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }}>
      {cells.map((item) => (
        <div
          key={`${item.x}-${item.y ?? 'single'}`}
          style={{
            borderRadius: 12,
            padding: 12,
            border: '1px solid rgba(148, 163, 184, 0.16)',
            background: colorForValue(item.value),
          }}
        >
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {heatmap?.y_key ? `${heatmap.x_key}=${item.x} · ${heatmap.y_key}=${item.y}` : `${heatmap?.metric || 'metric'} @ ${item.x}`}
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6 }}>
            {Number.isFinite(Number(item.value)) ? Number(item.value).toFixed(3) : '--'}
          </div>
        </div>
      ))}
    </div>
  );
};

const QuantLab = () => {
  const { message } = AntdApp.useApp();
  const [strategies, setStrategies] = useState([]);
  const [optimizerLoading, setOptimizerLoading] = useState(false);
  const [optimizerResult, setOptimizerResult] = useState(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskResult, setRiskResult] = useState(null);
  const [valuationLoading, setValuationLoading] = useState(false);
  const [valuationResult, setValuationResult] = useState(null);
  const [rotationLoading, setRotationLoading] = useState(false);
  const [rotationResult, setRotationResult] = useState(null);
  const [queuedTaskLoading, setQueuedTaskLoading] = useState({});
  const [opsLoading, setOpsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('optimizer');
  const [factorLoading, setFactorLoading] = useState(false);
  const [factorResult, setFactorResult] = useState(null);
  const [backtestEnhancementLoading, setBacktestEnhancementLoading] = useState(false);
  const [backtestEnhancementResult, setBacktestEnhancementResult] = useState(null);
  const [industryIntelLoading, setIndustryIntelLoading] = useState(false);
  const [industryIntelResult, setIndustryIntelResult] = useState(null);
  const [industryNetworkResult, setIndustryNetworkResult] = useState(null);
  const [signalValidationLoading, setSignalValidationLoading] = useState(false);
  const [macroValidationResult, setMacroValidationResult] = useState(null);
  const [altSignalDiagnostics, setAltSignalDiagnostics] = useState(null);
  const [marketProbeLoading, setMarketProbeLoading] = useState(false);
  const [replayResult, setReplayResult] = useState(null);
  const [orderbookResult, setOrderbookResult] = useState(null);
  const [linkedReplayResult, setLinkedReplayResult] = useState(null);
  const [anomalyDiagnostics, setAnomalyDiagnostics] = useState(null);
  const [infraLoading, setInfraLoading] = useState(false);
  const [infrastructureStatus, setInfrastructureStatus] = useState(null);
  const [infrastructureTasks, setInfrastructureTasks] = useState([]);
  const [authUsers, setAuthUsers] = useState([]);
  const [refreshSessions, setRefreshSessions] = useState([]);
  const [authProviders, setAuthProviders] = useState([]);
  const [oauthLaunchContext, setOauthLaunchContext] = useState(null);
  const [oauthDiagnostics, setOauthDiagnostics] = useState(null);
  const [persistenceDiagnostics, setPersistenceDiagnostics] = useState(null);
  const [persistenceBootstrapLoading, setPersistenceBootstrapLoading] = useState(false);
  const [persistenceMigrationPreview, setPersistenceMigrationPreview] = useState(null);
  const [persistenceMigrationLoading, setPersistenceMigrationLoading] = useState(false);
  const [persistenceRecords, setPersistenceRecords] = useState([]);
  const [persistenceTimeseries, setPersistenceTimeseries] = useState([]);
  const [configVersionLoading, setConfigVersionLoading] = useState(false);
  const [configVersions, setConfigVersions] = useState([]);
  const [configDiff, setConfigDiff] = useState(null);
  const [activeConfigScope, setActiveConfigScope] = useState({ ownerId: 'default', configType: 'strategy', configKey: 'moving_average' });
  const [authToken, setAuthToken] = useState(() => getApiAuthToken());
  const [refreshToken, setRefreshToken] = useState(() => getApiRefreshToken());
  const [authSession, setAuthSession] = useState(null);
  const [tradingJournal, setTradingJournal] = useState(null);
  const [alertOrchestration, setAlertOrchestration] = useState(null);
  const [dataQuality, setDataQuality] = useState(null);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [optimizerForm] = Form.useForm();
  const [riskForm] = Form.useForm();
  const [valuationForm] = Form.useForm();
  const [rotationForm] = Form.useForm();
  const [factorForm] = Form.useForm();
  const [monteCarloForm] = Form.useForm();
  const [significanceForm] = Form.useForm();
  const [multiPeriodForm] = Form.useForm();
  const [impactAnalysisForm] = Form.useForm();
  const [industryIntelForm] = Form.useForm();
  const [signalValidationForm] = Form.useForm();
  const [marketProbeForm] = Form.useForm();
  const [configVersionForm] = Form.useForm();
  const [configLookupForm] = Form.useForm();
  const [taskForm] = Form.useForm();
  const [tokenForm] = Form.useForm();
  const [authUserForm] = Form.useForm();
  const [authLoginForm] = Form.useForm();
  const [oauthProviderForm] = Form.useForm();
  const [oauthExchangeForm] = Form.useForm();
  const [authPolicyForm] = Form.useForm();
  const [rateLimitForm] = Form.useForm();
  const [persistenceRecordForm] = Form.useForm();
  const [timeseriesForm] = Form.useForm();
  const [persistenceQueryForm] = Form.useForm();
  const [persistenceBootstrapForm] = Form.useForm();
  const [persistenceMigrationForm] = Form.useForm();
  const [notificationForm] = Form.useForm();
  const [notificationChannelForm] = Form.useForm();
  const [journalForm] = Form.useForm();
  const [lifecycleForm] = Form.useForm();
  const [alertForm] = Form.useForm();
  const [alertEventForm] = Form.useForm();

  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch((error) => {
        message.error(`加载策略定义失败: ${error.userMessage || error.message}`);
      });
  }, [message]);

  const loadOperations = useCallback(async () => {
    setOpsLoading(true);
    try {
      const [journalPayload, alertPayload, qualityPayload] = await Promise.all([
        getQuantTradingJournal(),
        getQuantAlertOrchestration(),
        getQuantDataQuality(),
      ]);
      setTradingJournal(journalPayload);
      setAlertOrchestration(alertPayload);
      setDataQuality(qualityPayload);
    } catch (error) {
      message.error(`加载研究运营面板失败: ${error.userMessage || error.message}`);
    } finally {
      setOpsLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadOperations();
  }, [loadOperations]);

  useEffect(() => {
    if (typeof window === 'undefined' || !macroValidationResult || signalValidationLoading) {
      return;
    }

    const horizonResults = Array.isArray(macroValidationResult?.horizon_results)
      ? macroValidationResult.horizon_results
      : [];
    const strongestHorizon = horizonResults
      .filter((item) => Number(item?.samples || 0) >= 5 && Number.isFinite(Number(item?.hit_rate)))
      .sort((left, right) => Number(right?.hit_rate || 0) - Number(left?.hit_rate || 0))[0];

    if (!strongestHorizon || Number(strongestHorizon.hit_rate || 0) < 0.6) {
      return;
    }

    const publishKey = `quant-signal-bus-published:macro:${macroValidationResult.status}:${strongestHorizon.horizon_days}:${Number(strongestHorizon.hit_rate || 0).toFixed(3)}`;
    if (window.sessionStorage.getItem(publishKey)) {
      return;
    }
    window.sessionStorage.setItem(publishKey, 'true');

    void publishQuantAlertEvent({
      source_module: 'macro',
      rule_name: '宏观因子历史验证命中率偏强',
      symbol: '',
      severity: Number(strongestHorizon.hit_rate || 0) >= 0.7 ? 'critical' : 'warning',
      message: `${strongestHorizon.horizon_days}D horizon 命中率 ${formatPct(strongestHorizon.hit_rate)}，方向收益 ${formatPct(strongestHorizon.avg_signed_return || 0)}。`,
      condition_summary: 'macro:forward_return_validation',
      trigger_value: Number(strongestHorizon.hit_rate || 0),
      notify_channels: [],
      create_workbench_task: Number(strongestHorizon.hit_rate || 0) >= 0.7,
      workbench_task_type: 'cross_market',
      persist_event_record: true,
      cascade_actions: [
        { type: 'persist_record', record_type: 'macro_validation_signal_hit' },
        {
          type: 'persist_timeseries',
          series_name: 'macro.validation.hit_rate',
          value: Number(strongestHorizon.hit_rate || 0),
          payload: {
            horizon_days: strongestHorizon.horizon_days,
            samples: strongestHorizon.samples,
          },
        },
      ],
    }).catch((error) => {
      console.warn('Failed to publish macro validation signal to unified bus:', error);
      window.sessionStorage.removeItem(publishKey);
    });
  }, [macroValidationResult, signalValidationLoading]);

  useEffect(() => {
    if (typeof window === 'undefined' || !altSignalDiagnostics || signalValidationLoading) {
      return;
    }

    const overallHitRate = Number(altSignalDiagnostics?.overall?.hit_rate);
    const recordCount = Number(altSignalDiagnostics?.record_count || 0);
    if (!Number.isFinite(overallHitRate) || recordCount < 10 || overallHitRate < 0.6) {
      return;
    }

    const hitRateType = altSignalDiagnostics?.overall?.hit_rate_type || 'proxy';
    const publishKey = `quant-signal-bus-published:alt:${hitRateType}:${recordCount}:${overallHitRate.toFixed(3)}`;
    if (window.sessionStorage.getItem(publishKey)) {
      return;
    }
    window.sessionStorage.setItem(publishKey, 'true');

    void publishQuantAlertEvent({
      source_module: 'alt_data',
      rule_name: '另类数据信号命中率偏强',
      symbol: '',
      severity: overallHitRate >= 0.7 && hitRateType === 'realized' ? 'critical' : 'warning',
      message: `${recordCount} 条记录的整体命中率为 ${formatPct(overallHitRate)}，口径为 ${hitRateType}。`,
      condition_summary: 'alt_data:signal_diagnostics',
      trigger_value: overallHitRate,
      notify_channels: [],
      create_workbench_task: overallHitRate >= 0.7 && hitRateType === 'realized',
      workbench_task_type: 'cross_market',
      persist_event_record: true,
      cascade_actions: [
        { type: 'persist_record', record_type: 'alt_signal_diagnostic_hit' },
        {
          type: 'persist_timeseries',
          series_name: 'alt_data.signal.hit_rate',
          value: overallHitRate,
          payload: {
            hit_rate_type: hitRateType,
            record_count: recordCount,
          },
        },
      ],
    }).catch((error) => {
      console.warn('Failed to publish alt-data diagnostics to unified bus:', error);
      window.sessionStorage.removeItem(publishKey);
    });
  }, [altSignalDiagnostics, signalValidationLoading]);

  const loadInfrastructure = useCallback(async () => {
    setInfraLoading(true);
    try {
      const [statusPayload, tasksPayload, usersPayload, providersPayload, diagnosticsPayload, migrationPreviewPayload, recordsPayload, timeseriesPayload] = await Promise.all([
        getInfrastructureStatus(),
        getInfrastructureTasks(20),
        getInfrastructureAuthUsers(),
        getInfrastructureAuthProviders(),
        getInfrastructurePersistenceDiagnostics(),
        getInfrastructurePersistenceMigrationPreview(),
        getInfrastructureRecords({ limit: 12 }),
        getInfrastructureTimeseries({ limit: 12 }),
      ]);
      setInfrastructureStatus(statusPayload);
      setInfrastructureTasks(tasksPayload.tasks || []);
      setAuthUsers(usersPayload.users || []);
      setRefreshSessions(usersPayload.sessions || []);
      setAuthProviders(providersPayload.providers || []);
      setPersistenceDiagnostics(diagnosticsPayload);
      setPersistenceMigrationPreview(migrationPreviewPayload);
      setPersistenceRecords(recordsPayload.records || []);
      setPersistenceTimeseries(timeseriesPayload.timeseries || []);
    } catch (error) {
      message.error(`加载基础设施状态失败: ${error.userMessage || error.message}`);
    } finally {
      setInfraLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadInfrastructure();
  }, [loadInfrastructure]);

  const applyAuthSession = useCallback((response, successMessage) => {
    setAuthToken(response?.access_token || '');
    setApiAuthToken(response?.access_token || '');
    setRefreshToken(response?.refresh_token || '');
    setApiRefreshToken(response?.refresh_token || '');
    setAuthSession(response || null);
    if (successMessage) {
      message.success(successMessage);
    }
  }, [message]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const handleOAuthMessage = (event) => {
      if (!event?.data || event.data.type !== 'quant-oauth-callback') {
        return;
      }
      if (event.data.success && event.data.payload) {
        applyAuthSession(
          event.data.payload,
          `OAuth 登录成功: ${event.data.payload.user?.display_name || event.data.payload.user?.subject || event.data.provider_id}`,
        );
        loadInfrastructure();
      } else {
        message.error(`OAuth 登录失败: ${event.data.error || '未知错误'}`);
      }
    };
    window.addEventListener('message', handleOAuthMessage);
    return () => {
      window.removeEventListener('message', handleOAuthMessage);
    };
  }, [applyAuthSession, loadInfrastructure, message]);

  useEffect(() => {
    if (!infrastructureStatus?.rate_limits) {
      return;
    }
    rateLimitForm.setFieldsValue({
      default_requests_per_minute: infrastructureStatus.rate_limits.default_rule?.requests_per_minute || 100,
      default_burst_size: infrastructureStatus.rate_limits.default_rule?.burst_size || 120,
      rules_json: JSON.stringify(infrastructureStatus.rate_limits.rules || [], null, 2),
    });
  }, [infrastructureStatus, rateLimitForm]);

  useEffect(() => {
    if (!infrastructureStatus?.auth) {
      return;
    }
    authPolicyForm.setFieldsValue({
      required: infrastructureStatus.auth.required,
    });
  }, [authPolicyForm, infrastructureStatus]);

  useEffect(() => {
    persistenceBootstrapForm.setFieldsValue({
      enable_timescale_schema: true,
    });
  }, [persistenceBootstrapForm]);

  useEffect(() => {
    persistenceMigrationForm.setFieldsValue({
      sqlite_path: '',
      dry_run: true,
      include_records: true,
      include_timeseries: true,
      dedupe_timeseries: true,
      record_limit: undefined,
      timeseries_limit: undefined,
    });
  }, [persistenceMigrationForm]);

  const buildOptimizerPayload = (values) => ({
    ...values,
    parameters: values.parameters || {},
  });

  const buildValuationPayload = (values) => ({
    ...values,
    peer_symbols: String(values.peer_symbols || '')
      .split(/[\s,，]+/)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean),
  });

  const buildIndustryRotationPayload = (values) => ({
    ...values,
  });

  const buildRiskPayload = (values) => {
    const symbols = String(values.symbols || '')
      .split(/[\s,，]+/)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean);
    const weights = String(values.weights || '')
      .split(/[\s,，]+/)
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item));
    return {
      symbols,
      weights: weights.length ? weights : undefined,
      period: values.period,
    };
  };

  const buildFactorPayload = (values) => ({
    ...values,
  });

  const buildMonteCarloPayload = (values) => ({
    ...values,
  });

  const buildSignificancePayload = (values) => ({
    ...values,
    strategies: String(values.strategies || '')
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean),
    bootstrap_samples: values.bootstrap_samples,
  });

  const buildMultiPeriodPayload = (values) => ({
    ...values,
    intervals: String(values.intervals || '1d,1wk,1mo')
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  });

  const buildImpactPayload = (values) => ({
    ...values,
    sample_trade_values: String(values.sample_trade_values || '10000,50000,100000,250000')
      .split(/[\s,，]+/)
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item) && item > 0),
  });

  const parseJsonArrayField = (value, label) => {
    if (!String(value || '').trim()) {
      return [];
    }
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      throw new Error(`${label}必须是 JSON 数组`);
    }
    return parsed;
  };

  const submitAsyncQuantTask = async (submitter, payload, label, loadingKey) => {
    setQueuedTaskLoading((current) => ({ ...current, [loadingKey]: true }));
    try {
      const response = await submitter(payload);
      message.success(`${label} 已进入异步队列`);
      if ((response?.execution_backend || response?.task?.execution_backend) === 'celery') {
        message.info('任务已路由到 Celery worker，可在基础设施页观察 broker 状态');
      }
      loadInfrastructure();
      return response;
    } catch (error) {
      message.error(`提交${label}异步任务失败: ${error.userMessage || error.message}`);
      return null;
    } finally {
      setQueuedTaskLoading((current) => ({ ...current, [loadingKey]: false }));
    }
  };

  const handleOptimize = async (values) => {
    setOptimizerLoading(true);
    try {
      const payload = buildOptimizerPayload(values);
      const response = await runStrategyOptimizer(payload);
      setOptimizerResult(response);
      message.success('参数优化完成');
    } catch (error) {
      message.error(`参数优化失败: ${error.userMessage || error.message}`);
    } finally {
      setOptimizerLoading(false);
    }
  };

  const handleQueueOptimizer = async () => {
    const values = await optimizerForm.validateFields();
    await submitAsyncQuantTask(queueStrategyOptimizerTask, buildOptimizerPayload(values), '策略优化', 'optimizer');
  };

  const handleRiskAnalysis = async (values) => {
    setRiskLoading(true);
    try {
      const response = await getRiskCenterAnalysis(buildRiskPayload(values));
      setRiskResult(response);
      message.success('风险分析完成');
    } catch (error) {
      message.error(`风险分析失败: ${error.userMessage || error.message}`);
    } finally {
      setRiskLoading(false);
    }
  };

  const handleQueueRiskAnalysis = async () => {
    const values = await riskForm.validateFields();
    await submitAsyncQuantTask(queueQuantRiskCenterTask, buildRiskPayload(values), '风险分析', 'risk');
  };

  const handleValuationAnalysis = async (values) => {
    setValuationLoading(true);
    try {
      const response = await runQuantValuationLab(buildValuationPayload(values));
      setValuationResult(response);
      message.success('估值实验已更新并写入历史');
    } catch (error) {
      message.error(`估值实验失败: ${error.userMessage || error.message}`);
    } finally {
      setValuationLoading(false);
    }
  };

  const handleQueueValuation = async () => {
    const values = await valuationForm.validateFields();
    await submitAsyncQuantTask(queueQuantValuationLab, buildValuationPayload(values), '估值实验', 'valuation');
  };

  const handleIndustryRotation = async (values) => {
    setRotationLoading(true);
    try {
      const response = await runQuantIndustryRotationLab(buildIndustryRotationPayload(values));
      setRotationResult(response);
      message.success('行业轮动策略回测完成');
    } catch (error) {
      message.error(`行业轮动策略回测失败: ${error.userMessage || error.message}`);
    } finally {
      setRotationLoading(false);
    }
  };

  const handleQueueIndustryRotation = async () => {
    const values = await rotationForm.validateFields();
    await submitAsyncQuantTask(queueQuantIndustryRotationLab, buildIndustryRotationPayload(values), '行业轮动', 'industry_rotation');
  };

  const handleFactorExpression = async (values) => {
    setFactorLoading(true);
    try {
      const response = await runQuantFactorExpression(buildFactorPayload(values));
      setFactorResult(response);
      message.success('自定义因子已计算');
    } catch (error) {
      message.error(`因子表达式计算失败: ${error.userMessage || error.message}`);
    } finally {
      setFactorLoading(false);
    }
  };

  const handleQueueFactorExpression = async () => {
    const values = await factorForm.validateFields();
    await submitAsyncQuantTask(queueQuantFactorExpressionTask, buildFactorPayload(values), '因子表达式', 'factor');
  };

  const handleLoadTaskResult = (record) => {
    if (!record?.result) {
      message.warning('该任务还没有可载入的结果');
      return;
    }

    const taskName = String(record.name || '').trim();
    if (taskName === 'quant_strategy_optimizer') {
      setOptimizerResult(record.result);
      setActiveTab('optimizer');
    } else if (taskName === 'quant_risk_center') {
      setRiskResult(record.result);
      setActiveTab('risk');
    } else if (taskName === 'quant_valuation_lab') {
      setValuationResult(record.result);
      setActiveTab('valuation');
    } else if (taskName === 'quant_industry_rotation') {
      setRotationResult(record.result);
      setActiveTab('industry');
    } else if (taskName === 'quant_factor_expression') {
      setFactorResult(record.result);
      setActiveTab('factor');
    } else if (taskName === 'backtest_monte_carlo') {
      setBacktestEnhancementResult({ type: 'monte_carlo', payload: record.result?.data || record.result });
      setActiveTab('backtest-enhance');
    } else if (taskName === 'backtest_significance') {
      setBacktestEnhancementResult({ type: 'significance', payload: record.result?.data || record.result });
      setActiveTab('backtest-enhance');
    } else if (taskName === 'backtest_multi_period') {
      setBacktestEnhancementResult({ type: 'multi_period', payload: record.result?.data || record.result });
      setActiveTab('backtest-enhance');
    } else if (taskName === 'backtest_impact_analysis') {
      setBacktestEnhancementResult({ type: 'impact_analysis', payload: record.result?.data || record.result });
      setActiveTab('backtest-enhance');
    } else {
      message.warning('该任务结果暂不支持自动载入');
      return;
    }

    message.success('任务结果已载入对应研究面板');
  };

  const handleBacktestMonteCarlo = async (values) => {
    setBacktestEnhancementLoading(true);
    try {
      const response = await runBacktestMonteCarlo(buildMonteCarloPayload(values));
      setBacktestEnhancementResult({ type: 'monte_carlo', payload: response.data || response });
      message.success('Monte Carlo 路径模拟完成');
    } catch (error) {
      message.error(`Monte Carlo 模拟失败: ${error.userMessage || error.message}`);
    } finally {
      setBacktestEnhancementLoading(false);
    }
  };

  const handleQueueBacktestMonteCarlo = async () => {
    const values = await monteCarloForm.validateFields();
    await submitAsyncQuantTask(queueBacktestMonteCarlo, buildMonteCarloPayload(values), 'Monte Carlo 回测', 'backtest_monte_carlo');
  };

  const handleStrategySignificance = async (values) => {
    setBacktestEnhancementLoading(true);
    try {
      const response = await compareStrategySignificance(buildSignificancePayload(values));
      setBacktestEnhancementResult({ type: 'significance', payload: response.data || response });
      message.success('策略显著性检验完成');
    } catch (error) {
      message.error(`显著性检验失败: ${error.userMessage || error.message}`);
    } finally {
      setBacktestEnhancementLoading(false);
    }
  };

  const handleQueueStrategySignificance = async () => {
    const values = await significanceForm.validateFields();
    await submitAsyncQuantTask(queueStrategySignificance, buildSignificancePayload(values), '策略显著性检验', 'backtest_significance');
  };

  const handleMultiPeriodBacktest = async (values) => {
    setBacktestEnhancementLoading(true);
    try {
      const response = await runMultiPeriodBacktest(buildMultiPeriodPayload(values));
      setBacktestEnhancementResult({ type: 'multi_period', payload: response.data || response });
      message.success('多周期回测完成');
    } catch (error) {
      message.error(`多周期回测失败: ${error.userMessage || error.message}`);
    } finally {
      setBacktestEnhancementLoading(false);
    }
  };

  const handleQueueMultiPeriodBacktest = async () => {
    const values = await multiPeriodForm.validateFields();
    await submitAsyncQuantTask(queueMultiPeriodBacktest, buildMultiPeriodPayload(values), '多周期回测', 'backtest_multi_period');
  };

  const handleMarketImpactAnalysis = async (values) => {
    setBacktestEnhancementLoading(true);
    try {
      const response = await runMarketImpactAnalysis(buildImpactPayload(values));
      setBacktestEnhancementResult({ type: 'impact_analysis', payload: response.data || response });
      message.success('市场冲击敏感性分析完成');
    } catch (error) {
      message.error(`市场冲击分析失败: ${error.userMessage || error.message}`);
    } finally {
      setBacktestEnhancementLoading(false);
    }
  };

  const handleQueueMarketImpactAnalysis = async () => {
    const values = await impactAnalysisForm.validateFields();
    await submitAsyncQuantTask(queueMarketImpactAnalysis, buildImpactPayload(values), '市场冲击分析', 'backtest_impact_analysis');
  };

  const handleIndustryIntelligence = async (values) => {
    setIndustryIntelLoading(true);
    try {
      const [intelligencePayload, networkPayload] = await Promise.all([
        getIndustryIntelligence(values.top_n, values.lookback_days),
        getIndustryNetwork(values.network_top_n, values.lookback_days, values.min_similarity),
      ]);
      setIndustryIntelResult(intelligencePayload.data || intelligencePayload);
      setIndustryNetworkResult(networkPayload.data || networkPayload);
      message.success('行业智能扩展已刷新');
    } catch (error) {
      message.error(`行业智能扩展失败: ${error.userMessage || error.message}`);
    } finally {
      setIndustryIntelLoading(false);
    }
  };

  const handleSignalValidation = async (values) => {
    setSignalValidationLoading(true);
    try {
      const [macroPayload, altPayload] = await Promise.all([
        getMacroFactorBacktest({
          benchmark: values.benchmark,
          period: values.period,
          horizons: values.horizons,
          limit: values.macro_limit,
        }),
        getAltSignalDiagnostics({
          category: values.category,
          timeframe: values.timeframe,
          limit: values.alt_limit,
          half_life_days: values.half_life_days,
        }),
      ]);
      setMacroValidationResult(macroPayload.data || macroPayload);
      setAltSignalDiagnostics(altPayload.data || altPayload);
      message.success('信号验证已完成');
    } catch (error) {
      message.error(`信号验证失败: ${error.userMessage || error.message}`);
    } finally {
      setSignalValidationLoading(false);
    }
  };

  const handleMarketProbe = async (values) => {
    setMarketProbeLoading(true);
    try {
      const compareSymbols = String(values.compare_symbols || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean)
        .slice(0, 4);
      const [replayPayload, orderbookPayload, anomalyPayload] = await Promise.all([
        getRealtimeReplay(values.symbol, {
          period: values.replay_period,
          interval: values.replay_interval,
          limit: values.replay_limit,
        }),
        getRealtimeOrderbook(values.symbol, values.levels),
        getRealtimeAnomalyDiagnostics(values.symbol, {
          period: values.replay_period,
          interval: values.replay_interval,
          limit: values.replay_limit,
          z_window: values.z_window,
          return_z_threshold: values.return_z_threshold,
          volume_z_threshold: values.volume_z_threshold,
          cusum_threshold_sigma: values.cusum_threshold_sigma,
          pattern_lookback: values.pattern_lookback,
          pattern_matches: values.pattern_matches,
        }),
      ]);
      setReplayResult(replayPayload.data || replayPayload);
      setOrderbookResult(orderbookPayload.data || orderbookPayload);
      setAnomalyDiagnostics(anomalyPayload.data || anomalyPayload);
      if (compareSymbols.length) {
        const linkedPayloads = await Promise.all(
          compareSymbols.map((symbol) => getRealtimeReplay(symbol, {
            period: values.replay_period,
            interval: values.replay_interval,
            limit: values.replay_limit,
          }))
        );
        setLinkedReplayResult({
          symbols: compareSymbols,
          series: linkedPayloads.map((item, index) => ({
            symbol: compareSymbols[index],
            bars: item.data?.bars || item.bars || [],
          })),
        });
      } else {
        setLinkedReplayResult(null);
      }
      message.success('实时行情深度探测完成');
    } catch (error) {
      message.error(`实时行情探测失败: ${error.userMessage || error.message}`);
    } finally {
      setMarketProbeLoading(false);
    }
  };

  const handleCreateTask = async (values) => {
    try {
      let payload = {};
      if (values.payload) {
        payload = JSON.parse(values.payload);
      }
      const response = await createInfrastructureTask({
        name: values.name,
        payload,
        execution_backend: values.execution_backend || 'auto',
      });
      message.success('异步任务已提交');
      taskForm.resetFields();
      taskForm.setFieldsValue({
        name: values.name,
        execution_backend: values.execution_backend || 'auto',
        payload: values.payload,
      });
      if (response?.execution_backend === 'celery') {
        message.info('任务已路由到 Celery worker');
      }
      loadInfrastructure();
    } catch (error) {
      message.error(`提交任务失败: ${error.userMessage || error.message}`);
    }
  };

  const handleCancelTask = async (taskId) => {
    try {
      await cancelInfrastructureTask(taskId);
      message.success('任务取消请求已提交');
      loadInfrastructure();
    } catch (error) {
      message.error(`取消任务失败: ${error.userMessage || error.message}`);
    }
  };

  const handleSavePersistenceRecord = async (values) => {
    try {
      const payload = values.payload ? JSON.parse(values.payload) : {};
      await saveInfrastructureRecord({
        record_type: values.record_type,
        record_key: values.record_key,
        payload,
      });
      message.success('持久化记录已写入');
      persistenceRecordForm.resetFields();
      loadInfrastructure();
    } catch (error) {
      message.error(`写入持久化记录失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleBootstrapPersistence = async (values) => {
    setPersistenceBootstrapLoading(true);
    try {
      const response = await bootstrapInfrastructurePersistence({
        enable_timescale_schema: values.enable_timescale_schema !== false,
      });
      setPersistenceDiagnostics(response.diagnostics || null);
      message.success(`数据库持久化初始化完成: ${response.status}`);
      loadInfrastructure();
    } catch (error) {
      message.error(`初始化数据库持久化失败: ${error.userMessage || error.message}`);
    } finally {
      setPersistenceBootstrapLoading(false);
    }
  };

  const handlePreviewPersistenceMigration = async (values = {}) => {
    setPersistenceMigrationLoading(true);
    try {
      const response = await getInfrastructurePersistenceMigrationPreview({
        sqlitePath: values.sqlite_path || undefined,
      });
      setPersistenceMigrationPreview(response);
      message.success('持久化迁移预览已刷新');
    } catch (error) {
      message.error(`加载持久化迁移预览失败: ${error.userMessage || error.message}`);
    } finally {
      setPersistenceMigrationLoading(false);
    }
  };

  const handleRunPersistenceMigration = async (values) => {
    setPersistenceMigrationLoading(true);
    try {
      const response = await runInfrastructurePersistenceMigration({
        sqlite_path: values.sqlite_path || undefined,
        dry_run: values.dry_run !== false,
        include_records: values.include_records !== false,
        include_timeseries: values.include_timeseries !== false,
        dedupe_timeseries: values.dedupe_timeseries !== false,
        record_limit: values.record_limit || undefined,
        timeseries_limit: values.timeseries_limit || undefined,
      });
      setPersistenceMigrationPreview(response.preview || response);
      if (response.post_migration) {
        setPersistenceDiagnostics((current) => ({
          ...(current || {}),
          ...response.post_migration,
        }));
      }
      message.success(
        response.dry_run
          ? `迁移预演完成: records ${response.planned_records || 0} / timeseries ${response.planned_timeseries || 0}`
          : `迁移完成: 新增 records ${response.migrated_records || 0}，新增时序 ${response.migrated_timeseries || 0}`,
      );
      loadInfrastructure();
    } catch (error) {
      message.error(`执行持久化迁移失败: ${error.userMessage || error.message}`);
    } finally {
      setPersistenceMigrationLoading(false);
    }
  };

  const handleSaveTimeseries = async (values) => {
    try {
      const payload = values.payload ? JSON.parse(values.payload) : {};
      await saveInfrastructureTimeseries({
        series_name: values.series_name,
        symbol: values.symbol,
        timestamp: values.timestamp || new Date().toISOString(),
        value: values.value,
        payload,
      });
      message.success('时序样本已写入');
      timeseriesForm.resetFields();
      timeseriesForm.setFieldsValue({ timestamp: new Date().toISOString() });
      loadInfrastructure();
    } catch (error) {
      message.error(`写入时序样本失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleLoadPersistenceExplorer = async (values) => {
    try {
      const [recordsPayload, timeseriesPayload] = await Promise.all([
        getInfrastructureRecords({ recordType: values.record_type || undefined, limit: values.record_limit || 12 }),
        getInfrastructureTimeseries({ seriesName: values.series_name || undefined, symbol: values.symbol || undefined, limit: values.timeseries_limit || 12 }),
      ]);
      setPersistenceRecords(recordsPayload.records || []);
      setPersistenceTimeseries(timeseriesPayload.timeseries || []);
      message.success('持久化视图已刷新');
    } catch (error) {
      message.error(`刷新持久化视图失败: ${error.userMessage || error.message}`);
    }
  };

  const handleCreateToken = async (values) => {
    try {
      const response = await createInfrastructureToken(values);
      setAuthToken(response.access_token || '');
      setApiAuthToken(response.access_token || '');
      setRefreshToken(response.refresh_token || '');
      setApiRefreshToken(response.refresh_token || '');
      setAuthSession((current) => current || { user: { subject: values.subject, role: values.role } });
      message.success('研究令牌已签发');
    } catch (error) {
      message.error(`签发令牌失败: ${error.userMessage || error.message}`);
    }
  };

  const handleSaveAuthUser = async (values) => {
    try {
      const metadata = values.metadata ? JSON.parse(values.metadata) : {};
      const scopes = String(values.scopes || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      await saveInfrastructureAuthUser({
        subject: values.subject,
        password: values.password || undefined,
        role: values.role,
        display_name: values.display_name,
        enabled: values.enabled !== false,
        scopes,
        metadata,
      });
      message.success('本地用户已保存');
      authUserForm.resetFields();
      authUserForm.setFieldsValue({
        role: 'researcher',
        enabled: true,
        scopes: 'quant:read quant:write',
        metadata: '{"desk": "research"}',
      });
      loadInfrastructure();
    } catch (error) {
      message.error(`保存本地用户失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleLoginInfrastructureUser = async (values) => {
    try {
      const response = await loginInfrastructureUser(values);
      applyAuthSession(response, `已登录为 ${response.user?.display_name || response.user?.subject || values.subject}`);
      loadInfrastructure();
    } catch (error) {
      message.error(`用户登录失败: ${error.userMessage || error.message}`);
    }
  };

  const handleSaveOAuthProvider = async (values) => {
    try {
      const scopes = String(values.scopes || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const defaultScopes = String(values.default_scopes || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const extraParams = values.extra_params ? JSON.parse(values.extra_params) : {};
      const metadata = values.metadata ? JSON.parse(values.metadata) : {};
      await saveInfrastructureAuthProvider({
        provider_id: values.provider_id,
        label: values.label,
        provider_type: values.provider_type,
        enabled: values.enabled !== false,
        client_id: values.client_id,
        client_secret: values.client_secret || undefined,
        auth_url: values.auth_url || undefined,
        token_url: values.token_url || undefined,
        userinfo_url: values.userinfo_url || undefined,
        redirect_uri: values.redirect_uri || undefined,
        frontend_origin: values.frontend_origin || (typeof window !== 'undefined' ? window.location.origin : ''),
        scopes,
        auto_create_user: values.auto_create_user !== false,
        default_role: values.default_role,
        default_scopes: defaultScopes,
        subject_field: values.subject_field || undefined,
        display_name_field: values.display_name_field || undefined,
        email_field: values.email_field || undefined,
        extra_params: extraParams,
        metadata,
      });
      message.success('OAuth Provider 已保存');
      loadInfrastructure();
    } catch (error) {
      message.error(`保存 OAuth Provider 失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleStartOAuthLogin = async (providerId) => {
    try {
      const response = await startInfrastructureOAuthProvider(providerId, {
        frontend_origin: typeof window !== 'undefined' ? window.location.origin : '',
      });
      setOauthLaunchContext(response);
      oauthExchangeForm.setFieldsValue({
        provider_id: providerId,
        state: response.state,
        redirect_uri: response.redirect_uri,
      });
      const popup = typeof window !== 'undefined'
        ? window.open(response.authorization_url, `quant-oauth-${providerId}`, 'popup,width=720,height=820')
        : null;
      if (!popup) {
        message.warning('浏览器拦截了 OAuth 弹窗，请手动打开授权链接');
      } else {
        message.success(`已打开 ${providerId} OAuth 授权窗口`);
      }
    } catch (error) {
      message.error(`生成 OAuth 授权链接失败: ${error.userMessage || error.message}`);
    }
  };

  const handleExchangeOAuthCode = async (values) => {
    try {
      const response = await exchangeInfrastructureOAuthProvider(values.provider_id, {
        code: values.code,
        state: values.state,
        redirect_uri: values.redirect_uri || undefined,
        expires_in_seconds: values.expires_in_seconds,
        refresh_expires_in_seconds: values.refresh_expires_in_seconds,
      });
      applyAuthSession(response, `OAuth 登录成功: ${response.user?.display_name || response.user?.subject || values.provider_id}`);
      loadInfrastructure();
    } catch (error) {
      message.error(`OAuth 授权码交换失败: ${error.userMessage || error.message}`);
    }
  };

  const handleSyncOAuthProvidersFromEnv = async () => {
    try {
      const response = await syncInfrastructureAuthProvidersFromEnv();
      message.success(`已从环境同步 ${response.synced_count || 0} 个 OAuth Provider`);
      loadInfrastructure();
    } catch (error) {
      message.error(`从环境同步 OAuth Provider 失败: ${error.userMessage || error.message}`);
    }
  };

  const handleDiagnoseOAuthProvider = async (providerId) => {
    try {
      const response = await getInfrastructureAuthProviderDiagnostics(providerId);
      setOauthDiagnostics(response);
      message.success(`已生成 ${providerId} 诊断报告`);
    } catch (error) {
      message.error(`诊断 OAuth Provider 失败: ${error.userMessage || error.message}`);
    }
  };

  const handleRevokeRefreshSession = async (sessionId) => {
    try {
      await revokeInfrastructureAuthSession(sessionId);
      message.success('Refresh session 已撤销');
      if (authSession?.access_token && authSession?.user?.subject) {
        loadInfrastructure();
      } else {
        loadInfrastructure();
      }
    } catch (error) {
      message.error(`撤销 session 失败: ${error.userMessage || error.message}`);
    }
  };

  const handleUpdateAuthPolicy = async (values) => {
    try {
      await updateInfrastructureAuthPolicy({
        required: values.required === true,
      });
      message.success('认证策略已更新');
      loadInfrastructure();
    } catch (error) {
      message.error(`更新认证策略失败: ${error.userMessage || error.message}`);
    }
  };

  const handleUpdateRateLimits = async (values) => {
    try {
      const rules = values.rules_json ? JSON.parse(values.rules_json) : [];
      await updateInfrastructureRateLimits({
        default_requests_per_minute: values.default_requests_per_minute,
        default_burst_size: values.default_burst_size,
        rules,
      });
      message.success('限流规则已更新');
      loadInfrastructure();
    } catch (error) {
      message.error(`更新限流规则失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleTestNotification = async (values) => {
    try {
      const response = await testNotificationChannel({
        channel: values.channel,
        payload: {
          title: values.title,
          message: values.message,
          severity: values.severity,
        },
      });
      message.success(`通知通道返回: ${response.status}`);
      notificationForm.resetFields();
      loadInfrastructure();
    } catch (error) {
      message.error(`通知测试失败: ${error.userMessage || error.message}`);
    }
  };

  const handleSaveNotificationChannel = async (values) => {
    try {
      const settings = values.settings ? JSON.parse(values.settings) : {};
      await saveNotificationChannel({
        id: values.id,
        type: values.type,
        label: values.label,
        enabled: values.enabled !== false,
        settings,
      });
      notificationChannelForm.resetFields();
      message.success('通知渠道已保存');
      loadInfrastructure();
    } catch (error) {
      message.error(`保存通知渠道失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    }
  };

  const handleDeleteNotificationChannel = async (channelId) => {
    try {
      await deleteNotificationChannel(channelId);
      message.success('通知渠道已删除');
      loadInfrastructure();
    } catch (error) {
      message.error(`删除通知渠道失败: ${error.userMessage || error.message}`);
    }
  };

  const handleLoadConfigVersions = async (values) => {
    setConfigVersionLoading(true);
    try {
      const scope = {
        ownerId: values.owner_id || 'default',
        configType: values.config_type,
        configKey: values.config_key,
      };
      const response = await getConfigVersions({ ...scope, limit: values.limit || 20 });
      setActiveConfigScope(scope);
      setConfigVersions(response.versions || []);
      setConfigDiff(null);
      message.success('配置版本历史已加载');
    } catch (error) {
      message.error(`加载配置版本失败: ${error.userMessage || error.message}`);
    } finally {
      setConfigVersionLoading(false);
    }
  };

  const handleSaveConfigVersion = async (values) => {
    setConfigVersionLoading(true);
    try {
      const payload = values.payload ? JSON.parse(values.payload) : {};
      const response = await saveConfigVersion({
        owner_id: values.owner_id || 'default',
        config_type: values.config_type,
        config_key: values.config_key,
        payload,
      });
      const scope = {
        ownerId: values.owner_id || 'default',
        configType: values.config_type,
        configKey: values.config_key,
      };
      setActiveConfigScope(scope);
      const versions = await getConfigVersions({ ...scope, limit: 20 });
      setConfigVersions(versions.versions || []);
      setConfigDiff(null);
      message.success(`配置版本 v${response.payload?.version || ''} 已保存`);
    } catch (error) {
      message.error(`保存配置版本失败: ${error instanceof SyntaxError ? 'JSON 格式无效' : error.userMessage || error.message}`);
    } finally {
      setConfigVersionLoading(false);
    }
  };

  const handleDiffLatestConfigVersions = async () => {
    const ordered = [...configVersions]
      .map((record) => record.payload)
      .filter(Boolean)
      .sort((a, b) => Number(b.version || 0) - Number(a.version || 0));
    if (ordered.length < 2) {
      message.warning('至少需要两个配置版本才能对比');
      return;
    }

    setConfigVersionLoading(true);
    try {
      const response = await diffConfigVersions({
        ...activeConfigScope,
        fromVersion: ordered[1].version,
        toVersion: ordered[0].version,
      });
      setConfigDiff(response);
      message.success('最新两版配置差异已生成');
    } catch (error) {
      message.error(`配置差异生成失败: ${error.userMessage || error.message}`);
    } finally {
      setConfigVersionLoading(false);
    }
  };

  const handleRestoreConfigVersion = async (record) => {
    const version = record?.payload?.version;
    if (!version) {
      message.warning('无法识别要恢复的版本');
      return;
    }

    setConfigVersionLoading(true);
    try {
      await restoreConfigVersion({
        owner_id: activeConfigScope.ownerId,
        config_type: activeConfigScope.configType,
        config_key: activeConfigScope.configKey,
        version,
      });
      const response = await getConfigVersions({ ...activeConfigScope, limit: 20 });
      setConfigVersions(response.versions || []);
      setConfigDiff(null);
      message.success(`已从 v${version} 恢复为新版本`);
    } catch (error) {
      message.error(`恢复配置版本失败: ${error.userMessage || error.message}`);
    } finally {
      setConfigVersionLoading(false);
    }
  };

  const handleSaveTradeNote = async (values) => {
    if (!selectedTrade?.id) {
      message.warning('先选择一笔交易再保存备注');
      return;
    }

    try {
      const payload = {
        notes: {
          [selectedTrade.id]: values,
        },
      };
      const response = await updateQuantTradingJournal(payload);
      setTradingJournal(response);
      message.success('交易日志已更新');
    } catch (error) {
      message.error(`保存交易日志失败: ${error.userMessage || error.message}`);
    }
  };

  const handleAddLifecycleEntry = async (values) => {
    try {
      const existingEntries = Array.isArray(tradingJournal?.strategy_lifecycle)
        ? tradingJournal.strategy_lifecycle
        : [];
      const timestamp = new Date().toISOString();
      const payload = {
        strategy_lifecycle: [
          {
            id: `lifecycle_${Date.now()}`,
            strategy: values.strategy,
            stage: values.stage,
            status: values.status,
            owner: values.owner,
            conviction: values.conviction,
            next_action: values.next_action,
            notes: values.notes,
            created_at: timestamp,
            updated_at: timestamp,
          },
          ...existingEntries,
        ],
      };
      const response = await updateQuantTradingJournal(payload);
      setTradingJournal(response);
      lifecycleForm.resetFields();
      lifecycleForm.setFieldsValue({ stage: 'discovered', status: 'active', owner: 'research', conviction: 0.5 });
      message.success('策略生命周期条目已加入');
    } catch (error) {
      message.error(`更新策略生命周期失败: ${error.userMessage || error.message}`);
    }
  };

  const handleAddCompositeRule = async (values) => {
    try {
      const cascadeActions = parseJsonArrayField(values.cascade_actions_json, '规则级联动作');
      const existingRules = Array.isArray(alertOrchestration?.composite_rules)
        ? alertOrchestration.composite_rules
        : [];
      const payload = {
        composite_rules: [
          {
            id: `rule_${Date.now()}`,
            name: values.name,
            condition_summary: values.condition_summary,
            action: values.action,
            cascade_actions: cascadeActions,
            created_at: new Date().toISOString(),
          },
          ...existingRules,
        ],
      };
      const response = await updateQuantAlertOrchestration(payload);
      setAlertOrchestration(response);
      alertForm.resetFields();
      message.success('复合告警规则已添加');
    } catch (error) {
      message.error(`添加复合告警失败: ${error.userMessage || error.message}`);
    }
  };

  const handlePublishAlertEvent = async (values) => {
    try {
      const cascadeActions = parseJsonArrayField(values.cascade_actions_json, '事件级联动作');
      const notifyChannels = String(values.notify_channels || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const ruleIds = String(values.rule_ids || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await publishQuantAlertEvent({
        source_module: values.source_module,
        rule_name: values.rule_name,
        symbol: values.symbol,
        severity: values.severity,
        message: values.message,
        condition_summary: values.condition_summary,
        trigger_value: values.trigger_value,
        threshold: values.threshold,
        rule_ids: ruleIds,
        notify_channels: notifyChannels,
        create_workbench_task: values.create_workbench_task === true,
        workbench_task_type: values.workbench_task_type,
        workbench_status: values.workbench_status,
        persist_event_record: values.persist_event_record !== false,
        cascade_actions: cascadeActions,
      });
      setAlertOrchestration(response.orchestration || null);
      alertEventForm.resetFields();
      alertEventForm.setFieldsValue({
        source_module: 'manual',
        severity: 'warning',
        create_workbench_task: true,
        workbench_task_type: 'cross_market',
        workbench_status: 'new',
        persist_event_record: true,
        cascade_actions_json: '',
      });
      message.success(`告警事件已发布，级联动作 ${response.cascade_results?.length || 0} 条`);
    } catch (error) {
      message.error(`发布告警事件失败: ${error.userMessage || error.message}`);
    }
  };

  const handleReviewAlertHistory = async (record, reviewStatus) => {
    if (!record?.id) {
      message.warning('无法识别要更新的告警事件');
      return;
    }

    try {
      const acknowledgedAt = reviewStatus === 'pending' ? null : new Date().toISOString();
      const response = await updateQuantAlertOrchestration({
        history_updates: [
          {
            ...record,
            review_status: reviewStatus,
            acknowledged_at: acknowledgedAt,
          },
        ],
      });
      setAlertOrchestration(response);
      message.success(reviewStatus === 'false_positive' ? '已标记为误报' : '已标记为已处理');
    } catch (error) {
      message.error(`更新告警复盘状态失败: ${error.userMessage || error.message}`);
    }
  };

  const optimizerLeaderboard = useMemo(() => (
    Array.isArray(optimizerResult?.leaderboard) ? optimizerResult.leaderboard.map((item, index) => ({
      key: `${index}-${JSON.stringify(item.parameters)}`,
      rank: index + 1,
      score: item.score,
      parameters: JSON.stringify(item.parameters),
      total_return: item.metrics?.total_return,
      sharpe_ratio: item.metrics?.sharpe_ratio,
      max_drawdown: item.metrics?.max_drawdown,
    })) : []
  ), [optimizerResult]);

  const factorRows = useMemo(() => (
    Array.isArray(riskResult?.factor_decomposition?.risk_split)
      ? riskResult.factor_decomposition.risk_split.map((item) => ({ ...item, key: item.factor }))
      : []
  ), [riskResult]);

  const stressRows = useMemo(() => (
    Array.isArray(riskResult?.stress_tests)
      ? riskResult.stress_tests.map((item) => ({ ...item, key: item.scenario }))
      : []
  ), [riskResult]);

  const attributionRows = useMemo(() => (
    Array.isArray(riskResult?.performance_attribution?.rows)
      ? riskResult.performance_attribution.rows.map((item) => ({ ...item, key: item.symbol }))
      : []
  ), [riskResult]);

  const correlationCells = useMemo(() => (
    Array.isArray(riskResult?.correlation_matrix?.cells) ? riskResult.correlation_matrix.cells : []
  ), [riskResult]);

  const factorPreviewRows = useMemo(() => (
    Array.isArray(factorResult?.preview)
      ? factorResult.preview.map((item) => ({ ...item, key: item.date }))
      : []
  ), [factorResult]);

  const infrastructureTaskRows = useMemo(() => (
    Array.isArray(infrastructureTasks)
      ? infrastructureTasks.map((item) => ({ ...item, key: item.id }))
      : []
  ), [infrastructureTasks]);

  const configVersionRows = useMemo(() => (
    Array.isArray(configVersions)
      ? configVersions.map((item) => ({ ...item, key: item.id }))
      : []
  ), [configVersions]);

  const configDiffRows = useMemo(() => (
    Array.isArray(configDiff?.changes)
      ? configDiff.changes.map((item, index) => ({ ...item, key: `${item.path}-${index}` }))
      : []
  ), [configDiff]);

  const valuationPeerRows = useMemo(() => (
    Array.isArray(valuationResult?.peer_matrix?.rows)
      ? valuationResult.peer_matrix.rows.map((item) => ({ ...item, key: item.symbol }))
      : []
  ), [valuationResult]);

  const monteCarloFanRows = useMemo(() => (
    backtestEnhancementResult?.type === 'monte_carlo' && Array.isArray(backtestEnhancementResult.payload?.monte_carlo?.fan_chart)
      ? backtestEnhancementResult.payload.monte_carlo.fan_chart.map((item) => ({ ...item, key: item.step }))
      : []
  ), [backtestEnhancementResult]);

  const significanceRows = useMemo(() => (
    backtestEnhancementResult?.type === 'significance' && Array.isArray(backtestEnhancementResult.payload?.comparisons)
      ? backtestEnhancementResult.payload.comparisons.map((item) => ({
          key: `${item.baseline}-${item.challenger}`,
          baseline: item.baseline,
          challenger: item.challenger,
          p_value: item.significance?.bootstrap?.p_value,
          t_p_value: item.significance?.paired_t_test?.p_value,
          annualized_delta: item.significance?.observed_annualized_delta,
          sharpe_delta: item.significance?.observed_sharpe_delta,
          significant: item.significance?.bootstrap?.significant_95,
        }))
      : []
  ), [backtestEnhancementResult]);

  const multiPeriodRows = useMemo(() => (
    backtestEnhancementResult?.type === 'multi_period' && Array.isArray(backtestEnhancementResult.payload?.intervals)
      ? backtestEnhancementResult.payload.intervals.map((item) => ({ ...item, key: item.interval }))
      : []
  ), [backtestEnhancementResult]);

  const impactScenarioRows = useMemo(() => (
    backtestEnhancementResult?.type === 'impact_analysis' && Array.isArray(backtestEnhancementResult.payload?.scenarios)
      ? backtestEnhancementResult.payload.scenarios.map((item) => ({
          key: item.label,
          label: item.label,
          model: item.scenario?.market_impact_model,
          impact_bps: item.scenario?.market_impact_bps,
          total_return: item.metrics?.total_return,
          sharpe_ratio: item.metrics?.sharpe_ratio,
          max_drawdown: item.metrics?.max_drawdown,
          impact_cost: item.execution_costs?.estimated_market_impact_cost,
          avg_impact_rate: item.execution_costs?.average_market_impact_rate,
          return_delta: item.vs_baseline?.return_delta,
        }))
      : []
  ), [backtestEnhancementResult]);

  const impactCurveRows = useMemo(() => (
    backtestEnhancementResult?.type === 'impact_analysis' && Array.isArray(backtestEnhancementResult.payload?.scenarios)
      ? backtestEnhancementResult.payload.scenarios.flatMap((scenario) => (
          Array.isArray(scenario.impact_curve)
            ? scenario.impact_curve.map((point) => ({
                key: `${scenario.label}-${point.trade_value}`,
                label: scenario.label,
                ...point,
              }))
            : []
        ))
      : []
  ), [backtestEnhancementResult]);

  const industryIntelRows = useMemo(() => (
    Array.isArray(industryIntelResult?.industries)
      ? industryIntelResult.industries.map((item) => ({ ...item, key: item.industry_name }))
      : []
  ), [industryIntelResult]);

  const industryNetworkEdges = useMemo(() => (
    Array.isArray(industryNetworkResult?.edges)
      ? industryNetworkResult.edges.map((item, index) => ({ ...item, key: `${item.source}-${item.target}-${index}` }))
      : []
  ), [industryNetworkResult]);

  const macroHorizonRows = useMemo(() => (
    Array.isArray(macroValidationResult?.horizon_results)
      ? macroValidationResult.horizon_results.map((item) => ({ ...item, key: item.horizon_days }))
      : []
  ), [macroValidationResult]);

  const macroFactorRows = useMemo(() => (
    Array.isArray(macroValidationResult?.factor_results)
      ? macroValidationResult.factor_results.map((item, index) => ({ ...item, key: `${item.factor}-${item.horizon_days}-${index}` }))
      : []
  ), [macroValidationResult]);

  const altProviderRows = useMemo(() => (
    Array.isArray(altSignalDiagnostics?.providers)
      ? altSignalDiagnostics.providers.map((item) => ({ ...item, key: item.provider }))
      : []
  ), [altSignalDiagnostics]);

  const altDecayRows = useMemo(() => (
    Array.isArray(altSignalDiagnostics?.decay_curve)
      ? altSignalDiagnostics.decay_curve.map((item) => ({ ...item, key: item.age_days }))
      : []
  ), [altSignalDiagnostics]);

  const replayRows = useMemo(() => (
    Array.isArray(replayResult?.bars)
      ? replayResult.bars.map((item, index) => ({ ...item, key: `${item.timestamp}-${index}` }))
      : []
  ), [replayResult]);

  const orderbookRows = useMemo(() => {
    const bids = Array.isArray(orderbookResult?.bids) ? orderbookResult.bids.map((item, index) => ({ ...item, side: 'Bid', key: `bid-${index}` })) : [];
    const asks = Array.isArray(orderbookResult?.asks) ? orderbookResult.asks.map((item, index) => ({ ...item, side: 'Ask', key: `ask-${index}` })) : [];
    return [...bids, ...asks];
  }, [orderbookResult]);

  const orderbookProviderRows = useMemo(() => (
    Array.isArray(orderbookResult?.diagnostics?.provider_candidates)
      ? orderbookResult.diagnostics.provider_candidates.map((item, index) => ({ ...item, key: `${item.provider}-${index}` }))
      : []
  ), [orderbookResult]);

  const anomalyRows = useMemo(() => (
    Array.isArray(anomalyDiagnostics?.recent_anomalies)
      ? anomalyDiagnostics.recent_anomalies.map((item, index) => ({ ...item, key: `${item.timestamp}-${index}` }))
      : []
  ), [anomalyDiagnostics]);

  const anomalyPatternRows = useMemo(() => (
    Array.isArray(anomalyDiagnostics?.pattern_matches)
      ? anomalyDiagnostics.pattern_matches.map((item, index) => ({ ...item, key: `${item.timestamp}-${index}` }))
      : []
  ), [anomalyDiagnostics]);

  const linkedReplayRows = useMemo(() => {
    const series = Array.isArray(linkedReplayResult?.series) ? linkedReplayResult.series : [];
    if (!series.length) {
      return [];
    }

    const bucket = new Map();
    series.forEach((entry) => {
      (entry.bars || []).forEach((bar) => {
        const timestamp = bar.timestamp || bar.date;
        if (!timestamp) {
          return;
        }
        const existing = bucket.get(timestamp) || { key: timestamp, timestamp };
        existing[entry.symbol] = bar.close;
        bucket.set(timestamp, existing);
      });
    });

    return Array.from(bucket.values())
      .sort((left, right) => String(left.timestamp).localeCompare(String(right.timestamp)))
      .slice(-40);
  }, [linkedReplayResult]);

  const tabs = [
    {
      key: 'optimizer',
      label: <span><ClusterOutlined />策略优化器</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={optimizerForm}
              layout="vertical"
              initialValues={{
                symbol: 'AAPL',
                strategy: 'moving_average',
                density: 3,
                optimization_metric: 'sharpe_ratio',
                optimization_method: 'grid',
                initial_capital: 10000,
                commission: 0.001,
                slippage: 0.001,
              }}
              onFinish={handleOptimize}
            >
              <Row gutter={16}>
                <Col xs={24} md={6}>
                  <Form.Item name="symbol" label="标的代码" rules={[{ required: true, message: '请输入标的代码' }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item name="strategy" label="策略" rules={[{ required: true, message: '请选择策略' }]}>
                    <Select
                      options={strategies.map((item) => ({
                        value: item.name,
                        label: `${item.name} · ${item.description}`,
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="density" label="网格密度">
                    <InputNumber min={2} max={6} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="optimization_method" label="优化方式">
                    <Select options={[{ value: 'grid', label: '网格搜索' }, { value: 'bayesian', label: '贝叶斯搜索' }]} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="optimization_metric" label="优化目标">
                    <Select options={[{ value: 'sharpe_ratio', label: '夏普' }, { value: 'total_return', label: '总收益' }, { value: 'calmar_ratio', label: '卡玛' }]} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="initial_capital" label="初始资金">
                    <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="commission" label="手续费">
                    <InputNumber min={0} step={0.0005} precision={4} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="slippage" label="滑点">
                    <InputNumber min={0} step={0.0005} precision={4} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={optimizerLoading}>运行优化</Button>
                <Button onClick={handleQueueOptimizer} loading={Boolean(queuedTaskLoading.optimizer)}>异步排队</Button>
              </Space>
            </Form>
          </Card>

          {optimizerLoading ? <Spin size="large" /> : null}
          {!optimizerLoading && optimizerResult ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}><Card><Statistic title="最佳训练夏普" value={Number(optimizerResult.best_train_metrics?.sharpe_ratio || 0).toFixed(3)} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="样本外收益" value={formatPct(optimizerResult.validation_metrics?.total_return || 0)} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="参数稳定度" value={Number(optimizerResult.parameter_stability?.score || 0).toFixed(3)} /></Card></Col>
              </Row>
              <Card title="最优参数与验证闭环">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Alert
                    type="success"
                    showIcon
                    message={`最佳参数: ${JSON.stringify(optimizerResult.best_parameters || {})}`}
                    description={`已生成验证回测请求，可直接回放到主回测模块。全样本收益 ${formatPct(optimizerResult.full_sample_metrics?.total_return || 0)}，全样本夏普 ${Number(optimizerResult.full_sample_metrics?.sharpe_ratio || 0).toFixed(3)}。`}
                  />
                  <Text code>{JSON.stringify(optimizerResult.validation_backtest_request || {})}</Text>
                </Space>
              </Card>
              <Card title="参数敏感度热力图">
                <HeatmapGrid heatmap={optimizerResult.heatmap} />
              </Card>
              <Card title="候选参数排行榜">
                <Table
                  size="small"
                  pagination={{ pageSize: 8 }}
                  dataSource={optimizerLeaderboard}
                  columns={[
                    { title: '#', dataIndex: 'rank', width: 64 },
                    { title: 'Score', dataIndex: 'score', render: (value) => Number(value || 0).toFixed(3) },
                    { title: '参数', dataIndex: 'parameters', ellipsis: true },
                    { title: '收益', dataIndex: 'total_return', render: (value) => formatPct(value || 0) },
                    { title: '夏普', dataIndex: 'sharpe_ratio', render: (value) => Number(value || 0).toFixed(3) },
                    { title: '回撤', dataIndex: 'max_drawdown', render: (value) => formatPct(value || 0) },
                  ]}
                />
              </Card>
              {optimizerResult.walk_forward?.aggregate_metrics ? (
                <Card title="Walk-Forward 稳健性">
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={6}><Statistic title="窗口数" value={optimizerResult.walk_forward.n_windows || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="平均收益" value={formatPct(optimizerResult.walk_forward.aggregate_metrics.average_return || 0)} /></Col>
                    <Col xs={24} md={6}><Statistic title="平均夏普" value={Number(optimizerResult.walk_forward.aggregate_metrics.average_sharpe || 0).toFixed(3)} /></Col>
                    <Col xs={24} md={6}><Statistic title="Monte Carlo P50" value={Number(optimizerResult.walk_forward.monte_carlo?.p50 || 0).toFixed(3)} /></Col>
                  </Row>
                </Card>
              ) : null}
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'backtest-enhance',
      label: <span><BarChartOutlined />回测增强</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={6}>
              <Card title="Monte Carlo 模拟">
                <Form
                  form={monteCarloForm}
                  layout="vertical"
                  initialValues={{
                    symbol: 'AAPL',
                    strategy: 'buy_and_hold',
                    simulations: 500,
                    horizon_days: 63,
                    initial_capital: 10000,
                  }}
                  onFinish={handleBacktestMonteCarlo}
                >
                  <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '请输入标的' }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="strategy" label="策略">
                    <Select options={strategies.map((item) => ({ value: item.name, label: item.name }))} />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="simulations" label="模拟次数">
                        <InputNumber min={50} max={10000} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="horizon_days" label="预测天数">
                        <InputNumber min={5} max={756} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Space wrap>
                    <Button type="primary" htmlType="submit" loading={backtestEnhancementLoading}>运行 MC</Button>
                    <Button onClick={handleQueueBacktestMonteCarlo} loading={Boolean(queuedTaskLoading.backtest_monte_carlo)}>异步排队</Button>
                  </Space>
                </Form>
              </Card>
            </Col>
            <Col xs={24} xl={6}>
              <Card title="策略显著性检验">
                <Form
                  form={significanceForm}
                  layout="vertical"
                  initialValues={{
                    symbol: 'AAPL',
                    strategies: 'buy_and_hold, moving_average',
                    bootstrap_samples: 500,
                    initial_capital: 10000,
                  }}
                  onFinish={handleStrategySignificance}
                >
                  <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '请输入标的' }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="strategies" label="策略列表">
                    <Input placeholder="buy_and_hold, moving_average" />
                  </Form.Item>
                  <Form.Item name="bootstrap_samples" label="Bootstrap 次数">
                    <InputNumber min={100} max={10000} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                  <Space wrap>
                    <Button type="primary" htmlType="submit" loading={backtestEnhancementLoading}>检验显著性</Button>
                    <Button onClick={handleQueueStrategySignificance} loading={Boolean(queuedTaskLoading.backtest_significance)}>异步排队</Button>
                  </Space>
                </Form>
              </Card>
            </Col>
            <Col xs={24} xl={6}>
              <Card title="多周期回测">
                <Form
                  form={multiPeriodForm}
                  layout="vertical"
                  initialValues={{
                    symbol: 'AAPL',
                    strategy: 'buy_and_hold',
                    intervals: '1d,1wk,1mo',
                    initial_capital: 10000,
                  }}
                  onFinish={handleMultiPeriodBacktest}
                >
                  <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '请输入标的' }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="strategy" label="策略">
                    <Select options={strategies.map((item) => ({ value: item.name, label: item.name }))} />
                  </Form.Item>
                  <Form.Item name="intervals" label="周期列表">
                    <Input placeholder="1d,1wk,1mo" />
                  </Form.Item>
                  <Space wrap>
                    <Button type="primary" htmlType="submit" loading={backtestEnhancementLoading}>运行多周期</Button>
                    <Button onClick={handleQueueMultiPeriodBacktest} loading={Boolean(queuedTaskLoading.backtest_multi_period)}>异步排队</Button>
                  </Space>
                </Form>
              </Card>
            </Col>
            <Col xs={24} xl={6}>
              <Card title="市场冲击诊断">
                <Form
                  form={impactAnalysisForm}
                  layout="vertical"
                  initialValues={{
                    symbol: 'AAPL',
                    strategy: 'buy_and_hold',
                    market_impact_bps: 12,
                    market_impact_model: 'almgren_chriss',
                    impact_reference_notional: 100000,
                    impact_coefficient: 1.2,
                    permanent_impact_bps: 4,
                    sample_trade_values: '10000,50000,100000,250000',
                    initial_capital: 10000,
                  }}
                  onFinish={handleMarketImpactAnalysis}
                >
                  <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '请输入标的' }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="strategy" label="策略">
                    <Select options={strategies.map((item) => ({ value: item.name, label: item.name }))} />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="market_impact_model" label="模型">
                        <Select options={[
                          { value: 'constant', label: '常数冲击' },
                          { value: 'linear', label: '线性' },
                          { value: 'sqrt', label: '平方根' },
                          { value: 'almgren_chriss', label: 'Almgren-Chriss' },
                        ]} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="market_impact_bps" label="基础冲击(bps)">
                        <InputNumber min={0} max={200} precision={2} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="impact_reference_notional" label="流动性锚">
                        <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="impact_coefficient" label="冲击系数">
                        <InputNumber min={0} step={0.1} precision={2} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item name="permanent_impact_bps" label="永久冲击(bps)">
                    <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="sample_trade_values" label="样本成交额">
                    <Input placeholder="10000,50000,100000,250000" />
                  </Form.Item>
                  <Space wrap>
                    <Button type="primary" htmlType="submit" loading={backtestEnhancementLoading}>分析冲击</Button>
                    <Button onClick={handleQueueMarketImpactAnalysis} loading={Boolean(queuedTaskLoading.backtest_impact_analysis)}>异步排队</Button>
                  </Space>
                </Form>
              </Card>
            </Col>
          </Row>

          {backtestEnhancementLoading ? <Spin size="large" /> : null}
          {!backtestEnhancementLoading && backtestEnhancementResult?.type === 'monte_carlo' ? (
            <Card title="Monte Carlo 结果">
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Statistic title="亏损概率" value={formatPct(backtestEnhancementResult.payload?.monte_carlo?.return_distribution?.probability_of_loss || 0)} /></Col>
                <Col xs={24} md={6}><Statistic title="收益 P05" value={formatPct(backtestEnhancementResult.payload?.monte_carlo?.return_distribution?.p05 || 0)} /></Col>
                <Col xs={24} md={6}><Statistic title="收益 P95" value={formatPct(backtestEnhancementResult.payload?.monte_carlo?.return_distribution?.p95 || 0)} /></Col>
                <Col xs={24} md={6}><Statistic title="终值 P50" value={formatMoney(backtestEnhancementResult.payload?.monte_carlo?.terminal_value?.p50 || 0)} /></Col>
              </Row>
              <Table
                style={{ marginTop: 16 }}
                size="small"
                pagination={{ pageSize: 8 }}
                dataSource={monteCarloFanRows}
                columns={[
                  { title: 'Step', dataIndex: 'step' },
                  { title: 'P10', dataIndex: 'p10', render: formatMoney },
                  { title: 'P50', dataIndex: 'p50', render: formatMoney },
                  { title: 'P90', dataIndex: 'p90', render: formatMoney },
                ]}
              />
            </Card>
          ) : null}
          {!backtestEnhancementLoading && backtestEnhancementResult?.type === 'significance' ? (
            <Card title="显著性检验结果">
              <Table
                size="small"
                pagination={false}
                dataSource={significanceRows}
                columns={[
                  { title: '基准', dataIndex: 'baseline' },
                  { title: '挑战者', dataIndex: 'challenger' },
                  { title: '年化差值', dataIndex: 'annualized_delta', render: (value) => formatPct(value || 0) },
                  { title: '夏普差值', dataIndex: 'sharpe_delta', render: (value) => Number(value || 0).toFixed(3) },
                  { title: 'Bootstrap p', dataIndex: 'p_value', render: (value) => Number(value || 0).toFixed(4) },
                  { title: '显著', dataIndex: 'significant', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '是' : '否'}</Tag> },
                ]}
              />
            </Card>
          ) : null}
          {!backtestEnhancementLoading && backtestEnhancementResult?.type === 'multi_period' ? (
            <Card title="多周期结果">
              <Table
                size="small"
                pagination={false}
                dataSource={multiPeriodRows}
                columns={[
                  { title: '周期', dataIndex: 'interval' },
                  { title: '状态', dataIndex: 'success', render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '成功' : '失败'}</Tag> },
                  { title: '样本数', dataIndex: 'data_points' },
                  { title: '收益', render: (_, record) => formatPct(record.metrics?.total_return || 0) },
                  { title: '夏普', render: (_, record) => Number(record.metrics?.sharpe_ratio || 0).toFixed(3) },
                  { title: '回撤', render: (_, record) => formatPct(record.metrics?.max_drawdown || 0) },
                ]}
              />
            </Card>
          ) : null}
          {!backtestEnhancementLoading && backtestEnhancementResult?.type === 'impact_analysis' ? (
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Card title="市场冲击场景对比">
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={8}>
                    <Statistic title="场景数" value={backtestEnhancementResult.payload?.summary?.scenario_count || 0} />
                  </Col>
                  <Col xs={24} md={8}>
                    <Statistic title="最佳模型" value={backtestEnhancementResult.payload?.summary?.best_by_sharpe?.label || '--'} />
                  </Col>
                  <Col xs={24} md={8}>
                    <Statistic title="最佳夏普" value={Number(backtestEnhancementResult.payload?.summary?.best_by_sharpe?.metrics?.sharpe_ratio || 0).toFixed(3)} />
                  </Col>
                </Row>
                <Table
                  style={{ marginTop: 16 }}
                  size="small"
                  pagination={false}
                  dataSource={impactScenarioRows}
                  columns={[
                    { title: '场景', dataIndex: 'label' },
                    { title: '模型', dataIndex: 'model' },
                    { title: '基础冲击', dataIndex: 'impact_bps', render: (value) => `${Number(value || 0).toFixed(2)} bps` },
                    { title: '收益', dataIndex: 'total_return', render: (value) => formatPct(value || 0) },
                    { title: '夏普', dataIndex: 'sharpe_ratio', render: (value) => Number(value || 0).toFixed(3) },
                    { title: '回撤', dataIndex: 'max_drawdown', render: (value) => formatPct(value || 0) },
                    { title: '冲击成本', dataIndex: 'impact_cost', render: (value) => formatMoney(value || 0) },
                    { title: '相对基线收益', dataIndex: 'return_delta', render: (value) => formatPct(value || 0) },
                  ]}
                />
              </Card>
              <Card title="成交规模冲击曲线">
                <Table
                  size="small"
                  pagination={{ pageSize: 12 }}
                  dataSource={impactCurveRows}
                  columns={[
                    { title: '场景', dataIndex: 'label' },
                    { title: '成交额', dataIndex: 'trade_value', render: formatMoney },
                    { title: '估算股数', dataIndex: 'estimated_shares', render: (value) => Number(value || 0).toFixed(2) },
                    { title: '参与率', dataIndex: 'participation_rate', render: (value) => formatPct(value || 0) },
                    { title: '冲击(bps)', dataIndex: 'market_impact_bps', render: (value) => Number(value || 0).toFixed(2) },
                    { title: '估算成本', dataIndex: 'estimated_cost', render: formatMoney },
                  ]}
                />
              </Card>
            </Space>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'risk',
      label: <span><RadarChartOutlined />风险归因中心</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={riskForm}
              layout="vertical"
              initialValues={{
                symbols: 'AAPL, MSFT, NVDA',
                weights: '0.4, 0.35, 0.25',
                period: '1y',
              }}
              onFinish={handleRiskAnalysis}
            >
              <Row gutter={16}>
                <Col xs={24} md={10}>
                  <Form.Item name="symbols" label="组合标的" rules={[{ required: true, message: '请输入标的列表' }]}>
                    <Input placeholder="逗号分隔，如 AAPL, MSFT, NVDA" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="weights" label="组合权重">
                    <Input placeholder="可选，逗号分隔，如 0.4, 0.3, 0.3" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={4}>
                  <Form.Item name="period" label="历史区间">
                    <Select options={PERIOD_OPTIONS} />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={riskLoading}>运行风险分析</Button>
                <Button onClick={handleQueueRiskAnalysis} loading={Boolean(queuedTaskLoading.risk)}>异步排队</Button>
              </Space>
            </Form>
          </Card>

          {riskLoading ? <Spin size="large" /> : null}
          {!riskLoading && riskResult ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Card><Statistic title="年化收益" value={formatPct(riskResult.summary?.annualized_return || 0)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="年化波动" value={formatPct(riskResult.summary?.volatility || 0)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="夏普比率" value={Number(riskResult.summary?.sharpe_ratio || 0).toFixed(3)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="最大回撤" value={formatPct(riskResult.summary?.max_drawdown || 0)} /></Card></Col>
              </Row>
              <Card title="VaR / CVaR">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="method"
                  dataSource={[
                    { method: '历史模拟', ...riskResult.var_cvar?.historical },
                    { method: '参数法', ...riskResult.var_cvar?.parametric },
                    { method: 'Monte Carlo', ...riskResult.var_cvar?.monte_carlo },
                  ]}
                  columns={[
                    { title: '方法', dataIndex: 'method' },
                    { title: '95% VaR', render: (_, record) => formatPct(record.confidence_95?.var || 0) },
                    { title: '95% CVaR', render: (_, record) => formatPct(record.confidence_95?.cvar || 0) },
                    { title: '99% VaR', render: (_, record) => formatPct(record.confidence_99?.var || 0) },
                    { title: '99% CVaR', render: (_, record) => formatPct(record.confidence_99?.cvar || 0) },
                  ]}
                />
              </Card>
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={12}>
                  <Card title="因子风险分解">
                    <Table
                      size="small"
                      pagination={false}
                      dataSource={factorRows}
                      columns={[
                        { title: '因子', dataIndex: 'factor' },
                        { title: '暴露', dataIndex: 'loading', render: (value) => Number(value || 0).toFixed(3) },
                        { title: '年化贡献', dataIndex: 'annual_contribution', render: (value) => formatPct(value || 0) },
                        { title: '风险占比', dataIndex: 'risk_share', render: (value) => formatPct(value || 0) },
                      ]}
                    />
                  </Card>
                </Col>
                <Col xs={24} xl={12}>
                  <Card title="压力测试">
                    <Table
                      size="small"
                      pagination={false}
                      dataSource={stressRows}
                      columns={[
                        { title: '情景', dataIndex: 'label' },
                        { title: '投影收益', dataIndex: 'projected_return', render: (value) => formatPct(value || 0) },
                        { title: '投影 VaR95', dataIndex: 'projected_var_95', render: (value) => formatPct(value || 0) },
                        { title: '级别', dataIndex: 'severity', render: (value) => <Tag color={value === 'high' ? 'red' : value === 'medium' ? 'orange' : 'green'}>{value}</Tag> },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
              <Card title="收益归因">
                <Table
                  size="small"
                  pagination={{ pageSize: 6 }}
                  dataSource={attributionRows}
                  columns={[
                    { title: '标的', dataIndex: 'symbol' },
                    { title: '组合权重', dataIndex: 'portfolio_weight', render: (value) => formatPct(value || 0) },
                    { title: '基准权重', dataIndex: 'benchmark_weight', render: (value) => formatPct(value || 0) },
                    { title: '区间收益', dataIndex: 'asset_return', render: (value) => formatPct(value || 0) },
                    { title: '配置效应', dataIndex: 'allocation_effect', render: (value) => formatPct(value || 0) },
                  ]}
                />
              </Card>
              <Card title="相关性矩阵">
                {correlationCells.length ? <HeatmapGrid heatmap={{ type: 'matrix', x_key: 'asset', y_key: 'asset', cells: correlationCells.map((item) => ({ x: item.symbol1, y: item.symbol2, value: item.correlation })) }} /> : <Empty description="暂无相关性矩阵" />}
              </Card>
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'valuation',
      label: <span><FundOutlined />估值历史与集成</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={valuationForm}
              layout="vertical"
              initialValues={{ symbol: 'AAPL', period: '1y', peer_limit: 6, peer_symbols: 'MSFT, NVDA, GOOGL, AMZN' }}
              onFinish={handleValuationAnalysis}
            >
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item name="symbol" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item name="period" label="因子周期">
                    <Select options={PERIOD_OPTIONS} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={4}>
                  <Form.Item name="peer_limit" label="同行数量">
                    <InputNumber min={2} max={12} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item name="peer_symbols" label="自定义 Peer 组">
                    <Input placeholder="可选，如 MSFT, NVDA, GOOGL" />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={valuationLoading}>运行估值实验</Button>
                <Button onClick={handleQueueValuation} loading={Boolean(queuedTaskLoading.valuation)}>异步排队</Button>
              </Space>
            </Form>
          </Card>
          {valuationLoading ? <Spin size="large" /> : null}
          {!valuationLoading && valuationResult ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}><Card><Statistic title="综合公允价值" value={formatMoney(valuationResult.ensemble_valuation?.fair_value || 0)} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="市场偏离" value={formatSignedPct(valuationResult.ensemble_valuation?.gap_pct || 0)} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="现价" value={formatMoney(valuationResult.analysis?.valuation?.current_price || 0)} /></Card></Col>
              </Row>
              <Card title="模型集成权重">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="model"
                  dataSource={valuationResult.ensemble_valuation?.models || []}
                  columns={[
                    { title: '模型', dataIndex: 'model' },
                    { title: '估值', dataIndex: 'value', render: (value) => formatMoney(value || 0) },
                    { title: '权重', dataIndex: 'weight', render: (value) => formatPct(value || 0) },
                  ]}
                />
              </Card>
              <Card title="估值历史追踪">
                <Table
                  size="small"
                  pagination={{ pageSize: 6 }}
                  rowKey="timestamp"
                  dataSource={valuationResult.valuation_history || []}
                  columns={[
                    { title: '时间', dataIndex: 'timestamp', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                    { title: '综合公允价值', dataIndex: 'fair_value', render: (value) => formatMoney(value || 0) },
                    { title: '现价', dataIndex: 'market_price', render: (value) => formatMoney(value || 0) },
                    { title: '偏离', dataIndex: 'gap_pct', render: (value) => formatSignedPct(value || 0) },
                  ]}
                />
              </Card>
              {valuationPeerRows.length ? (
                <Card title="同行对比矩阵">
                  <Space wrap size={8} style={{ marginBottom: 12 }}>
                    {valuationResult.peer_matrix?.sector ? <Tag color="blue">{valuationResult.peer_matrix.sector}</Tag> : null}
                    {valuationResult.peer_matrix?.industry ? <Tag>{valuationResult.peer_matrix.industry}</Tag> : null}
                    <Tag>{`同行 ${valuationResult.peer_matrix?.summary?.peer_count || 0} 家`}</Tag>
                    <Tag>{`自定义 Peer ${valuationResult.peer_matrix?.summary?.custom_peer_count || 0} 家`}</Tag>
                    {valuationResult.peer_matrix?.summary?.median_peer_premium_discount !== null && valuationResult.peer_matrix?.summary?.median_peer_premium_discount !== undefined ? (
                      <Tag>{`同行溢折价中位数 ${Number(valuationResult.peer_matrix.summary.median_peer_premium_discount).toFixed(1)}%`}</Tag>
                    ) : null}
                  </Space>
                  <Table
                    size="small"
                    pagination={{ pageSize: 8 }}
                    dataSource={valuationPeerRows}
                    columns={[
                      {
                        title: '标的',
                        dataIndex: 'symbol',
                        render: (value, record) => (
                          <Space size={6}>
                            <Text strong>{value}</Text>
                            {record.is_target ? <Tag color="blue">当前</Tag> : null}
                            {!record.is_target ? <Tag color={record.peer_source === 'custom' ? 'gold' : 'default'}>{record.peer_source === 'custom' ? '自定义' : '自动'}</Tag> : null}
                          </Space>
                        ),
                      },
                      { title: '现价 / 公允', render: (_, record) => `${formatMoney(record.current_price || 0)} / ${formatMoney(record.fair_value || 0)}` },
                      { title: '溢折价', dataIndex: 'premium_discount', render: (value) => value === null || value === undefined ? '--' : <Tag color={value > 0 ? 'red' : 'green'}>{`${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`}</Tag> },
                      { title: 'P/E', dataIndex: 'pe_ratio', render: (value) => value ? Number(value).toFixed(1) : '--' },
                      { title: 'P/S', dataIndex: 'price_to_sales', render: (value) => value ? Number(value).toFixed(1) : '--' },
                      { title: '收入增速', dataIndex: 'revenue_growth', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                      { title: '盈利增速', dataIndex: 'earnings_growth', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                      { title: 'ROE', dataIndex: 'return_on_equity', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                      { title: '利润率', dataIndex: 'profit_margin', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                      { title: '价值分', dataIndex: 'value_score', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(3) },
                      { title: '成长分', dataIndex: 'growth_score', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(3) },
                      { title: '质量分', dataIndex: 'quality_score', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(3) },
                    ]}
                  />
                </Card>
              ) : null}
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'industry',
      label: <span><ClusterOutlined />行业轮动策略</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={rotationForm}
              layout="vertical"
              initialValues={{
                start_date: '2024-01-01',
                end_date: '2025-12-31',
                rebalance_freq: 'monthly',
                top_industries: 3,
                stocks_per_industry: 3,
                weight_method: 'equal',
                initial_capital: 1000000,
                commission: 0.001,
                slippage: 0.001,
              }}
              onFinish={handleIndustryRotation}
            >
              <Row gutter={16}>
                <Col xs={24} md={6}>
                  <Form.Item name="start_date" label="开始日期" rules={[{ required: true, message: '请输入开始日期' }]}>
                    <Input placeholder="YYYY-MM-DD" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item name="end_date" label="结束日期" rules={[{ required: true, message: '请输入结束日期' }]}>
                    <Input placeholder="YYYY-MM-DD" />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="rebalance_freq" label="调仓频率">
                    <Select options={[{ value: 'weekly', label: '每周' }, { value: 'biweekly', label: '双周' }, { value: 'monthly', label: '每月' }, { value: 'quarterly', label: '季度' }]} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="top_industries" label="热门行业数">
                    <InputNumber min={1} max={6} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="stocks_per_industry" label="每行业股票数">
                    <InputNumber min={1} max={6} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="weight_method" label="权重方式">
                    <Select options={[{ value: 'equal', label: '等权' }, { value: 'market_cap', label: '市值权重' }]} />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={rotationLoading}>运行行业轮动回测</Button>
                <Button onClick={handleQueueIndustryRotation} loading={Boolean(queuedTaskLoading.industry_rotation)}>异步排队</Button>
              </Space>
            </Form>
          </Card>
          {rotationLoading ? <Spin size="large" /> : null}
          {!rotationLoading && rotationResult ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Card><Statistic title="总收益" value={formatPct(rotationResult.summary?.total_return || 0)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="超额收益" value={formatPct(rotationResult.summary?.excess_return || 0)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="夏普" value={Number(rotationResult.summary?.sharpe_ratio || 0).toFixed(3)} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="最大回撤" value={formatPct(rotationResult.summary?.max_drawdown || 0)} /></Card></Col>
              </Row>
              <Card title="策略诊断">
                <Alert
                  type="info"
                  showIcon
                  message={`基准 ${formatPct(rotationResult.summary?.benchmark_return || 0)}，胜率 ${formatPct(rotationResult.summary?.win_rate || 0)}`}
                  description={`交易次数 ${rotationResult.summary?.trade_count || 0}，Sortino ${Number(rotationResult.summary?.sortino_ratio || 0).toFixed(3)}，Calmar ${Number(rotationResult.summary?.calmar_ratio || 0).toFixed(3)}，VaR95 ${formatPct(rotationResult.summary?.var_95 || 0)}。`}
                />
                <Table
                  style={{ marginTop: 16 }}
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.date}
                  dataSource={(rotationResult.equity_curve || []).slice(-12)}
                  columns={[
                    { title: '日期', dataIndex: 'date' },
                    { title: '净值', dataIndex: 'value', render: (value) => formatMoney(value || 0) },
                  ]}
                />
              </Card>
              <Card title="回测执行与代理诊断">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="label"
                  dataSource={[
                    { label: '行业选择来源', value: rotationResult.diagnostics?.industry_selection_source || '--' },
                    { label: '龙头选择来源', value: rotationResult.diagnostics?.leader_selection_source || '--' },
                    { label: 'Proxy 覆盖率', value: `${Math.round(Number(rotationResult.diagnostics?.proxy_coverage_ratio || 0) * 100)}%` },
                    { label: 'Benchmark', value: rotationResult.diagnostics?.benchmark_symbol || '--' },
                  ]}
                  columns={[
                    { title: '诊断项', dataIndex: 'label' },
                    { title: '值', dataIndex: 'value' },
                  ]}
                />
              </Card>
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'industry-intel',
      label: <span><ApartmentOutlined />行业智能</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={industryIntelForm}
              layout="vertical"
              initialValues={{
                top_n: 12,
                network_top_n: 18,
                lookback_days: 5,
                min_similarity: 0.92,
              }}
              onFinish={handleIndustryIntelligence}
            >
              <Row gutter={16}>
                <Col xs={12} md={4}>
                  <Form.Item name="top_n" label="行业数">
                    <InputNumber min={1} max={30} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="network_top_n" label="网络节点">
                    <InputNumber min={4} max={50} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="lookback_days" label="回看天数">
                    <InputNumber min={1} max={30} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={12} md={4}>
                  <Form.Item name="min_similarity" label="网络相似度">
                    <InputNumber min={0} max={1} step={0.01} precision={2} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={industryIntelLoading}>刷新行业智能</Button>
            </Form>
          </Card>
          {industryIntelLoading ? <Spin size="large" /> : null}
          {!industryIntelLoading && industryIntelRows.length ? (
            <Card title="生命周期、ETF 映射与事件日历">
              <Table
                size="small"
                pagination={{ pageSize: 8 }}
                dataSource={industryIntelRows}
                columns={[
                  { title: '行业', dataIndex: 'industry_name' },
                  { title: '阶段', render: (_, record) => <Tag color={record.lifecycle?.stage === '成长期' ? 'green' : record.lifecycle?.stage === '衰退期' ? 'red' : 'blue'}>{record.lifecycle?.stage || '--'}</Tag> },
                  { title: '置信度', render: (_, record) => formatPct(record.lifecycle?.confidence || 0) },
                  { title: 'ETF', render: (_, record) => (record.etf_mapping || []).slice(0, 3).map((item) => <Tag key={`${record.industry_name}-${item.symbol}`}>{item.symbol}</Tag>) },
                  { title: '下一事件', render: (_, record) => {
                    const event = (record.event_calendar || [])[0];
                    return event ? `${event.date} · ${event.title}` : '--';
                  } },
                ]}
              />
            </Card>
          ) : null}
          {!industryIntelLoading && industryNetworkResult ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} md={8}><Card><Statistic title="网络节点" value={(industryNetworkResult.nodes || []).length} /></Card></Col>
              <Col xs={24} md={8}><Card><Statistic title="联动边" value={(industryNetworkResult.edges || []).length} /></Card></Col>
              <Col xs={24} md={8}><Card><Statistic title="相似度阈值" value={Number(industryNetworkResult.metadata?.min_similarity || 0).toFixed(2)} /></Card></Col>
            </Row>
          ) : null}
          {!industryIntelLoading && industryNetworkEdges.length ? (
            <Card title="行业联动网络边">
              <Table
                size="small"
                pagination={{ pageSize: 10 }}
                dataSource={industryNetworkEdges}
                columns={[
                  { title: 'Source', dataIndex: 'source' },
                  { title: 'Target', dataIndex: 'target' },
                  { title: '关系', dataIndex: 'relationship' },
                  { title: '权重', dataIndex: 'weight', render: (value) => Number(value || 0).toFixed(4) },
                ]}
              />
            </Card>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'signal-validation',
      label: <span><LineChartOutlined />信号验证与行情深度</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="宏观因子与另类数据验证">
                <Form
                  form={signalValidationForm}
                  layout="vertical"
                  initialValues={{
                    benchmark: 'SPY',
                    period: '2y',
                    horizons: '5,20,60',
                    macro_limit: 250,
                    timeframe: '90d',
                    alt_limit: 300,
                    half_life_days: 14,
                  }}
                  onFinish={handleSignalValidation}
                >
                  <Row gutter={12}>
                    <Col xs={24} md={8}>
                      <Form.Item name="benchmark" label="验证基准">
                        <Input placeholder="SPY" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item name="period" label="价格区间">
                        <Select options={PERIOD_OPTIONS} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item name="horizons" label="Forward 天数">
                        <Input placeholder="5,20,60" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={12}>
                    <Col xs={12} md={6}>
                      <Form.Item name="macro_limit" label="宏观快照">
                        <InputNumber min={2} max={1000} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="timeframe" label="另类周期">
                        <Select options={[{ value: '30d', label: '30天' }, { value: '90d', label: '90天' }, { value: '180d', label: '180天' }]} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="alt_limit" label="另类记录">
                        <InputNumber min={1} max={1000} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="half_life_days" label="半衰期">
                        <InputNumber min={1} max={365} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item name="category" label="另类数据类别">
                    <Select
                      allowClear
                      placeholder="全部类别"
                      options={[
                        { value: 'policy', label: '政策' },
                        { value: 'hiring', label: '招聘' },
                        { value: 'bidding', label: '招投标' },
                        { value: 'env_assessment', label: '环评' },
                        { value: 'commodity_inventory', label: '商品库存' },
                      ]}
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={signalValidationLoading}>运行信号验证</Button>
                </Form>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="实时回放与订单簿探测">
                <Form
                  form={marketProbeForm}
                  layout="vertical"
                  initialValues={{
                    symbol: 'AAPL',
                    replay_period: '5d',
                    replay_interval: '1d',
                    replay_limit: 60,
                    levels: 10,
                    z_window: 20,
                    return_z_threshold: 2,
                    volume_z_threshold: 2,
                    cusum_threshold_sigma: 2.5,
                    pattern_lookback: 5,
                    pattern_matches: 5,
                    compare_symbols: 'AAPL, MSFT, NVDA',
                  }}
                  onFinish={handleMarketProbe}
                >
                  <Row gutter={12}>
                    <Col xs={24} md={8}>
                      <Form.Item name="symbol" label="标的" rules={[{ required: true, message: '请输入标的' }]}>
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item name="replay_period" label="回放区间">
                        <Select options={[{ value: '1d', label: '1天' }, { value: '5d', label: '5天' }, { value: '1mo', label: '1个月' }, { value: '3mo', label: '3个月' }]} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item name="replay_interval" label="频率">
                        <Select options={[{ value: '1m', label: '1m' }, { value: '5m', label: '5m' }, { value: '1h', label: '1h' }, { value: '1d', label: '1d' }]} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item name="compare_symbols" label="联动对比标的">
                    <Input placeholder="最多 4 个，如 AAPL, MSFT, NVDA" />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col xs={12} md={8}>
                      <Form.Item name="replay_limit" label="回放点数">
                        <InputNumber min={5} max={500} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={8}>
                      <Form.Item name="levels" label="盘口层数">
                        <InputNumber min={1} max={50} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={8}>
                      <Form.Item name="z_window" label="Z-Score 窗口">
                        <InputNumber min={10} max={120} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={12}>
                    <Col xs={12} md={6}>
                      <Form.Item name="return_z_threshold" label="收益阈值">
                        <InputNumber min={1} max={6} step={0.1} precision={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="volume_z_threshold" label="量能阈值">
                        <InputNumber min={1} max={6} step={0.1} precision={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="cusum_threshold_sigma" label="CUSUM σ">
                        <InputNumber min={1} max={6} step={0.1} precision={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={12} md={6}>
                      <Form.Item name="pattern_lookback" label="相似窗口">
                        <InputNumber min={3} max={15} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Button type="primary" htmlType="submit" loading={marketProbeLoading}>探测行情深度</Button>
                </Form>
              </Card>
            </Col>
          </Row>

          {(signalValidationLoading || marketProbeLoading) ? <Spin size="large" /> : null}
          {!signalValidationLoading && macroValidationResult ? (
            <>
              <Alert
                type={macroValidationResult.status === 'ok' ? 'success' : 'warning'}
                showIcon
                message={`宏观因子验证状态: ${macroValidationResult.status}`}
                description={macroValidationResult.diagnostics?.note || macroValidationResult.message || '已完成历史快照与 forward return 对齐。'}
              />
              <Card title="宏观信号 Forward Return 验证">
                <Table
                  size="small"
                  pagination={false}
                  dataSource={macroHorizonRows}
                  columns={[
                    { title: 'Horizon', dataIndex: 'horizon_days', render: (value) => `${value}D` },
                    { title: '样本数', dataIndex: 'samples' },
                    { title: '命中率', dataIndex: 'hit_rate', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                    { title: '平均收益', dataIndex: 'avg_forward_return', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                    { title: '方向收益', dataIndex: 'avg_signed_return', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                  ]}
                />
              </Card>
              {macroFactorRows.length ? (
                <Card title="宏观因子拆分命中率">
                  <Table
                    size="small"
                    pagination={{ pageSize: 8 }}
                    dataSource={macroFactorRows}
                    columns={[
                      { title: '因子', dataIndex: 'factor' },
                      { title: 'Horizon', dataIndex: 'horizon_days', render: (value) => `${value}D` },
                      { title: '样本数', dataIndex: 'samples' },
                      { title: '命中率', dataIndex: 'hit_rate', render: (value) => formatPct(value || 0) },
                      { title: '方向收益', dataIndex: 'avg_signed_return', render: (value) => formatPct(value || 0) },
                    ]}
                  />
                </Card>
              ) : null}
            </>
          ) : null}
          {!signalValidationLoading && altSignalDiagnostics ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} md={6}><Card><Statistic title="另类记录数" value={altSignalDiagnostics.record_count || 0} /></Card></Col>
              <Col xs={24} md={6}><Card><Statistic title="真实 Outcome" value={altSignalDiagnostics.realized_outcome_count || 0} /></Card></Col>
              <Col xs={24} md={6}><Card><Statistic title="整体命中率" value={altSignalDiagnostics.overall?.hit_rate === null || altSignalDiagnostics.overall?.hit_rate === undefined ? '--' : formatPct(altSignalDiagnostics.overall.hit_rate)} /></Card></Col>
              <Col xs={24} md={6}><Card><Statistic title="命中率类型" value={altSignalDiagnostics.overall?.hit_rate_type || '--'} /></Card></Col>
              <Col xs={24} xl={12}>
                <Card title="Provider 信号诊断">
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={altProviderRows}
                    columns={[
                      { title: 'Provider', dataIndex: 'provider' },
                      { title: '记录', dataIndex: 'count' },
                      { title: '平均强度', dataIndex: 'avg_abs_strength', render: (value) => Number(value || 0).toFixed(3) },
                      { title: '置信度', dataIndex: 'avg_confidence', render: (value) => formatPct(value || 0) },
                      { title: '命中率', dataIndex: 'hit_rate', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                    ]}
                  />
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card title="信号衰减曲线">
                  <Table
                    size="small"
                    pagination={{ pageSize: 6 }}
                    dataSource={altDecayRows}
                    columns={[
                      { title: 'Age', dataIndex: 'age_days', render: (value) => `${value}D` },
                      { title: '衰减权重', dataIndex: 'decay_weight', render: (value) => Number(value || 0).toFixed(4) },
                      { title: '平均衰减信号', dataIndex: 'avg_decayed_signal', render: (value) => Number(value || 0).toFixed(6) },
                    ]}
                  />
                </Card>
              </Col>
            </Row>
          ) : null}
          {!marketProbeLoading && (replayResult || orderbookResult || anomalyDiagnostics) ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <Card title="个股行情回放样本">
                  <Table
                    size="small"
                    pagination={{ pageSize: 8 }}
                    dataSource={replayRows}
                    columns={[
                      { title: '时间', dataIndex: 'timestamp', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                      { title: 'Open', dataIndex: 'open', render: (value) => Number(value || 0).toFixed(2) },
                      { title: 'Close', dataIndex: 'close', render: (value) => Number(value || 0).toFixed(2) },
                      { title: 'Volume', dataIndex: 'volume', render: (value) => Number(value || 0).toLocaleString() },
                    ]}
                  />
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card
                  title="订单簿深度"
                  extra={
                    orderbookResult?.mode === 'provider_level2'
                      ? <Tag color="green">Provider L2</Tag>
                      : orderbookResult?.mode === 'provider_quote_proxy'
                        ? <Tag color="gold">Quote Proxy</Tag>
                        : <Tag color="orange">Synthetic</Tag>
                  }
                >
                  <Alert
                    type={orderbookResult?.mode === 'provider_level2' ? 'success' : 'info'}
                    showIcon
                    style={{ marginBottom: 12 }}
                    message={orderbookResult?.diagnostics?.message || '暂无盘口诊断'}
                    description={(
                      <Space wrap size={[8, 4]}>
                        <Text type="secondary">来源: {orderbookResult?.source || '--'}</Text>
                        <Text type="secondary">模式: {orderbookResult?.mode || '--'}</Text>
                        <Text type="secondary">候选 Provider: {orderbookResult?.diagnostics?.provider_count ?? 0}</Text>
                      </Space>
                    )}
                  />
                  <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
                    <Col xs={12} md={6}><Statistic title="Best Bid" value={orderbookResult?.metrics?.best_bid ?? 0} precision={4} /></Col>
                    <Col xs={12} md={6}><Statistic title="Best Ask" value={orderbookResult?.metrics?.best_ask ?? 0} precision={4} /></Col>
                    <Col xs={12} md={6}><Statistic title="Spread (bps)" value={orderbookResult?.metrics?.spread_bps ?? 0} precision={2} /></Col>
                    <Col xs={12} md={6}><Statistic title="Depth Imbalance" value={orderbookResult?.metrics?.depth_imbalance ?? 0} precision={4} /></Col>
                  </Row>
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={orderbookRows}
                    columns={[
                      { title: 'Side', dataIndex: 'side', render: (value) => <Tag color={value === 'Bid' ? 'green' : 'red'}>{value}</Tag> },
                      { title: 'Price', dataIndex: 'price', render: (value) => Number(value || 0).toFixed(4) },
                      { title: 'Size', render: (_, record) => Number(record.size ?? record.quantity ?? record.volume ?? 0).toLocaleString() },
                      { title: 'Notional', dataIndex: 'notional', render: (value) => value === null || value === undefined ? '--' : formatMoney(value) },
                    ]}
                  />
                  <Table
                    size="small"
                    style={{ marginTop: 12 }}
                    pagination={false}
                    dataSource={orderbookProviderRows}
                    locale={{ emptyText: '暂无 provider 诊断' }}
                    columns={[
                      { title: 'Provider', dataIndex: 'provider' },
                      { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value || 'unknown'}</Tag> },
                      { title: '模式', dataIndex: 'mode', render: (value) => value || '--' },
                      { title: 'Native L2', dataIndex: 'supports_level2', render: (value) => value ? 'Yes' : 'No' },
                      { title: 'Quote Proxy', dataIndex: 'supports_quote_proxy', render: (value) => value ? 'Yes' : 'No' },
                      { title: '延迟(ms)', dataIndex: 'latency_ms', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(2) },
                    ]}
                    expandable={{
                      expandedRowRender: (record) => <Text type="secondary">{record.detail || '无额外说明'}</Text>,
                      rowExpandable: (record) => Boolean(record.detail),
                    }}
                  />
                </Card>
              </Col>
              {anomalyDiagnostics ? (
                <Col xs={24}>
                  <Card
                    title="统计异常波动诊断"
                    extra={anomalyDiagnostics.latest_signal?.is_anomaly ? <Tag color="red">当前存在异常</Tag> : <Tag color="green">当前平稳</Tag>}
                  >
                    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                      <Col xs={24} md={6}><Statistic title="异常点数" value={anomalyDiagnostics.summary?.anomaly_count || 0} /></Col>
                      <Col xs={24} md={6}><Statistic title="近期异常率" value={formatPct(anomalyDiagnostics.summary?.recent_anomaly_rate || 0)} /></Col>
                      <Col xs={24} md={6}><Statistic title="当前收益 Z" value={Number(anomalyDiagnostics.latest_signal?.return_zscore || 0).toFixed(2)} /></Col>
                      <Col xs={24} md={6}><Statistic title="当前量能 Z" value={Number(anomalyDiagnostics.latest_signal?.volume_zscore || 0).toFixed(2)} /></Col>
                    </Row>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={14}>
                        <Table
                          size="small"
                          pagination={{ pageSize: 6 }}
                          dataSource={anomalyRows}
                          columns={[
                            { title: '时间', dataIndex: 'timestamp', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                            { title: '类型', dataIndex: 'anomaly_type' },
                            { title: '收益', dataIndex: 'return', render: (value) => formatPct(value || 0) },
                            { title: '收益 Z', dataIndex: 'return_zscore', render: (value) => Number(value || 0).toFixed(2) },
                            { title: '量能 Z', dataIndex: 'volume_zscore', render: (value) => Number(value || 0).toFixed(2) },
                            { title: '严重度', dataIndex: 'severity', render: (value) => Number(value || 0).toFixed(2) },
                          ]}
                        />
                      </Col>
                      <Col xs={24} xl={10}>
                        <Table
                          size="small"
                          pagination={false}
                          dataSource={anomalyPatternRows}
                          columns={[
                            { title: '历史相似时间', dataIndex: 'timestamp', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                            { title: '相似度', dataIndex: 'similarity_score', render: (value) => Number(value || 0).toFixed(3) },
                            { title: '后 1 bar', dataIndex: 'next_1_bar_return', render: (value) => formatPct(value || 0) },
                            { title: '后 5 bar', dataIndex: 'next_5_bar_return', render: (value) => formatPct(value || 0) },
                          ]}
                        />
                      </Col>
                    </Row>
                  </Card>
                </Col>
              ) : null}
            </Row>
          ) : null}
          {!marketProbeLoading && linkedReplayRows.length ? (
            <Card title="多标的联动看板">
              <Table
                size="small"
                pagination={{ pageSize: 10 }}
                dataSource={linkedReplayRows}
                columns={[
                  { title: '时间', dataIndex: 'timestamp', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                  ...((linkedReplayResult?.symbols || []).map((symbol) => ({
                    title: symbol,
                    dataIndex: symbol,
                    render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(2),
                  }))),
                ]}
              />
            </Card>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'factor',
      label: <span><CodeOutlined />自定义因子语言</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Form
              form={factorForm}
              layout="vertical"
              initialValues={{
                symbol: 'AAPL',
                period: '1y',
                expression: 'rank(close / sma(close, 20)) + rank(volume / sma(volume, 20))',
                preview_rows: 30,
              }}
              onFinish={handleFactorExpression}
            >
              <Row gutter={16}>
                <Col xs={24} md={5}>
                  <Form.Item name="symbol" label="标的代码" rules={[{ required: true, message: '请输入标的代码' }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col xs={24} md={5}>
                  <Form.Item name="period" label="历史区间">
                    <Select options={PERIOD_OPTIONS} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={4}>
                  <Form.Item name="preview_rows" label="预览行数">
                    <InputNumber min={5} max={120} precision={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={10}>
                  <Form.Item name="expression" label="因子表达式" rules={[{ required: true, message: '请输入因子表达式' }]}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={factorLoading}>计算因子</Button>
                <Button onClick={handleQueueFactorExpression} loading={Boolean(queuedTaskLoading.factor)}>异步排队</Button>
              </Space>
            </Form>
          </Card>
          <Alert
            type="info"
            showIcon
            message="表达式使用安全白名单解析"
            description="支持 close/open/high/low/volume 字段，以及 rank、zscore、sma、ema、rolling_std、pct_change、delay、clip 等函数。表达式只解析数学和白名单函数，不执行任意代码。"
          />
          {factorLoading ? <Spin size="large" /> : null}
          {!factorLoading && factorResult ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={8}><Card><Statistic title="最新因子值" value={factorResult.latest_value === null || factorResult.latest_value === undefined ? '--' : Number(factorResult.latest_value).toFixed(4)} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="有效点数" value={factorResult.diagnostics?.non_null_factor_points || 0} /></Card></Col>
                <Col xs={24} md={8}><Card><Statistic title="样本行数" value={factorResult.diagnostics?.rows || 0} /></Card></Col>
              </Row>
              <Card title="因子预览">
                <Table
                  size="small"
                  pagination={{ pageSize: 10 }}
                  dataSource={factorPreviewRows}
                  columns={[
                    { title: '日期', dataIndex: 'date' },
                    { title: '因子值', dataIndex: 'factor', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(6) },
                  ]}
                />
              </Card>
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'infrastructure',
      label: <span><DatabaseOutlined />基础设施</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadInfrastructure} loading={infraLoading}>刷新基础设施</Button>
          </Space>
          {infraLoading ? <Spin size="large" /> : null}
          {!infraLoading && infrastructureStatus ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Card><Statistic title="持久化模式" value={infrastructureStatus.persistence?.mode || '--'} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="任务队列" value={infrastructureStatus.task_queue?.mode || '--'} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="运行中任务" value={infrastructureStatus.task_queue?.queued_or_running || 0} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="通知通道" value={(infrastructureStatus.notifications?.channels || []).length} /></Card></Col>
              </Row>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Card><Statistic title="已完成任务" value={infrastructureStatus.task_queue?.completed || 0} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="失败任务" value={infrastructureStatus.task_queue?.failed || 0} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="已取消任务" value={infrastructureStatus.task_queue?.cancelled || 0} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="平均时长(s)" value={infrastructureStatus.task_queue?.average_duration_seconds ?? '--'} /></Card></Col>
              </Row>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={6}><Card><Statistic title="持久化任务" value={infrastructureStatus.task_queue?.persisted_tasks || 0} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="Redis" value={infrastructureStatus.task_queue?.redis_configured ? '已配置' : '未配置'} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="Celery" value={infrastructureStatus.task_queue?.celery_importable ? '可用' : '未启用'} /></Card></Col>
                <Col xs={24} md={6}><Card><Statistic title="后端路由" value={(infrastructureStatus.task_queue?.execution_backends || []).join(', ') || '--'} /></Card></Col>
              </Row>
              <Card size="small" title="Broker 状态观测">
                <Space wrap>
                  {Array.isArray(infrastructureStatus.task_queue?.broker_states) && infrastructureStatus.task_queue.broker_states.length ? (
                    infrastructureStatus.task_queue.broker_states.map((item) => (
                      <Tag key={item} color={item === 'SUCCESS' ? 'green' : item === 'FAILURE' ? 'red' : item === 'REVOKED' ? 'default' : 'blue'}>
                        {item}
                      </Tag>
                    ))
                  ) : (
                    <Text type="secondary">当前没有 broker 状态样本</Text>
                  )}
                </Space>
              </Card>
              <Card size="small" title="Worker 运行时">
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color={infrastructureStatus.task_queue?.worker_running ? 'green' : 'default'}>
                      {infrastructureStatus.task_queue?.worker_running ? 'running' : 'stopped'}
                    </Tag>
                    <Tag color={infrastructureStatus.task_queue?.celery_importable ? 'blue' : 'orange'}>
                      {infrastructureStatus.task_queue?.celery_importable ? 'celery import ready' : 'celery missing'}
                    </Tag>
                    {infrastructureStatus.task_queue?.worker_pid ? (
                      <Tag>{`PID ${infrastructureStatus.task_queue.worker_pid}`}</Tag>
                    ) : null}
                  </Space>
                  <Text type="secondary">启动命令: {infrastructureStatus.task_queue?.worker_command || './scripts/start_celery_worker.sh'}</Text>
                  <Text type="secondary">PID File: {infrastructureStatus.task_queue?.worker_pid_file || '--'}</Text>
                  <Text type="secondary">Log File: {infrastructureStatus.task_queue?.worker_log_file || '--'}</Text>
                </Space>
              </Card>
              <Alert
                type={infrastructureStatus.persistence?.timescale_ready ? 'success' : 'warning'}
                showIcon
                message={infrastructureStatus.persistence?.timescale_ready ? 'PostgreSQL / TimescaleDB 已就绪' : '当前使用本地 SQLite 降级持久化'}
                description={infrastructureStatus.persistence?.note}
              />
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={8}>
                  <Card title="提交异步任务">
                    <Form form={taskForm} layout="vertical" onFinish={handleCreateTask} initialValues={{ name: 'research_batch', execution_backend: 'auto', payload: '{"sleep_seconds": 1.2, "steps": 4}' }}>
                      <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
                        <Input />
                      </Form.Item>
                      <Form.Item name="execution_backend" label="执行后端">
                        <Select
                          options={[
                            { value: 'auto', label: 'Auto · 优先 Celery，失败回退本地' },
                            { value: 'local', label: 'Local Executor' },
                            { value: 'celery', label: 'Celery Worker' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="payload" label="任务参数 JSON">
                        <Input.TextArea rows={4} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">提交任务</Button>
                      <Alert
                        style={{ marginTop: 12 }}
                        showIcon
                        type={infrastructureStatus.task_queue?.worker_running ? 'success' : infrastructureStatus.task_queue?.celery_importable ? 'warning' : 'info'}
                        message={infrastructureStatus.task_queue?.worker_running ? 'Celery worker 正在运行' : infrastructureStatus.task_queue?.celery_importable ? 'Celery 已可用，但 worker 未启动' : '当前仅本地执行器可用'}
                        description={infrastructureStatus.task_queue?.worker_running ? infrastructureStatus.task_queue?.worker_log_file : (infrastructureStatus.task_queue?.worker_command || infrastructureStatus.task_queue?.note)}
                      />
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} xl={8}>
                  <Card title="签发研究令牌">
                    <Form form={tokenForm} layout="vertical" onFinish={handleCreateToken} initialValues={{ subject: 'researcher', role: 'researcher', expires_in_seconds: 86400 }}>
                      <Form.Item name="subject" label="Subject">
                        <Input />
                      </Form.Item>
                      <Form.Item name="role" label="Role">
                        <Input />
                      </Form.Item>
                      <Form.Item name="expires_in_seconds" label="有效秒数">
                        <InputNumber min={60} max={2592000} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">生成令牌</Button>
                    </Form>
                    {authToken ? (
                      <Input.TextArea style={{ marginTop: 12 }} rows={4} value={authToken} readOnly />
                    ) : null}
                    <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                      手工签发仍是 access token 模式；OAuth2 登录会额外返回 refresh token。
                    </Text>
                  </Card>
                </Col>
                <Col xs={24} xl={8}>
                  <Card title="通知通道测试">
                    <Form form={notificationForm} layout="vertical" onFinish={handleTestNotification} initialValues={{ channel: 'dry_run', severity: 'info', title: 'Quant Lab 通知测试', message: '基础设施通知通道已打通' }}>
                      <Form.Item name="channel" label="通道">
                        <Select options={(infrastructureStatus.notifications?.channels || []).map((channel) => ({ value: channel.id, label: `${channel.label || channel.id} · ${channel.type}` }))} />
                      </Form.Item>
                      <Form.Item name="severity" label="级别">
                        <Select options={[{ value: 'info', label: 'Info' }, { value: 'warning', label: 'Warning' }, { value: 'critical', label: 'Critical' }]} />
                      </Form.Item>
                      <Form.Item name="title" label="标题">
                        <Input />
                      </Form.Item>
                      <Form.Item name="message" label="内容">
                        <Input.TextArea rows={3} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">发送测试</Button>
                    </Form>
                    <Card size="small" title="登记通知渠道" style={{ marginTop: 16 }}>
                      <Form
                        form={notificationChannelForm}
                        layout="vertical"
                        onFinish={handleSaveNotificationChannel}
                        initialValues={{
                          id: 'research_webhook',
                          type: 'webhook',
                          label: 'Research Webhook',
                          enabled: true,
                          settings: '{"url": "https://example.com/webhook"}',
                        }}
                      >
                        <Row gutter={12}>
                          <Col xs={24} md={12}>
                            <Form.Item name="id" label="渠道 ID" rules={[{ required: true, message: '请输入渠道 ID' }]}>
                              <Input />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item name="type" label="类型">
                              <Select options={[{ value: 'webhook', label: 'Webhook' }, { value: 'wecom', label: '企业微信' }, { value: 'email', label: 'Email' }, { value: 'dry_run', label: 'Dry Run' }]} />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item name="label" label="显示名称">
                          <Input />
                        </Form.Item>
                        <Form.Item name="settings" label="渠道设置 JSON">
                          <Input.TextArea rows={3} placeholder='Webhook: {"url":"..."}；Email: {"host":"smtp.example.com","from":"...","to":"..."}' />
                        </Form.Item>
                        <Button htmlType="submit">保存渠道</Button>
                      </Form>
                    </Card>
                    <Table
                      style={{ marginTop: 16 }}
                      size="small"
                      pagination={false}
                      rowKey="id"
                      dataSource={infrastructureStatus.notifications?.channels || []}
                      columns={[
                        { title: 'ID', dataIndex: 'id' },
                        { title: '类型', dataIndex: 'type' },
                        { title: '来源', dataIndex: 'source' },
                        { title: '启用', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '是' : '否'}</Tag> },
                        {
                          title: '操作',
                          render: (_, record) => record.source === 'stored' ? (
                            <Button size="small" danger onClick={() => handleDeleteNotificationChannel(record.id)}>删除</Button>
                          ) : '--',
                        },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
              <Card title="本地用户认证中心">
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={6}><Statistic title="本地用户数" value={infrastructureStatus.auth?.local_user_count || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="已启用用户" value={infrastructureStatus.auth?.enabled_users || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="OAuth Provider" value={infrastructureStatus.auth?.oauth_enabled_providers || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="认证模式" value={infrastructureStatus.auth?.required ? 'Required' : 'Optional'} /></Col>
                  </Row>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={12}>
                      <Card size="small">
                        <Text strong>Bootstrap</Text>
                        <div style={{ marginTop: 8 }}>
                          <Tag color={infrastructureStatus.auth?.bootstrap_required ? 'orange' : 'green'}>
                            {infrastructureStatus.auth?.bootstrap_required ? '需要首个管理员' : '已完成初始化'}
                          </Tag>
                        </div>
                      </Card>
                    </Col>
                    <Col xs={24} md={12}>
                      <Card size="small">
                        <Text strong>OAuth Env</Text>
                        <div style={{ marginTop: 8 }}>
                          <Tag color={(infrastructureStatus.auth?.oauth_env_candidates || 0) > 0 ? 'green' : 'default'}>
                            {`候选 ${infrastructureStatus.auth?.oauth_env_candidates || 0}`}
                          </Tag>
                          <Tag color="blue">{`活跃 Session ${infrastructureStatus.auth?.active_refresh_sessions || 0}`}</Tag>
                        </div>
                      </Card>
                    </Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="创建 / 更新本地用户">
                        <Form
                          form={authUserForm}
                          layout="vertical"
                          onFinish={handleSaveAuthUser}
                          initialValues={{
                            subject: 'admin',
                            display_name: 'Quant Admin',
                            role: 'admin',
                            enabled: true,
                            scopes: 'quant:read quant:write infra:admin',
                            metadata: '{"desk": "research"}',
                          }}
                        >
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="subject" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                                <Input />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="display_name" label="显示名称">
                                <Input />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="role" label="角色">
                                <Select options={[{ value: 'admin', label: 'Admin' }, { value: 'researcher', label: 'Researcher' }, { value: 'viewer', label: 'Viewer' }, { value: 'service', label: 'Service' }]} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="enabled" label="状态">
                                <Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="password" label="密码">
                            <Input.Password placeholder="新建用户必填；留空表示保留旧密码" />
                          </Form.Item>
                          <Form.Item name="scopes" label="Scopes">
                            <Input placeholder="空格或逗号分隔" />
                          </Form.Item>
                          <Form.Item name="metadata" label="元数据 JSON">
                            <Input.TextArea rows={3} />
                          </Form.Item>
                          <Button type="primary" htmlType="submit">保存用户</Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="用户登录">
                        <Form
                          form={authLoginForm}
                          layout="vertical"
                          onFinish={handleLoginInfrastructureUser}
                          initialValues={{ subject: 'admin', expires_in_seconds: 86400, refresh_expires_in_seconds: 2592000 }}
                        >
                          <Form.Item name="subject" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                            <Input />
                          </Form.Item>
                          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                            <Input.Password />
                          </Form.Item>
                          <Form.Item name="expires_in_seconds" label="登录后令牌有效秒数">
                            <InputNumber min={60} max={2592000} precision={0} style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item name="refresh_expires_in_seconds" label="Refresh Token 有效秒数">
                            <InputNumber min={3600} max={15552000} precision={0} style={{ width: '100%' }} />
                          </Form.Item>
                          <Button type="primary" htmlType="submit">登录并签发令牌</Button>
                        </Form>
                        {authSession?.user ? (
                          <Card size="small" style={{ marginTop: 16 }}>
                            <Space direction="vertical" size={4}>
                              <Text strong>{authSession.user.display_name || authSession.user.subject}</Text>
                              <Text type="secondary">角色: {authSession.user.role}</Text>
                              <Text type="secondary">登录方式: {authSession.oauth_provider ? `oauth:${authSession.oauth_provider}` : 'local'}</Text>
                              <Text type="secondary">Scopes: {(authSession.user.scopes || []).join(', ') || '--'}</Text>
                              <Text type="secondary">累计登录: {authSession.user.login_count || 0}</Text>
                              <Text type="secondary">Access TTL: {authSession.expires_in_seconds || '--'}s</Text>
                              <Text type="secondary">Refresh TTL: {authSession.refresh_expires_in_seconds || '--'}s</Text>
                            </Space>
                          </Card>
                        ) : null}
                        {refreshToken ? (
                          <Input.TextArea style={{ marginTop: 12 }} rows={3} value={refreshToken} readOnly />
                        ) : null}
                      </Card>
                    </Col>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="认证策略">
                        <Form form={authPolicyForm} layout="vertical" onFinish={handleUpdateAuthPolicy}>
                          <Form.Item name="required" label="访问策略">
                            <Select options={[{ value: false, label: 'Optional · 允许匿名研究访问' }, { value: true, label: 'Required · 强制登录' }]} />
                          </Form.Item>
                          <Button type="primary" htmlType="submit">更新策略</Button>
                        </Form>
                        <Alert
                          style={{ marginTop: 16 }}
                          showIcon
                          type={infrastructureStatus.auth?.required ? 'warning' : 'info'}
                          message={infrastructureStatus.auth?.policy?.note || '认证策略说明'}
                          description={`支持方式: ${(infrastructureStatus.auth?.supported || []).join(' / ')}`}
                        />
                      </Card>
                    </Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={12}>
                      <Card size="small" title="OAuth Provider 配置">
                        <Space style={{ marginBottom: 12 }}>
                          <Button onClick={handleSyncOAuthProvidersFromEnv}>从环境同步 GitHub / Google</Button>
                        </Space>
                        <Form
                          form={oauthProviderForm}
                          layout="vertical"
                          onFinish={handleSaveOAuthProvider}
                          initialValues={{
                            provider_id: 'github',
                            label: 'GitHub',
                            provider_type: 'github',
                            enabled: true,
                            client_id: '',
                            scopes: 'read:user user:email',
                            auto_create_user: true,
                            default_role: 'researcher',
                            default_scopes: 'quant:read quant:write',
                            frontend_origin: typeof window !== 'undefined' ? window.location.origin : '',
                            extra_params: '{"allow_signup":"true"}',
                            metadata: '{"team":"research"}',
                          }}
                        >
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="provider_id" label="Provider ID" rules={[{ required: true, message: '请输入 Provider ID' }]}>
                                <Input />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="provider_type" label="Provider 类型">
                                <Select options={[{ value: 'github', label: 'GitHub' }, { value: 'google', label: 'Google' }, { value: 'generic', label: 'Generic OAuth2' }]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="label" label="显示名称">
                                <Input />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="enabled" label="状态">
                                <Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="client_id" label="Client ID" rules={[{ required: true, message: '请输入 Client ID' }]}>
                            <Input />
                          </Form.Item>
                          <Form.Item name="client_secret" label="Client Secret">
                            <Input.Password placeholder="留空表示保留已有 secret" />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={8}>
                              <Form.Item name="default_role" label="默认角色">
                                <Select options={[{ value: 'admin', label: 'Admin' }, { value: 'researcher', label: 'Researcher' }, { value: 'viewer', label: 'Viewer' }]} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item name="auto_create_user" label="自动建用户">
                                <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item name="frontend_origin" label="前端 Origin">
                                <Input />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="scopes" label="OAuth Scopes">
                            <Input placeholder="空格或逗号分隔" />
                          </Form.Item>
                          <Form.Item name="default_scopes" label="本地默认 Scopes">
                            <Input placeholder="空格或逗号分隔" />
                          </Form.Item>
                          <Form.Item name="redirect_uri" label="固定 Redirect URI">
                            <Input placeholder="留空则自动生成 backend callback URL" />
                          </Form.Item>
                          <Form.Item name="auth_url" label="Auth URL">
                            <Input placeholder="Generic Provider 必填；GitHub/Google 可留空走预置" />
                          </Form.Item>
                          <Form.Item name="token_url" label="Token URL">
                            <Input placeholder="Generic Provider 必填；GitHub/Google 可留空走预置" />
                          </Form.Item>
                          <Form.Item name="userinfo_url" label="UserInfo URL">
                            <Input placeholder="Generic Provider 必填；GitHub/Google 可留空走预置" />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={8}>
                              <Form.Item name="subject_field" label="Subject Field">
                                <Input placeholder="如 sub / login" />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item name="display_name_field" label="Display Field">
                                <Input placeholder="如 name" />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item name="email_field" label="Email Field">
                                <Input placeholder="如 email" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="extra_params" label="额外授权参数 JSON">
                            <Input.TextArea rows={3} />
                          </Form.Item>
                          <Form.Item name="metadata" label="元数据 JSON">
                            <Input.TextArea rows={3} />
                          </Form.Item>
                          <Button type="primary" htmlType="submit">保存 Provider</Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={12}>
                      <Card size="small" title="OAuth 登录与回调">
                        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                          <div>
                            <Text strong>快捷发起</Text>
                            <div style={{ marginTop: 8 }}>
                              <Space wrap>
                                {(authProviders || []).filter((item) => item.enabled).map((provider) => (
                                  <Button key={provider.provider_id} onClick={() => handleStartOAuthLogin(provider.provider_id)}>
                                    {`登录 ${provider.label || provider.provider_id}`}
                                  </Button>
                                ))}
                              </Space>
                            </div>
                          </div>
                          {oauthLaunchContext ? (
                            <Alert
                              showIcon
                              type="info"
                              message={`已生成 ${oauthLaunchContext.provider?.label || oauthLaunchContext.provider?.provider_id} 授权请求`}
                              description={(
                                <Space direction="vertical" size={4}>
                                  <Text type="secondary">State: <Text code>{oauthLaunchContext.state}</Text></Text>
                                  <Text type="secondary">Redirect: {oauthLaunchContext.redirect_uri}</Text>
                                  <Text type="secondary">若弹窗被拦截，可手动打开下面的授权链接。</Text>
                                  <Input.TextArea rows={3} value={oauthLaunchContext.authorization_url} readOnly />
                                </Space>
                              )}
                            />
                          ) : null}
                          <Form
                            form={oauthExchangeForm}
                            layout="vertical"
                            onFinish={handleExchangeOAuthCode}
                            initialValues={{
                              provider_id: 'github',
                              expires_in_seconds: 86400,
                              refresh_expires_in_seconds: 2592000,
                            }}
                          >
                            <Row gutter={12}>
                              <Col span={12}>
                                <Form.Item name="provider_id" label="Provider" rules={[{ required: true, message: '请选择 Provider' }]}>
                                  <Select options={(authProviders || []).map((item) => ({ value: item.provider_id, label: item.label || item.provider_id }))} />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name="state" label="State" rules={[{ required: true, message: '请输入 state' }]}>
                                  <Input />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item name="code" label="Authorization Code" rules={[{ required: true, message: '请输入授权码' }]}>
                              <Input.TextArea rows={3} />
                            </Form.Item>
                            <Form.Item name="redirect_uri" label="Redirect URI">
                              <Input placeholder="留空则沿用自动生成的 callback" />
                            </Form.Item>
                            <Row gutter={12}>
                              <Col span={12}>
                                <Form.Item name="expires_in_seconds" label="Access TTL">
                                  <InputNumber min={60} max={2592000} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name="refresh_expires_in_seconds" label="Refresh TTL">
                                  <InputNumber min={3600} max={15552000} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Button type="primary" htmlType="submit">手动交换授权码</Button>
                          </Form>
                          {oauthDiagnostics ? (
                            <Card
                              size="small"
                              title={`Provider 诊断 · ${oauthDiagnostics.provider?.label || oauthDiagnostics.provider?.provider_id || '--'}`}
                            >
                              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                <div>
                                  <Tag color={oauthDiagnostics.ready ? 'green' : 'gold'}>
                                    {oauthDiagnostics.ready ? 'ready' : 'needs_attention'}
                                  </Tag>
                                  <Tag>{`Redirect ${oauthDiagnostics.expected_redirect_uri || '--'}`}</Tag>
                                </div>
                                <div>
                                  {(oauthDiagnostics.findings || []).length ? (
                                    <Space wrap>
                                      {(oauthDiagnostics.findings || []).map((item, index) => (
                                        <Tag key={`${item.severity}-${index}`} color={item.severity === 'high' ? 'red' : item.severity === 'medium' ? 'gold' : 'blue'}>
                                          {item.message}
                                        </Tag>
                                      ))}
                                    </Space>
                                  ) : <Text type="secondary">未发现明显配置问题</Text>}
                                </div>
                              </Space>
                            </Card>
                          ) : null}
                        </Space>
                      </Card>
                    </Col>
                  </Row>
                  <Table
                    size="small"
                    rowKey="provider_id"
                    pagination={false}
                    dataSource={authProviders}
                    columns={[
                      { title: 'Provider', dataIndex: 'provider_id' },
                      { title: '类型', dataIndex: 'provider_type', render: (value) => <Tag color="purple">{value}</Tag> },
                      { title: '显示名', dataIndex: 'label' },
                      { title: 'Client ID', dataIndex: 'client_id', render: (value) => <Text code>{String(value || '').slice(0, 18)}</Text> },
                      { title: 'Scopes', dataIndex: 'scopes', render: (value) => (value || []).length ? <Space wrap>{(value || []).map((scope) => <Tag key={scope}>{scope}</Tag>)}</Space> : '--' },
                      { title: 'Secret', dataIndex: 'client_secret_configured', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? 'configured' : 'missing'}</Tag> },
                      { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '禁用'}</Tag> },
                      {
                        title: '操作',
                        render: (_, record) => (
                          <Space wrap>
                            <Button size="small" onClick={() => handleDiagnoseOAuthProvider(record.provider_id)}>诊断</Button>
                            <Button size="small" onClick={() => handleStartOAuthLogin(record.provider_id)} disabled={!record.enabled}>登录</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                  <Table
                    size="small"
                    rowKey="subject"
                    pagination={false}
                    dataSource={authUsers}
                    columns={[
                      { title: '用户', dataIndex: 'subject' },
                      { title: '显示名', dataIndex: 'display_name' },
                      { title: '角色', dataIndex: 'role', render: (value) => <Tag color={value === 'admin' ? 'red' : value === 'service' ? 'purple' : 'blue'}>{value}</Tag> },
                      { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '禁用'}</Tag> },
                      { title: 'Scopes', dataIndex: 'scopes', render: (value) => (value || []).length ? <Space wrap>{(value || []).map((scope) => <Tag key={scope}>{scope}</Tag>)}</Space> : '--' },
                      { title: '最近登录', dataIndex: 'last_login_at', render: (value) => value ? formatDateTime(new Date(Number(value) * 1000).toISOString()) : '--' },
                      { title: '登录次数', dataIndex: 'login_count' },
                    ]}
                  />
                  <Alert
                    showIcon
                    type="info"
                    message={`当前活跃 refresh sessions: ${infrastructureStatus.auth?.active_refresh_sessions || 0}`}
                    description="前端现在会在 access token 过期后自动尝试 refresh；管理员也可以在下表撤销单个 session。"
                  />
                  <Table
                    size="small"
                    rowKey="session_id"
                    pagination={{ pageSize: 5 }}
                    dataSource={refreshSessions}
                    columns={[
                      { title: 'Session', dataIndex: 'session_id', render: (value) => <Text code>{String(value || '').slice(0, 12)}</Text> },
                      { title: '用户', dataIndex: 'subject' },
                      { title: 'Grant', dataIndex: 'grant_type', render: (value) => <Tag>{value || '--'}</Tag> },
                      { title: '签发', dataIndex: 'issued_at', render: (value) => value ? formatDateTime(new Date(Number(value) * 1000).toISOString()) : '--' },
                      { title: '过期', dataIndex: 'expires_at', render: (value) => value ? formatDateTime(new Date(Number(value) * 1000).toISOString()) : '--' },
                      { title: '状态', render: (_, record) => <Tag color={record.revoked_at ? 'default' : 'green'}>{record.revoked_at ? 'revoked' : 'active'}</Tag> },
                      {
                        title: '操作',
                        render: (_, record) => (
                          <Button
                            size="small"
                            danger
                            disabled={Boolean(record.revoked_at)}
                            onClick={() => handleRevokeRefreshSession(record.session_id)}
                          >
                            撤销
                          </Button>
                        ),
                      },
                    ]}
                  />
                </Space>
              </Card>
              <Card title="精细化限流">
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={6}><Statistic title="默认 RPM" value={infrastructureStatus.rate_limits?.default_rule?.requests_per_minute || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="默认 Burst" value={infrastructureStatus.rate_limits?.default_rule?.burst_size || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="追踪桶" value={infrastructureStatus.rate_limits?.tracked_buckets || 0} /></Col>
                    <Col xs={24} md={6}><Statistic title="最近阻断" value={(infrastructureStatus.rate_limits?.recent_blocks || []).length} /></Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={10}>
                      <Form form={rateLimitForm} layout="vertical" onFinish={handleUpdateRateLimits}>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Form.Item name="default_requests_per_minute" label="默认每分钟请求数" rules={[{ required: true, message: '请输入默认 RPM' }]}>
                              <InputNumber min={1} max={10000} precision={0} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="default_burst_size" label="默认突发容量" rules={[{ required: true, message: '请输入默认 Burst' }]}>
                              <InputNumber min={1} max={10000} precision={0} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item name="rules_json" label="端点规则 JSON">
                          <Input.TextArea rows={12} placeholder='[{"pattern":"/api/v1/backtest*","requests_per_minute":24,"burst_size":36,"enabled":true}]' />
                        </Form.Item>
                        <Button type="primary" htmlType="submit">更新限流规则</Button>
                      </Form>
                    </Col>
                    <Col xs={24} xl={14}>
                      <Space direction="vertical" size="large" style={{ width: '100%' }}>
                        <Card size="small" title="按端点统计">
                          <Table
                            size="small"
                            pagination={{ pageSize: 5 }}
                            rowKey="endpoint"
                            dataSource={infrastructureStatus.rate_limits?.top_endpoints || []}
                            columns={[
                              { title: '端点', dataIndex: 'endpoint', ellipsis: true },
                              { title: '规则', dataIndex: 'rule_pattern', ellipsis: true },
                              { title: '放行', dataIndex: 'allowed' },
                              { title: '阻断', dataIndex: 'blocked' },
                              { title: '最近访问', dataIndex: 'last_seen', render: (value) => value ? formatDateTime(value) : '--' },
                            ]}
                          />
                        </Card>
                        <Card size="small" title="最近阻断事件">
                          <Table
                            size="small"
                            pagination={{ pageSize: 4 }}
                            rowKey={(record, index) => `${record.subject}-${record.timestamp}-${index}`}
                            dataSource={infrastructureStatus.rate_limits?.recent_blocks || []}
                            columns={[
                              { title: '时间', dataIndex: 'timestamp', render: (value) => formatDateTime(value) },
                              { title: '端点', dataIndex: 'endpoint', ellipsis: true },
                              { title: '身份', dataIndex: 'identity_type', render: (value) => <Tag color="red">{value}</Tag> },
                              { title: '重试(s)', dataIndex: 'retry_after' },
                            ]}
                          />
                        </Card>
                      </Space>
                    </Col>
                  </Row>
                </Space>
              </Card>
              <Card title="持久化记录与时序数据">
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <Card size="small" title="数据库接入中心">
                    <Space direction="vertical" size="large" style={{ width: '100%' }}>
                      <Row gutter={[12, 12]}>
                        <Col xs={24} md={6}><Statistic title="连接状态" value={persistenceDiagnostics?.connection_ok ? 'Connected' : 'Unavailable'} /></Col>
                        <Col xs={24} md={6}><Statistic title="数据库" value={persistenceDiagnostics?.database_name || '--'} /></Col>
                        <Col xs={24} md={6}><Statistic title="Timescale 扩展" value={persistenceDiagnostics?.timescale_extension_installed ? 'Installed' : 'Missing'} /></Col>
                        <Col xs={24} md={6}><Statistic title="Hypertable 数" value={(persistenceDiagnostics?.hypertables || []).length} /></Col>
                      </Row>
                      <Alert
                        showIcon
                        type={persistenceDiagnostics?.connection_ok ? (persistenceDiagnostics?.timescale_extension_installed ? 'success' : 'warning') : 'info'}
                        message={persistenceDiagnostics?.connection_ok ? 'PostgreSQL 连接诊断已就绪' : '当前未接入 PostgreSQL / TimescaleDB'}
                        description={persistenceDiagnostics?.error || (persistenceDiagnostics?.recommended_next_steps || []).join('；') || '可使用下方引导初始化持久化结构'}
                      />
                      <Row gutter={[16, 16]}>
                        <Col xs={24} xl={10}>
                          <Form
                            form={persistenceBootstrapForm}
                            layout="vertical"
                            onFinish={handleBootstrapPersistence}
                            initialValues={{ enable_timescale_schema: true }}
                          >
                            <Form.Item name="enable_timescale_schema" label="初始化范围">
                              <Select
                                options={[
                                  { value: true, label: 'Infra + Timescale 研究 Schema' },
                                  { value: false, label: '仅 Infra 基础表' },
                                ]}
                              />
                            </Form.Item>
                            <Button type="primary" htmlType="submit" loading={persistenceBootstrapLoading}>执行 Bootstrap</Button>
                          </Form>
                        </Col>
                        <Col xs={24} xl={14}>
                          <Card size="small" title="数据库诊断">
                            <Space direction="vertical" size={6}>
                              <Text type="secondary">Driver: {persistenceDiagnostics?.driver || '--'}</Text>
                              <Text type="secondary">Latency: {persistenceDiagnostics?.connection_latency_ms ?? '--'} ms</Text>
                              <Text type="secondary">Current User: {persistenceDiagnostics?.current_user || '--'}</Text>
                              <Text type="secondary">Schema File: {persistenceDiagnostics?.schema_file?.exists ? persistenceDiagnostics.schema_file.path : 'missing'}</Text>
                              <Text type="secondary">Tables: {(persistenceDiagnostics?.tables || []).join(', ') || '--'}</Text>
                              <Text type="secondary">Hypertables: {(persistenceDiagnostics?.hypertables || []).join(', ') || '--'}</Text>
                            </Space>
                          </Card>
                        </Col>
                      </Row>
                    </Space>
                  </Card>
                  <Card size="small" title="SQLite -> PostgreSQL 迁移">
                    <Space direction="vertical" size="large" style={{ width: '100%' }}>
                      <Row gutter={[12, 12]}>
                        <Col xs={24} md={6}><Statistic title="迁移状态" value={persistenceMigrationPreview?.status || '--'} /></Col>
                        <Col xs={24} md={6}><Statistic title="SQLite Records" value={persistenceMigrationPreview?.source?.record_count || 0} /></Col>
                        <Col xs={24} md={6}><Statistic title="SQLite 时序" value={persistenceMigrationPreview?.source?.timeseries_count || 0} /></Col>
                        <Col xs={24} md={6}><Statistic title="目标连接" value={persistenceMigrationPreview?.target?.connection_ok ? 'Ready' : 'Blocked'} /></Col>
                      </Row>
                      <Alert
                        showIcon
                        type={persistenceMigrationPreview?.status === 'ready' ? 'success' : 'warning'}
                        message={persistenceMigrationPreview?.status === 'ready' ? 'SQLite fallback 数据可迁移到 PostgreSQL' : '目标 PostgreSQL 尚未满足迁移条件'}
                        description={
                          persistenceMigrationPreview?.status === 'ready'
                            ? `策略: ${persistenceMigrationPreview?.plan?.record_strategy || 'upsert'} / ${persistenceMigrationPreview?.plan?.timeseries_strategy || 'dedupe'}`
                            : (persistenceMigrationPreview?.recommended_next_steps || []).join('；') || '请先完成 PostgreSQL 连接与 schema bootstrap'
                        }
                      />
                      <Row gutter={[16, 16]}>
                        <Col xs={24} xl={10}>
                          <Form
                            form={persistenceMigrationForm}
                            layout="vertical"
                            onFinish={handleRunPersistenceMigration}
                            initialValues={{
                              sqlite_path: '',
                              dry_run: true,
                              include_records: true,
                              include_timeseries: true,
                              dedupe_timeseries: true,
                            }}
                          >
                            <Form.Item name="sqlite_path" label="SQLite 源路径">
                              <Input placeholder={persistenceMigrationPreview?.source?.path || '默认使用本地 fallback store'} />
                            </Form.Item>
                            <Row gutter={12}>
                              <Col span={12}>
                                <Form.Item name="dry_run" label="执行模式">
                                  <Select
                                    options={[
                                      { value: true, label: 'Dry Run 预演' },
                                      { value: false, label: 'Apply 正式迁移' },
                                    ]}
                                  />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name="dedupe_timeseries" label="时序去重">
                                  <Select
                                    options={[
                                      { value: true, label: 'Exact Match 去重' },
                                      { value: false, label: '允许重复写入' },
                                    ]}
                                  />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Row gutter={12}>
                              <Col span={12}>
                                <Form.Item name="include_records" label="迁移 Records">
                                  <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name="include_timeseries" label="迁移时序">
                                  <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Row gutter={12}>
                              <Col span={12}>
                                <Form.Item name="record_limit" label="Record Limit">
                                  <InputNumber min={1} max={100000} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name="timeseries_limit" label="Timeseries Limit">
                                  <InputNumber min={1} max={100000} precision={0} style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Space>
                              <Button loading={persistenceMigrationLoading} onClick={() => handlePreviewPersistenceMigration(persistenceMigrationForm.getFieldsValue())}>
                                刷新预览
                              </Button>
                              <Button type="primary" htmlType="submit" loading={persistenceMigrationLoading}>
                                执行迁移
                              </Button>
                            </Space>
                          </Form>
                        </Col>
                        <Col xs={24} xl={14}>
                          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                            <Card size="small" title="迁移预览">
                              <Space direction="vertical" size={6}>
                                <Text type="secondary">SQLite Path: {persistenceMigrationPreview?.source?.path || '--'}</Text>
                                <Text type="secondary">Latest Record: {persistenceMigrationPreview?.source?.latest_record_updated_at || '--'}</Text>
                                <Text type="secondary">Latest Timeseries: {persistenceMigrationPreview?.source?.latest_timeseries_timestamp || '--'}</Text>
                                <Text type="secondary">Target DB: {persistenceMigrationPreview?.target?.database_name || '--'}</Text>
                                <Text type="secondary">Hypertables: {(persistenceMigrationPreview?.target?.hypertables || []).join(', ') || '--'}</Text>
                                <Text type="secondary">CLI: python3 scripts/migrate_infra_store.py --apply</Text>
                              </Space>
                            </Card>
                            <Card size="small" title="源数据分布">
                              <Row gutter={[16, 16]}>
                                <Col xs={24} md={12}>
                                  <Table
                                    size="small"
                                    pagination={false}
                                    rowKey={(record) => record.record_type}
                                    dataSource={persistenceMigrationPreview?.source?.record_types || []}
                                    columns={[
                                      { title: 'Record Type', dataIndex: 'record_type' },
                                      { title: '数量', dataIndex: 'count' },
                                    ]}
                                  />
                                </Col>
                                <Col xs={24} md={12}>
                                  <Table
                                    size="small"
                                    pagination={false}
                                    rowKey={(record) => record.series_name}
                                    dataSource={persistenceMigrationPreview?.source?.series_names || []}
                                    columns={[
                                      { title: 'Series', dataIndex: 'series_name' },
                                      { title: '数量', dataIndex: 'count' },
                                    ]}
                                  />
                                </Col>
                              </Row>
                            </Card>
                          </Space>
                        </Col>
                      </Row>
                    </Space>
                  </Card>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={8}><Statistic title="Record 总数" value={infrastructureStatus.persistence?.record_count || 0} /></Col>
                    <Col xs={24} md={8}><Statistic title="时序样本" value={infrastructureStatus.persistence?.timeseries_count || 0} /></Col>
                    <Col xs={24} md={8}><Statistic title="序列数量" value={infrastructureStatus.persistence?.distinct_series || 0} /></Col>
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="写入 Record">
                        <Form
                          form={persistenceRecordForm}
                          layout="vertical"
                          onFinish={handleSavePersistenceRecord}
                          initialValues={{
                            record_type: 'research_snapshot',
                            record_key: 'daily-alpha',
                            payload: '{"summary":"alpha watch","score":0.72}',
                          }}
                        >
                          <Form.Item name="record_type" label="Record Type" rules={[{ required: true, message: '请输入类型' }]}>
                            <Input />
                          </Form.Item>
                          <Form.Item name="record_key" label="Record Key" rules={[{ required: true, message: '请输入键' }]}>
                            <Input />
                          </Form.Item>
                          <Form.Item name="payload" label="Payload JSON">
                            <Input.TextArea rows={4} />
                          </Form.Item>
                          <Button htmlType="submit">写入 Record</Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="写入 Timeseries">
                        <Form
                          form={timeseriesForm}
                          layout="vertical"
                          onFinish={handleSaveTimeseries}
                          initialValues={{
                            series_name: 'research.alpha_score',
                            symbol: 'SPY',
                            timestamp: new Date().toISOString(),
                            value: 0.68,
                            payload: '{"source":"quant_lab","window":"1d"}',
                          }}
                        >
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="series_name" label="Series" rules={[{ required: true, message: '请输入序列名' }]}>
                                <Input />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="symbol" label="Symbol" rules={[{ required: true, message: '请输入标的' }]}>
                                <Input />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="timestamp" label="Timestamp">
                            <Input />
                          </Form.Item>
                          <Form.Item name="value" label="Value">
                            <InputNumber style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item name="payload" label="Payload JSON">
                            <Input.TextArea rows={3} />
                          </Form.Item>
                          <Button htmlType="submit">写入 Timeseries</Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={8}>
                      <Card size="small" title="查询过滤器">
                        <Form
                          form={persistenceQueryForm}
                          layout="vertical"
                          onFinish={handleLoadPersistenceExplorer}
                          initialValues={{ record_type: '', series_name: '', symbol: '', record_limit: 12, timeseries_limit: 12 }}
                        >
                          <Form.Item name="record_type" label="Record Type">
                            <Input placeholder="如 research_snapshot" />
                          </Form.Item>
                          <Form.Item name="series_name" label="Series">
                            <Input placeholder="如 research.alpha_score" />
                          </Form.Item>
                          <Form.Item name="symbol" label="Symbol">
                            <Input placeholder="如 SPY" />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="record_limit" label="Record 数量">
                                <InputNumber min={1} max={200} precision={0} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="timeseries_limit" label="时序数量">
                                <InputNumber min={1} max={500} precision={0} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Button type="primary" htmlType="submit">刷新视图</Button>
                        </Form>
                      </Card>
                    </Col>
                  </Row>
                  <Tabs
                    items={[
                      {
                        key: 'persistence-records',
                        label: 'Records',
                        children: (
                          <Table
                            size="small"
                            pagination={{ pageSize: 5 }}
                            rowKey="id"
                            dataSource={persistenceRecords}
                            columns={[
                              { title: 'Type', dataIndex: 'record_type', ellipsis: true },
                              { title: 'Key', dataIndex: 'record_key', ellipsis: true },
                              { title: '更新时间', dataIndex: 'updated_at', render: (value) => formatDateTime(value) },
                            ]}
                            expandable={{
                              expandedRowRender: (record) => <Text code>{JSON.stringify(record.payload || {}, null, 2)}</Text>,
                            }}
                          />
                        ),
                      },
                      {
                        key: 'persistence-timeseries',
                        label: 'Timeseries',
                        children: (
                          <Table
                            size="small"
                            pagination={{ pageSize: 5 }}
                            rowKey="id"
                            dataSource={persistenceTimeseries}
                            columns={[
                              { title: 'Series', dataIndex: 'series_name', ellipsis: true },
                              { title: 'Symbol', dataIndex: 'symbol' },
                              { title: 'Value', dataIndex: 'value', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(4) },
                              { title: '时间', dataIndex: 'timestamp', render: (value) => formatDateTime(value) },
                            ]}
                            expandable={{
                              expandedRowRender: (record) => <Text code>{JSON.stringify(record.payload || {}, null, 2)}</Text>,
                            }}
                          />
                        ),
                      },
                    ]}
                  />
                </Space>
              </Card>
              <Card
                title="配置版本化与回滚"
                extra={<Button size="small" onClick={handleDiffLatestConfigVersions} disabled={configVersionRows.length < 2} loading={configVersionLoading}>对比最新两版</Button>}
              >
                <Row gutter={[16, 16]}>
                  <Col xs={24} xl={10}>
                    <Form
                      form={configVersionForm}
                      layout="vertical"
                      onFinish={handleSaveConfigVersion}
                      initialValues={{
                        owner_id: 'default',
                        config_type: 'strategy',
                        config_key: 'moving_average',
                        payload: '{"short_window": 20, "long_window": 60, "risk_budget": 0.12}',
                      }}
                    >
                      <Row gutter={12}>
                        <Col xs={24} md={8}>
                          <Form.Item name="owner_id" label="Owner">
                            <Input />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                          <Form.Item name="config_type" label="配置类型" rules={[{ required: true, message: '请输入配置类型' }]}>
                            <Input />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                          <Form.Item name="config_key" label="配置键" rules={[{ required: true, message: '请输入配置键' }]}>
                            <Input />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item name="payload" label="配置 JSON">
                        <Input.TextArea rows={5} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit" loading={configVersionLoading}>保存新版本</Button>
                    </Form>
                  </Col>
                  <Col xs={24} xl={14}>
                    <Form
                      form={configLookupForm}
                      layout="inline"
                      onFinish={handleLoadConfigVersions}
                      initialValues={{ owner_id: 'default', config_type: 'strategy', config_key: 'moving_average', limit: 20 }}
                      style={{ marginBottom: 12 }}
                    >
                      <Form.Item name="owner_id" label="Owner">
                        <Input style={{ width: 110 }} />
                      </Form.Item>
                      <Form.Item name="config_type" label="类型">
                        <Input style={{ width: 120 }} />
                      </Form.Item>
                      <Form.Item name="config_key" label="键">
                        <Input style={{ width: 150 }} />
                      </Form.Item>
                      <Form.Item name="limit" label="数量">
                        <InputNumber min={1} max={200} precision={0} style={{ width: 90 }} />
                      </Form.Item>
                      <Button htmlType="submit" loading={configVersionLoading}>读取历史</Button>
                    </Form>
                    <Table
                      size="small"
                      pagination={{ pageSize: 5 }}
                      dataSource={configVersionRows}
                      columns={[
                        { title: '版本', render: (_, record) => `v${record.payload?.version || '--'}` },
                        { title: '创建者', render: (_, record) => record.payload?.created_by || '--' },
                        { title: '恢复自', render: (_, record) => record.payload?.restored_from ? `v${record.payload.restored_from}` : '--' },
                        { title: '更新时间', dataIndex: 'updated_at', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                        {
                          title: '操作',
                          render: (_, record) => (
                            <Button size="small" onClick={() => handleRestoreConfigVersion(record)} loading={configVersionLoading}>
                              恢复为新版本
                            </Button>
                          ),
                        },
                      ]}
                      expandable={{
                        expandedRowRender: (record) => (
                          <Text code>{JSON.stringify(record.payload?.payload || {}, null, 2)}</Text>
                        ),
                      }}
                    />
                  </Col>
                </Row>
                {configDiff ? (
                  <Card size="small" title={`配置差异 v${configDiff.from_version} → v${configDiff.to_version}`} style={{ marginTop: 16 }}>
                    <Table
                      size="small"
                      pagination={{ pageSize: 6 }}
                      dataSource={configDiffRows}
                      columns={[
                        { title: '路径', dataIndex: 'path' },
                        { title: '变更', dataIndex: 'change', render: (value) => <Tag color={value === 'added' ? 'green' : value === 'removed' ? 'red' : 'blue'}>{value}</Tag> },
                        { title: 'Before', dataIndex: 'before', ellipsis: true, render: (value) => JSON.stringify(value) },
                        { title: 'After', dataIndex: 'after', ellipsis: true, render: (value) => JSON.stringify(value) },
                      ]}
                    />
                  </Card>
                ) : null}
              </Card>
              <Card title="任务队列">
                <Table
                  size="small"
                  pagination={{ pageSize: 8 }}
                  dataSource={infrastructureTaskRows}
                  columns={[
                    { title: 'ID', dataIndex: 'id', ellipsis: true },
                    { title: '任务', dataIndex: 'name' },
                    { title: '后端', dataIndex: 'execution_backend', render: (value) => <Tag color={value === 'celery' ? 'purple' : 'blue'}>{value || 'local'}</Tag> },
                    { title: 'Broker', dataIndex: 'broker_state', render: (value) => value ? <Tag color={value === 'SUCCESS' ? 'green' : value === 'FAILURE' ? 'red' : value === 'REVOKED' ? 'default' : 'processing'}>{value}</Tag> : '--' },
                    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'completed' ? 'green' : value === 'failed' ? 'red' : value === 'cancelled' ? 'default' : 'blue'}>{value}</Tag> },
                    { title: '阶段', dataIndex: 'stage', render: (value) => value || '--' },
                    { title: '进度', dataIndex: 'progress', render: (value) => formatPct(value || 0) },
                    { title: '创建时间', dataIndex: 'created_at', render: (value) => String(value || '').slice(0, 19).replace('T', ' ') },
                    {
                      title: '操作',
                      render: (_, record) => (
                        <Space wrap>
                          {record.status === 'queued' || record.status === 'running' ? (
                            <Button size="small" danger onClick={() => handleCancelTask(record.id)}>取消</Button>
                          ) : null}
                          {record.status === 'completed' && (String(record.name || '').startsWith('quant_') || String(record.name || '').startsWith('backtest_')) ? (
                            <Button size="small" onClick={() => handleLoadTaskResult(record)}>载入结果</Button>
                          ) : null}
                          {record.status !== 'queued' && record.status !== 'running' && !(record.status === 'completed' && (String(record.name || '').startsWith('quant_') || String(record.name || '').startsWith('backtest_'))) ? '--' : null}
                        </Space>
                      ),
                    },
                  ]}
                  expandable={{
                    expandedRowRender: (record) => (
                      <Space direction="vertical" size={4}>
                        <Text type="secondary">{record.error || record.result?.message || '暂无额外结果'}</Text>
                        <Text type="secondary">Broker Task ID: {record.broker_task_id || '--'}</Text>
                        <Text type="secondary">Broker 状态刷新: {record.broker_checked_at ? formatDateTime(record.broker_checked_at) : '--'}</Text>
                        <Text code>{JSON.stringify(record.payload || {}, null, 2)}</Text>
                      </Space>
                    ),
                  }}
                />
              </Card>
            </>
          ) : null}
        </Space>
      ),
    },
    {
      key: 'ops',
      label: <span><SettingOutlined />研究运营中心</span>,
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadOperations} loading={opsLoading}>刷新运营面板</Button>
          </Space>
          {opsLoading ? <Spin size="large" /> : null}
          {!opsLoading ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={12}>
                  <Card title="交易日志与绩效追踪">
                    {tradingJournal?.summary ? (
                      <Tabs
                        items={[
                          {
                            key: 'journal-overview',
                            label: '交易明细',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size="large">
                                <Row gutter={[12, 12]}>
                                  <Col span={12}><Statistic title="总交易数" value={tradingJournal.summary.total_trades || 0} /></Col>
                                  <Col span={12}><Statistic title="已实现盈亏" value={formatMoney(tradingJournal.summary.realized_pnl || 0)} /></Col>
                                  <Col span={12}><Statistic title="胜率" value={formatPct(tradingJournal.summary.win_rate || 0)} /></Col>
                                  <Col span={12}><Statistic title="平均信号强度" value={formatPct(tradingJournal.summary.average_signal_strength || 0)} /></Col>
                                </Row>
                                <Row gutter={[12, 12]}>
                                  <Col span={12}>
                                    <Card size="small" title="认知偏差检测">
                                      <List
                                        size="small"
                                        dataSource={tradingJournal.bias_detection || []}
                                        renderItem={(item) => (
                                          <List.Item>
                                            <Space direction="vertical" size={2}>
                                              <Text strong>{item.bias}</Text>
                                              <Text type="secondary">{item.evidence}</Text>
                                            </Space>
                                          </List.Item>
                                        )}
                                      />
                                    </Card>
                                  </Col>
                                  <Col span={12}>
                                    <Card size="small" title="来源与风险桶">
                                      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                                        <div>
                                          <Text type="secondary">策略来源</Text>
                                          <div style={{ marginTop: 8 }}>
                                            {(tradingJournal.source_breakdown || []).map((item) => (
                                              <Tag key={item.source}>{`${item.source} ${item.count}`}</Tag>
                                            ))}
                                          </div>
                                        </div>
                                        <div>
                                          <Text type="secondary">风险桶分布</Text>
                                          <div style={{ marginTop: 8 }}>
                                            {(tradingJournal.risk_breakdown || []).map((item) => (
                                              <Tag key={item.bucket} color={item.bucket === 'high' ? 'red' : item.bucket === 'medium' ? 'gold' : 'green'}>
                                                {`${item.bucket} ${item.count}`}
                                              </Tag>
                                            ))}
                                          </div>
                                        </div>
                                      </Space>
                                    </Card>
                                  </Col>
                                </Row>
                                <Table
                                  size="small"
                                  rowKey="id"
                                  pagination={{ pageSize: 4 }}
                                  dataSource={tradingJournal.trades || []}
                                  onRow={(record) => ({
                                    onClick: () => {
                                      setSelectedTrade(record);
                                      journalForm.setFieldsValue({
                                        notes: record.notes,
                                        strategy_source: record.strategy_source,
                                        signal_strength: record.signal_strength,
                                        reason_category: record.reason_category,
                                        error_category: record.error_category,
                                      });
                                    },
                                    style: { cursor: 'pointer' },
                                  })}
                                  columns={[
                                    { title: '时间', dataIndex: 'timestamp', render: (value) => formatDateTime(value) },
                                    { title: '标的', dataIndex: 'symbol' },
                                    { title: '动作', dataIndex: 'action', render: (value) => <Tag color={value === 'BUY' ? 'green' : 'red'}>{value}</Tag> },
                                    { title: '来源', dataIndex: 'strategy_source', render: (value) => <Tag>{value || 'manual'}</Tag> },
                                    { title: '信号', dataIndex: 'signal_strength', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                                    { title: 'PnL', dataIndex: 'pnl', render: (value) => value === null || value === undefined ? '--' : formatMoney(value) },
                                  ]}
                                />
                                <Card size="small" title={selectedTrade ? `编辑交易备注 · ${selectedTrade.symbol}` : '选择交易后编辑备注'}>
                                  <Form form={journalForm} layout="vertical" onFinish={handleSaveTradeNote}>
                                    <Form.Item name="notes" label="交易备注">
                                      <Input.TextArea rows={3} placeholder="记录买卖理由、执行偏差或复盘结论" />
                                    </Form.Item>
                                    <Row gutter={12}>
                                      <Col span={12}>
                                        <Form.Item name="strategy_source" label="策略来源">
                                          <Select options={[{ value: 'manual', label: '人工触发' }, { value: 'signal', label: '策略信号' }, { value: 'hedge', label: '对冲动作' }]} />
                                        </Form.Item>
                                      </Col>
                                      <Col span={12}>
                                        <Form.Item name="signal_strength" label="信号强度">
                                          <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                    <Row gutter={12}>
                                      <Col span={12}>
                                        <Form.Item name="reason_category" label="原因分类">
                                          <Select options={[{ value: 'signal_entry', label: '信号入场' }, { value: 'profit_taking', label: '止盈' }, { value: 'risk_exit', label: '风险退出' }]} />
                                        </Form.Item>
                                      </Col>
                                      <Col span={12}>
                                        <Form.Item name="error_category" label="错误分类">
                                          <Select options={[{ value: 'none', label: '无' }, { value: 'timing_error', label: '择时错误' }, { value: 'oversized_position', label: '仓位过重' }, { value: 'noise_trade', label: '噪音交易' }]} />
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                    <Button type="primary" htmlType="submit" disabled={!selectedTrade}>保存备注</Button>
                                  </Form>
                                </Card>
                              </Space>
                            ),
                          },
                          {
                            key: 'journal-reports',
                            label: '日报与复盘',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size="large">
                                <Card size="small" title="每日 / 每周绩效">
                                  <Tabs
                                    items={[
                                      {
                                        key: 'daily-report',
                                        label: '日报',
                                        children: (
                                          <Table
                                            size="small"
                                            rowKey="period"
                                            pagination={{ pageSize: 5 }}
                                            dataSource={tradingJournal.daily_report || []}
                                            columns={[
                                              { title: '周期', dataIndex: 'period' },
                                              { title: '交易数', dataIndex: 'trade_count' },
                                              { title: '胜率', dataIndex: 'win_rate', render: (value) => formatPct(value) },
                                              { title: '平均PnL', dataIndex: 'average_pnl', render: (value) => formatMoney(value) },
                                              { title: '总PnL', dataIndex: 'realized_pnl', render: (value) => formatMoney(value) },
                                            ]}
                                          />
                                        ),
                                      },
                                      {
                                        key: 'weekly-report',
                                        label: '周报',
                                        children: (
                                          <Table
                                            size="small"
                                            rowKey="period"
                                            pagination={{ pageSize: 5 }}
                                            dataSource={tradingJournal.weekly_report || []}
                                            columns={[
                                              { title: '周期', dataIndex: 'period' },
                                              { title: '交易数', dataIndex: 'trade_count' },
                                              { title: '胜率', dataIndex: 'win_rate', render: (value) => formatPct(value) },
                                              { title: '平均PnL', dataIndex: 'average_pnl', render: (value) => formatMoney(value) },
                                              { title: '总PnL', dataIndex: 'realized_pnl', render: (value) => formatMoney(value) },
                                            ]}
                                          />
                                        ),
                                      },
                                    ]}
                                  />
                                </Card>
                                <Card size="small" title="亏损交易归因">
                                  <Table
                                    size="small"
                                    rowKey="category"
                                    pagination={{ pageSize: 5 }}
                                    dataSource={tradingJournal.loss_analysis || []}
                                    columns={[
                                      { title: '分类', dataIndex: 'category', render: (value) => <Tag color="red">{value}</Tag> },
                                      { title: '次数', dataIndex: 'count' },
                                      { title: '亏损占比', dataIndex: 'share_of_losses', render: (value) => formatPct(value) },
                                      { title: '平均亏损', dataIndex: 'average_loss', render: (value) => formatMoney(value) },
                                      { title: '平均仓位', dataIndex: 'average_size', render: (value) => formatMoney(value) },
                                      { title: '高频标的', dataIndex: 'top_symbols', render: (value) => Array.isArray(value) && value.length ? value.map((symbol) => <Tag key={symbol}>{symbol}</Tag>) : '--' },
                                    ]}
                                  />
                                </Card>
                              </Space>
                            ),
                          },
                          {
                            key: 'journal-lifecycle',
                            label: '策略生命周期',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size="large">
                                <Row gutter={[12, 12]}>
                                  <Col span={8}><Statistic title="策略条目" value={tradingJournal.strategy_lifecycle_summary?.total || 0} /></Col>
                                  <Col span={8}><Statistic title="进行中" value={tradingJournal.strategy_lifecycle_summary?.active || 0} /></Col>
                                  <Col span={8}><Statistic title="平均信心" value={formatPct(tradingJournal.strategy_lifecycle_summary?.average_conviction || 0)} /></Col>
                                </Row>
                                <Card size="small" title="新增生命周期条目">
                                  <Form
                                    form={lifecycleForm}
                                    layout="vertical"
                                    initialValues={{ stage: 'discovered', status: 'active', owner: 'research', conviction: 0.5 }}
                                    onFinish={handleAddLifecycleEntry}
                                  >
                                    <Row gutter={12}>
                                      <Col span={12}>
                                        <Form.Item name="strategy" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
                                          <Input placeholder="如 Industry Rotation Alpha" />
                                        </Form.Item>
                                      </Col>
                                      <Col span={12}>
                                        <Form.Item name="owner" label="负责人">
                                          <Input placeholder="research / pm / execution" />
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                    <Row gutter={12}>
                                      <Col span={8}>
                                        <Form.Item name="stage" label="阶段">
                                          <Select options={JOURNAL_STAGE_OPTIONS} />
                                        </Form.Item>
                                      </Col>
                                      <Col span={8}>
                                        <Form.Item name="status" label="状态">
                                          <Select options={JOURNAL_STATUS_OPTIONS} />
                                        </Form.Item>
                                      </Col>
                                      <Col span={8}>
                                        <Form.Item name="conviction" label="信心度">
                                          <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                    <Form.Item name="next_action" label="下一步动作">
                                      <Input placeholder="如 本周完成 walk-forward 验证并准备 paper trading" />
                                    </Form.Item>
                                    <Form.Item name="notes" label="阶段备注">
                                      <Input.TextArea rows={3} placeholder="记录当前结论、阻塞点或验证结果" />
                                    </Form.Item>
                                    <Button type="primary" htmlType="submit">添加条目</Button>
                                  </Form>
                                </Card>
                                <Card size="small" title="生命周期看板">
                                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                                    <div>
                                      {(tradingJournal.strategy_lifecycle_summary?.stage_breakdown || []).map((item) => (
                                        <Tag key={item.stage} color={lifecycleStageColor(item.stage)}>{`${item.stage} ${item.count}`}</Tag>
                                      ))}
                                    </div>
                                    <Table
                                      size="small"
                                      rowKey="id"
                                      pagination={{ pageSize: 5 }}
                                      dataSource={tradingJournal.strategy_lifecycle || []}
                                      columns={[
                                        { title: '策略', dataIndex: 'strategy' },
                                        { title: '阶段', dataIndex: 'stage', render: (value) => <Tag color={lifecycleStageColor(value)}>{value}</Tag> },
                                        { title: '状态', dataIndex: 'status', render: (value) => <Tag color={lifecycleStatusColor(value)}>{value}</Tag> },
                                        { title: '负责人', dataIndex: 'owner' },
                                        { title: '信心度', dataIndex: 'conviction', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                                        { title: '下一步', dataIndex: 'next_action', ellipsis: true },
                                        { title: '更新时间', dataIndex: 'updated_at', render: (value) => formatDateTime(value) },
                                      ]}
                                      expandable={{
                                        expandedRowRender: (record) => (
                                          <Space direction="vertical" size={4}>
                                            <Text type="secondary">{record.notes || '暂无备注'}</Text>
                                          </Space>
                                        ),
                                      }}
                                    />
                                  </Space>
                                </Card>
                              </Space>
                            ),
                          },
                        ]}
                      />
                    ) : <Empty description="暂无交易日志数据" />}
                  </Card>
                </Col>
                <Col xs={24} xl={12}>
                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    <Card title="智能告警编排中心">
                      {alertOrchestration?.summary ? (
                        <Space direction="vertical" style={{ width: '100%' }} size="large">
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="实时规则" value={alertOrchestration.summary.realtime_rules || 0} /></Col>
                            <Col span={8}><Statistic title="复合规则" value={alertOrchestration.summary.composite_rules || 0} /></Col>
                            <Col span={8}><Statistic title="事件总线" value={alertOrchestration.summary.alert_history_events || 0} /></Col>
                          </Row>
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="已复盘事件" value={alertOrchestration.summary.reviewed_events || 0} /></Col>
                            <Col span={8}><Statistic title="误报率" value={formatPct(alertOrchestration.summary.false_positive_rate || 0)} /></Col>
                            <Col span={8}><Statistic title="平均响应(分钟)" value={alertOrchestration.summary.average_response_minutes ?? '--'} /></Col>
                          </Row>
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="级联事件" value={alertOrchestration.summary.cascaded_events || 0} /></Col>
                            <Col span={8}><Statistic title="通知触发" value={alertOrchestration.summary.notified_events || 0} /></Col>
                            <Col span={8}><Statistic title="工作台任务" value={alertOrchestration.summary.workbench_tasks_created || 0} /></Col>
                          </Row>
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="基础设施任务" value={alertOrchestration.summary.infra_tasks_created || 0} /></Col>
                            <Col span={8}><Statistic title="时序写入" value={alertOrchestration.summary.timeseries_points_written || 0} /></Col>
                            <Col span={8}><Statistic title="配置快照" value={alertOrchestration.summary.config_snapshots_created || 0} /></Col>
                          </Row>
                          <Tabs
                            items={[
                              {
                                key: 'alert-rules',
                                label: '规则编排',
                                children: (
                                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                                    <Form form={alertForm} layout="vertical" onFinish={handleAddCompositeRule}>
                                      <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
                                        <Input placeholder="如 跨市场对冲信号" />
                                      </Form.Item>
                                      <Form.Item name="condition_summary" label="复合条件" rules={[{ required: true, message: '请输入条件摘要' }]}>
                                        <Input.TextArea rows={2} placeholder="如 A股走弱 + 商品走强 + 情绪转空" />
                                      </Form.Item>
                                      <Form.Item name="action" label="触发动作">
                                        <Input placeholder="如 保存到研究工作台 + Webhook" />
                                      </Form.Item>
                                      <Form.Item
                                        name="cascade_actions_json"
                                        label="级联动作 JSON"
                                        extra="支持 create_infra_task / persist_timeseries / save_config_version 等动作"
                                      >
                                        <Input.TextArea
                                          rows={4}
                                          placeholder='[{"type":"persist_timeseries","series_name":"alert_bus.manual"},{"type":"save_config_version","config_type":"alert_playbook","config_key":"macro_defense"}]'
                                        />
                                      </Form.Item>
                                      <Button type="primary" htmlType="submit">新增复合规则</Button>
                                    </Form>
                                    <Card size="small" title="发布事件到统一总线">
                                      <Form
                                        form={alertEventForm}
                                        layout="vertical"
                                        onFinish={handlePublishAlertEvent}
                                        initialValues={{
                                          source_module: 'manual',
                                          severity: 'warning',
                                          create_workbench_task: true,
                                          workbench_task_type: 'cross_market',
                                          workbench_status: 'new',
                                          persist_event_record: true,
                                          cascade_actions_json: '',
                                        }}
                                      >
                                        <Row gutter={12}>
                                          <Col span={12}>
                                            <Form.Item name="source_module" label="来源模块">
                                              <Select options={[{ value: 'manual', label: 'manual' }, { value: 'realtime', label: 'realtime' }, { value: 'composite', label: 'composite' }, { value: 'pricing', label: 'pricing' }, { value: 'godeye', label: 'godeye' }]} />
                                            </Form.Item>
                                          </Col>
                                          <Col span={12}>
                                            <Form.Item name="severity" label="级别">
                                              <Select options={[{ value: 'info', label: 'info' }, { value: 'warning', label: 'warning' }, { value: 'critical', label: 'critical' }]} />
                                            </Form.Item>
                                          </Col>
                                        </Row>
                                        <Form.Item name="rule_name" label="事件名称" rules={[{ required: true, message: '请输入事件名称' }]}>
                                          <Input placeholder="如 跨市场防御切换" />
                                        </Form.Item>
                                        <Row gutter={12}>
                                          <Col span={12}>
                                            <Form.Item name="symbol" label="标的">
                                              <Input placeholder="如 SPY" />
                                            </Form.Item>
                                          </Col>
                                          <Col span={12}>
                                            <Form.Item name="rule_ids" label="匹配规则 ID">
                                              <Input placeholder="可选，空格或逗号分隔" />
                                            </Form.Item>
                                          </Col>
                                        </Row>
                                        <Form.Item name="condition_summary" label="条件摘要">
                                          <Input.TextArea rows={2} placeholder="如 A股走弱 + 商品走强 + 波动率抬升" />
                                        </Form.Item>
                                        <Form.Item name="message" label="事件说明">
                                          <Input.TextArea rows={2} placeholder="如 建议切换到防御 / 对冲研究流程" />
                                        </Form.Item>
                                        <Row gutter={12}>
                                          <Col span={12}>
                                            <Form.Item name="trigger_value" label="触发值">
                                              <InputNumber style={{ width: '100%' }} />
                                            </Form.Item>
                                          </Col>
                                          <Col span={12}>
                                            <Form.Item name="threshold" label="阈值">
                                              <InputNumber style={{ width: '100%' }} />
                                            </Form.Item>
                                          </Col>
                                        </Row>
                                        <Form.Item name="notify_channels" label="通知通道">
                                          <Input placeholder="如 dry_run webhook research_webhook" />
                                        </Form.Item>
                                        <Row gutter={12}>
                                          <Col span={8}>
                                            <Form.Item name="create_workbench_task" label="创建工作台任务">
                                              <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                                            </Form.Item>
                                          </Col>
                                          <Col span={8}>
                                            <Form.Item name="workbench_task_type" label="任务类型">
                                              <Select options={[{ value: 'cross_market', label: 'cross_market' }, { value: 'pricing', label: 'pricing' }, { value: 'macro_mispricing', label: 'macro_mispricing' }, { value: 'trade_thesis', label: 'trade_thesis' }]} />
                                            </Form.Item>
                                          </Col>
                                          <Col span={8}>
                                            <Form.Item name="workbench_status" label="任务状态">
                                              <Select options={[{ value: 'new', label: 'new' }, { value: 'in_progress', label: 'in_progress' }, { value: 'blocked', label: 'blocked' }]} />
                                            </Form.Item>
                                          </Col>
                                        </Row>
                                        <Form.Item name="persist_event_record" label="持久化事件记录">
                                          <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                                        </Form.Item>
                                        <Form.Item
                                          name="cascade_actions_json"
                                          label="额外级联动作 JSON"
                                          extra="支持 create_infra_task / persist_timeseries / save_config_version；留空则只执行上面的基础动作"
                                        >
                                          <Input.TextArea
                                            rows={5}
                                            placeholder={'[{"type":"create_infra_task","task_name":"quant_strategy_optimizer","payload":{"symbol":"AAPL","strategy":"moving_average"}},{"type":"persist_timeseries","series_name":"alert.signal_strength"},{"type":"save_config_version","config_type":"alert_playbook","config_key":"cross_market_hedge"}]'}
                                          />
                                        </Form.Item>
                                        <Button type="primary" htmlType="submit">发布事件</Button>
                                      </Form>
                                    </Card>
                                    <Table
                                      size="small"
                                      pagination={{ pageSize: 4 }}
                                      rowKey={(record) => record.id || record.name}
                                      dataSource={alertOrchestration.composite_rules || []}
                                      columns={[
                                        { title: '规则', dataIndex: 'name' },
                                        { title: '条件', dataIndex: 'condition_summary', ellipsis: true },
                                        { title: '动作', dataIndex: 'action', ellipsis: true },
                                        { title: '级联动作', dataIndex: 'cascade_actions', render: (value) => Array.isArray(value) ? value.length : 0 },
                                      ]}
                                    />
                                    <Card size="small" title="规则命中画像">
                                      <Table
                                        size="small"
                                        pagination={{ pageSize: 4 }}
                                        rowKey={(record) => `${record.rule_name}-${record.source_module}`}
                                        dataSource={alertOrchestration.history_stats?.rule_stats || []}
                                        columns={[
                                          { title: '规则', dataIndex: 'rule_name', ellipsis: true },
                                          { title: '模块', dataIndex: 'source_module', render: (value) => <Tag>{value}</Tag> },
                                          { title: '命中数', dataIndex: 'hit_count' },
                                          { title: '复盘数', dataIndex: 'reviewed_count' },
                                          { title: '误报率', dataIndex: 'false_positive_rate', render: (value) => formatPct(value) },
                                          { title: '最近触发', dataIndex: 'last_trigger_time', render: (value) => value ? formatDateTime(value) : '--' },
                                        ]}
                                      />
                                    </Card>
                                  </Space>
                                ),
                              },
                              {
                                key: 'alert-history',
                                label: '历史与复盘',
                                children: (
                                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                                    <Card size="small" title="模块统计">
                                      <Table
                                        size="small"
                                        pagination={false}
                                        rowKey="module"
                                        dataSource={alertOrchestration.history_stats?.module_stats || []}
                                        columns={[
                                          { title: '模块', dataIndex: 'module', render: (value) => <Tag>{value}</Tag> },
                                          { title: '事件数', dataIndex: 'event_count' },
                                          { title: '待处理', dataIndex: 'pending_count' },
                                          { title: '已复盘', dataIndex: 'reviewed_count' },
                                          { title: '误报率', dataIndex: 'false_positive_rate', render: (value) => formatPct(value) },
                                        ]}
                                      />
                                    </Card>
                                    <Card size="small" title="级联动作统计">
                                      <Table
                                        size="small"
                                        pagination={false}
                                        rowKey="action_type"
                                        dataSource={alertOrchestration.history_stats?.cascade_stats || []}
                                        columns={[
                                          { title: '动作', dataIndex: 'action_type', render: (value) => <Tag color="purple">{value}</Tag> },
                                          { title: '总次数', dataIndex: 'count' },
                                          { title: '成功', dataIndex: 'success_count' },
                                          { title: '失败', dataIndex: 'failure_count' },
                                        ]}
                                      />
                                    </Card>
                                    <Card size="small" title="近期告警历史">
                                      <Table
                                        size="small"
                                        pagination={{ pageSize: 5 }}
                                        rowKey="id"
                                        dataSource={alertOrchestration.event_bus?.history || []}
                                        columns={[
                                          { title: '时间', dataIndex: 'trigger_time', render: (value) => formatDateTime(value) },
                                          { title: '模块', dataIndex: 'source_module', render: (value) => <Tag>{value}</Tag> },
                                          { title: '规则', dataIndex: 'rule_name', ellipsis: true },
                                          { title: '标的', dataIndex: 'symbol', render: (value) => value || '--' },
                                          { title: '分发', dataIndex: 'dispatch_status', render: (value) => <Tag color={value === 'dispatched' ? 'green' : value === 'degraded' ? 'red' : 'gold'}>{value || 'pending'}</Tag> },
                                          { title: '状态', dataIndex: 'review_status', render: (value) => <Tag color={value === 'resolved' ? 'green' : value === 'false_positive' ? 'red' : 'gold'}>{value || 'pending'}</Tag> },
                                          { title: '响应(分钟)', dataIndex: 'response_minutes', render: (value) => value === null || value === undefined ? '--' : Number(value).toFixed(1) },
                                          {
                                            title: '操作',
                                            render: (_, record) => (
                                              <Space wrap>
                                                <Button
                                                  size="small"
                                                  type={record.review_status === 'resolved' ? 'primary' : 'default'}
                                                  onClick={() => handleReviewAlertHistory(record, 'resolved')}
                                                >
                                                  已处理
                                                </Button>
                                                <Button
                                                  size="small"
                                                  danger
                                                  type={record.review_status === 'false_positive' ? 'primary' : 'default'}
                                                  onClick={() => handleReviewAlertHistory(record, 'false_positive')}
                                                >
                                                  误报
                                                </Button>
                                              </Space>
                                            ),
                                          },
                                        ]}
                                        expandable={{
                                          expandedRowRender: (record) => (
                                            <Space direction="vertical" size={4}>
                                              <Text type="secondary">命中规则: {(record.matched_rule_names || []).join(', ') || '--'}</Text>
                                              <Text type="secondary">通知通道: {(record.dispatched_channels || []).join(', ') || '--'}</Text>
                                              <Text type="secondary">工作台任务: {(record.workbench_task_ids || []).join(', ') || '--'}</Text>
                                              <Text type="secondary">基础设施任务: {(record.infra_task_ids || []).join(', ') || '--'}</Text>
                                              <Text type="secondary">时序写入: {(record.timeseries_points || []).map((item) => `${item.series_name || 'unknown'}@${item.timestamp || '--'}`).join(', ') || '--'}</Text>
                                              <Text type="secondary">配置快照: {(record.config_snapshots || []).map((item) => `${item.config_type || 'config'}/${item.config_key || 'default'} v${item.version || '?'}`).join(', ') || '--'}</Text>
                                              <Text code>{JSON.stringify(record.cascade_results || [], null, 2)}</Text>
                                            </Space>
                                          ),
                                        }}
                                      />
                                    </Card>
                                    <Card size="small" title="待处理队列">
                                      {(alertOrchestration.history_stats?.pending_queue || []).length ? (
                                        <List
                                          size="small"
                                          dataSource={alertOrchestration.history_stats?.pending_queue || []}
                                          renderItem={(item) => (
                                            <List.Item
                                              actions={[
                                                <Button key="resolve" size="small" type="link" onClick={() => handleReviewAlertHistory(item, 'resolved')}>处理</Button>,
                                                <Button key="false-positive" size="small" type="link" danger onClick={() => handleReviewAlertHistory(item, 'false_positive')}>误报</Button>,
                                              ]}
                                            >
                                              <List.Item.Meta
                                                title={<Space wrap><Tag>{item.source_module}</Tag><Text strong>{item.rule_name}</Text></Space>}
                                                description={`${item.symbol || '--'} · ${formatDateTime(item.trigger_time)}`}
                                              />
                                            </List.Item>
                                          )}
                                        />
                                      ) : <Empty description="暂无待处理告警事件" />}
                                    </Card>
                                  </Space>
                                ),
                              },
                            ]}
                          />
                        </Space>
                      ) : <Empty description="暂无告警编排数据" />}
                    </Card>
                    <Card title="数据质量可观测平台">
                      {dataQuality?.providers ? (
                        <Space direction="vertical" size="large" style={{ width: '100%' }}>
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="平均质量分" value={formatPct(dataQuality.summary?.average_quality_score || 0)} /></Col>
                            <Col span={8}><Statistic title="平均延迟(ms)" value={Number(dataQuality.summary?.average_latency_ms || 0).toFixed(1)} /></Col>
                            <Col span={8}><Statistic title="平均完整性" value={formatPct(dataQuality.summary?.average_completeness || 0)} /></Col>
                          </Row>
                          <Row gutter={[12, 12]}>
                            <Col span={8}><Statistic title="过期数据源" value={dataQuality.summary?.stale || 0} /></Col>
                            <Col span={8}><Statistic title="可用性退化" value={(dataQuality.summary?.degraded || 0) + (dataQuality.summary?.down || 0)} /></Col>
                            <Col span={8}><Statistic title="回测风险" value={dataQuality.backtest_quality_report?.risk_level || '--'} /></Col>
                          </Row>
                          <Card
                            size="small"
                            title="回测数据质量评估"
                            extra={<Tag color={dataQuality.backtest_quality_report?.risk_level === 'low' ? 'green' : dataQuality.backtest_quality_report?.risk_level === 'medium' ? 'gold' : 'red'}>{dataQuality.backtest_quality_report?.risk_level || 'unknown'}</Tag>}
                          >
                            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                              <Text>{dataQuality.backtest_quality_report?.recommendation || '暂无评估结论'}</Text>
                              <div>
                                {(dataQuality.backtest_quality_report?.drivers || []).map((item) => (
                                  <Tag key={`${item.provider}-${item.status}`} color={item.status === 'available' ? 'blue' : 'red'}>
                                    {`${item.provider} · ${formatPct(item.quality_score || 0)} · ${(item.flags || []).join(', ') || 'stable'}`}
                                  </Tag>
                                ))}
                              </div>
                            </Space>
                          </Card>
                          <Tabs
                            items={[
                              {
                                key: 'provider-health',
                                label: 'Provider 健康',
                                children: (
                                  <Table
                                    size="small"
                                    pagination={false}
                                    rowKey="provider"
                                    dataSource={dataQuality.providers}
                                    columns={[
                                      { title: 'Provider', dataIndex: 'provider' },
                                      { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'available' ? 'green' : value === 'degraded' ? 'orange' : 'red'}>{value}</Tag> },
                                      { title: '质量分', dataIndex: 'quality_score', render: (value) => formatPct(value) },
                                      { title: '延迟(ms)', dataIndex: 'latency_ms', render: (value) => Number(value || 0).toFixed(1) },
                                      { title: '完整性', dataIndex: 'completeness_score', render: (value) => value === null || value === undefined ? '--' : formatPct(value) },
                                      { title: '新鲜度', dataIndex: 'freshness_label', render: (value) => <Tag color={value === 'fresh' ? 'green' : value === 'recent' ? 'blue' : value === 'aging' ? 'gold' : 'red'}>{value || 'unknown'}</Tag> },
                                      { title: '审计标记', dataIndex: 'audit_flags', render: (value) => Array.isArray(value) && value.length ? value.map((item) => <Tag key={item}>{item}</Tag>) : <Tag color="green">stable</Tag> },
                                    ]}
                                  />
                                ),
                              },
                              {
                                key: 'quality-audit',
                                label: '审计与故障转移',
                                children: (
                                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                                    <Card size="small" title="审计发现">
                                      <List
                                        size="small"
                                        dataSource={dataQuality.audit_report?.findings || []}
                                        renderItem={(item) => (
                                          <List.Item>
                                            <Space direction="vertical" size={2}>
                                              <Space wrap>
                                                <Tag color={item.severity === 'high' ? 'red' : item.severity === 'medium' ? 'gold' : 'green'}>{item.severity}</Tag>
                                                <Text strong>{item.title}</Text>
                                              </Space>
                                              <Text type="secondary">{item.detail}</Text>
                                            </Space>
                                          </List.Item>
                                        )}
                                      />
                                    </Card>
                                    <Card size="small" title="故障热点与最弱链路">
                                      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                                        <div>
                                          <Text type="secondary">故障转移热点</Text>
                                          <div style={{ marginTop: 8 }}>
                                            {(dataQuality.audit_report?.failover_hotspots || []).map((item) => (
                                              <Tag key={item.provider} color="red">{`${item.provider} ${item.count}`}</Tag>
                                            ))}
                                          </div>
                                        </div>
                                        <div>
                                          <Text type="secondary">当前最弱 Provider</Text>
                                          <div style={{ marginTop: 8 }}>
                                            {dataQuality.audit_report?.weakest_provider ? (
                                              <Space wrap>
                                                <Tag color="red">{dataQuality.audit_report.weakest_provider.provider}</Tag>
                                                <Tag>{`质量 ${formatPct(dataQuality.audit_report.weakest_provider.quality_score || 0)}`}</Tag>
                                                {(dataQuality.audit_report.weakest_provider.audit_flags || []).map((item) => (
                                                  <Tag key={item}>{item}</Tag>
                                                ))}
                                              </Space>
                                            ) : <Text type="secondary">暂无弱项</Text>}
                                          </div>
                                        </div>
                                      </Space>
                                    </Card>
                                    <Card size="small" title="最近故障转移日志">
                                      <Table
                                        size="small"
                                        pagination={{ pageSize: 4 }}
                                        rowKey={(record, index) => `${record.provider}-${record.timestamp}-${index}`}
                                        dataSource={dataQuality.failover_log || []}
                                        columns={[
                                          { title: '时间', dataIndex: 'timestamp', render: (value) => formatDateTime(value) },
                                          { title: 'Provider', dataIndex: 'provider', render: (value) => <Tag color="red">{value}</Tag> },
                                          { title: '原因', dataIndex: 'reason', ellipsis: true },
                                        ]}
                                      />
                                    </Card>
                                  </Space>
                                ),
                              },
                            ]}
                          />
                        </Space>
                      ) : <Empty description="暂无数据质量快照" />}
                    </Card>
                  </Space>
                </Col>
              </Row>
            </>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 12 }}>Quant Lab</Title>
      <Paragraph type="secondary" style={{ marginBottom: 20 }}>
        把参数优化、风险归因、估值历史、交易日志、告警编排和数据质量放进同一个研究工作台，方便我们把“发现机会”一路推进到“复盘与运营”。
      </Paragraph>
      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="这一版优先补齐研究闭环"
        description="后端已经把策略优化、风险分析、估值历史追踪、交易日志、智能告警编排和数据质量观测统一到 Quant Lab；前端则先提供一个集中工作台，便于持续迭代。"
      />
      <Tabs items={tabs} activeKey={activeTab} onChange={setActiveTab} />
    </div>
  );
};

export default QuantLab;
