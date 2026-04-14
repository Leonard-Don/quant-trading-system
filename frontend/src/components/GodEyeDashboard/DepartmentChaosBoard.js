import React from 'react';
import { Button, Card, Empty, List, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

export default function DepartmentChaosBoard({ overview = {}, onNavigate }) {
  const summary = overview?.department_chaos_summary || {};
  const departments = summary?.top_departments || [];

  return (
    <Card
      title="Department Chaos Board"
      extra={summary?.label ? <Tag color={summary.label === 'chaotic' ? 'red' : summary.label === 'watch' ? 'gold' : 'green'}>{summary.label}</Tag> : null}
      styles={{ body: { minHeight: 280 } }}
    >
      {summary?.summary ? (
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          {summary.summary}
        </Paragraph>
      ) : null}
      {!departments.length ? (
        <Empty description="暂无部门执行混乱数据" />
      ) : (
        <List
          dataSource={departments.slice(0, 5)}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key="cross-market"
                  size="small"
                  type="link"
                  onClick={() => onNavigate?.({
                    target: 'cross-market',
                    template: 'utilities_vs_growth',
                    source: 'godeye_department_chaos',
                    note: item?.reason || summary?.summary || '来自 GodEye Department Chaos Board',
                  })}
                >
                  政策模板
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={(
                  <Space wrap size={6}>
                    <Text strong>{item?.department_label || item?.department || '-'}</Text>
                    <Tag color={item?.label === 'chaotic' ? 'red' : item?.label === 'watch' ? 'gold' : 'green'}>
                      {item?.label || 'stable'}
                    </Tag>
                    <Tag>{`混乱 ${Number(item?.chaos_score || 0).toFixed(2)}`}</Tag>
                    <Tag>{`反转 ${Number(item?.policy_reversal_count || 0)}`}</Tag>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Text type="secondary">
                      正文覆盖 {Number(item?.full_text_ratio || 0).toFixed(2)}
                      {' · '}
                      滞后 {Number(item?.lag_days || 0)} 天
                      {' · '}
                      执行状态 {item?.execution_status || 'unknown'}
                    </Text>
                    {item?.reason ? <Text>{item.reason}</Text> : null}
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
