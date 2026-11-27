import { buildXlsx } from '../utils/xlsx';
import { formatBacktestForExport } from '../utils/export';
import { formatCurrency } from '../utils/formatting';

describe('buildXlsx', () => {
  it('produces a zip package with workbook and sheet parts', () => {
    const bytes = buildXlsx([{ name: '回测指标', rows: [['指标', '数值'], ['夏普', 1.25], ['备注', 'a<b&c']] }]);
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x50, 0x4b, 0x03, 0x04]);
    const text = new TextDecoder().decode(bytes);
    expect(text).toContain('xl/workbook.xml');
    expect(text).toContain('<c r="B2"><v>1.25</v></c>');
    expect(text).toContain('a&lt;b&amp;c');
    expect(text).toContain('name="回测指标"');
  });
});

describe('currency formatting', () => {
  it('formats CNY amounts with the yuan sign', () => {
    expect(formatCurrency(9270.12, 'CNY')).toBe('¥9,270.12');
    expect(formatCurrency(9270.12)).toBe('$9,270.12');
  });

  it('labels A-share export capital in yuan', () => {
    const { metrics } = formatBacktestForExport({
      symbol: '600519.SS',
      initial_capital: 10000,
      final_value: 9270.12,
    });
    const finalValue = metrics.find((item) => item.metric === '最终资金');
    expect(finalValue.value.startsWith('¥')).toBe(true);
  });
});
