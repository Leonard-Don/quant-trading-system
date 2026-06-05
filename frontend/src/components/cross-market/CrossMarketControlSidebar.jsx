/**
 * Right-hand control rail for the cross-market backtest panel: the control
 * overview card, the recommended-template quick-pick, the parameter / template
 * form, the priority-review alert and the run / clear actions.
 *
 * Pure presentational split (layer 2): all state lives in the host panel and is
 * passed down with its mutation callbacks. Extracted verbatim from
 * CrossMarketBacktestPanel.jsx so behaviour is identical.
 */

import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Tag, Typography } from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';

import {
  formatSignalLabel,
  formatSignalList,
  formatStatusLabel,
  formatTemplateName,
  formatTemplateTheme,
} from '../../utils/crossMarketFormatters';
import {
  getReviewPriorityTitleSuffix,
  getSelectionQualityExplanationLines,
} from '../../utils/crossMarketReviewHelpers';
import { DEFAULT_PARAMETERS } from '../../utils/crossMarketDefaults';

const { Paragraph, Text } = Typography;

function CrossMarketControlSidebar({
  sidebarOverviewItems,
  selectedTemplate,
  displayRecommendedTemplates,
  templates,
  loadingTemplates,
  selectedTemplateId,
  parameters,
  quality,
  constraints,
  meta,
  selectedTemplateNeedsPriorityReview,
  running,
  applyTemplate,
  setParameters,
  setQuality,
  setConstraints,
  setMeta,
  setResults,
  onRun,
}) {
  return (
    <aside className="cross-market-sidebar">
      <Card variant="borderless" className="workspace-panel cross-market-sidebar-card cross-market-sidebar-card--overview">
        <div className="app-page-section-kicker">控制总览</div>
        <Text strong className="cross-market-sidebar-card__title">右侧保持输入，左侧专注结果</Text>
        <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
          模板快选、参数和约束都固定在侧栏里，主画布只保留篮子和运行预览，减少宽屏下的视线往返。
        </Paragraph>
        <div className="cross-market-sidebar-card__grid">
          {sidebarOverviewItems.map((item) => (
            <div key={item.label} className="cross-market-sidebar-card__item">
              <span className="cross-market-sidebar-card__item-label">{item.label}</span>
              <span className="cross-market-sidebar-card__item-value">{item.value}</span>
            </div>
          ))}
        </div>
        <div className="cross-market-sidebar-card__note">
          {selectedTemplate
            ? `当前模板：${formatTemplateName(selectedTemplate)}${selectedTemplate.theme ? ` · ${formatTemplateTheme(selectedTemplate)}` : ''}`
            : '当前未锁定模板，建议先从模板快选开始。'}
        </div>
      </Card>

      <Card title="模板快选" variant="borderless" className="workspace-panel cross-market-sidebar-card">
        <div className="cross-market-template-list">
          {displayRecommendedTemplates.slice(0, 3).map((template) => (
            <div
              key={template.id}
              className={`cross-market-template-card${selectedTemplate?.id === template.id ? ' cross-market-template-card--active' : ''}`}
            >
              <div className="cross-market-template-card__header">
                <div>
                  <div className="cross-market-template-card__title">{formatTemplateName(template)}</div>
                  <Text type="secondary">{template.driverHeadline}</Text>
                </div>
                <Button size="small" type={selectedTemplate?.id === template.id ? 'default' : 'primary'} onClick={() => applyTemplate(template, { useBias: true })}>
                  {selectedTemplate?.id === template.id ? '已载入' : '载入'}
                </Button>
              </div>
              <Space wrap size={[6, 6]} className="cross-market-template-card__tags">
                <Tag color={template.recommendationTone}>{template.recommendationTier}</Tag>
                <Tag color="cyan">评分 {Number(template.recommendationScore || 0).toFixed(2)}</Tag>
                {template.executionPosture ? (
                  <Tag color="lime">{formatSignalLabel(template.executionPosture)}</Tag>
                ) : null}
                {template.refreshMeta?.selectionQualityRunState?.active ? (
                  <Tag color="gold">优先重看</Tag>
                ) : null}
                {template.refreshMeta?.reviewContextDriven && !template.refreshMeta?.selectionQualityRunState?.active ? (
                  <Tag color="geekblue">语境切换</Tag>
                ) : null}
              </Space>
              {(template.themeCore || template.themeSupport) ? (
                <Text type="secondary" className="cross-market-template-card__line">
                  核心腿：{formatSignalList(template.themeCore) || '暂无'} · 辅助腿：{formatSignalList(template.themeSupport) || '暂无'}
                </Text>
              ) : null}
              {template.recentComparisonLead ? (
                <Text type="secondary" className="cross-market-template-card__line">
                  最近两版：{template.recentComparisonLead}
                </Text>
              ) : null}
              {(template.rankingPenaltyReason || getSelectionQualityExplanationLines(template.refreshMeta)[0]) ? (
                <Text type="secondary" className="cross-market-template-card__line">
                  {template.rankingPenaltyReason || getSelectionQualityExplanationLines(template.refreshMeta)[0]}
                </Text>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <Card title="参数与模板" variant="borderless" className="workspace-panel cross-market-sidebar-card">
        <Space direction="vertical" style={{ width: '100%' }} size={14}>
          <Select
            placeholder="载入演示模板"
            loading={loadingTemplates}
            value={selectedTemplateId || undefined}
            options={templates.map((template) => ({
              label: formatTemplateName(template),
              value: template.id,
            }))}
            onChange={(value) => applyTemplate(value, { useBias: false })}
          />

          <Form layout="vertical">
            <Form.Item label="构造模式">
              <Select
                value={quality.construction_mode}
                options={[
                  { value: 'equal_weight', label: '等权配置' },
                  { value: 'ols_hedge', label: '滚动 OLS 对冲' },
                ]}
                onChange={(value) => setQuality((prev) => ({ ...prev, construction_mode: value }))}
              />
            </Form.Item>
            <Form.Item label="回看窗口">
              <InputNumber
                min={5}
                value={parameters.lookback}
                style={{ width: '100%' }}
                onChange={(value) =>
                  setParameters((prev) => ({ ...prev, lookback: value || DEFAULT_PARAMETERS.lookback }))
                }
              />
            </Form.Item>
            <Form.Item label="入场阈值">
              <InputNumber
                min={0.5}
                step={0.1}
                value={parameters.entry_threshold}
                style={{ width: '100%' }}
                onChange={(value) =>
                  setParameters((prev) => ({ ...prev, entry_threshold: value || DEFAULT_PARAMETERS.entry_threshold }))
                }
              />
            </Form.Item>
            <Form.Item label="离场阈值">
              <InputNumber
                min={0.1}
                step={0.1}
                value={parameters.exit_threshold}
                style={{ width: '100%' }}
                onChange={(value) =>
                  setParameters((prev) => ({ ...prev, exit_threshold: value || DEFAULT_PARAMETERS.exit_threshold }))
                }
              />
            </Form.Item>
            <Form.Item label="初始资金">
              <InputNumber
                min={1000}
                step={1000}
                value={meta.initial_capital}
                style={{ width: '100%' }}
                onChange={(value) => setMeta((prev) => ({ ...prev, initial_capital: value || 100000 }))}
              />
            </Form.Item>
            <Form.Item label="最少历史天数">
              <InputNumber
                min={10}
                step={5}
                value={quality.min_history_days}
                style={{ width: '100%' }}
                onChange={(value) => setQuality((prev) => ({ ...prev, min_history_days: value || 60 }))}
              />
            </Form.Item>
            <Form.Item label="最小重叠比例">
              <InputNumber
                min={0.1}
                max={1}
                step={0.05}
                value={quality.min_overlap_ratio}
                style={{ width: '100%' }}
                onChange={(value) => setQuality((prev) => ({ ...prev, min_overlap_ratio: value || 0.7 }))}
              />
            </Form.Item>
            <Form.Item label="单资产上限 (%)">
              <InputNumber
                min={1}
                max={100}
                step={1}
                value={constraints.max_single_weight}
                style={{ width: '100%' }}
                placeholder="可留空"
                onChange={(value) => setConstraints((prev) => ({ ...prev, max_single_weight: value ?? null }))}
              />
            </Form.Item>
            <Form.Item label="单资产下限 (%)">
              <InputNumber
                min={1}
                max={100}
                step={1}
                value={constraints.min_single_weight}
                style={{ width: '100%' }}
                placeholder="可留空"
                onChange={(value) => setConstraints((prev) => ({ ...prev, min_single_weight: value ?? null }))}
              />
            </Form.Item>
            <Form.Item label="手续费 (%)">
              <InputNumber
                min={0}
                step={0.01}
                value={meta.commission}
                style={{ width: '100%' }}
                onChange={(value) => setMeta((prev) => ({ ...prev, commission: value ?? 0.1 }))}
              />
            </Form.Item>
            <Form.Item label="滑点 (%)">
              <InputNumber
                min={0}
                step={0.01}
                value={meta.slippage}
                style={{ width: '100%' }}
                onChange={(value) => setMeta((prev) => ({ ...prev, slippage: value ?? 0.1 }))}
              />
            </Form.Item>
            <Form.Item label="开始日期">
              <Input
                value={meta.start_date}
                placeholder="YYYY-MM-DD"
                onChange={(event) => setMeta((prev) => ({ ...prev, start_date: event.target.value }))}
              />
            </Form.Item>
            <Form.Item label="结束日期">
              <Input
                value={meta.end_date}
                placeholder="YYYY-MM-DD"
                onChange={(event) => setMeta((prev) => ({ ...prev, end_date: event.target.value }))}
              />
            </Form.Item>
          </Form>

          {selectedTemplateNeedsPriorityReview ? (
            <Alert
              type="warning"
              showIcon
              message={`当前模板：${selectedTemplate ? formatTemplateName(selectedTemplate) : ''} · ${getReviewPriorityTitleSuffix(selectedTemplate?.refreshMeta) || '建议优先重看'}`}
              description={`这次运行更适合作为复核型回测，而不是普通默认模板回测。${
                selectedTemplate?.recentComparisonLead
                  ? `最近两版：${selectedTemplate.recentComparisonLead} · `
                  : ''
              }${
                selectedTemplate?.refreshMeta?.selectionQualityRunState?.active
                  ? `当前保存结果已按 ${formatStatusLabel(selectedTemplate?.refreshMeta?.selectionQualityRunState?.label || 'degraded')} 强度运行`
                  : selectedTemplate?.refreshMeta?.reviewContextDriven
                    ? '最近两版已发生复核语境切换'
                    : selectedTemplate?.refreshMeta?.inputReliabilityDriven
                      ? '当前整体输入可靠度已经发生明显变化'
                      : '当前主题已进入优先重看语境'
              }${
                selectedTemplate?.refreshMeta?.selectionQualityRunState?.baseScore || selectedTemplate?.refreshMeta?.selectionQualityRunState?.effectiveScore
                  ? ` · ${Number(selectedTemplate?.refreshMeta?.selectionQualityRunState?.baseScore || 0).toFixed(2)}→${Number(selectedTemplate?.refreshMeta?.selectionQualityRunState?.effectiveScore || 0).toFixed(2)}`
                  : ''
              }${
                selectedTemplate?.refreshMeta?.selectionQualityRunState?.reason
                  ? ` · ${selectedTemplate.refreshMeta.selectionQualityRunState.reason}`
                  : selectedTemplate?.refreshMeta?.reviewContextShift?.actionHint
                    ? ` · ${selectedTemplate.refreshMeta.reviewContextShift.actionHint}`
                    : selectedTemplate?.refreshMeta?.inputReliabilityShift?.actionHint
                      ? ` · ${selectedTemplate.refreshMeta.inputReliabilityShift.actionHint}`
                      : selectedTemplate?.refreshMeta?.reviewContextShift?.lead
                        ? ` · ${selectedTemplate.refreshMeta.reviewContextShift.lead}`
                        : selectedTemplate?.refreshMeta?.inputReliabilityShift?.currentLead
                          ? ` · ${selectedTemplate.refreshMeta.inputReliabilityShift.currentLead}`
                          : ''
              }`}
            />
          ) : null}

          <div className="cross-market-parameter-actions">
            <Button icon={<ReloadOutlined />} onClick={() => setResults(null)}>
              清空结果
            </Button>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={onRun}>
              运行回测
            </Button>
          </div>
        </Space>
      </Card>
    </aside>
  );
}

export default CrossMarketControlSidebar;
