import React from 'react';
import { Button, Card, Empty, Space, Tag, Typography } from 'antd';
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

import { getSignalLabel } from './viewModels';

const { Text } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

function RiskPremiumRadar({ data = [], macroScore = 0, confidence = 0, macroSignal = 0, primaryAction = null, onNavigate }) {
  return (
    <Card
      title="Risk Premium Radar"
      variant="borderless"
      extra={
        <Space>
          <Tag color={signalColor[macroSignal]}>{getSignalLabel(macroSignal)}</Tag>
          <Tag color="blue">conf {Number(confidence || 0).toFixed(2)}</Tag>
        </Space>
      }
      styles={{ body: { minHeight: 360 } }}
    >
      {data.length ? (
        <>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <RadarChart data={data}>
                <PolarGrid stroke="rgba(255,255,255,0.18)" />
                <PolarAngleAxis dataKey="factor" tick={{ fill: '#d7e3ee', fontSize: 12 }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                <Radar
                  name="Intensity"
                  dataKey="intensity"
                  stroke="#36cfc9"
                  fill="#36cfc9"
                  fillOpacity={0.36}
                />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <Text type="secondary">综合错价分数 {Number(macroScore || 0).toFixed(4)}</Text>
            <Space>
              <Text type="secondary">因子数量 {data.length}</Text>
              {primaryAction ? (
                <Button size="small" type="primary" onClick={() => onNavigate?.(primaryAction)}>
                  {primaryAction.label}
                </Button>
              ) : null}
            </Space>
          </div>
        </>
      ) : (
        <Empty description="暂无雷达数据" />
      )}
    </Card>
  );
}

export default RiskPremiumRadar;
