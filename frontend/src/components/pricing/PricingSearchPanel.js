import React from 'react';
import { AutoComplete, Button, Card, Col, Input, Row, Select, Space, Tag, Typography } from 'antd';
import { DownloadOutlined, ExperimentOutlined, SearchOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { Option } = Select;

export default function PricingSearchPanel({
  data,
  handleAnalyze,
  handleExportAudit,
  handleExportReport,
  handleKeyPress,
  handleOpenRecentResearchTask,
  handleSuggestionSelect,
  period,
  loading,
  recentResearchShortcutCards,
  searchHistory,
  setPeriod,
  setSymbol,
  suggestions,
  symbol,
  suggestionTagColors,
  hotSymbols,
}) {
  return (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Space size="middle" wrap style={{ width: '100%' }}>
        <AutoComplete
          options={suggestions.map((option) => ({
            value: option.value,
            taskId: option.taskId,
            period: option.period,
            label: (
              <Space direction="vertical" size={0}>
                <Space size={6}>
                  <Text strong>{option.value}</Text>
                  {option.richLabel?.recent ? <Tag color="gold">最近研究</Tag> : null}
                  {option.richLabel?.primaryView ? (
                    <Tag color={option.richLabel.primaryView === '低估' ? 'green' : option.richLabel.primaryView === '高估' ? 'red' : 'default'}>
                      {option.richLabel.primaryView}
                    </Tag>
                  ) : null}
                  {option.richLabel?.confidenceLabel ? <Tag>{`置信度 ${option.richLabel.confidenceLabel}`}</Tag> : null}
                  {option.richLabel?.factorAlignmentLabel ? (
                    <Tag color={suggestionTagColors[option.richLabel.factorAlignmentStatus] || 'default'}>
                      {option.richLabel.factorAlignmentLabel}
                    </Tag>
                  ) : null}
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{option.richLabel?.name}</Text>
                {option.richLabel?.group ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {option.richLabel.group}{option.richLabel.market ? ` · ${option.richLabel.market}` : ''}
                  </Text>
                ) : null}
                {option.richLabel?.period || option.richLabel?.headline || option.richLabel?.summary ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {[option.richLabel.period ? `窗口 ${option.richLabel.period}` : '', option.richLabel.headline || option.richLabel.summary].filter(Boolean).join(' · ')}
                  </Text>
                ) : null}
                {option.richLabel?.primaryDriver ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {`主驱动 ${option.richLabel.primaryDriver}`}
                  </Text>
                ) : null}
                {option.richLabel?.taskId ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    点击将直接打开对应研究任务
                  </Text>
                ) : null}
              </Space>
            ),
          }))}
          value={symbol}
          onChange={setSymbol}
          onSelect={handleSuggestionSelect}
          style={{ width: 320 }}
        >
          <Input
            data-testid="pricing-symbol-input"
            placeholder="输入股票代码或公司名，如 AAPL / Apple"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyPress={handleKeyPress}
            prefix={<SearchOutlined />}
            allowClear
          />
        </AutoComplete>
        <Select data-testid="pricing-period-select" value={period} onChange={setPeriod} style={{ width: 120 }}>
          <Option value="6mo">近6个月</Option>
          <Option value="1y">近1年</Option>
          <Option value="2y">近2年</Option>
          <Option value="3y">近3年</Option>
        </Select>
        <Button
          data-testid="pricing-analyze-button"
          type="primary"
          icon={<ExperimentOutlined />}
          onClick={handleAnalyze}
          loading={loading}
        >
          开始分析
        </Button>
        <Button
          data-testid="pricing-export-report-button"
          icon={<DownloadOutlined />}
          onClick={handleExportReport}
          disabled={!data}
        >
          导出研究报告
        </Button>
        <Button
          data-testid="pricing-export-audit-button"
          onClick={handleExportAudit}
          disabled={!data}
        >
          导出审计 JSON
        </Button>
      </Space>
      <Space wrap size={8} style={{ marginTop: 12 }}>
        <Text type="secondary">热门标的:</Text>
        {hotSymbols.map((item) => (
          <Tag
            key={item.symbol}
            style={{ cursor: 'pointer' }}
            onClick={() => setSymbol(item.symbol)}
          >
            {item.symbol}
          </Tag>
        ))}
      </Space>
      {searchHistory.length ? (
        <Space wrap size={8} style={{ marginTop: 8 }}>
          <Text type="secondary">最近搜索:</Text>
          {searchHistory.map((item) => (
            <Tag
              key={item}
              color="blue"
              style={{ cursor: 'pointer' }}
              onClick={() => setSymbol(item)}
            >
              {item}
            </Tag>
          ))}
        </Space>
      ) : null}
      {recentResearchShortcutCards.length ? (
        <div data-testid="pricing-recent-research-shortcuts" style={{ marginTop: 12 }}>
          <Text type="secondary">最近研究捷径:</Text>
          <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
            {recentResearchShortcutCards.map((item) => (
              <Col xs={24} md={12} key={item.task_id || item.symbol}>
                <Button
                  block
                  style={{ height: 'auto', textAlign: 'left', padding: 12 }}
                  onClick={() => handleOpenRecentResearchTask(item)}
                >
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space wrap size={6}>
                      <Text strong>{item.symbol}</Text>
                      {item.primary_view ? (
                        <Tag color={item.primary_view === '低估' ? 'green' : item.primary_view === '高估' ? 'red' : 'default'}>
                          {item.primary_view}
                        </Tag>
                      ) : null}
                      {item.confidence_label ? <Tag>{`置信度 ${item.confidence_label}`}</Tag> : null}
                      {item.factor_alignment_label ? (
                        <Tag color={suggestionTagColors[item.factor_alignment_status] || 'default'}>
                          {item.factor_alignment_label}
                        </Tag>
                      ) : null}
                    </Space>
                    <Text style={{ fontSize: 12 }}>{item.title}</Text>
                    {item.subtitle ? <Text type="secondary" style={{ fontSize: 11 }}>{item.subtitle}</Text> : null}
                    {item.primary_driver ? <Text type="secondary" style={{ fontSize: 11 }}>{`主驱动 ${item.primary_driver}`}</Text> : null}
                    {item.summary ? <Text type="secondary" style={{ fontSize: 11 }}>{item.summary}</Text> : null}
                  </Space>
                </Button>
              </Col>
            ))}
          </Row>
        </div>
      ) : null}
    </Card>
  );
}
