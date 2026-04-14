import React from 'react';
import { Card, Typography } from 'antd';

const { Text } = Typography;

const GodEyeTacticalNotes = () => (
  <Card
    title="战术说明"
    variant="borderless"
    styles={{ body: { display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' } }}
  >
    <Text type="secondary">Supply Chain Heatmap 看物理世界堵点和人才结构压力。</Text>
    <Text type="secondary">Risk Radar 和 Macro Factor Panel 看错价强度与因子驱动。</Text>
    <Text type="secondary">Policy Timeline + Alert Hunter 用来决定是去 pricing 还是 cross-market。</Text>
  </Card>
);

export default GodEyeTacticalNotes;
