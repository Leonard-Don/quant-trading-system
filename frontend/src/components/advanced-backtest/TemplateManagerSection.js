import React from 'react';
import { Alert, Button, Card, Col, Input, Row, Select, Space, Table, Tag } from 'antd';

import { ADVANCED_TEMPLATE_CATEGORY_LABELS } from '../../utils/advancedExperimentTemplates';
import { getStrategyName, getStrategyParameterLabel } from '../../constants/strategies';

function TemplateManagerSection({
  compact = false,
  templateName,
  setTemplateName,
  templateNote,
  setTemplateNote,
  templateCategoryFilter,
  setTemplateCategoryFilter,
  selectedTemplateId,
  setSelectedTemplateId,
  groupedTemplateOptions,
  handleSaveTemplate,
  handleSuggestTemplateName,
  handleApplyTemplate,
  handleImportTemplateToMainBacktest,
  handleOverwriteTemplate,
  handleTogglePinnedTemplate,
  handleDeleteTemplate,
  savedTemplates,
  selectedTemplate,
  selectedTemplatePreview,
  selectedSnapshotId,
  setSelectedSnapshotId,
  savedSnapshots,
  handleSaveSnapshot,
  currentSnapshot,
  experimentComparison,
}) {
  return (
    <Card className={`workspace-panel advanced-lab-control-card${compact ? ' advanced-lab-control-card--compact' : ''}`}>
      <div className="workspace-section__header">
        <div>
          <div className="workspace-section__title">实验模板与版本对比</div>
          <div className="workspace-section__description">把常用实验配置保存成模板，并将当前实验结果与上一版关键指标并排比较。</div>
        </div>
      </div>
      <Row gutter={[16, 16]} align="top">
        <Col xs={24} xl={compact ? 24 : 10}>
          <div className="workspace-field-label">模板名称</div>
          <Input
            value={templateName}
            onChange={(event) => setTemplateName(event.target.value)}
            placeholder="例如：趋势策略稳健性模板"
          />
          <div className="workspace-field-label" style={{ marginTop: 12 }}>模板备注</div>
          <Input.TextArea
            value={templateNote}
            onChange={(event) => setTemplateNote(event.target.value)}
            placeholder="例如：适合做趋势策略在大盘股上的参数寻优与稳健性验证"
            rows={3}
            maxLength={160}
            showCount
          />
          <div className="workspace-field-label" style={{ marginTop: 12 }}>已保存模板</div>
          <Select
            value={templateCategoryFilter}
            style={{ width: '100%', marginBottom: 12 }}
            options={[
              { value: 'all', label: '全部研究场景' },
              ...Object.entries(ADVANCED_TEMPLATE_CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
            ]}
            onChange={setTemplateCategoryFilter}
          />
          <Select
            value={selectedTemplateId || undefined}
            style={{ width: '100%' }}
            placeholder="选择一个已保存模板"
            options={groupedTemplateOptions}
            onChange={setSelectedTemplateId}
          />
          <Space wrap style={{ marginTop: 12 }}>
            <Button type="primary" onClick={handleSaveTemplate}>保存模板</Button>
            <Button onClick={handleSuggestTemplateName}>推荐命名</Button>
            <Button onClick={handleApplyTemplate} disabled={!savedTemplates.length}>套用模板</Button>
            <Button onClick={handleImportTemplateToMainBacktest} disabled={!selectedTemplateId}>带回主回测</Button>
            <Button onClick={handleOverwriteTemplate} disabled={!selectedTemplateId}>覆盖当前模板</Button>
            <Button onClick={handleTogglePinnedTemplate} disabled={!selectedTemplateId}>
              {selectedTemplate?.pinned ? '取消置顶' : '置顶模板'}
            </Button>
            <Button danger onClick={handleDeleteTemplate} disabled={!selectedTemplateId}>删除模板</Button>
          </Space>
          {selectedTemplatePreview ? (
            <div className="workspace-section" style={{ marginTop: 16 }}>
              <div className="workspace-section__header" style={{ marginBottom: 12 }}>
                <div>
                  <div className="workspace-section__title">模板预览</div>
                  <div className="workspace-section__description">套用前先确认这个模板对应的研究场景、标的和关键参数。</div>
                </div>
                <Space size="small">
                  {selectedTemplate?.pinned ? <Tag color="gold">已置顶</Tag> : null}
                  <Tag color="processing">
                    {ADVANCED_TEMPLATE_CATEGORY_LABELS[selectedTemplatePreview.category] || selectedTemplatePreview.category}
                  </Tag>
                </Space>
              </div>
              <div className="summary-strip" style={{ marginTop: 0 }}>
                <div className="summary-strip__item">
                  <span className="summary-strip__label">标的</span>
                  <span className="summary-strip__value">{selectedTemplatePreview.symbol || '未设置'}</span>
                </div>
                <div className="summary-strip__item">
                  <span className="summary-strip__label">主策略</span>
                  <span className="summary-strip__value">{selectedTemplatePreview.strategy ? getStrategyName(selectedTemplatePreview.strategy) : '未设置'}</span>
                </div>
                <div className="summary-strip__item">
                  <span className="summary-strip__label">策略数量</span>
                  <span className="summary-strip__value">{selectedTemplatePreview.strategyCount || 1}</span>
                </div>
                <div className="summary-strip__item">
                  <span className="summary-strip__label">寻优密度</span>
                  <span className="summary-strip__value">{selectedTemplatePreview.optimizationDensity}</span>
                </div>
              </div>
              <div className="workspace-section__hint">
                区间：{selectedTemplatePreview.dateRange?.filter(Boolean).join(' 至 ') || '未设置'}
              </div>
              <div className="workspace-section__hint">
                研究标的池：{selectedTemplatePreview.researchSymbolsInput || '未设置'}
              </div>
              {selectedTemplatePreview.note ? <div className="workspace-section__hint">备注：{selectedTemplatePreview.note}</div> : null}
              {selectedTemplatePreview.keyParameters.length ? (
                <Space wrap style={{ marginTop: 12 }}>
                  {selectedTemplatePreview.keyParameters.map((entry) => (
                    <Tag key={entry.key} color="blue">
                      {getStrategyParameterLabel(entry.key)}: {String(entry.value)}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <div className="workspace-section__hint">这个模板当前没有额外参数覆盖。</div>
              )}
            </div>
          ) : null}
        </Col>
        <Col xs={24} xl={compact ? 24 : 14}>
          <div className="workspace-section">
            <div className="workspace-section__header">
              <div>
                <div className="workspace-section__title">实验版本对比</div>
                <div className="workspace-section__description">当前结果会与一条已保存实验版本对比，快速确认这次改动到底带来了什么变化。</div>
              </div>
              <Space wrap>
                <Select
                  value={selectedSnapshotId || undefined}
                  style={{ minWidth: 260 }}
                  placeholder="选择一个历史版本"
                  options={savedSnapshots.map((snapshot) => ({
                    value: snapshot.id,
                    label: snapshot.name,
                  }))}
                  onChange={setSelectedSnapshotId}
                />
                <Button onClick={handleSaveSnapshot} disabled={!currentSnapshot}>保存本次版本</Button>
              </Space>
            </div>
            {experimentComparison ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Alert
                  type="info"
                  showIcon
                  message="版本对比已生成"
                  description={experimentComparison.title}
                />
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.key}
                  dataSource={experimentComparison.rows}
                  columns={[
                    { title: '指标', dataIndex: 'label', key: 'label' },
                    { title: '当前版本', dataIndex: 'current', key: 'current' },
                    { title: '对比版本', dataIndex: 'previous', key: 'previous' },
                    { title: '变化', dataIndex: 'delta', key: 'delta' },
                  ]}
                />
              </Space>
            ) : (
              <Alert
                type="info"
                showIcon
                message="还没有可比较的实验版本"
                description="先保存一个实验版本，再把当前结果与它做关键指标对比。"
              />
            )}
          </div>
        </Col>
      </Row>
    </Card>
  );
}

export default TemplateManagerSection;
