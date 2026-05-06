import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';

if (typeof window.matchMedia !== 'function') {
    window.matchMedia = (query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
    });
}

import HeatmapStatsBar from '../components/industry/HeatmapStatsBar';

const buildData = (overrides = {}) => ({
    update_time: '2026-05-05T08:00:00+00:00',
    industries: [
        { name: '新能源', value: 2.5, moneyFlow: 5_000_000_000 },
        { name: '半导体', value: 1.0, moneyFlow: 3_000_000_000 },
        { name: '医药', value: -0.5, moneyFlow: 2_000_000_000 },
        { name: '银行', value: 0, moneyFlow: -1_000_000_000 },
    ],
    ...overrides,
});

describe('HeatmapStatsBar', () => {
    it('returns null when data has no industries', () => {
        const { container } = render(<HeatmapStatsBar data={{}} />);
        expect(container.firstChild).toBeNull();
    });

    it('counts up / down / flat industries', () => {
        const { container } = render(<HeatmapStatsBar data={buildData()} />);
        const stats = container.querySelectorAll('.ant-statistic-content-value');
        const values = Array.from(stats).map((node) => node.textContent);
        expect(values).toContain('2'); // up: 新能源 + 半导体
        expect(values).toContain('1'); // down: 医药
        expect(values).toContain('1'); // flat: 银行
    });

    it('classifies sentiment as bullish when more than 60% up', () => {
        const data = buildData({
            industries: [
                { name: 'a', value: 1, moneyFlow: 0 },
                { name: 'b', value: 1, moneyFlow: 0 },
                { name: 'c', value: 1, moneyFlow: 0 },
                { name: 'd', value: -1, moneyFlow: 0 },
            ],
        });
        render(<HeatmapStatsBar data={data} />);
        expect(screen.getByText('偏多')).toBeInTheDocument();
    });

    it('classifies sentiment as bearish when fewer than 40% up', () => {
        const data = buildData({
            industries: [
                { name: 'a', value: 1, moneyFlow: 0 },
                { name: 'b', value: -1, moneyFlow: 0 },
                { name: 'c', value: -1, moneyFlow: 0 },
                { name: 'd', value: -1, moneyFlow: 0 },
            ],
        });
        render(<HeatmapStatsBar data={data} />);
        expect(screen.getByText('偏空')).toBeInTheDocument();
    });

    it('classifies sentiment as neutral in the middle band', () => {
        // 2 up / 2 down / 1 flat → ratio = 0.4, lands in neutral [0.4, 0.6]
        const data = buildData({
            industries: [
                { name: 'a', value: 1, moneyFlow: 0 },
                { name: 'b', value: 1, moneyFlow: 0 },
                { name: 'c', value: -1, moneyFlow: 0 },
                { name: 'd', value: -1, moneyFlow: 0 },
                { name: 'e', value: 0, moneyFlow: 0 },
            ],
        });
        render(<HeatmapStatsBar data={data} />);
        expect(screen.getByText('中性')).toBeInTheDocument();
    });

    it('renders top-3 net inflow tags only for positive moneyFlow industries', () => {
        render(<HeatmapStatsBar data={buildData()} />);
        // 银行 has negative moneyFlow, should not appear
        expect(screen.queryByText(/银行/)).not.toBeInTheDocument();
        // 新能源 leads with 50亿
        expect(screen.getByText(/新能源 \+50\.0亿/)).toBeInTheDocument();
        expect(screen.getByText(/半导体 \+30\.0亿/)).toBeInTheDocument();
        expect(screen.getByText(/医药 \+20\.0亿/)).toBeInTheDocument();
    });

    it('clicking an inflow tag forwards the symbol via onIndustryClick', () => {
        const onIndustryClick = vi.fn();
        render(<HeatmapStatsBar data={buildData()} onIndustryClick={onIndustryClick} />);
        fireEvent.click(screen.getByText(/新能源/));
        expect(onIndustryClick).toHaveBeenCalledWith('新能源');
    });

    it('renders "-" for update time when missing', () => {
        const { container } = render(
            <HeatmapStatsBar data={buildData({ update_time: null })} />,
        );
        // Update-time Statistic shows the dash
        expect(container.textContent).toContain('-');
    });

    it('hides the inflow banner when no industries have positive moneyFlow', () => {
        const data = buildData({
            industries: [
                { name: 'a', value: 1, moneyFlow: -1 },
                { name: 'b', value: -1, moneyFlow: -2 },
            ],
        });
        render(<HeatmapStatsBar data={data} />);
        expect(screen.queryByText(/💰 主力净流入/)).not.toBeInTheDocument();
    });
});
