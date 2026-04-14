import React from 'react';
import {
  Card, Spin, Alert, Typography, Empty, Button,
  Skeleton
} from 'antd';
import { FundOutlined } from '@ant-design/icons';
import ResearchPlaybook from './research-playbook/ResearchPlaybook';
import {
  GapHistoryCard,
  GapOverview,
  PeerComparisonCard,
  PricingScreenerCard,
  SensitivityAnalysisCard,
} from './pricing/PricingOverviewSections';
import { DriversCard, ImplicationsCard, PeopleLayerCard, StructuralDecayCard } from './pricing/PricingInsightCards';
import { FactorModelCard, ValuationCard } from './pricing/PricingModelCards';
import PricingResultsSection from './pricing/PricingResultsSection';
import PricingSearchPanel from './pricing/PricingSearchPanel';
import { formatResearchSource, navigateByResearchAction } from '../utils/researchContext';
import usePricingResearchData from './pricing/usePricingResearchData';

const { Title, Paragraph } = Typography;

/**
 * 定价研究面板
 * 整合因子模型分析、内在价值估值和定价差异分析
 */
const PricingResearch = () => {
  const {
    data,
    error,
    filteredScreeningResults,
    gapHistory,
    gapHistoryError,
    gapHistoryLoading,
    handleAnalyze,
    handleApplyPreset,
    handleExportAudit,
    handleExportReport,
    handleExportScreening,
    handleInspectScreeningResult,
    handleKeyPress,
    handleOpenMacroMispricingDraft,
    handleOpenRecentResearchTask,
    handleReturnToWorkbenchNextTask,
    handleRunScreener,
    handleRunSensitivity,
    handleSaveTask,
    handleSuggestionSelect,
    handleUpdateSnapshot,
    HOT_PRICING_SYMBOLS: hotSymbols,
    loading,
    peerComparison,
    peerComparisonError,
    peerComparisonLoading,
    period,
    playbook,
    recentResearchShortcutCards,
    researchContext,
    canReturnToWorkbenchQueue,
    queueResumeHint,
    savedTaskId,
    savingTask,
    updatingSnapshot,
    screeningError,
    screeningFilter,
    screeningLoading,
    screeningMeta,
    screeningMinScore,
    screeningProgress,
    screeningSector,
    screeningSectors,
    screeningUniverse,
    searchHistory,
    sensitivity,
    sensitivityControls,
    sensitivityError,
    sensitivityLoading,
    setPeriod,
    setScreeningFilter,
    setScreeningMinScore,
    setScreeningSector,
    setScreeningUniverse,
    setSensitivityControls,
    setSymbol,
    suggestions,
    suggestionTagColors,
    symbol,
  } = usePricingResearchData({ navigateByResearchAction });

  return (
    <div data-testid="pricing-research-page">
      <Title level={4} style={{ marginBottom: 16 }}>
        <FundOutlined style={{ marginRight: 8 }} />
        资产定价研究
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 20 }}>
        打通一级市场估值逻辑（DCF / 可比估值）与二级市场因子定价（CAPM / Fama-French），识别定价偏差与驱动因素。
      </Paragraph>

      {researchContext?.source && researchContext?.symbol ? (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message={`来自 ${formatResearchSource(researchContext.source)} 的定价研究建议 · ${playbook?.stageLabel || '待分析'}`}
          description={
            researchContext.note
              ? `${researchContext.symbol} · ${researchContext.note}`
              : `${researchContext.symbol} 已自动带入研究页，当前剧本阶段为 ${playbook?.stageLabel || '待分析'}`
          }
        />
      ) : null}

      {canReturnToWorkbenchQueue ? (
        <Alert
          style={{ marginBottom: 16 }}
          type="success"
          showIcon
          message="当前任务来自工作台复盘队列"
          description="分析完成后，可以直接回到工作台并切到下一条 Pricing 任务，保持同类型连续复盘节奏。"
          action={(
            <Button type="primary" size="small" onClick={handleReturnToWorkbenchNextTask}>
              回到工作台下一条 Pricing 任务
            </Button>
          )}
        />
      ) : null}

      {canReturnToWorkbenchQueue && queueResumeHint ? (
        <Alert
          style={{ marginBottom: 16 }}
          type="success"
          showIcon
          message={queueResumeHint === 'snapshot' ? '当前复盘快照已更新' : '当前复盘任务已保存'}
          description={
            queueResumeHint === 'snapshot'
              ? '这条 Pricing 任务的最新判断已经写回工作台，可以继续推进到同类型队列的下一条。'
              : '这条 Pricing 任务已经落到工作台，可以继续推进到同类型队列的下一条。'
          }
          action={(
            <Button type="primary" size="small" onClick={handleReturnToWorkbenchNextTask}>
              完成当前复盘并继续下一条
            </Button>
          )}
        />
      ) : null}

      {playbook ? (
        <div style={{ marginBottom: 16 }}>
          <ResearchPlaybook
            playbook={playbook}
            onAction={(action) => navigateByResearchAction(action)}
            onSaveTask={handleSaveTask}
            onUpdateSnapshot={data && savedTaskId ? handleUpdateSnapshot : null}
            saveLoading={savingTask}
            updateLoading={updatingSnapshot}
          />
        </div>
      ) : null}

      <PricingSearchPanel
        data={data}
        handleAnalyze={handleAnalyze}
        handleExportAudit={handleExportAudit}
        handleExportReport={handleExportReport}
        handleKeyPress={handleKeyPress}
        handleOpenRecentResearchTask={handleOpenRecentResearchTask}
        handleSuggestionSelect={handleSuggestionSelect}
        hotSymbols={hotSymbols}
        loading={loading}
        period={period}
        recentResearchShortcutCards={recentResearchShortcutCards}
        savingTask={savingTask}
        searchHistory={searchHistory}
        setPeriod={setPeriod}
        setSymbol={setSymbol}
        suggestions={suggestions}
        suggestionTagColors={suggestionTagColors}
        symbol={symbol}
      />

      <PricingScreenerCard
        value={screeningUniverse}
        onChange={setScreeningUniverse}
        onRun={handleRunScreener}
        onInspect={handleInspectScreeningResult}
        loading={screeningLoading}
        error={screeningError}
        period={period}
        results={filteredScreeningResults}
        meta={screeningMeta}
        progress={screeningProgress}
        filter={screeningFilter}
        onFilterChange={setScreeningFilter}
        sectorFilter={screeningSector}
        onSectorFilterChange={setScreeningSector}
        minScore={screeningMinScore}
        onMinScoreChange={setScreeningMinScore}
        sectorOptions={screeningSectors}
        onApplyPreset={handleApplyPreset}
        onExport={handleExportScreening}
      />

      {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {loading && (
        <Card style={{ marginBottom: 16 }}>
          <Skeleton active paragraph={{ rows: 8 }} />
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: '#8c8c8c' }}>
              正在分析 {symbol.toUpperCase()} 的定价模型，首次加载因子数据可能需要10-20秒...
            </div>
          </div>
        </Card>
      )}

      {data && !loading && (
        <PricingResultsSection
          data={data}
          gapHistory={gapHistory}
          gapHistoryError={gapHistoryError}
          gapHistoryLoading={gapHistoryLoading}
          handleAnalyze={handleAnalyze}
          handleInspectScreeningResult={handleInspectScreeningResult}
          handleOpenMacroMispricingDraft={handleOpenMacroMispricingDraft}
          handleRunSensitivity={handleRunSensitivity}
          peerComparison={peerComparison}
          peerComparisonError={peerComparisonError}
          peerComparisonLoading={peerComparisonLoading}
          sensitivity={sensitivity}
          sensitivityControls={sensitivityControls}
          sensitivityError={sensitivityError}
          sensitivityLoading={sensitivityLoading}
          setSensitivityControls={setSensitivityControls}
          symbol={symbol}
        />
      )}

      {!data && !loading && !error && (
        <Empty
          description="输入股票代码开始定价研究分析"
          style={{ padding: 80 }}
        />
      )}
    </div>
  );
};

export {
  FactorModelCard,
  ValuationCard,
  GapHistoryCard,
  GapOverview,
  DriversCard,
  ImplicationsCard,
  PeopleLayerCard,
  StructuralDecayCard,
  PeerComparisonCard,
  PricingScreenerCard,
  SensitivityAnalysisCard,
};

export default PricingResearch;
