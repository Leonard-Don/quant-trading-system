import React from 'react';
import { render, screen } from '@testing-library/react';
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

// Recharts' ResponsiveContainer requires a real layout size, which JSDOM
// doesn't provide. Mock it (and the radar primitives we render) like
// market-analysis.test.js does.
jest.mock('recharts', () => {
    const Mock = () => null;
    return {
        Radar: Mock,
        RadarChart: ({ children }) => <div data-testid="radar-chart">{children}</div>,
        PolarGrid: Mock,
        PolarAngleAxis: Mock,
        PolarRadiusAxis: Mock,
        ResponsiveContainer: ({ children }) => <div>{children}</div>,
        Tooltip: Mock,
    };
});

import {
    RecommendationTag,
    ScoreGauge,
    ScoreRadarChart,
    __TEST_ONLY__,
} from '../components/market-analysis/MarketAnalysisScoreVisuals';

const { colorForScore, colorForRecommendation } = __TEST_ONLY__;

describe('colorForScore', () => {
    it('maps high scores to green', () => {
        expect(colorForScore(90)).toBe('#00b578');
        expect(colorForScore(75)).toBe('#00b578');
    });

    it('maps mid-high scores to blue', () => {
        expect(colorForScore(60)).toBe('#1890ff');
        expect(colorForScore(50)).toBe('#1890ff');
    });

    it('maps mid-low scores to amber', () => {
        expect(colorForScore(40)).toBe('#faad14');
        expect(colorForScore(30)).toBe('#faad14');
    });

    it('maps low scores to red', () => {
        expect(colorForScore(10)).toBe('#ff3030');
        expect(colorForScore(0)).toBe('#ff3030');
    });

    it('falls back to blue on non-numeric input', () => {
        expect(colorForScore(null)).toBe('#1890ff');
        expect(colorForScore('not a number')).toBe('#1890ff');
        expect(colorForScore(undefined)).toBe('#1890ff');
    });
});

describe('colorForRecommendation', () => {
    it('maps 买入 phrases to success', () => {
        expect(colorForRecommendation('强烈买入')).toBe('success');
        expect(colorForRecommendation('买入')).toBe('success');
    });

    it('maps 卖出 phrases to error', () => {
        expect(colorForRecommendation('卖出')).toBe('error');
    });

    it('maps 持有 phrases to warning', () => {
        expect(colorForRecommendation('持有观望')).toBe('warning');
    });

    it('falls back to default for unknown labels', () => {
        expect(colorForRecommendation('unknown')).toBe('default');
        expect(colorForRecommendation('')).toBe('default');
        expect(colorForRecommendation(null)).toBe('default');
    });
});

describe('ScoreGauge / RecommendationTag rendering', () => {
    it('renders the gauge with the score number visible', () => {
        const { container } = render(<ScoreGauge score={68} />);
        // The 68 appears inside the dashboard format()
        expect(container.textContent).toContain('68');
        expect(container.textContent).toContain('综合评分');
    });

    it('renders the recommendation text inside a Tag', () => {
        render(<RecommendationTag recommendation="买入" />);
        expect(screen.getByText('买入')).toBeInTheDocument();
    });
});

describe('ScoreRadarChart', () => {
    it('renders without crashing for a complete score payload', () => {
        const { container } = render(
            <ScoreRadarChart scores={{ trend: 70, volume: 50, sentiment: 30, technical: 60 }} />,
        );
        expect(container.querySelector('.radar-chart-container')).toBeInTheDocument();
    });

    it('substitutes 0 for missing axes', () => {
        const { container } = render(<ScoreRadarChart scores={{ trend: 70 }} />);
        // Just confirms the component handles partial data without throwing
        expect(container.querySelector('.radar-chart-container')).toBeInTheDocument();
    });

    it('handles null scores defensively', () => {
        const { container } = render(<ScoreRadarChart scores={null} />);
        expect(container.querySelector('.radar-chart-container')).toBeInTheDocument();
    });
});
