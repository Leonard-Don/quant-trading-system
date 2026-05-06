import React from 'react';
import { Alert, Button, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

function ResearchSummaryBanner({
  title,
  headline,
  thesis,
  context = [],
  warnings = [],
  nextActions = [],
  onAction,
}) {
  return (
    <Alert
      type={warnings.length ? 'warning' : 'info'}
      showIcon
      message={headline || title}
      description={(
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          {thesis ? (
            <Paragraph style={{ marginBottom: 0 }}>
              {thesis}
            </Paragraph>
          ) : null}

          {context.length ? (
            <Space wrap>
              {context.map((item) => (
                <Tag key={item} color="blue">
                  {item}
                </Tag>
              ))}
            </Space>
          ) : null}

          {warnings.length ? (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {warnings.slice(0, 3).map((warning) => (
                <Text key={warning} style={{ color: '#ad6800' }}>
                  {warning}
                </Text>
              ))}
            </Space>
          ) : null}

          {nextActions.length ? (
            <Space wrap>
              {nextActions.map((action) => (
                <Button
                  key={`${action.target}-${action.symbol || action.template || action.note || action.label}`}
                  size="small"
                  type={action.target === 'godsEye' ? 'default' : 'primary'}
                  onClick={() => onAction?.(action)}
                >
                  {action.label}
                </Button>
              ))}
            </Space>
          ) : null}
        </Space>
      )}
    />
  );
}

export default ResearchSummaryBanner;
