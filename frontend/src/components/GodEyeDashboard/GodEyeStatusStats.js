import React from 'react';
import {
  Card,
  Col,
  Row,
  Statistic,
  Typography,
} from 'antd';
import {
  ClockCircleOutlined,
  GlobalOutlined,
  RadarChartOutlined,
  SyncOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

const GodEyeStatusStats = ({
  macroScore,
  providerCount,
  providerHealth,
  refreshing,
  schedulerStatus,
  snapshotTimestamp,
  staleness,
}) => (
  <Row gutter={[16, 16]}>
    <Col xs={24} md={6}>
      <Card variant="borderless">
        <Statistic
          title="最近刷新"
          value={snapshotTimestamp || '未刷新'}
          valueStyle={{ fontSize: 16 }}
          prefix={<ClockCircleOutlined />}
        />
      </Card>
    </Col>
    <Col xs={24} md={6}>
      <Card variant="borderless">
        <Statistic
          title="数据新鲜度"
          value={staleness?.label || 'unknown'}
          prefix={<SyncOutlined spin={refreshing} />}
        />
        <Text type="secondary">最大快照年龄 {staleness?.max_snapshot_age_seconds ?? '-'} 秒</Text>
      </Card>
    </Col>
    <Col xs={24} md={6}>
      <Card variant="borderless">
        <Statistic
          title="健康提供器"
          value={providerHealth?.healthy_providers ?? 0}
          suffix={`/ ${providerCount}`}
          prefix={<GlobalOutlined />}
        />
        <Text type="secondary">
          degraded {providerHealth?.degraded_providers ?? 0} / error {providerHealth?.error_providers ?? 0}
        </Text>
      </Card>
    </Col>
    <Col xs={24} md={6}>
      <Card variant="borderless">
        <Statistic
          title="宏观错价分数"
          value={macroScore ?? 0}
          precision={4}
          prefix={<RadarChartOutlined />}
        />
        <Text type="secondary">scheduler jobs {schedulerStatus?.jobs?.length ?? 0}</Text>
      </Card>
    </Col>
  </Row>
);

export default GodEyeStatusStats;
