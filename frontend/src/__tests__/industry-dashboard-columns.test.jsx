/**
 * Characterization tests for the column factories extracted out of
 * IndustryDashboard (`buildHotIndustryColumns` / `buildStockColumns`), mirroring
 * the `buildIndustryPolicySignalColumn` test pattern.
 *
 * These guard the new prop-drilling boundary the split introduced: the column
 * `render` callbacks must keep forwarding interactions through the handlers the
 * parent (`IndustryDashboard`) passes in, with the same data-testids / labels
 * the rest of the suite and the UI rely on.
 */

import { render, screen, fireEvent, within } from '@testing-library/react';
import { Table } from 'antd';
import '@testing-library/jest-dom';

import buildHotIndustryColumns from '../components/industry/buildHotIndustryColumns';
import buildStockColumns from '../components/industry/buildStockColumns';

const renderTable = (columns, rows, rowKey) => render(
    <Table dataSource={rows} columns={columns} rowKey={rowKey} pagination={false} />,
);

const noopVolatilityMeta = () => ({ value: 0, color: 'default', label: '', sourceLabel: '', filter: 'all' });

describe('buildHotIndustryColumns (IndustryDashboard split)', () => {
    const baseRow = {
        industry_name: '新能源汽车',
        rank: 1,
        score: 88.5,
        change_pct: 2.31,
        money_flow: 1.2e8,
        momentum: 1.5,
        industryVolatility: 0,
        total_market_cap: 5e11,
        stock_count: 42,
        marketCapSource: 'live',
        policy_signal: null,
    };

    test('score cell forwards the record through onScoreRadarRecord', () => {
        const onScoreRadarRecord = vi.fn();
        const columns = buildHotIndustryColumns({
            getIndustryVolatilityMeta: noopVolatilityMeta,
            onIndustryClick: vi.fn(),
            onJumpToMarketCapFilter: vi.fn(),
            onScoreRadarRecord,
            onAddToComparison: vi.fn(),
        });
        renderTable(columns, [baseRow], 'industry_name');

        fireEvent.click(screen.getByTestId('industry-score-radar-trigger'));
        expect(onScoreRadarRecord).toHaveBeenCalledTimes(1);
        expect(onScoreRadarRecord).toHaveBeenCalledWith(expect.objectContaining({ industry_name: '新能源汽车' }));
    });

    test('market-cap source tag forwards its filter through onJumpToMarketCapFilter', () => {
        const onJumpToMarketCapFilter = vi.fn();
        const columns = buildHotIndustryColumns({
            getIndustryVolatilityMeta: noopVolatilityMeta,
            onIndustryClick: vi.fn(),
            onJumpToMarketCapFilter,
            onScoreRadarRecord: vi.fn(),
            onAddToComparison: vi.fn(),
        });
        renderTable(columns, [baseRow], 'industry_name');

        const sourceTag = screen.getByTestId('industry-market-cap-source-tag');
        fireEvent.click(sourceTag);
        expect(onJumpToMarketCapFilter).toHaveBeenCalledWith('live');
    });

    test('action column forwards 详情 / 对比 clicks to the right handlers', () => {
        const onIndustryClick = vi.fn();
        const onAddToComparison = vi.fn();
        const columns = buildHotIndustryColumns({
            getIndustryVolatilityMeta: noopVolatilityMeta,
            onIndustryClick,
            onJumpToMarketCapFilter: vi.fn(),
            onScoreRadarRecord: vi.fn(),
            onAddToComparison,
        });
        renderTable(columns, [baseRow], 'industry_name');

        fireEvent.click(screen.getByText('详情'));
        expect(onIndustryClick).toHaveBeenCalledWith('新能源汽车');

        fireEvent.click(screen.getByText('对比'));
        expect(onAddToComparison).toHaveBeenCalledWith('新能源汽车');
    });
});

describe('buildStockColumns (IndustryDashboard split)', () => {
    test('回测 action forwards the record + source through onBacktestStock', () => {
        const onBacktestStock = vi.fn();
        const columns = buildStockColumns({ onBacktestStock });
        const row = { symbol: '600519', name: '贵州茅台', rank: 1, total_score: 91 };
        renderTable(columns, [row], 'symbol');

        fireEvent.click(screen.getByText('回测'));
        expect(onBacktestStock).toHaveBeenCalledTimes(1);
        expect(onBacktestStock).toHaveBeenCalledWith(
            expect.objectContaining({ symbol: '600519' }),
            'industry_stock_table',
        );
    });

    test('renders a "-" placeholder for missing score / change_pct', () => {
        const columns = buildStockColumns({ onBacktestStock: vi.fn() });
        const row = { symbol: '000001', name: '平安银行', rank: 2, total_score: null, change_pct: null };
        const { container } = renderTable(columns, [row], 'symbol');

        // The code tag still renders the symbol.
        expect(screen.getByText('000001')).toBeInTheDocument();
        // The body row prints "-" placeholders for the null numeric cells.
        const bodyRow = container.querySelector('tbody tr.ant-table-row');
        expect(within(bodyRow).getAllByText('-').length).toBeGreaterThanOrEqual(2);
    });
});
