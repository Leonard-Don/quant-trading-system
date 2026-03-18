import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Button,
  Card,
  Row,
  Col,
  Dropdown,
  Space,
  Modal,
  Tag,
  Popconfirm
} from 'antd';
import { PlayCircleOutlined, SaveOutlined, FolderOpenOutlined, DeleteOutlined, DownOutlined } from '@ant-design/icons';
import moment from 'moment';
import { getStrategyName, getStrategyParameterLabel } from '../constants/strategies';
import { useSafeMessageApi } from '../utils/messageApi';

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
  const watchedValues = Form.useWatch([], form) || {};

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
      dateRange: data.dateRange ? [moment(data.dateRange[0]), moment(data.dateRange[1])] : null,
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
      <Col span={8} key={key}>
        <Form.Item label={getStrategyParameterLabel(key, param.description)}>
          <InputNumber
            value={strategyParams[key] || param.default}
            onChange={(value) => handleParamChange(key, value)}
            min={param.min}
            max={param.max}
            step={param.step || 0.01}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </Col>
    ));
  };

  const summaryItems = [
    {
      label: '当前策略',
      value: selectedStrategy ? getStrategyName(selectedStrategy.name) : '待选择',
    },
    {
      label: '回测区间',
      value: watchedValues.dateRange
        ? `${watchedValues.dateRange[0]?.format('YYYY-MM-DD')} ~ ${watchedValues.dateRange[1]?.format('YYYY-MM-DD')}`
        : '最近一年',
    },
    {
      label: '初始资金',
      value: watchedValues.initial_capital ? `$${Number(watchedValues.initial_capital).toLocaleString()}` : '$10,000',
    },
    {
      label: '成本设置',
      value: `${watchedValues.commission ?? 0.1}% / ${watchedValues.slippage ?? 0.1}%`,
    },
  ];

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
            <div className="workspace-title__hint">先配置标的与策略，再运行并进入结果工作区。</div>
          </div>
        </div>
      }
      extra={
        <Space wrap>
          {selectedStrategy ? <Tag color="geekblue">{getStrategyName(selectedStrategy.name)}</Tag> : null}
          <Tag color="blue">{savedConfigs.length} 个已保存配置</Tag>
        </Space>
      }
      style={{
        margin: '0 0 20px 0',
      }}
      styles={{ body: { padding: '24px' } }}
    >
      <div className="summary-strip summary-strip--compact">
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
        size="middle"
        initialValues={{
          symbol: 'AAPL',
          strategy: strategies[0]?.name,
          dateRange: [moment().subtract(1, 'year'), moment()],
          initial_capital: 10000,
          commission: 0.1,
          slippage: 0.1
        }}
      >
        <Row gutter={[20, 20]}>
          <Col xs={24} xl={15}>
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">基础配置</div>
                  <div className="workspace-section__description">选择标的、策略和回测区间，建立本次实验的基本上下文。</div>
                </div>
              </div>
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item
                    label="股票代码"
                    name="symbol"
                    rules={[{ required: true, message: '请输入股票代码' }]}
                  >
                    <Input placeholder="输入股票代码 (如: AAPL)" />
                  </Form.Item>
                </Col>

                <Col xs={24} md={8}>
                  <Form.Item
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
                </Col>

                <Col xs={24} md={8}>
                  <Form.Item
                    label="回测时间范围"
                    name="dateRange"
                    rules={[{ required: true, message: '请选择时间范围' }]}
                  >
                    <RangePicker placeholder={['开始日期', '结束日期']} separator="至" style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </div>

            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">交易设置</div>
                  <div className="workspace-section__description">配置资金规模、手续费和滑点，模拟更接近真实执行环境的回测结果。</div>
                </div>
              </div>
              <Row gutter={16}>
                <Col xs={24} md={8}>
                  <Form.Item
                    label="初始资金"
                    name="initial_capital"
                    rules={[{ required: true, message: '请输入初始资金' }]}
                  >
                    <InputNumber
                      min={1000}
                      max={10000000}
                      step={1000}
                      style={{ width: '100%' }}
                      formatter={value => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={value => value.replace(/\$\s?|(,*)/g, '')}
                    />
                  </Form.Item>
                </Col>

                <Col xs={24} md={8}>
                  <Form.Item
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
                </Col>

                <Col xs={24} md={8}>
                  <Form.Item
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
                </Col>
              </Row>
            </div>
          </Col>

          <Col xs={24} xl={9}>
            {selectedStrategy && selectedStrategy.parameters &&
              Object.keys(selectedStrategy.parameters).length > 0 && (
                <div className="workspace-section">
                  <div className="workspace-section__header">
                    <div>
                      <div className="workspace-section__title">策略参数</div>
                      <div className="workspace-section__description">当前策略的关键参数会在这里动态展开，便于快速迭代假设。</div>
                    </div>
                  </div>
                  <Row gutter={16}>
                    {renderParameterInputs()}
                  </Row>
                </div>
              )}

            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">配置库</div>
                  <div className="workspace-section__description">把常用实验组合存成浏览器本地配置，后续可直接复用。</div>
                </div>
              </div>
              <Space wrap>
                {savedConfigs.length > 0 ? savedConfigs.slice(0, 6).map((config) => (
                  <Tag key={config.name} color="blue">
                    {config.name}
                  </Tag>
                )) : <Tag color="default">暂无已保存配置</Tag>}
              </Space>
              <div className="workspace-section__hint">
                当前表单值会在点击“保存配置”后记录到浏览器本地存储。
              </div>
            </div>
          </Col>
        </Row>

        <div className="workspace-run-brief">
          <span className="workspace-run-brief__label">本次运行摘要</span>
          <span className="workspace-run-brief__value">
            {`${watchedValues.symbol || 'AAPL'} · ${selectedStrategy ? getStrategyName(selectedStrategy.name) : '待选策略'} · ${(watchedValues.initial_capital || 10000).toLocaleString()} 美元 · 手续费 ${watchedValues.commission ?? 0.1}% · 滑点 ${watchedValues.slippage ?? 0.1}%`}
          </span>
        </div>

        <Form.Item>
          <Space wrap>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              size="large"
              icon={<PlayCircleOutlined />}
              style={{ width: '160px' }}
            >
              开始回测
            </Button>

            <Button
              icon={<SaveOutlined />}
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
                <Button icon={<FolderOpenOutlined />}>
                  加载配置 <DownOutlined />
                </Button>
              </Dropdown>
            )}

            {savedConfigs.length > 0 && (
              <Tag color="blue">{savedConfigs.length} 个已保存配置</Tag>
            )}
          </Space>
        </Form.Item>
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
