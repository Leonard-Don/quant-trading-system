import React from 'react';
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from 'antd';
import { buildActiveWorkbenchFilterMeta } from './workbenchUtils';

const { Text } = Typography;

const WorkbenchOverviewPanels = ({
  filters,
  onOpenQueueCrossMarket,
  onOpenQueueLead,
  onOpenQueuePricing,
  onCopyViewLink,
  queueLaunchSummary,
  refreshStats,
  setFilters,
  snapshotSummaryOptions,
  sourceOptions,
  stats,
  TYPE_OPTIONS,
  REFRESH_OPTIONS,
  REASON_OPTIONS,
  SNAPSHOT_VIEW_OPTIONS,
}) => {
  const toggleReasonFilter = (reason) => {
    if (!setFilters) {
      return;
    }
    setFilters((prev) => ({
      ...prev,
      reason: prev.reason === reason ? '' : reason,
    }));
  };

  const clearAllFilters = () => {
    if (!setFilters) {
      return;
    }
    setFilters((prev) => ({
      ...prev,
      type: '',
      source: '',
      refresh: '',
      reason: '',
      snapshotView: '',
      snapshotFingerprint: '',
      snapshotSummary: '',
      keyword: '',
    }));
  };

  const clearFilterField = (field) => {
    if (!setFilters || !field) {
      return;
    }
    setFilters((prev) => ({
      ...prev,
      [field]: '',
    }));
  };

  const toggleSnapshotSummary = (summary, fingerprint = '') => {
    if (!setFilters) {
      return;
    }
    setFilters((prev) => ({
      ...prev,
      snapshotSummary: prev.snapshotSummary === summary ? '' : summary,
      snapshotFingerprint: prev.snapshotSummary === summary ? '' : fingerprint,
    }));
  };

  const isReasonActive = (reason) => filters?.reason === reason;
  const activeFilterMeta = buildActiveWorkbenchFilterMeta(filters, {
    reasonOptions: REASON_OPTIONS,
    refreshOptions: REFRESH_OPTIONS,
    snapshotViewOptions: SNAPSHOT_VIEW_OPTIONS,
    sourceOptions,
    typeOptions: TYPE_OPTIONS,
  });

  return (
    <>
    {activeFilterMeta.length ? (
      <Alert
        type="info"
        showIcon
        message="当前工作台筛选已生效"
        description={(
          <Space wrap>
            {activeFilterMeta.map((item) => (
              <Tag
                key={item.field}
                color={item.color}
                closable
                closeIcon={<span data-testid={`overview-filter-close-${item.field}`}>×</span>}
                onClose={(event) => {
                  event.preventDefault();
                  clearFilterField(item.field);
                }}
              >
                {item.text}
              </Tag>
            ))}
          </Space>
        )}
        action={(
          <Space>
            <Button size="small" onClick={onCopyViewLink}>
              复制当前视图链接
            </Button>
            <Button size="small" onClick={clearAllFilters}>
              清空全部筛选
            </Button>
          </Space>
        )}
      />
    ) : null}
    <Row gutter={[16, 16]}>
      <Col xs={12} md={6}>
        <Card variant="borderless">
          <Statistic title="总任务" value={stats?.total || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card variant="borderless">
          <Statistic title="进行中" value={stats?.status_counts?.in_progress || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card variant="borderless">
          <Statistic title="阻塞" value={stats?.status_counts?.blocked || 0} />
        </Card>
      </Col>
      <Col xs={12} md={6}>
        <Card variant="borderless">
          <Statistic title="已完成" value={stats?.status_counts?.complete || 0} />
        </Card>
      </Col>
    </Row>

    <Row gutter={[16, 16]}>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="建议更新" value={refreshStats.high} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">宏观或另类数据与保存输入明显脱节，建议优先重开研究。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="建议复核" value={refreshStats.medium} valueStyle={{ color: '#d48806' }} />
          <Text type="secondary">核心驱动在变化，适合先做一次中间复核，再决定是否更新快照。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="共振驱动" value={refreshStats.resonance} valueStyle={{ color: '#c41d7f' }} />
          <Text type="secondary">这些任务的优先级变化来自宏观共振结构切换，更值得优先看。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="核心腿受压" value={refreshStats.biasQualityCore} valueStyle={{ color: '#fa541c' }} />
          <Text type="secondary">这些任务的主题核心腿已经成为偏置收缩焦点，通常比普通配置压缩更值得先处理。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="降级运行" value={refreshStats.selectionQualityActive} valueStyle={{ color: '#ad6800' }} />
          <Text type="secondary">这些任务的当前结果已经按收缩或自动降级强度运行，通常应排在普通更新前面优先重看。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="复核语境切换" value={refreshStats.reviewContext} valueStyle={{ color: '#1d39c4' }} />
          <Text type="secondary">这些任务最近两版刚切入复核语境，或从复核型结果回到普通结果，适合尽快复核最新判断。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="系统衰败雷达" value={refreshStats.structuralDecayRadar || 0} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">这些任务的系统级结构衰败雷达较保存时升温，通常意味着风险预算需要先收缩，再讨论表达方向。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button
              type="link"
              size="small"
              onClick={() => setFilters((prev) => ({ ...prev, snapshotView: prev.snapshotView === 'filtered' ? '' : 'filtered' }))}
            >
              {filters?.snapshotView === 'filtered' ? '取消筛选' : '只看带视角'}
            </Button>
          )}
        >
          <Statistic title="带视角快照" value={refreshStats.snapshotViewFiltered || 0} valueStyle={{ color: '#389e0d' }} />
          <Text type="secondary">这些任务最近一次快照带有工作台筛选视角，适合回溯“当时为什么会看它”。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button
              type="link"
              size="small"
              onClick={() => setFilters((prev) => ({ ...prev, snapshotView: prev.snapshotView === 'scoped' ? '' : 'scoped' }))}
            >
              {filters?.snapshotView === 'scoped' ? '取消筛选' : '只看带焦点'}
            </Button>
          )}
        >
          <Statistic title="带任务焦点快照" value={refreshStats.snapshotViewScoped || 0} valueStyle={{ color: '#1677ff' }} />
          <Text type="secondary">这些任务的最近快照还带有明确研究焦点，适合直接进入复盘或复核。</Text>
        </Card>
      </Col>
      <Col xs={24} md={12}>
        <Card
          variant="borderless"
          title="研究视角复盘入口"
          extra={stats?.snapshot_view_queues?.length ? <Tag color="blue">全量工作台</Tag> : null}
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {snapshotSummaryOptions?.length ? (
              snapshotSummaryOptions.slice(0, 4).map((item) => (
                <Space key={item.value} wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space wrap>
                    <Button
                      size="small"
                      type={filters?.snapshotSummary === item.value ? 'primary' : 'default'}
                      onClick={() => toggleSnapshotSummary(item.value, item.fingerprint)}
                    >
                      {filters?.snapshotSummary === item.value ? '取消复盘队列' : `查看“${item.value}”`}
                    </Button>
                    <Tag color="volcano">{item.count}</Tag>
                    {item.scopedCount ? <Tag color="processing">焦点 {item.scopedCount}</Tag> : null}
                  </Space>
                  <Text type="secondary">{item.label}</Text>
                </Space>
              ))
            ) : (
              <Text type="secondary">暂时还没有带研究视角的快照，等下一轮保存后这里会形成复盘入口。</Text>
            )}
            <Text type="secondary">
              按保存当时的工作台研究视角回看任务，比只看最新状态更容易复盘当时的判断框架。
              {stats?.snapshot_view_queues?.length ? ' 当前入口来自全量工作台聚合，不受页面已加载任务数限制。' : ''}
            </Text>
          </Space>
        </Card>
      </Col>
      <Col xs={24} md={12}>
        <Card
          variant="borderless"
          title="当前复盘队列执行入口"
          extra={queueLaunchSummary?.launchableCount ? <Tag color="purple">可重开 {queueLaunchSummary.launchableCount}</Tag> : null}
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Space wrap>
              <Button
                type="primary"
                onClick={onOpenQueueLead}
                disabled={!queueLaunchSummary?.leadTask}
              >
                打开队列首条
              </Button>
              <Button
                onClick={onOpenQueuePricing}
                disabled={!queueLaunchSummary?.pricingTask}
              >
                打开首个 Pricing
              </Button>
              <Button
                onClick={onOpenQueueCrossMarket}
                disabled={!queueLaunchSummary?.crossMarketTask}
              >
                打开首个跨市场
              </Button>
            </Space>
            <Space wrap>
              <Tag color="blue">Pricing {queueLaunchSummary?.pricingCount || 0}</Tag>
              <Tag color="purple">Cross-Market {queueLaunchSummary?.crossMarketCount || 0}</Tag>
            </Space>
            <Text type="secondary">
              {queueLaunchSummary?.leadTask
                ? `当前排序首条：${queueLaunchSummary.leadTask.title || queueLaunchSummary.leadTask.id}`
                : '当前筛选队列里还没有可直接重新打开的研究页。'}
            </Text>
            <Text type="secondary">
              这个入口适合把当前筛选队列直接送回执行页，不用先点开单张任务卡再重开研究。
            </Text>
          </Space>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button type="link" size="small" onClick={() => toggleReasonFilter('priority_new')}>
              {isReasonActive('priority_new') ? '取消筛选' : '只看首次'}
            </Button>
          )}
        >
          <Statistic title="自动排序首次入列" value={refreshStats.priorityNew || 0} valueStyle={{ color: '#1677ff' }} />
          <Text type="secondary">这些任务是第一次被系统推进自动排序队列，适合先快速扫一眼，确认是否需要立刻升级处理。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button type="link" size="small" onClick={() => toggleReasonFilter('priority_escalated')}>
              {isReasonActive('priority_escalated') ? '取消筛选' : '只看升档'}
            </Button>
          )}
        >
          <Statistic title="自动排序升档" value={refreshStats.priorityEscalated || 0} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">这些任务最近一次自动排序不是简单复写，而是优先级真的升了一档，通常应该先看。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="人的维度" value={refreshStats.peopleLayer} valueStyle={{ color: '#722ed1' }} />
          <Text type="secondary">这些任务的人事与组织结构较保存时明显走弱，适合优先确认长期判断是否需要下修。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="部门混乱" value={refreshStats.departmentChaos} valueStyle={{ color: '#ad4e00' }} />
          <Text type="secondary">这些任务的部门级政策混乱较保存时恶化，适合优先确认政策执行主体是否已经改变组合风险。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="自动降级" value={refreshStats.selectionQuality} valueStyle={{ color: '#d48806' }} />
          <Text type="secondary">这些任务已经从原始推荐切到降级处理，说明主题排序本身正在被重新评估。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="政策源驱动" value={refreshStats.policySource} valueStyle={{ color: '#cf1322' }} />
          <Text type="secondary">这些任务的更新优先级来自政策正文抓取质量退化，应先确认研究输入是否仍然可靠。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card variant="borderless">
          <Statistic title="偏置收缩" value={refreshStats.biasQuality} valueStyle={{ color: '#d46b08' }} />
          <Text type="secondary">这些任务的宏观偏置强度已经被证据质量压缩，建议先确认模板还适不适合维持原有配置力度。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button type="link" size="small" onClick={() => toggleReasonFilter('priority_relaxed')}>
              {isReasonActive('priority_relaxed') ? '取消筛选' : '只看缓和'}
            </Button>
          )}
        >
          <Statistic title="自动排序缓和" value={refreshStats.priorityRelaxed || 0} valueStyle={{ color: '#389e0d' }} />
          <Text type="secondary">这些任务最近一次自动排序显示风险边际缓和，更适合从“马上处理”切回“跟踪观察”。</Text>
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card
          variant="borderless"
          extra={(
            <Button type="link" size="small" onClick={() => toggleReasonFilter('priority_updated')}>
              {isReasonActive('priority_updated') ? '取消筛选' : '只看更新'}
            </Button>
          )}
        >
          <Statistic title="自动排序同类更新" value={refreshStats.priorityUpdated || 0} valueStyle={{ color: '#d48806' }} />
          <Text type="secondary">这些任务的自动排序没有升档或缓和，但同类风险还在持续刷新，适合放进日常复核列表里稳定跟踪。</Text>
        </Card>
      </Col>
    </Row>

    <Row gutter={[16, 16]}>
      <Col xs={24} md={24}>
        <Card variant="borderless">
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

    {refreshStats.structuralDecayRadar ? (
      <Alert
        type="error"
        showIcon
        message="系统衰败雷达升温任务应优先处理"
        description={`当前有 ${refreshStats.structuralDecayRadar} 条任务被系统级结构衰败雷达重新排序。这类任务通常不是单点证据变化，而是风险预算、治理和执行压力形成了新的系统级负向共振。`}
      />
    ) : null}

    {refreshStats.priorityEscalated ? (
      <Alert
        type="error"
        showIcon
        message="自动排序刚升档的任务应排在最前面"
        description={`当前有 ${refreshStats.priorityEscalated} 条任务最近一次自动排序被系统判定为“升级”。这意味着优先级不是重复记录，而是较上次真的更紧急了。`}
        action={(
          <Button size="small" type="primary" danger onClick={() => toggleReasonFilter('priority_escalated')}>
            {isReasonActive('priority_escalated') ? '取消筛选' : '只看升档'}
          </Button>
        )}
      />
    ) : null}
    </>
  );
};

export default WorkbenchOverviewPanels;
