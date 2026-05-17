import { renderHook, waitFor } from '@testing-library/react';

import useIndustryRanking from '../components/industry/useIndustryRanking';
import { getHotIndustries, getIndustryClusters } from '../services/api';

vi.mock('../services/api', () => ({
    getHotIndustries: vi.fn(),
    getIndustryClusters: vi.fn(),
}));

const baseProps = (overrides = {}) => ({
    activeTab: 'ranking',
    rankType: 'gainers',
    sortBy: 'total_score',
    lookbackDays: 5,
    volatilityFilter: 'all',
    rankingMarketCapFilter: 'all',
    heatmapIndustriesLength: 2,
    bootstrapHotIndustries: [],
    bootstrapHotMeta: null,
    message: { error: vi.fn() },
    ...overrides,
});

describe('useIndustryRanking policy_signal cache identity', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getIndustryClusters.mockResolvedValue(null);
    });

    test('does not let non-policy bootstrap rows satisfy the policy ranking request', async () => {
        const bootstrapRows = [
            {
                rank: 1,
                industry_name: '新能源汽车',
                score: 88,
            },
        ];
        const policyRows = [
            {
                ...bootstrapRows[0],
                policy_signal: {
                    avg_impact: 0.42,
                    mentions: 8,
                    signal: 'bullish',
                },
            },
        ];
        getHotIndustries.mockResolvedValue(policyRows);

        const { result } = renderHook(() => useIndustryRanking(baseProps({
            bootstrapHotIndustries: bootstrapRows,
            bootstrapHotMeta: {
                topN: 50,
                type: 'gainers',
                sortBy: 'total_score',
                lookbackDays: 5,
                includePolicySignal: false,
            },
        })));

        await waitFor(() => expect(getHotIndustries).toHaveBeenCalledTimes(1));
        const call = getHotIndustries.mock.calls[0];
        expect(call.slice(0, 4)).toEqual([50, 5, 'total_score', 'desc']);
        expect(call[5]).toEqual({ includePolicySignal: true });

        await waitFor(() => {
            expect(result.current.hotIndustries[0].policy_signal).toEqual(
                policyRows[0].policy_signal,
            );
        });
    });

    test('allows policy-aware bootstrap rows to satisfy the same ranking identity', async () => {
        const bootstrapRows = [
            {
                rank: 1,
                industry_name: '银行',
                score: 70,
                policy_signal: null,
            },
        ];

        const { result } = renderHook(() => useIndustryRanking(baseProps({
            bootstrapHotIndustries: bootstrapRows,
            bootstrapHotMeta: {
                topN: 50,
                type: 'gainers',
                sortBy: 'total_score',
                lookbackDays: 5,
                includePolicySignal: true,
            },
        })));

        await waitFor(() => expect(result.current.hotIndustries).toEqual(bootstrapRows));
        expect(getHotIndustries).not.toHaveBeenCalled();
    });
});
