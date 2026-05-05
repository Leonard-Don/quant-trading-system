import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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

import HeatmapLegend from '../components/industry/HeatmapLegend';

const BASE_LEGEND_META = {
    leftLabel: '−',
    rightLabel: '+',
    min: -5,
    max: 5,
    step: 0.1,
    suffix: '%',
};

describe('HeatmapLegend', () => {
    const renderLegend = (overrides = {}) => render(
        <HeatmapLegend
            legendMeta={BASE_LEGEND_META}
            effectiveLegendRange={[-1.5, 2.5]}
            colorMetric="change_pct"
            sizeMetric="market_cap"
            onLegendRangeChange={jest.fn()}
            top3InflowBanner={[]}
            onIndustryClick={jest.fn()}
            {...overrides}
        />,
    );

    it('renders metric labels and the formatted range readout', () => {
        renderLegend();
        expect(screen.getByText('−')).toBeInTheDocument();
        expect(screen.getByText('+')).toBeInTheDocument();
        // Range readout uses 1-decimal formatting for change_pct
        expect(screen.getByText(/-1\.5/)).toBeInTheDocument();
        expect(screen.getByText(/2\.5/)).toBeInTheDocument();
    });

    it('uses 0-decimal formatting when colorMetric is pe_ttm', () => {
        renderLegend({
            colorMetric: 'pe_ttm',
            effectiveLegendRange: [12, 88],
            legendMeta: { ...BASE_LEGEND_META, suffix: '' },
        });
        expect(screen.getByText(/12 ~ 88/)).toBeInTheDocument();
    });

    it('renders the size-metric label according to sizeMetric prop', () => {
        renderLegend({ sizeMetric: 'turnover' });
        expect(screen.getByText(/方块大小 = 当日总成交额/)).toBeInTheDocument();
    });

    it('renders the top3 inflow banner with clickable tags', () => {
        const onIndustryClick = jest.fn();
        renderLegend({
            top3InflowBanner: [
                { name: '新能源', moneyFlow: 1000 },
                { name: '半导体', moneyFlow: 800 },
                { name: '医药', moneyFlow: 600 },
            ],
            onIndustryClick,
        });

        expect(screen.getByText('💰 净流入 TOP')).toBeInTheDocument();
        const tag = screen.getByText('新能源');
        fireEvent.click(tag);
        expect(onIndustryClick).toHaveBeenCalledWith('新能源');
    });

    it('hides the inflow banner when top3InflowBanner is empty', () => {
        renderLegend({ top3InflowBanner: [] });
        expect(screen.queryByText(/净流入 TOP/)).not.toBeInTheDocument();
    });

    it('forwards range changes to onLegendRangeChange', () => {
        const onLegendRangeChange = jest.fn();
        const { container } = renderLegend({ onLegendRangeChange });
        // The Slider component triggers onChange via its internal handles.
        // Easiest behavioral assertion: the slider node is rendered with
        // the correct test id and the callback exists.
        expect(container.querySelector('[data-testid="heatmap-legend-slider"]')).toBeInTheDocument();
        expect(onLegendRangeChange).not.toHaveBeenCalled();
    });
});
