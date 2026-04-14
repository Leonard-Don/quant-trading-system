import React from 'react';
import { Card, Col, Empty, List, Row, Tag, Typography } from 'antd';

const { Text } = Typography;

const toneStyle = {
  hot: 'linear-gradient(135deg, rgba(207, 19, 34, 0.9), rgba(250, 140, 22, 0.7))',
  cold: 'linear-gradient(135deg, rgba(8, 93, 153, 0.85), rgba(19, 194, 194, 0.65))',
  neutral: 'linear-gradient(135deg, rgba(37, 46, 58, 0.95), rgba(69, 85, 96, 0.82))',
};

function SupplyChainHeatmap({ cells = [], anomalies = [] }) {
  return (
    <Card
      title="Supply Chain Heatmap"
      variant="borderless"
      extra={<Tag color="blue">{cells.length} heat zones</Tag>}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 18 } }}
    >
      {cells.length ? (
        <Row gutter={[12, 12]}>
          {cells.map((cell) => (
            <Col xs={24} sm={12} xl={8} key={cell.key}>
              <div
                style={{
                  minHeight: 132,
                  padding: 16,
                  borderRadius: 16,
                  background: toneStyle[cell.tone] || toneStyle.neutral,
                  color: '#f6fbff',
                  boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.06)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 12 }}>
                  <Tag color={cell.group === 'Supply Chain' ? 'gold' : 'cyan'}>{cell.group}</Tag>
                  <Text style={{ color: 'rgba(246, 251, 255, 0.75)' }}>{cell.count} 条</Text>
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>{cell.label}</div>
                <div style={{ fontSize: 30, fontWeight: 700, lineHeight: 1, marginBottom: 12 }}>
                  {cell.score.toFixed(2)}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                  <Tag color={cell.momentum === 'strengthening' ? 'red' : cell.momentum === 'weakening' ? 'blue' : 'default'}>
                    {cell.momentum === 'strengthening' ? '趋势增强' : cell.momentum === 'weakening' ? '趋势走弱' : '趋势稳定'}
                  </Tag>
                  <Tag color="default">
                    Δ{cell.trendDelta >= 0 ? '+' : ''}{cell.trendDelta.toFixed(2)}
                  </Tag>
                </div>
                <Text style={{ color: 'rgba(246, 251, 255, 0.78)' }}>{cell.summary}</Text>
              </div>
            </Col>
          ))}
        </Row>
      ) : (
        <Empty description="暂无可用热区" />
      )}

      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>最近异常点</div>
        <List
          size="small"
          dataSource={anomalies}
          locale={{ emptyText: '暂无显著异常' }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={<Text strong>{item.title}</Text>}
                description={item.description}
              />
              <Tag color={item.type === 'alert' || item.type === 'hot' ? 'red' : item.type === 'cold' ? 'blue' : 'default'}>
                {item.type}
              </Tag>
            </List.Item>
          )}
        />
      </div>
    </Card>
  );
}

export default SupplyChainHeatmap;
