import React from 'react';
import {
  Card, Spin, Alert, Typography, Empty,
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
import { DriversCard, ImplicationsCard } from './pricing/PricingInsightCards';
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
    handleOpenRecentResearchTask,
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
    savedTaskId,
    savingTask,
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

      {playbook ? (
        <div style={{ marginBottom: 16 }}>
          <ResearchPlaybook
            playbook={playbook}
            onAction={(action) => navigateByResearchAction(action)}
            onSaveTask={handleSaveTask}
            onUpdateSnapshot={data && savedTaskId ? handleUpdateSnapshot : null}
            saving={savingTask}
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
  PeerComparisonCard,
  PricingScreenerCard,
  SensitivityAnalysisCard,
};

export default PricingResearch;
