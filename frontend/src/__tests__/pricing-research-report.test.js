import {
  buildPricingResearchAuditPayload,
  buildPricingResearchReportHtml,
  openPricingResearchPrintWindow,
} from '../utils/pricingResearchReport';

describe('pricingResearchReport', () => {
  test('builds printable pricing research report html with core sections', () => {
    const html = buildPricingResearchReportHtml({
      symbol: 'AAPL',
      period: '1y',
      generatedAt: '2026-03-30 10:00:00',
      context: { source: 'research-workbench' },
      analysis: {
        symbol: 'AAPL',
        summary: '当前研究显示定价存在明显低估。',
        gap_analysis: {
          current_price: 102.4,
          fair_value_mid: 118.5,
          fair_value_low: 96.2,
          fair_value_high: 131.4,
          gap_pct: -13.6,
          direction: '低估',
        },
        factor_model: {
          period: '1y',
          data_points: 180,
          capm: { alpha_pct: 3.1, beta: 0.92 },
          fama_french: { alpha_pct: 2.4 },
          fama_french_five_factor: { alpha_pct: 2.1 },
        },
        valuation: {
          current_price_source: 'live',
          dcf: {
            intrinsic_value: 120.4,
            scenarios: [
              { label: '悲观', intrinsic_value: 96.2, premium_discount: 6.1, assumptions: { wacc: 0.093, initial_growth: 0.08 } },
              { label: '基准', intrinsic_value: 118.5, premium_discount: -13.6, assumptions: { wacc: 0.082, initial_growth: 0.12 } },
            ],
          },
          comparable: {
            fair_value: 116.2,
            benchmark_source: '动态同行中位数',
            methods: [
              { method: 'P/E 倍数法', current_multiple: 22.1, benchmark_multiple: 25.4, fair_value: 114.2 },
            ],
          },
          fair_value: {
            method: 'DCF + 可比估值加权',
          },
        },
        deviation_drivers: {
          primary_driver: {
            factor: 'P/E 倍数法折价',
            ranking_reason: '相对同行中位数折价最明显，说明市场给予的倍数仍偏保守。',
          },
        },
        implications: {
          primary_view: '低估',
          confidence: 'high',
          confidence_score: 0.84,
          factor_alignment: { label: '同向' },
          trade_setup: {
            stance: '关注做多修复',
            target_price: 118.5,
            stop_loss: 95.0,
            risk_reward: 1.9,
          },
          confidence_breakdown: [
            { label: '证据共振', delta: 0.12, status: 'positive', detail: '因子与估值方向一致' },
          ],
        },
      },
      snapshot: {
        audit_trail: {
          price_source: 'live',
          factor_source: 'ff3_live',
          comparable_benchmark_source: 'peer_median',
        },
      },
      sensitivity: {
        selected_case: { label: '自定义' },
      },
      history: {
        history: [
          { date: '2026-03-28', price: 100.1, gap_pct: -15.4 },
        ],
      },
      peerComparison: {
        target: { symbol: 'AAPL', current_price: 102.4, fair_value: 118.5, premium_discount: -13.6 },
        peers: [
          { symbol: 'MSFT', current_price: 410.1, fair_value: 399.8, premium_discount: 2.6 },
        ],
      },
    });

    expect(html).toContain('定价研究报告');
    expect(html).toContain('执行摘要');
    expect(html).toContain('估值细节');
    expect(html).toContain('置信度拆解');
    expect(html).toContain('AAPL');
    expect(html).toContain('关注做多修复');
    expect(html).toContain('动态同行中位数');
  });

  test('builds audit payload with snapshot and raw analysis', () => {
    const payload = buildPricingResearchAuditPayload({
      symbol: 'AAPL',
      period: '6mo',
      context: { source: 'pricing' },
      analysis: { summary: 'test' },
      snapshot: { audit_trail: { price_source: 'live' } },
      playbook: { stageLabel: '估值锚点' },
      sensitivity: { selected_case: { label: '乐观' } },
      history: { summary: { latest_gap_pct: -12.3 } },
      peerComparison: { sector: 'Technology' },
    });

    expect(payload.symbol).toBe('AAPL');
    expect(payload.period).toBe('6mo');
    expect(payload.snapshot.audit_trail.price_source).toBe('live');
    expect(payload.analysis.summary).toBe('test');
    expect(payload.peer_comparison.sector).toBe('Technology');
    expect(payload.exported_at).toBeTruthy();
  });

  test('opens a printable window for pricing report', () => {
    const write = jest.fn();
    const focus = jest.fn();
    const mockWindow = {
      opener: 'something',
      document: {
        open: jest.fn(),
        write,
        close: jest.fn(),
      },
      focus,
    };
    const windowOpenSpy = jest.spyOn(window, 'open').mockReturnValue(mockWindow);

    const result = openPricingResearchPrintWindow('<html><body>report</body></html>');

    expect(result).toBe(true);
    expect(windowOpenSpy).toHaveBeenCalledWith('', '_blank');
    expect(write).toHaveBeenCalledWith('<html><body>report</body></html>');
    expect(mockWindow.opener).toBeNull();

    windowOpenSpy.mockRestore();
  });
});
