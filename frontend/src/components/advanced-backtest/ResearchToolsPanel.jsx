import React from 'react';
import { Button, Card, Col, Input, InputNumber, Row, Select } from 'antd';

function ResearchToolsPanel({
  compact = false,
  researchSymbolsInput,
  setResearchSymbolsInput,
  optimizationDensity,
  setOptimizationDensity,
  portfolioObjective,
  setPortfolioObjective,
  batchLoading,
  benchmarkLoading,
  marketRegimeLoading,
  portfolioLoading,
  handleRunParameterOptimization,
  handleRunBenchmarkComparison,
  handleRunMultiSymbolResearch,
  handleRunCostSensitivity,
  handleRunRobustnessDiagnostic,
  handleRunMarketRegimeAnalysis,
  handleRunPortfolioStrategy,
}) {
  return (
    <Card className={`workspace-panel advanced-lab-tool-panel${compact ? ' advanced-lab-tool-panel--compact' : ''}`}>
      <div className="workspace-section__header">
        <div>
          <div className="workspace-section__title">研究增强工具</div>
          <div className="workspace-section__description">把参数寻优、基准对照、多标的研究、成本敏感性、稳健性诊断和组合级策略回测收进同一组实验模板。</div>
        </div>
      </div>
      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} xl={compact ? 24 : 10}>
          <div className="workspace-field-label">研究标的池</div>
          <Input
            value={researchSymbolsInput}
            onChange={(event) => setResearchSymbolsInput(event.target.value)}
            placeholder="用逗号分隔标的，例如 AAPL,MSFT,NVDA"
          />
          <div className="workspace-section__hint" style={{ marginTop: 8 }}>
            参数寻优、基准对照会优先使用当前滚动前瞻表单里的单一标的；多标的和组合级回测会读取这里的标的池。
          </div>
        </Col>
        <Col xs={12} xl={compact ? 12 : 4}>
          <div className="workspace-field-label">寻优密度</div>
          <InputNumber
            min={3}
            max={5}
            precision={0}
            style={{ width: '100%' }}
            value={optimizationDensity}
            onChange={(value) => setOptimizationDensity(Number(value || 3))}
          />
        </Col>
        <Col xs={12} xl={compact ? 12 : 4}>
          <div className="workspace-field-label">组合权重模式</div>
          <Select
            value={portfolioObjective}
            style={{ width: '100%' }}
            options={[
              { value: 'equal_weight', label: '等权组合' },
              { value: 'max_sharpe', label: '最大夏普' },
              { value: 'min_volatility', label: '最小波动' },
            ]}
            onChange={setPortfolioObjective}
          />
        </Col>
        <Col xs={24} xl={compact ? 24 : 6}>
          <div className={`advanced-lab-tool-panel__actions${compact ? ' advanced-lab-tool-panel__actions--compact' : ''}`}>
            <Button onClick={handleRunParameterOptimization} loading={batchLoading}>参数寻优</Button>
            <Button onClick={handleRunBenchmarkComparison} loading={benchmarkLoading}>基准对照</Button>
            <Button onClick={handleRunMultiSymbolResearch} loading={batchLoading}>多标的研究</Button>
            <Button onClick={handleRunCostSensitivity} loading={batchLoading}>成本敏感性</Button>
            <Button onClick={handleRunRobustnessDiagnostic} loading={batchLoading}>稳健性诊断</Button>
            <Button onClick={handleRunMarketRegimeAnalysis} loading={marketRegimeLoading}>市场状态</Button>
            <Button type="primary" onClick={handleRunPortfolioStrategy} loading={portfolioLoading}>组合级策略回测</Button>
          </div>
        </Col>
      </Row>
    </Card>
  );
}

export default ResearchToolsPanel;
