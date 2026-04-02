import React from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Space,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import {
  ClockCircleOutlined,
  CommentOutlined,
  HistoryOutlined,
  SaveOutlined,
} from '@ant-design/icons';

import SelectedTaskRefreshPanel from './SelectedTaskRefreshPanel';
import { SnapshotHistoryList, SnapshotSummary } from './SnapshotSummary';
import { formatContextValue } from './workbenchUtils';

const { Text } = Typography;
const { TextArea } = Input;

export const WorkbenchTaskSummarySection = ({
  latestSnapshotComparison,
  selectedTask,
  selectedTaskRefreshSignal,
}) => (
  <>
    {latestSnapshotComparison?.lead ? (
      <Alert
        type={latestSnapshotComparison.summary?.[0]?.includes('复核型结果') ? 'warning' : 'info'}
        showIcon
        message="最近两版变化摘要"
        description={latestSnapshotComparison.lead}
      />
    ) : null}

    <Row gutter={[12, 12]}>
      <Col xs={24} md={12}>
        <Card size="small" bordered={false}>
          <Text type="secondary">类型</Text>
          <div><Text strong>{selectedTask.type}</Text></div>
        </Card>
      </Col>
      <Col xs={24} md={12}>
        <Card size="small" bordered={false}>
          <Text type="secondary">来源</Text>
          <div><Text strong>{selectedTask.sourceLabel}</Text></div>
        </Card>
      </Col>
      <Col xs={24} md={12}>
        <Card size="small" bordered={false}>
          <Text type="secondary">Symbol</Text>
          <div><Text strong>{selectedTask.symbol || '-'}</Text></div>
        </Card>
      </Col>
      <Col xs={24} md={12}>
        <Card size="small" bordered={false}>
          <Text type="secondary">Template</Text>
          <div><Text strong>{selectedTask.template || '-'}</Text></div>
        </Card>
      </Col>
    </Row>

    <Card size="small" title="任务上下文" bordered={false}>
      <Space wrap>
        {Object.entries(selectedTask.context || {}).map(([key, value]) => (
          <Tag key={key}>
            {key}: {formatContextValue(value)}
          </Tag>
        ))}
      </Space>
    </Card>

    {selectedTask.type === 'cross_market' ? (
      <SelectedTaskRefreshPanel selectedTaskRefreshSignal={selectedTaskRefreshSignal} />
    ) : null}

    <Card size="small" title="当前快照" bordered={false}>
      <SnapshotSummary task={selectedTask} />
    </Card>

    <Card size="small" title="历史快照" bordered={false}>
      {latestSnapshotComparison?.lead ? (
        <Alert
          type={latestSnapshotComparison.summary?.[0]?.includes('复核型结果') ? 'warning' : 'info'}
          showIcon
          style={{ marginBottom: 12 }}
          message="最近两版变化摘要"
          description={latestSnapshotComparison.lead}
        />
      ) : null}
      <SnapshotHistoryList task={selectedTask} />
    </Card>
  </>
);

export const WorkbenchTaskEditorSection = ({
  handleMetaSave,
  noteDraft,
  saving,
  setNoteDraft,
  setTitleDraft,
  titleDraft,
}) => (
  <Card size="small" title="任务信息" bordered={false}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Input value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} placeholder="任务标题" />
      <TextArea
        rows={3}
        value={noteDraft}
        onChange={(event) => setNoteDraft(event.target.value)}
        placeholder="补充备注或下一步计划"
      />
      <Button icon={<SaveOutlined />} onClick={handleMetaSave} loading={saving} style={{ alignSelf: 'flex-start' }}>
        保存备注
      </Button>
    </Space>
  </Card>
);

export const WorkbenchTaskActivitySection = ({
  commentDraft,
  handleAddComment,
  handleDeleteComment,
  handleRestoreArchived,
  handleStatusUpdate,
  saving,
  selectedTask,
  setCommentDraft,
  setShowAllTimeline,
  showAllTimeline,
  timeline,
  timelineItems,
}) => (
  <>
    <Card
      size="small"
      title={(
        <Space>
          <HistoryOutlined />
          <span>研究时间线</span>
        </Space>
      )}
      extra={
        timeline.length > 8 ? (
          <Button type="link" size="small" onClick={() => setShowAllTimeline((prev) => !prev)}>
            {showAllTimeline ? '收起' : '展开更多'}
          </Button>
        ) : null
      }
      bordered={false}
    >
      {timeline.length ? (
        <Timeline
          items={timelineItems.map((event) => ({
            color: event.color,
            dot: event.dot === 'comment' ? <CommentOutlined /> : <ClockCircleOutlined />,
            children: (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap>
                  <Text strong>{event.children.label}</Text>
                  <Tag color={event.children.color}>{event.children.type}</Tag>
                  <Text type="secondary">{new Date(event.children.createdAt).toLocaleString()}</Text>
                </Space>
                {event.children.detail ? <Text type="secondary">{event.children.detail}</Text> : null}
              </Space>
            ),
          }))}
        />
      ) : (
        <Empty description="暂无时间线事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Card>

    <Card
      size="small"
      title={(
        <Space>
          <CommentOutlined />
          <span>评论</span>
        </Space>
      )}
      bordered={false}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <TextArea
          rows={3}
          value={commentDraft}
          onChange={(event) => setCommentDraft(event.target.value)}
          placeholder="记录这一步的判断、风险或下一步动作"
        />
        <Button
          type="primary"
          icon={<CommentOutlined />}
          onClick={handleAddComment}
          loading={saving}
          disabled={!commentDraft.trim()}
          style={{ alignSelf: 'flex-start' }}
        >
          添加评论
        </Button>

        {(selectedTask.comments || []).length ? (
          <List
            size="small"
            dataSource={selectedTask.comments}
            renderItem={(comment) => (
              <List.Item
                actions={[
                  <Button
                    key="delete"
                    type="link"
                    danger
                    size="small"
                    onClick={() => handleDeleteComment(comment.id)}
                  >
                    删除
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={(
                    <Space wrap>
                      <Text strong>{comment.author || 'local'}</Text>
                      <Text type="secondary">{new Date(comment.created_at).toLocaleString()}</Text>
                    </Space>
                  )}
                  description={comment.body}
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="暂无评论" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Space>
    </Card>

    <Card size="small" title="状态流转" bordered={false}>
      <Space wrap>
        {selectedTask.status === 'archived' ? (
          <Button type="primary" onClick={() => handleRestoreArchived(selectedTask.id)} loading={saving}>
            恢复到新建
          </Button>
        ) : (
          <>
            <Button onClick={() => handleStatusUpdate('new')} loading={saving}>
              放回新建
            </Button>
            <Button onClick={() => handleStatusUpdate('in_progress')} loading={saving}>
              进行中
            </Button>
            <Button onClick={() => handleStatusUpdate('blocked')} loading={saving}>
              阻塞
            </Button>
            <Button type="primary" onClick={() => handleStatusUpdate('complete')} loading={saving}>
              完成
            </Button>
            <Button onClick={() => handleStatusUpdate('archived')} loading={saving}>
              归档
            </Button>
          </>
        )}
      </Space>
    </Card>
  </>
);
