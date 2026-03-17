import React from 'react';
import { Button, Card, Col, Empty, Row, Statistic, Table, Tag, Typography } from 'antd';

const { Text } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

function MacroFactorPanel({ model = {}, onNavigate }) {
  const topFactors = model.topFactors || [];
  const factors = model.factors || [];
  const providerHealth = model.providerHealth || {};
  const staleness = model.staleness || {};

  return (
    <Card
      title="Macro Factor Panel"
      bordered={false}
      extra={
        <Tag color={staleness.is_stale ? 'orange' : 'green'}>
          {staleness.label || 'fresh'}
        </Tag>
      }
      bodyStyle={{ display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      {factors.length ? (
        <>
          <Row gutter={[12, 12]}>
            {topFactors.map((factor) => (
              <Col xs={24} md={8} key={factor.name}>
                <div
                  style={{
                    borderRadius: 14,
                    padding: 14,
                    background: 'rgba(9, 25, 37, 0.78)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
                    <Text strong style={{ color: '#f5f8fc' }}>{factor.displayName}</Text>
                    <Tag color={signalColor[factor.signal]}>{factor.signal}</Tag>
                  </div>
                  <Statistic
                    title="Z-Score"
                    value={Number(factor.z_score || 0)}
                    precision={3}
                    valueStyle={{ color: '#f5f8fc', fontSize: 24 }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">confidence {Number(factor.confidence || 0).toFixed(2)}</Text>
                  </div>
                  {factor.action ? (
                    <Button size="small" style={{ marginTop: 12 }} onClick={() => onNavigate?.(factor.action)}>
                      {factor.action.label}
                    </Button>
                  ) : null}
                </div>
              </Col>
            ))}
          </Row>

          <Table
            size="small"
            pagination={false}
            dataSource={factors.map((factor) => ({ key: factor.name, ...factor }))}
            locale={{ emptyText: <Empty description="暂无因子" /> }}
            columns={[
              {
                title: '因子',
                dataIndex: 'displayName',
                key: 'displayName',
                render: (value) => <Text strong>{value}</Text>,
              },
              {
                title: '值',
                dataIndex: 'value',
                key: 'value',
                render: (value) => Number(value || 0).toFixed(4),
              },
              {
                title: 'Z',
                dataIndex: 'z_score',
                key: 'z_score',
                render: (value) => Number(value || 0).toFixed(3),
              },
              {
                title: '置信度',
                dataIndex: 'confidence',
                key: 'confidence',
                render: (value) => Number(value || 0).toFixed(2),
              },
              {
                title: '信号',
                dataIndex: 'signal',
                key: 'signal',
                render: (value) => <Tag color={signalColor[value]}>{value}</Tag>,
              },
            ]}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <Text type="secondary">healthy {providerHealth.healthy_providers || 0}</Text>
            <Text type="secondary">degraded {providerHealth.degraded_providers || 0}</Text>
            <Text type="secondary">error {providerHealth.error_providers || 0}</Text>
          </div>
        </>
      ) : (
        <Empty description="暂无宏观因子" />
      )}
    </Card>
  );
}

export default MacroFactorPanel;
