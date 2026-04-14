import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Empty, List, Select, Space, Tag, Typography } from 'antd';

import { buildSnapshotComparison } from './snapshotCompare';

const { Paragraph, Text } = Typography;

function SnapshotComparePanel({ task }) {
  const history = useMemo(() => task?.snapshot_history || [], [task]);
  const options = useMemo(
    () =>
      history.map((snapshot, index) => ({
        label: snapshot.saved_at ? new Date(snapshot.saved_at).toLocaleString() : `版本 ${index + 1}`,
        value: index,
      })),
    [history]
  );
  const [baseIndex, setBaseIndex] = useState(1);
  const [targetIndex, setTargetIndex] = useState(0);

  useEffect(() => {
    setBaseIndex(history.length > 1 ? 1 : 0);
    setTargetIndex(0);
  }, [history]);

  const baseSnapshot = history[baseIndex];
  const targetSnapshot = history[targetIndex];
  const comparison = useMemo(
    () => buildSnapshotComparison(task?.type, baseSnapshot, targetSnapshot),
    [baseSnapshot, targetSnapshot, task?.type]
  );

  if (history.length < 2) {
    return (
      <Card data-testid="workbench-snapshot-compare" size="small" title="版本对比" variant="borderless">
        <Empty description="至少需要两个快照版本才能开始对比" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  return (
    <Card
      data-testid="workbench-snapshot-compare"
      size="small"
      title={(
        <Space direction="vertical" size={0}>
          <span>版本对比</span>
          {comparison?.lead ? (
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {comparison.lead}
            </Text>
          ) : null}
        </Space>
      )}
      variant="borderless"
      extra={(
        <Space wrap>
          <Select
            data-testid="workbench-snapshot-compare-base"
            size="small"
            value={baseIndex}
            options={options}
            onChange={setBaseIndex}
            style={{ width: 170 }}
          />
          <Text type="secondary">vs</Text>
          <Select
            data-testid="workbench-snapshot-compare-target"
            size="small"
            value={targetIndex}
            options={options}
            onChange={setTargetIndex}
            style={{ width: 170 }}
          />
        </Space>
      )}
    >
      {comparison ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph style={{ marginBottom: 0 }}>
            对比 {options[baseIndex]?.label || '基准版本'} 与 {options[targetIndex]?.label || '目标版本'} 的关键研究结论变化。
          </Paragraph>
          {comparison.lead ? (
            <Alert
              type={comparison.summary?.[0]?.includes('复核型结果') ? 'warning' : 'info'}
              showIcon
              message="版本变化解读"
              description={comparison.lead}
            />
          ) : null}
          <Space wrap>
            {(comparison.summary || []).filter(Boolean).map((item) => (
              <Tag key={item}>{item}</Tag>
            ))}
          </Space>
          <List
            size="small"
            dataSource={comparison.rows || []}
            renderItem={(row) => (
              <List.Item>
                <List.Item.Meta
                  title={<Text strong>{row.label}</Text>}
                  description={(
                    <Space wrap>
                      <Text type="secondary">基准 {row.left}</Text>
                      <Text type="secondary">目标 {row.right}</Text>
                      {row.delta ? <Tag color="blue">{row.delta}</Tag> : null}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        </Space>
      ) : (
        <Empty description="当前快照结构不足以生成对比" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Card>
  );
}

export default SnapshotComparePanel;
