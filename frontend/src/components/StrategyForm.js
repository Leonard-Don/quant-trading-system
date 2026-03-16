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
  Divider,
  Dropdown,
  Space,
  Modal,
  message,
  Tag,
  Popconfirm
} from 'antd';
import { PlayCircleOutlined, SaveOutlined, FolderOpenOutlined, DeleteOutlined, DownOutlined } from '@ant-design/icons';
import moment from 'moment';
import { getStrategyName } from '../constants/strategies';

const { Option } = Select;
const { RangePicker } = DatePicker;

const StrategyForm = ({ strategies, onSubmit, loading }) => {
  const [form] = Form.useForm();
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [strategyParams, setStrategyParams] = useState({});
  const [savedConfigs, setSavedConfigs] = useState([]);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [configName, setConfigName] = useState('');

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
      start_date: values.dateRange[0].toISOString(),
      end_date: values.dateRange[1].toISOString(),
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
        <Form.Item label={param.description || key}>
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

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: '8px',
            background: 'var(--gradient-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: 'var(--shadow-md)'
          }}>
            <PlayCircleOutlined style={{ color: '#fff', fontSize: '16px' }} />
          </div>
          <span style={{ fontSize: '16px', fontWeight: 600 }}>策略回测配置</span>
        </div>
      }
      style={{
        margin: '0 0 20px 0',
      }}
      styles={{ body: { padding: '24px' } }}
    >
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
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item
              label="股票代码"
              name="symbol"
              rules={[{ required: true, message: '请输入股票代码' }]}
            >
              <Input placeholder="输入股票代码 (如: AAPL)" />
            </Form.Item>
          </Col>

          <Col span={8}>
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

          <Col span={8}>
            <Form.Item
              label="回测时间范围"
              name="dateRange"
              rules={[{ required: true, message: '请选择时间范围' }]}
            >
              <RangePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        {selectedStrategy && selectedStrategy.parameters &&
          Object.keys(selectedStrategy.parameters).length > 0 && (
            <>
              <Divider>策略参数</Divider>
              <Row gutter={16}>
                {renderParameterInputs()}
              </Row>
            </>
          )}

        <Divider>交易设置</Divider>
        <Row gutter={16}>
          <Col span={8}>
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

          <Col span={8}>
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

          <Col span={8}>
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

        <Form.Item>
          <Space>
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
