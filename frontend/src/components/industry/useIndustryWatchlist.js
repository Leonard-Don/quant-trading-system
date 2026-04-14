import { useMemo } from 'react';

export default function useIndustryWatchlist({
    filteredHotIndustries,
    focusIndustrySuggestions,
    heatmapIndustries,
    hotIndustries,
    rawIndustryAlerts,
    replayComparison,
    selectedIndustry,
    watchlistIndustries,
}) {
    const watchlistAlertByIndustry = useMemo(
        () => new Map(rawIndustryAlerts.map((item) => [item.industry_name, item])),
        [rawIndustryAlerts]
    );

    const watchlistEntries = useMemo(() => {
        const rankingCandidates = [...(hotIndustries || []), ...(filteredHotIndustries || [])];
        return watchlistIndustries.map((industryName) => {
            const rankingSnapshot = rankingCandidates.find((item) => item?.industry_name === industryName) || null;
            const heatmapSnapshot = (heatmapIndustries || []).find((item) => item?.name === industryName) || null;
            const replayDiff = replayComparison?.detailsByIndustry?.get(industryName) || null;
            const alert = watchlistAlertByIndustry.get(industryName) || null;

            return {
                industryName,
                score: rankingSnapshot?.score
                    ?? rankingSnapshot?.total_score
                    ?? heatmapSnapshot?.total_score
                    ?? null,
                change_pct: rankingSnapshot?.change_pct
                    ?? heatmapSnapshot?.value
                    ?? null,
                money_flow: rankingSnapshot?.money_flow
                    ?? heatmapSnapshot?.moneyFlow
                    ?? null,
                turnoverRate: heatmapSnapshot?.turnoverRate ?? null,
                volatility: rankingSnapshot?.industryVolatility
                    ?? heatmapSnapshot?.industryVolatility
                    ?? null,
                leadingStock: heatmapSnapshot?.leadingStock || null,
                alert,
                replayDiff,
            };
        });
    }, [filteredHotIndustries, heatmapIndustries, hotIndustries, replayComparison, watchlistAlertByIndustry, watchlistIndustries]);

    const watchlistSuggestions = useMemo(() => {
        const seen = new Set(watchlistIndustries);
        const suggestions = [];
        const maybePush = (name) => {
            if (!name || seen.has(name)) return;
            seen.add(name);
            suggestions.push(name);
        };

        if (selectedIndustry) maybePush(selectedIndustry);
        rawIndustryAlerts.slice(0, 4).forEach((item) => maybePush(item.industry_name));
        focusIndustrySuggestions.forEach((name) => maybePush(name));
        return suggestions.slice(0, 5);
    }, [focusIndustrySuggestions, rawIndustryAlerts, selectedIndustry, watchlistIndustries]);

    return {
        watchlistEntries,
        watchlistSuggestions,
    };
}
