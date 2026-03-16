import React, { useMemo } from 'react';
import { Card, Typography, Tooltip as AntTooltip, Empty } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

/**
 * 相关性热力图组件
 * 用于展示股票/策略间的相关性矩阵
 */
const HeatmapChart = ({ 
  data, 
  title = "相关性热力图",
  showValues = true,
  colorScheme = 'diverging' // 'diverging' | 'sequential'
}) => {
  // 计算颜色 - 使用diverging色阶 (-1到1范围)
  const getColor = (value) => {
    if (value === null || value === undefined || isNaN(value)) {
      return '#f0f0f0';
    }
    
    if (colorScheme === 'diverging') {
      // 红蓝色阶: -1 = 红色, 0 = 白色, 1 = 蓝色
      if (value < 0) {
        const intensity = Math.abs(value);
        return `rgba(239, 68, 68, ${0.2 + intensity * 0.8})`;
      } else {
        const intensity = value;
        return `rgba(59, 130, 246, ${0.2 + intensity * 0.8})`;
      }
    } else {
      // 单色色阶: 0 = 浅色, 1 = 深色
      const normalizedValue = Math.max(0, Math.min(1, value));
      return `rgba(99, 102, 241, ${0.1 + normalizedValue * 0.9})`;
    }
  };

  // 处理数据
  const { matrix, labels } = useMemo(() => {
    if (!data || !data.matrix || !data.labels) {
      return { matrix: [], labels: [] };
    }
    return {
      matrix: data.matrix,
      labels: data.labels
    };
  }, [data]);

  // 如果没有数据
  if (labels.length === 0) {
    return (
      <Card title={title} size="small">
        <Empty description="暂无相关性数据" />
      </Card>
    );
  }

  const cellSize = Math.min(60, 400 / labels.length);
  const fontSize = Math.max(10, Math.min(12, cellSize / 5));

  return (
    <Card 
      title={
        <span>
          {title}
          <AntTooltip title="相关系数范围: -1 (负相关) 到 +1 (正相关)">
            <InfoCircleOutlined style={{ marginLeft: 8, color: '#999' }} />
          </AntTooltip>
        </span>
      }
      size="small"
      style={{ height: '100%' }}
    >
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'center',
        overflow: 'auto',
        maxHeight: 450
      }}>
        {/* 顶部标签 */}
        <div style={{ 
          display: 'flex', 
          marginLeft: cellSize + 10,
          marginBottom: 4
        }}>
          {labels.map((label, i) => (
            <div
              key={`top-${i}`}
              style={{
                width: cellSize,
                height: 40,
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
                paddingBottom: 4
              }}
            >
              <Text 
                style={{ 
                  fontSize: fontSize - 1, 
                  writingMode: 'vertical-rl',
                  transform: 'rotate(180deg)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxHeight: 40
                }}
              >
                {label.length > 6 ? label.substring(0, 5) + '..' : label}
              </Text>
            </div>
          ))}
        </div>

        {/* 热力图主体 */}
        {matrix.map((row, i) => (
          <div key={`row-${i}`} style={{ display: 'flex', alignItems: 'center' }}>
            {/* 左侧标签 */}
            <div style={{ 
              width: cellSize + 10,
              textAlign: 'right',
              paddingRight: 8
            }}>
              <Text style={{ fontSize: fontSize - 1 }}>
                {labels[i].length > 8 ? labels[i].substring(0, 7) + '..' : labels[i]}
              </Text>
            </div>
            
            {/* 单元格 */}
            {row.map((value, j) => (
              <AntTooltip 
                key={`cell-${i}-${j}`}
                title={`${labels[i]} vs ${labels[j]}: ${value?.toFixed(3) || 'N/A'}`}
              >
                <div
                  style={{
                    width: cellSize,
                    height: cellSize,
                    backgroundColor: getColor(value),
                    border: '1px solid #fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'transform 0.1s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'scale(1.05)';
                    e.currentTarget.style.zIndex = '10';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'scale(1)';
                    e.currentTarget.style.zIndex = '1';
                  }}
                >
                  {showValues && cellSize >= 35 && (
                    <Text style={{ 
                      fontSize: fontSize - 2,
                      color: Math.abs(value) > 0.5 ? '#fff' : '#333'
                    }}>
                      {value?.toFixed(2) || '-'}
                    </Text>
                  )}
                </div>
              </AntTooltip>
            ))}
          </div>
        ))}

        {/* 图例 */}
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          marginTop: 16,
          gap: 8
        }}>
          {colorScheme === 'diverging' ? (
            <>
              <Text style={{ fontSize: 11 }}>-1</Text>
              <div style={{ 
                width: 150, 
                height: 12, 
                background: 'linear-gradient(to right, rgba(239,68,68,1), rgba(239,68,68,0.2), #fff, rgba(59,130,246,0.2), rgba(59,130,246,1))',
                borderRadius: 2
              }} />
              <Text style={{ fontSize: 11 }}>+1</Text>
            </>
          ) : (
            <>
              <Text style={{ fontSize: 11 }}>低</Text>
              <div style={{ 
                width: 100, 
                height: 12, 
                background: 'linear-gradient(to right, rgba(99,102,241,0.1), rgba(99,102,241,1))',
                borderRadius: 2
              }} />
              <Text style={{ fontSize: 11 }}>高</Text>
            </>
          )}
        </div>
      </div>
    </Card>
  );
};

export default HeatmapChart;
