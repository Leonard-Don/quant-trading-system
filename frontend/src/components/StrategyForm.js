import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Button,
  Card,
  Dropdown,
  Modal,
  Tag,
  Popconfirm,
} from 'antd';
import { PlayCircleOutlined, SaveOutlined, FolderOpenOutlined, DeleteOutlined, DownOutlined } from '@ant-design/icons';
import dayjs from '../utils/dayjs';
import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../constants/strategies';
import { useSafeMessageApi } from '../utils/messageApi';
import {
  BACKTEST_WORKSPACE_DRAFT_EVENT,
  loadBacktestWorkspaceDraft,
  saveBacktestWorkspaceDraft,
} from '../utils/backtestWorkspace';

const { Option } = Select;
const { RangePicker } = DatePicker;
const DATE_FORMAT = 'YYYY-MM-DD';

const StrategyForm = ({ strategies, onSubmit, loading }) => {
  const message = useSafeMessageApi();
  const [form] = Form.useForm();
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [strategyParams, setStrategyParams] = useState({});
  const [savedConfigs, setSavedConfigs] = useState([]);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [configName, setConfigName] = useState('');
  const watchedValues = Form.useWatch([], form);
  const selectedStrategyDetails = selectedStrategy ? getStrategyDetails(selectedStrategy.name) : null;
  const hasStrategyParameters = Boolean(selectedStrategy && selectedStrategy.parameters && Object.keys(selectedStrategy.parameters).length > 0);

  // Load saved configs from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('backtest_configs');
    if (saved) {
      try {
        setSavedConfigs(JSON.parse(saved));
      } catch (e) {
        console.error('Failed to parse saved configs:', e);
      }
    }
  }, []);

  useEffect(() => {
    if (!selectedStrategy && strategies.length > 0) {
      const defaultStrategy = strategies[0];
      setSelectedStrategy(defaultStrategy);
      if (defaultStrategy.parameters) {
        const defaults = {};
        Object.keys(defaultStrategy.parameters).forEach((key) => {
          defaults[key] = defaultStrategy.parameters[key].default;
        });
        setStrategyParams(defaults);
      }
    }
  }, [selectedStrategy, strategies]);

  useEffect(() => {
    const currentStrategy = form.getFieldValue('strategy');
    if (currentStrategy) {
      const matchedStrategy = strategies.find((item) => item.name === currentStrategy);
      if (matchedStrategy && matchedStrategy.name !== selectedStrategy?.name) {
        setSelectedStrategy(matchedStrategy);
        setStrategyParams((prev) => ({
          ...Object.fromEntries(
            Object.entries(matchedStrategy.parameters || {}).map(([key, config]) => [key, config.default])
          ),
          ...prev,
        }));
      }
      return;
    }

    if (selectedStrategy?.name) {
      form.setFieldValue('strategy', selectedStrategy.name);
    }
  }, [form, selectedStrategy, strategies]);

  useEffect(() => {
    const applyWorkspaceDraft = () => {
      const draft = loadBacktestWorkspaceDraft();
      if (!draft?.symbol || !draft?.strategy || !draft?.dateRange?.[0] || !draft?.dateRange?.[1]) {
        return;
      }

      const strategy = strategies.find((item) => item.name === draft.strategy);
      const resolvedStrategy = strategy || strategies[0] || null;
      if (resolvedStrategy) {
        setSelectedStrategy(resolvedStrategy);
        const defaultParams = Object.fromEntries(
          Object.entries(resolvedStrategy.parameters || {}).map(([key, config]) => [key, config.default])
        );
        setStrategyParams({
          ...defaultParams,
          ...(draft.parameters || {}),
        });
      }

      form.setFieldsValue({
        symbol: draft.symbol,
        strategy: draft.strategy,
        dateRange: [dayjs(draft.dateRange[0], DATE_FORMAT), dayjs(draft.dateRange[1], DATE_FORMAT)],
        initial_capital: draft.initial_capital ?? 10000,
        commission: draft.commission ?? 0.1,
        slippage: draft.slippage ?? 0.1,
      });
    };

    applyWorkspaceDraft();
    const handleWorkspaceDraftEvent = (event) => {
      if (event?.detail?.source === 'advanced_template') {
        applyWorkspaceDraft();
      }
    };
    window.addEventListener(BACKTEST_WORKSPACE_DRAFT_EVENT, handleWorkspaceDraftEvent);
    return () => window.removeEventListener(BACKTEST_WORKSPACE_DRAFT_EVENT, handleWorkspaceDraftEvent);
  }, [form, strategies]);

  useEffect(() => {
    if (!watchedValues?.symbol && !watchedValues?.strategy && !selectedStrategy) {
      return;
    }

    saveBacktestWorkspaceDraft({
      symbol: watchedValues?.symbol || 'AAPL',
      strategy: watchedValues?.strategy || selectedStrategy?.name || '',
      dateRange: watchedValues?.dateRange
        ? [
            watchedValues.dateRange[0]?.format(DATE_FORMAT),
            watchedValues.dateRange[1]?.format(DATE_FORMAT),
          ]
        : null,
      initial_capital: watchedValues?.initial_capital ?? 10000,
      commission: watchedValues?.commission ?? 0.1,
      slippage: watchedValues?.slippage ?? 0.1,
      parameters: strategyParams,
      updated_at: new Date().toISOString(),
    });
  }, [selectedStrategy, strategyParams, watchedValues]);

  // Save current config
  const saveConfig = () => {
    if (!configName.trim()) {
      message.error('请输入配置名称');
      return;
    }
    const values = form.getFieldsValue();
    const config = {
      name: configName,
      timestamp: new Date().toISOString(),
      data: {
        ...values,
        dateRange: values.dateRange ? [values.dateRange[0].format(), values.dateRange[1].format()] : null,
        strategyParams: strategyParams
      }
    };

    const updatedConfigs = [...savedConfigs.filter(c => c.name !== configName), config];
    setSavedConfigs(updatedConfigs);
    localStorage.setItem('backtest_configs', JSON.stringify(updatedConfigs));
    message.success(`配置 "${configName}" 已保存`);
    setSaveModalVisible(false);
    setConfigName('');
  };

  // Load a saved config
  const loadConfig = (config) => {
    const { data } = config;
    form.setFieldsValue({
      symbol: data.symbol,
      strategy: data.strategy,
      dateRange: data.dateRange ? [dayjs(data.dateRange[0]), dayjs(data.dateRange[1])] : null,
      initial_capital: data.initial_capital,
      commission: data.commission,
      slippage: data.slippage
    });
    if (data.strategyParams) {
      setStrategyParams(data.strategyParams);
    }
    if (data.strategy) {
      const strategy = strategies.find(s => s.name === data.strategy);
      setSelectedStrategy(strategy);
    }
    message.success(`已加载配置 "${config.name}"`);
  };

  // Delete a saved config
  const deleteConfig = (configName) => {
    const updatedConfigs = savedConfigs.filter(c => c.name !== configName);
    setSavedConfigs(updatedConfigs);
    localStorage.setItem('backtest_configs', JSON.stringify(updatedConfigs));
    message.success(`配置 "${configName}" 已删除`);
  };

  const handleStrategyChange = (strategyName) => {
    const strategy = strategies.find(s => s.name === strategyName);
    setSelectedStrategy(strategy);
    setStrategyParams({});

    // 重置参数表单
    const paramFields = {};
    if (strategy && strategy.parameters) {
      Object.keys(strategy.parameters).forEach(key => {
        paramFields[key] = strategy.parameters[key].default;
      });
    }
    setStrategyParams(paramFields);
  };

  const handleParamChange = (paramName, value) => {
    setStrategyParams(prev => ({
      ...prev,
      [paramName]: value
    }));
  };

  const handleSubmit = (values) => {
    const formData = {
      symbol: values.symbol,
      strategy: values.strategy,
      start_date: values.dateRange[0].format(DATE_FORMAT),
      end_date: values.dateRange[1].format(DATE_FORMAT),
      initial_capital: values.initial_capital,
      commission: values.commission / 100,
      slippage: values.slippage / 100,
      parameters: strategyParams
    };
    onSubmit(formData);
  };

  const renderParameterInputs = () => {
    if (!selectedStrategy || !selectedStrategy.parameters) return null;

    return Object.entries(selectedStrategy.parameters).map(([key, param]) => (
      <Form.Item
        key={key}
        className="strategy-form-grid__item"
        label={getStrategyParameterLabel(key, param.description)}
      >
        <InputNumber
          value={strategyParams[key] || param.default}
          onChange={(value) => handleParamChange(key, value)}
          min={param.min}
          max={param.max}
          step={param.step || 0.01}
          style={{ width: '100%' }}
        />
      </Form.Item>
    ));
  };

  const renderSectionHeader = (step, title, description, extra = null) => (
    <div className="workspace-section__header strategy-form-section-header">
      <div>
        <div className="strategy-form-section-header__eyebrow">步骤 {step}</div>
        <div className="workspace-section__title">{title}</div>
        <div className="workspace-section__description">{description}</div>
      </div>
      {extra}
    </div>
  );

  const summaryItems = [
    {
      label: '标的',
      value: watchedValues?.symbol || 'AAPL',
    },
    {
      label: '策略',
      value: selectedStrategy ? getStrategyName(selectedStrategy.name) : '待选择',
    },
    {
      label: '区间',
      value: watchedValues?.dateRange
        ? `${watchedValues.dateRange[0]?.format('YYYY-MM-DD')} ~ ${watchedValues.dateRange[1]?.format('YYYY-MM-DD')}`
        : '最近一年',
    },
    {
      label: '资金 / 成本',
      value: `${watchedValues?.initial_capital ? `$${Number(watchedValues.initial_capital).toLocaleString()}` : '$10,000'} · ${watchedValues?.commission ?? 0.1}% / ${watchedValues?.slippage ?? 0.1}%`,
    },
  ];
  const runBriefSymbol = watchedValues?.symbol || 'AAPL';
  const runBriefCapital = Number(watchedValues?.initial_capital ?? 10000).toLocaleString();
  const runBriefCommission = watchedValues?.commission ?? 0.1;
  const runBriefSlippage = watchedValues?.slippage ?? 0.1;
  const recentConfigs = savedConfigs.slice(-6).reverse();

  return (
    <Card
      className="workspace-panel workspace-panel--form"
      title={
        <div className="workspace-title">
          <div className="workspace-title__icon">
            <PlayCircleOutlined style={{ color: '#fff', fontSize: '16px' }} />
          </div>
          <div>
            <div className="workspace-title__text">策略回测配置</div>
            <div className="workspace-title__hint">把输入、参数和本地配置整理成一条清晰的实验流，再运行进入结果工作区。</div>
          </div>
        </div>
      }
      extra={
        <Tag color={savedConfigs.length > 0 ? 'blue' : 'default'}>
          {savedConfigs.length > 0 ? `${savedConfigs.length} 个本地配置` : '未保存配置'}
        </Tag>
      }
      style={{
        margin: '0 0 20px 0',
      }}
      styles={{ body: { padding: '24px' } }}
    >
      <div className="summary-strip summary-strip--compact strategy-form-summary">
        {summaryItems.map((item) => (
          <div key={item.label} className="summary-strip__item">
            <span className="summary-strip__label">{item.label}</span>
            <span className="summary-strip__value">{item.value}</span>
          </div>
        ))}
      </div>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        className="strategy-form"
        size="middle"
        initialValues={{
          symbol: 'AAPL',
          strategy: strategies[0]?.name,
          dateRange: [dayjs().subtract(1, 'year'), dayjs()],
          initial_capital: 10000,
          commission: 0.1,
          slippage: 0.1
        }}
      >
        <div className="strategy-form-layout">
          <div className="workspace-section strategy-form-section strategy-form-section--primary">
            {renderSectionHeader('01', '基础配置', '先确定标的、策略和回测区间，建立本次回测的实验上下文。')}
            <div className="strategy-form-grid strategy-form-grid--primary">
              <Form.Item
                className="strategy-form-grid__item"
                label="标的代码"
                name="symbol"
                rules={[{ required: true, message: '请输入股票代码' }]}
              >
                <Input placeholder="输入股票代码 (如: AAPL)" />
              </Form.Item>

              <Form.Item
                className="strategy-form-grid__item"
                label="交易策略"
                name="strategy"
                rules={[{ required: true, message: '请选择交易策略' }]}
              >
                <Select onChange={handleStrategyChange}>
                  {strategies.map(strategy => (
                    <Option key={strategy.name} value={strategy.name}>
                      {getStrategyName(strategy.name)}
                    </Option>
                  ))}
                </Select>
              </Form.Item>

              <Form.Item
                className="strategy-form-grid__item strategy-form-grid__item--span-2"
                label="回测区间"
                name="dateRange"
                rules={[{ required: true, message: '请选择时间范围' }]}
              >
                <RangePicker placeholder={['开始日期', '结束日期']} separator="至" style={{ width: '100%' }} />
              </Form.Item>
            </div>
          </div>

          <div className="workspace-section strategy-form-section">
            {renderSectionHeader('02', '交易假设', '把资金规模、手续费和滑点放在一起，快速校准执行环境。')}
            <div className="strategy-form-grid strategy-form-grid--trading">
              <Form.Item
                className="strategy-form-grid__item"
                label="初始资金"
                name="initial_capital"
                rules={[{ required: true, message: '请输入初始资金' }]}
              >
                <InputNumber
                  min={1000}
                  max={10000000}
                  step={1000}
                  style={{ width: '100%' }}
                  formatter={(value) => `$ ${value ?? ''}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(value) => (value ? value.replace(/\$\s?|(,*)/g, '') : '')}
                />
              </Form.Item>

              <Form.Item
                className="strategy-form-grid__item"
                label="手续费 (%)"
                name="commission"
                rules={[{ required: true, message: '请输入手续费' }]}
              >
                <InputNumber
                  min={0}
                  max={5}
                  step={0.01}
                  style={{ width: '100%' }}
                />
              </Form.Item>

              <Form.Item
                className="strategy-form-grid__item"
                label="滑点 (%)"
                name="slippage"
                rules={[{ required: true, message: '请输入滑点' }]}
              >
                <InputNumber
                  min={0}
                  max={5}
                  step={0.01}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </div>
          </div>

          {hasStrategyParameters ? (
            <div className="workspace-section strategy-form-section">
              {renderSectionHeader('03', '策略参数', '只展示当前策略的关键参数，集中调参，不再把输入项横向挤在一起。')}
              <div className="strategy-form-grid strategy-form-grid--params">
                {renderParameterInputs()}
              </div>
            </div>
          ) : null}

          <div className="strategy-form-support-stack">
            {selectedStrategyDetails ? (
              <div className="workspace-section strategy-form-support-card strategy-form-support-card--focus">
                <div className="workspace-section__header strategy-form-section-header">
                  <div>
                    <div className="strategy-form-section-header__eyebrow">策略画像</div>
                    <div className="workspace-section__title">{getStrategyName(selectedStrategy.name)}</div>
                    <div className="workspace-section__description">先确认信号逻辑和适用场景，再决定是否继续迭代。</div>
                  </div>
                  <Tag color="cyan">{selectedStrategyDetails.style}</Tag>
                </div>
                <div className="strategy-form-insight">
                  <div className="strategy-form-insight__block">
                    <span className="strategy-form-insight__label">逻辑简介</span>
                    <span className="strategy-form-insight__value">{selectedStrategyDetails.summary}</span>
                  </div>
                  <div className="strategy-form-insight__block">
                    <span className="strategy-form-insight__label">更适合的行情</span>
                    <span className="strategy-form-insight__value strategy-form-insight__value--muted">{selectedStrategyDetails.marketFit}</span>
                  </div>
                </div>
              </div>
            ) : null}

            <div className="workspace-section strategy-form-support-card">
              <div className="workspace-section__header strategy-form-section-header">
                <div>
                  <div className="strategy-form-section-header__eyebrow">本地配置库</div>
                  <div className="workspace-section__title">常用组合</div>
                  <div className="workspace-section__description">把稳定的实验输入存起来，后续可以直接加载复用。</div>
                </div>
                <Tag color={savedConfigs.length > 0 ? 'blue' : 'default'}>
                  {savedConfigs.length > 0 ? `${savedConfigs.length} 个已保存配置` : '暂未保存配置'}
                </Tag>
              </div>
              {savedConfigs.length > 0 ? (
                <div className="strategy-form-config-list">
                  {recentConfigs.map((config) => (
                    <Tag key={config.name} color="blue">
                      {config.name}
                    </Tag>
                  ))}
                </div>
              ) : (
                <div className="strategy-form-empty-note">
                  还没有本地配置。把常用参数和成本假设保存下来，下一次就不用重复录入。
                </div>
              )}
              <div className="workspace-section__hint">
                当前表单值会在点击“保存配置”后记录到浏览器本地存储。
              </div>
            </div>
          </div>

          <div className="strategy-form-footer">
            <div className="workspace-run-brief strategy-form-run-brief">
              <span className="workspace-run-brief__label">本次运行摘要</span>
              <span className="workspace-run-brief__value">
                {`${runBriefSymbol} · ${selectedStrategy ? getStrategyName(selectedStrategy.name) : '待选策略'} · ${runBriefCapital} 美元 · 手续费 ${runBriefCommission}% · 滑点 ${runBriefSlippage}%`}
              </span>
            </div>

            <Form.Item className="strategy-form-actions">
              <div className="strategy-form-actions__row">
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  size="large"
                  icon={<PlayCircleOutlined />}
                  aria-label="开始回测"
                  className="strategy-form-actions__run"
                >
                  开始回测
                </Button>

                <div className="strategy-form-actions__secondary">
                  <Button
                    icon={<SaveOutlined />}
                    aria-label="保存配置"
                    onClick={() => setSaveModalVisible(true)}
                  >
                    保存配置
                  </Button>

                  {savedConfigs.length > 0 && (
                    <Dropdown
                      menu={{
                        items: savedConfigs.map((config) => ({
                          key: config.name,
                          label: (
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', minWidth: 200 }}>
                              <span onClick={() => loadConfig(config)}>{config.name}</span>
                              <Popconfirm
                                title="确定删除此配置?"
                                onConfirm={(e) => {
                                  e.stopPropagation();
                                  deleteConfig(config.name);
                                }}
                                okText="删除"
                                cancelText="取消"
                              >
                                <DeleteOutlined
                                  style={{ color: 'var(--accent-danger)', marginLeft: 8 }}
                                  onClick={(e) => e.stopPropagation()}
                                />
                              </Popconfirm>
                            </div>
                          )
                        }))
                      }}
                    >
                      <Button icon={<FolderOpenOutlined />} aria-label="加载配置">
                        加载配置 <DownOutlined />
                      </Button>
                    </Dropdown>
                  )}
                </div>
              </div>
            </Form.Item>
          </div>
        </div>
      </Form>

      {/* Save Config Modal */}
      <Modal
        title="保存回测配置"
        open={saveModalVisible}
        onOk={saveConfig}
        onCancel={() => {
          setSaveModalVisible(false);
          setConfigName('');
        }}
        okText="保存"
        cancelText="取消"
      >
        <Input
          placeholder="输入配置名称 (如: AAPL均线策略)"
          value={configName}
          onChange={(e) => setConfigName(e.target.value)}
          onPressEnter={saveConfig}
        />
        <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 12 }}>
          配置将保存到本地浏览器，包括股票代码、策略、参数和交易设置。
        </div>
      </Modal>
    </Card>
  );
};

export default StrategyForm;
