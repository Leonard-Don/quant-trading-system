import {
  buildStrategyComparisonReportHtml,
  openStrategyComparisonPrintWindow,
} from '../utils/strategyComparisonReport';

describe('strategyComparisonReport', () => {
  test('builds Chinese comparison report content', () => {
    const html = buildStrategyComparisonReportHtml({
      symbol: 'TSLA',
      startDate: '2025-03-18',
      endDate: '2026-03-18',
      generatedAt: '2026-03-18 12:00:00',
      initialCapital: '$25,000',
      commission: '0.2%',
      slippage: '0.15%',
      rankedData: [
        {
          strategyName: '买入持有',
          total_return: 0.12,
          sharpe_ratio: 1.23,
          scores: { overall_score: 88 },
        },
      ],
      dataSource: [
        {
          strategyName: '买入持有',
          total_return: 0.12,
          annualized_return: 0.15,
          max_drawdown: -0.08,
          sharpe_ratio: 1.23,
          num_trades: 1,
          parameters: { fast_period: 8, slow_period: 21 },
        },
      ],
    });

    expect(html).toContain('策略对比报告');
    expect(html).toContain('买入持有');
    expect(html).toContain('TSLA');
    expect(html).toContain('总收益率');
    expect(html).toContain('参数版本');
    expect(html).toContain('快速周期：8');
    expect(html).toContain('初始资金 $25,000');
  });

  test('opens printable report window and writes HTML into it', () => {
    const documentApi = {
      open: jest.fn(),
      write: jest.fn(),
      close: jest.fn(),
    };
    const popupWindow = {
      document: documentApi,
      focus: jest.fn(),
      opener: {},
    };
    const openSpy = jest.spyOn(window, 'open').mockReturnValue(popupWindow);

    const opened = openStrategyComparisonPrintWindow('<html><body>策略对比报告</body></html>');

    expect(opened).toBe(true);
    expect(openSpy).toHaveBeenCalledWith('', '_blank');
    expect(popupWindow.opener).toBeNull();
    expect(documentApi.open).toHaveBeenCalled();
    expect(documentApi.write).toHaveBeenCalledWith('<html><body>策略对比报告</body></html>');
    expect(documentApi.close).toHaveBeenCalled();
    expect(popupWindow.focus).toHaveBeenCalled();

    openSpy.mockRestore();
  });
});
