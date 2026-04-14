import React from 'react';
import {
  Button,
  Card,
  Col,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

import { getSignalLabel } from './viewModels';

const { Paragraph, Title } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

const GodEyeHeader = ({
  handleManualRefresh,
  macroSignal,
  navigateTo,
  refreshing,
}) => (
  <Card
    variant="borderless"
    style={{
      background:
        'radial-gradient(circle at top left, rgba(26, 66, 98, 0.96), rgba(10, 22, 33, 0.98) 55%, rgba(38, 54, 34, 0.92))',
      color: '#f4f7fb',
      overflow: 'hidden',
      boxShadow: '0 22px 48px rgba(0, 0, 0, 0.25)',
    }}
  >
    <Row gutter={[24, 24]} align="middle">
      <Col xs={24} lg={15}>
        <Space direction="vertical" size={10}>
          <Tag color="cyan" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            Macro Mispricing Command Center
          </Tag>
          <Title level={2} style={{ margin: 0, color: '#f4f7fb' }}>
            GodEye V2 作战大屏
          </Title>
          <Paragraph style={{ margin: 0, color: 'rgba(244, 247, 251, 0.82)', maxWidth: 760 }}>
            这一版把单页总览升级成六面板战情沙盘。你可以同时看到供应链热区、风险雷达、政策时间轴、
            宏观因子、猎杀信号，以及跨市场模板入口。
          </Paragraph>
          <Space wrap>
            <Button type="primary" onClick={() => navigateTo('cross-market')}>
              打开跨市场剧本
            </Button>
            <Button onClick={() => navigateTo('pricing')}>
              打开定价剧本
            </Button>
          </Space>
        </Space>
      </Col>
      <Col xs={24} lg={9} style={{ textAlign: 'right' }}>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={handleManualRefresh}>
            强制刷新
          </Button>
          <Tag color={signalColor[macroSignal ?? 0]} style={{ fontSize: 14, padding: '6px 10px' }}>
            {getSignalLabel(macroSignal ?? 0)}
          </Tag>
        </Space>
      </Col>
    </Row>
  </Card>
);

export default GodEyeHeader;
