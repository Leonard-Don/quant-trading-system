import React from 'react';
import { Alert, Card, Col, Row, Statistic, Typography } from 'antd';

const { Text } = Typography;

const WorkbenchOverviewPanels = ({ refreshStats, stats }) => (
  <>
    <Row gutter={[16, 16]}>
      <Col xs={12} md={6}>
        <Card bordered={false}>
          <Statistic title="总任务" value={stats?.total || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card bordered={false}>
          <Statistic title="进行中" value={stats?.status_counts?.in_progress || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card bordered={false}>
          <Statistic title="阻塞" value={stats?.status_counts?.blocked || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card bordered={false}>
          <Statistic title="已完成" value={stats?.status_counts?.complete || 0} />
        </Card>
      </Col>
    </Row>

    <Row gutter={[16, 16]}>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="建议更新" value={refreshStats.high} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">宏观或另类数据与保存输入明显脱节，建议优先重开研究。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="建议复核" value={refreshStats.medium} valueStyle={{ color: '#d48806' }} />
          <Text type="secondary">核心驱动在变化，适合先做一次中间复核，再决定是否更新快照。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="共振驱动" value={refreshStats.resonance} valueStyle={{ color: '#c41d7f' }} />
          <Text type="secondary">这些任务的优先级变化来自宏观共振结构切换，更值得优先看。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="核心腿受压" value={refreshStats.biasQualityCore} valueStyle={{ color: '#fa541c' }} />
          <Text type="secondary">这些任务的主题核心腿已经成为偏置收缩焦点，通常比普通配置压缩更值得先处理。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="降级运行" value={refreshStats.selectionQualityActive} valueStyle={{ color: '#ad6800' }} />
          <Text type="secondary">这些任务的当前结果已经按收缩或自动降级强度运行，通常应排在普通更新前面优先重看。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="复核语境切换" value={refreshStats.reviewContext} valueStyle={{ color: '#1d39c4' }} />
          <Text type="secondary">这些任务最近两版刚切入复核语境，或从复核型结果回到普通结果，适合尽快复核最新判断。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="自动降级" value={refreshStats.selectionQuality} valueStyle={{ color: '#d48806' }} />
          <Text type="secondary">这些任务已经从原始推荐切到降级处理，说明主题排序本身正在被重新评估。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="政策源驱动" value={refreshStats.policySource} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">这些任务的更新优先级来自政策正文抓取质量退化，应先确认研究输入是否仍然可靠。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card bordered={false}>
          <Statistic title="偏置收缩" value={refreshStats.biasQuality} valueStyle={{ color: '#d46b08' }} />
          <Text type="secondary">这些任务的宏观偏置强度已经被证据质量压缩，建议先确认模板还适不适合维持原有配置力度。</Text>
        </Card>
      </Col>
    </Row>

    <Row gutter={[16, 16]}>
      <Col xs={24} md={24}>
        <Card bordered={false}>
          <Statistic title="继续观察" value={refreshStats.low} valueStyle={{ color: '#1677ff' }} />
          <Text type="secondary">当前输入与保存快照仍然相近，可以继续沿现有研究路线推进。</Text>
        </Card>
      </Col>
    </Row>

    {refreshStats.selectionQualityActive ? (
      <Alert
        type="warning"
        showIcon
        message="降级运行任务应优先重看"
        description={`当前有 ${refreshStats.selectionQualityActive} 条任务的保存结果已经按收缩或自动降级强度运行。这类结果本身已经受推荐质量变化影响，通常应排在普通“建议更新”前面优先处理。`}
      />
    ) : null}
  </>
);

export default WorkbenchOverviewPanels;
