import React from 'react';
import { Col, Row } from 'antd';

import {
  GapHistoryCard,
  GapOverview,
  PeerComparisonCard,
  SensitivityAnalysisCard,
} from './PricingOverviewSections';
import { DriversCard, ImplicationsCard } from './PricingInsightCards';
import { FactorModelCard, ValuationCard } from './PricingModelCards';

const PricingResultsSection = ({
  data,
  gapHistory,
  gapHistoryError,
  gapHistoryLoading,
  handleAnalyze,
  handleInspectScreeningResult,
  handleRunSensitivity,
  peerComparison,
  peerComparisonError,
  peerComparisonLoading,
  sensitivity,
  sensitivityControls,
  sensitivityError,
  sensitivityLoading,
  setSensitivityControls,
  symbol,
}) => {
  if (!data) return null;

  return (
    <>
      <GapOverview data={data} />

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <FactorModelCard data={data.factor_model} />
        </Col>
        <Col xs={24} lg={12}>
          <ValuationCard data={data.valuation} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <DriversCard data={data.deviation_drivers} />
        </Col>
        <Col xs={24} lg={12}>
          <ImplicationsCard
            data={data.implications}
            valuation={data.valuation}
            factorModel={data.factor_model}
            gapAnalysis={data.gap_analysis}
            onRetry={handleAnalyze}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <SensitivityAnalysisCard
            symbol={symbol}
            loading={sensitivityLoading}
            error={sensitivityError}
            sensitivity={sensitivity}
            controls={sensitivityControls}
            onControlChange={setSensitivityControls}
            onRun={handleRunSensitivity}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <GapHistoryCard
            loading={gapHistoryLoading}
            error={gapHistoryError}
            historyData={gapHistory}
          />
        </Col>
        <Col xs={24} lg={12}>
          <PeerComparisonCard
            loading={peerComparisonLoading}
            error={peerComparisonError}
            peerComparison={peerComparison}
            onInspect={handleInspectScreeningResult}
          />
        </Col>
      </Row>
    </>
  );
};

export default PricingResultsSection;
