import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Col, Row, Segmented, Space, Tag } from 'antd';

import useAdvancedBacktestLab from '../hooks/useAdvancedBacktestLab';
import TemplateManagerSection from './advanced-backtest/TemplateManagerSection';
import ResearchInsightsSection from './advanced-backtest/ResearchInsightsSection';
import ResearchToolsPanel from './advanced-backtest/ResearchToolsPanel';
import { BatchBacktestForm, BatchBacktestResults } from './advanced-backtest/BatchBacktestSection';
import { WalkForwardForm, WalkForwardResults } from './advanced-backtest/WalkForwardSection';
import BenchmarkSection from './advanced-backtest/BenchmarkSection';
import PortfolioSection from './advanced-backtest/PortfolioSection';

const CHART_NEUTRAL = '#0ea5e9';
const CHART_POSITIVE = '#22c55e';

function AdvancedBacktestLab({ strategies, onImportTemplateToMainBacktest }) {
  const lab = useAdvancedBacktestLab({ strategies, onImportTemplateToMainBacktest });
  const [activePanel, setActivePanel] = useState('execute');
  const hasResults = Boolean(
    lab.batchResult
    || lab.walkResult
    || lab.marketRegimeResult
    || lab.benchmarkResult
    || lab.portfolioStrategyResult
  );
  const heroStats = [
    { label: '实验主线', value: '批量回测 + 滚动前瞻' },
    { label: '模板库存', value: `${lab.savedTemplates.length} 个` },
    { label: '版本快照', value: `${lab.savedSnapshots.length} 个` },
    {
      label: '运行状态',
      value: lab.batchLoading || lab.walkLoading ? '实验运行中' : (hasResults ? '结果已生成' : '待执行'),
    },
  ];
  const workflowLanes = [
    {
      eyebrow: '控制轨',
      title: '模板与研究工具',
      description: '先整理模板、版本与研究标的池，再决定这一轮实验要比较什么。',
    },
    {
      eyebrow: '执行区',
      title: '批量筛选 + 样本外验证',
      description: '批量回测负责横向筛选，滚动前瞻负责确认稳定性，两条线在同一页联动。',
    },
    {
      eyebrow: '结果区',
      title: '洞察、基准与组合响应',
      description: '把研究结论、基准对照和组合级策略结果放在同一块画布里收口。',
    },
  ];
  const panelOptions = useMemo(() => ([
    { label: '执行', value: 'execute' },
    { label: '结果', value: 'results' },
    { label: '研究判断', value: 'insights' },
    { label: '外部对照', value: 'compare' },
  ]), []);

  useEffect(() => {
    if (lab.batchResult || lab.walkResult) {
      setActivePanel('results');
    }
  }, [lab.batchResult, lab.walkResult]);

  useEffect(() => {
    if (lab.marketRegimeResult) {
      setActivePanel('insights');
    }
  }, [lab.marketRegimeResult]);

  useEffect(() => {
    if (lab.benchmarkResult || lab.portfolioStrategyResult) {
      setActivePanel('compare');
    }
  }, [lab.benchmarkResult, lab.portfolioStrategyResult]);

  const renderMainPanel = () => {
    if (activePanel === 'execute') {
      return (
        <section className="advanced-lab-section">
          <div className="advanced-lab-section__heading">
            <div className="app-page-section-kicker">实验执行</div>
            <div className="advanced-lab-section__title">批量筛选与样本外验证</div>
            <div className="advanced-lab-section__description">
              左侧批量回测负责同一场景下的横向筛选，右侧滚动前瞻负责稳定性确认，让“找策略”和“验策略”处在同一层级。
            </div>
          </div>
          <Row gutter={[20, 20]}>
            <Col xs={24} xxl={13}>
              <BatchBacktestForm
                batchForm={lab.batchForm}
                strategies={strategies}
                selectedBatchStrategies={lab.selectedBatchStrategies}
                strategyDefinitions={lab.strategyDefinitions}
                batchConfigs={lab.batchConfigs}
                updateBatchParam={lab.updateBatchParam}
                batchLoading={lab.batchLoading}
                handleRunBatch={lab.handleRunBatch}
              />
            </Col>
            <Col xs={24} xxl={11}>
              <WalkForwardForm
                walkForm={lab.walkForm}
                strategies={strategies}
                selectedWalkStrategy={lab.selectedWalkStrategy}
                strategyDefinitions={lab.strategyDefinitions}
                walkParams={lab.walkParams}
                setWalkParams={lab.setWalkParams}
                walkLoading={lab.walkLoading}
                handleRunWalkForward={lab.handleRunWalkForward}
              />
            </Col>
          </Row>
        </section>
      );
    }

    if (activePanel === 'results') {
      return (
        <section className="advanced-lab-section">
          <div className="advanced-lab-section__heading">
            <div className="app-page-section-kicker">实验结果</div>
            <div className="advanced-lab-section__title">把筛选结果和样本外表现放到同一屏</div>
            <div className="advanced-lab-section__description">
              先看批量回测排名，再看滚动前瞻窗口表现，避免只看某一个实验结果就过早下结论。
            </div>
          </div>
          <Row gutter={[20, 20]}>
            <Col xs={24} xxl={13}>
              <BatchBacktestResults
                batchResult={lab.batchResult}
                batchRecords={lab.batchRecords}
                batchRankingData={lab.batchRankingData}
                batchInsight={lab.batchInsight}
                batchExperimentMeta={lab.batchExperimentMeta}
                batchPendingMeta={lab.batchPendingMeta}
                batchLoading={lab.batchLoading}
                focusedBatchRecord={lab.focusedBatchRecord}
                focusedBatchTaskId={lab.focusedBatchTaskId}
                setFocusedBatchTaskId={lab.setFocusedBatchTaskId}
                handleSaveBatchHistory={lab.handleSaveBatchHistory}
                handleExportBatch={lab.handleExportBatch}
              />
            </Col>
            <Col xs={24} xxl={11}>
              <WalkForwardResults
                walkResult={lab.walkResult}
                walkForwardChartData={lab.walkForwardChartData}
                walkInsight={lab.walkInsight}
                walkLoading={lab.walkLoading}
                focusedWalkRecord={lab.focusedWalkRecord}
                focusedWalkWindowKey={lab.focusedWalkWindowKey}
                setFocusedWalkWindowKey={lab.setFocusedWalkWindowKey}
                handleSaveWalkHistory={lab.handleSaveWalkHistory}
                handleExportWalkForward={lab.handleExportWalkForward}
              />
            </Col>
          </Row>
        </section>
      );
    }

    if (activePanel === 'insights') {
      return (
        <section className="advanced-lab-section">
          <div className="advanced-lab-section__heading">
            <div className="app-page-section-kicker">研究判断</div>
            <div className="advanced-lab-section__title">把稳健性、过拟合信号和市场状态收口</div>
            <div className="advanced-lab-section__description">
              这一块专门负责告诉你“能不能继续推进”，不让研究结论散落在多个实验结果里。
            </div>
          </div>
          <ResearchInsightsSection
            robustnessScore={lab.robustnessScore}
            overfittingWarnings={lab.overfittingWarnings}
            researchConclusion={lab.researchConclusion}
            marketRegimeResult={lab.marketRegimeResult}
            marketRegimeInsight={lab.marketRegimeInsight}
            marketRegimeChartData={lab.marketRegimeChartData}
            marketRegimeLoading={lab.marketRegimeLoading}
            CHART_NEUTRAL={CHART_NEUTRAL}
            CHART_POSITIVE={CHART_POSITIVE}
          />
        </section>
      );
    }

    return (
      <section className="advanced-lab-section">
        <div className="advanced-lab-section__heading">
          <div className="app-page-section-kicker">外部对照</div>
          <div className="advanced-lab-section__title">基准差异与组合级响应</div>
          <div className="advanced-lab-section__description">
            最后一屏把策略相对基准的表现，以及组合级回测的暴露与净值表现并排放出来，方便决定后续动作。
          </div>
        </div>
        <Row gutter={[20, 20]}>
          <Col xs={24} xxl={12}>
            <BenchmarkSection
              benchmarkResult={lab.benchmarkResult}
              benchmarkContext={lab.benchmarkContext}
              benchmarkSummary={lab.benchmarkSummary}
              benchmarkChartData={lab.benchmarkChartData}
              benchmarkLoading={lab.benchmarkLoading}
            />
          </Col>
          <Col xs={24} xxl={12}>
            <PortfolioSection
              portfolioStrategyResult={lab.portfolioStrategyResult}
              portfolioChartData={lab.portfolioChartData}
              portfolioPositionSnapshot={lab.portfolioPositionSnapshot}
              portfolioExposureSummary={lab.portfolioExposureSummary}
              portfolioLoading={lab.portfolioLoading}
            />
          </Col>
        </Row>
      </section>
    );
  };

  return (
    <div className="workspace-tab-view advanced-lab">
      <div className="workspace-section workspace-section--accent advanced-lab-hero">
        <div className="advanced-lab-hero__top">
          <div>
            <div className="workspace-tagline">量化实验画布</div>
            <div className="advanced-lab-hero__title">实验控制总览</div>
            <div className="advanced-lab-hero__description">
              把模板管理、实验执行和研究判断收进同一块工作画布，先确定实验上下文，再做批量筛选与样本外验证，
              最后把结果沉淀成可复盘的研究版本。
            </div>
          </div>
          <div className="advanced-lab-hero__actions">
            <Button type="default" onClick={lab.handleApplyMainBacktestDraft}>
              带入主回测当前配置
            </Button>
          </div>
        </div>
        <div className="summary-strip summary-strip--compact advanced-lab-hero__metrics">
          {heroStats.map((item) => (
            <div key={item.label} className="summary-strip__item">
              <span className="summary-strip__label">{item.label}</span>
              <span className="summary-strip__value">{item.value}</span>
            </div>
          ))}
        </div>
        <div className="advanced-lab-hero__lanes">
          {workflowLanes.map((lane) => (
            <div key={lane.eyebrow} className="advanced-lab-hero__lane">
              <div className="advanced-lab-hero__lane-eyebrow">{lane.eyebrow}</div>
              <div className="advanced-lab-hero__lane-title">{lane.title}</div>
              <div className="advanced-lab-hero__lane-description">{lane.description}</div>
            </div>
          ))}
        </div>
        <Space wrap className="advanced-lab-hero__tags">
          <Tag color="geekblue">模板驱动</Tag>
          <Tag color="cyan">{strategies.length} 个策略可用</Tag>
          <Tag color={lab.batchLoading || lab.walkLoading ? 'processing' : 'default'}>
            {lab.batchLoading || lab.walkLoading ? '实验运行中' : '状态稳定'}
          </Tag>
          {hasResults ? <Tag color="success">已有结果可复盘</Tag> : null}
        </Space>
        {lab.importedMainDraftSummary ? (
          <Alert
            type="success"
            showIcon
            style={{ marginTop: 16 }}
            message={`已同步主回测配置：${lab.importedMainDraftSummary.symbol} · ${lab.importedMainDraftSummary.strategyLabel}`}
            description={`区间 ${lab.importedMainDraftSummary.dateRangeLabel}。本次覆盖字段：${lab.importedMainDraftSummary.changedFields.join('、')}。`}
          />
        ) : null}
      </div>

      <div className="advanced-lab-layout">
        <aside className="advanced-lab-sidebar">
          <div className="advanced-lab-section__heading advanced-lab-section__heading--sidebar">
            <div className="app-page-section-kicker">实验控制台</div>
            <div className="advanced-lab-section__title">模板、版本与研究工具</div>
            <div className="advanced-lab-section__description">
              先把模板、版本和研究标的池准备好，再决定这一轮实验要跑什么、比较什么、保存什么。
            </div>
          </div>
          <div className="advanced-lab-sidebar__stack">
            <TemplateManagerSection
              compact
              templateName={lab.templateName}
              setTemplateName={lab.setTemplateName}
              templateNote={lab.templateNote}
              setTemplateNote={lab.setTemplateNote}
              templateCategoryFilter={lab.templateCategoryFilter}
              setTemplateCategoryFilter={lab.setTemplateCategoryFilter}
              selectedTemplateId={lab.selectedTemplateId}
              setSelectedTemplateId={lab.setSelectedTemplateId}
              groupedTemplateOptions={lab.groupedTemplateOptions}
              handleSaveTemplate={lab.handleSaveTemplate}
              handleSuggestTemplateName={lab.handleSuggestTemplateName}
              handleApplyTemplate={lab.handleApplyTemplate}
              handleImportTemplateToMainBacktest={lab.handleImportTemplateToMainBacktest}
              handleOverwriteTemplate={lab.handleOverwriteTemplate}
              handleTogglePinnedTemplate={lab.handleTogglePinnedTemplate}
              handleDeleteTemplate={lab.handleDeleteTemplate}
              savedTemplates={lab.savedTemplates}
              selectedTemplate={lab.selectedTemplate}
              selectedTemplatePreview={lab.selectedTemplatePreview}
              selectedSnapshotId={lab.selectedSnapshotId}
              setSelectedSnapshotId={lab.setSelectedSnapshotId}
              savedSnapshots={lab.savedSnapshots}
              handleSaveSnapshot={lab.handleSaveSnapshot}
              currentSnapshot={lab.currentSnapshot}
              experimentComparison={lab.experimentComparison}
            />

            <ResearchToolsPanel
              compact
              researchSymbolsInput={lab.researchSymbolsInput}
              setResearchSymbolsInput={lab.setResearchSymbolsInput}
              optimizationDensity={lab.optimizationDensity}
              setOptimizationDensity={lab.setOptimizationDensity}
              portfolioObjective={lab.portfolioObjective}
              setPortfolioObjective={lab.setPortfolioObjective}
              batchLoading={lab.batchLoading}
              benchmarkLoading={lab.benchmarkLoading}
              marketRegimeLoading={lab.marketRegimeLoading}
              portfolioLoading={lab.portfolioLoading}
              handleRunParameterOptimization={lab.handleRunParameterOptimization}
              handleRunBenchmarkComparison={lab.handleRunBenchmarkComparison}
              handleRunMultiSymbolResearch={lab.handleRunMultiSymbolResearch}
              handleRunCostSensitivity={lab.handleRunCostSensitivity}
              handleRunRobustnessDiagnostic={lab.handleRunRobustnessDiagnostic}
              handleRunMarketRegimeAnalysis={lab.handleRunMarketRegimeAnalysis}
              handleRunPortfolioStrategy={lab.handleRunPortfolioStrategy}
            />
          </div>
        </aside>

        <div className="advanced-lab-main">
          <div className="advanced-lab-section">
            <div className="advanced-lab-section__heading">
              <div className="app-page-section-kicker">主画布</div>
              <div className="advanced-lab-section__title">按阶段切换实验视角</div>
              <div className="advanced-lab-section__description">
                先在执行区配置实验，再切到结果、研究判断和外部对照，避免一次性背负整页信息。
              </div>
            </div>
            <Segmented
              block
              options={panelOptions}
              value={activePanel}
              onChange={setActivePanel}
              style={{ marginBottom: 20 }}
            />
            {renderMainPanel()}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdvancedBacktestLab;
