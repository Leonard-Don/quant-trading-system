import React from 'react';
import { Spin, Card } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

const LoadingSpinner = ({ message = "正在处理...", size = "large" }) => {
  const antIcon = <LoadingOutlined style={{ fontSize: 24 }} spin />;

  return (
    <Card style={{ textAlign: 'center', margin: '20px 0' }}>
      <Spin indicator={antIcon} size={size} />
      <div style={{ marginTop: '16px', fontSize: '16px', color: '#666' }}>
        {message}
      </div>
    </Card>
  );
};

export default LoadingSpinner;
