import React from 'react';
import { Button, Col, Row } from 'antd';

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

  return (
    <div className="workspace-tab-view">
      <div className="workspace-section workspace-section--accent">
        <div className="workspace-section__header">
          <div>
            <div className="workspace-section__title">高级实验台</div>
            <div className="workspace-section__description">把批量回测和滚动前瞻分析接进正式工作流，方便做更系统的策略研究。</div>
          </div>
          <Button type="default" onClick={lab.handleApplyMainBacktestDraft}>
            带入主回测当前配置
          </Button>
        </div>
        <div className="summary-strip summary-strip--compact">
          <div className="summary-strip__item">
            <span className="summary-strip__label">实验模块</span>
            <span className="summary-strip__value">批量回测 + 滚动前瞻分析</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">可选策略</span>
            <span className="summary-strip__value">{strategies.length} 个</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">当前状态</span>
            <span className="summary-strip__value">{lab.batchLoading || lab.walkLoading ? '实验运行中' : '待执行'}</span>
          </div>
        </div>
      </div>

      <TemplateManagerSection
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

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={13}>
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
        <Col xs={24} xl={11}>
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

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={13}>
          <BatchBacktestResults
            batchResult={lab.batchResult}
            batchRecords={lab.batchRecords}
            batchRankingData={lab.batchRankingData}
            batchInsight={lab.batchInsight}
            batchExperimentMeta={lab.batchExperimentMeta}
            focusedBatchRecord={lab.focusedBatchRecord}
            focusedBatchTaskId={lab.focusedBatchTaskId}
            setFocusedBatchTaskId={lab.setFocusedBatchTaskId}
            handleSaveBatchHistory={lab.handleSaveBatchHistory}
            handleExportBatch={lab.handleExportBatch}
          />
        </Col>
        <Col xs={24} xl={11}>
          <WalkForwardResults
            walkResult={lab.walkResult}
            walkForwardChartData={lab.walkForwardChartData}
            walkInsight={lab.walkInsight}
            focusedWalkRecord={lab.focusedWalkRecord}
            focusedWalkWindowKey={lab.focusedWalkWindowKey}
            setFocusedWalkWindowKey={lab.setFocusedWalkWindowKey}
            handleSaveWalkHistory={lab.handleSaveWalkHistory}
            handleExportWalkForward={lab.handleExportWalkForward}
          />
        </Col>
      </Row>

      <ResearchInsightsSection
        robustnessScore={lab.robustnessScore}
        overfittingWarnings={lab.overfittingWarnings}
        researchConclusion={lab.researchConclusion}
        marketRegimeResult={lab.marketRegimeResult}
        marketRegimeInsight={lab.marketRegimeInsight}
        marketRegimeChartData={lab.marketRegimeChartData}
        CHART_NEUTRAL={CHART_NEUTRAL}
        CHART_POSITIVE={CHART_POSITIVE}
      />

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={12}>
          <BenchmarkSection
            benchmarkResult={lab.benchmarkResult}
            benchmarkContext={lab.benchmarkContext}
            benchmarkSummary={lab.benchmarkSummary}
            benchmarkChartData={lab.benchmarkChartData}
          />
        </Col>
        <Col xs={24} xl={12}>
          <PortfolioSection
            portfolioStrategyResult={lab.portfolioStrategyResult}
            portfolioChartData={lab.portfolioChartData}
            portfolioPositionSnapshot={lab.portfolioPositionSnapshot}
            portfolioExposureSummary={lab.portfolioExposureSummary}
          />
        </Col>
      </Row>
    </div>
  );
}

export default AdvancedBacktestLab;
