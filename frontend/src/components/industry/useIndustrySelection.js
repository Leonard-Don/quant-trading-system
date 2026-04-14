import { useCallback, useMemo } from 'react';

import {
    clampNumeric,
    formatIndustryAlertMoneyFlow,
    getMarketCapBadgeMeta,
} from './industryShared';

export default function useIndustrySelection({
    filteredHotIndustries,
    heatmapIndustries,
    hotIndustries,
    industryStocks,
    selectedIndustry,
    watchlistIndustries,
}) {
    const getIndustryVolatilityMeta = useCallback((value, source) => {
        const numericValue = Number(value || 0);
        const tone = numericValue >= 4
            ? { label: '高波动', color: 'error' }
            : numericValue >= 2
                ? { label: '中波动', color: 'warning' }
                : { label: '低波动', color: 'success' };
        const sourceLabelMap = {
            historical_index: '历史指数',
            stock_dispersion: '成分股离散度',
            amplitude_proxy: '振幅代理',
            turnover_rate_proxy: '换手率代理',
            change_proxy: '涨跌幅代理',
            unavailable: '暂无',
        };
        return {
            ...tone,
            value: numericValue,
            sourceLabel: sourceLabelMap[source] || '暂无',
        };
    }, []);

    const selectedIndustrySnapshot = useMemo(() => {
        if (!selectedIndustry) return null;

        const rankingCandidates = [...(hotIndustries || []), ...(filteredHotIndustries || [])];
        const rankingSnapshot = rankingCandidates.find((item) => item?.industry_name === selectedIndustry) || null;
        const heatmapSnapshot = (heatmapIndustries || []).find((item) => item?.name === selectedIndustry) || null;

        if (!rankingSnapshot && !heatmapSnapshot) {
            return null;
        }

        return {
            industry_name: selectedIndustry,
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
            industryVolatility: rankingSnapshot?.industryVolatility
                ?? heatmapSnapshot?.industryVolatility
                ?? null,
            industryVolatilitySource: rankingSnapshot?.industryVolatilitySource
                ?? heatmapSnapshot?.industryVolatilitySource
                ?? 'unavailable',
            total_market_cap: rankingSnapshot?.total_market_cap
                ?? heatmapSnapshot?.size
                ?? null,
            stock_count: rankingSnapshot?.stock_count
                ?? heatmapSnapshot?.stockCount
                ?? null,
            marketCapSource: rankingSnapshot?.marketCapSource
                ?? heatmapSnapshot?.marketCapSource
                ?? 'unknown',
            leadingStock: heatmapSnapshot?.leadingStock || null,
            leadingStockChange: heatmapSnapshot?.leadingStockChange ?? null,
            turnoverRate: heatmapSnapshot?.turnoverRate ?? null,
            netInflowRatio: heatmapSnapshot?.netInflowRatio ?? null,
            pe_ttm: heatmapSnapshot?.pe_ttm ?? null,
            pb: heatmapSnapshot?.pb ?? null,
            valuationSource: heatmapSnapshot?.valuationSource ?? 'unavailable',
            valuationQuality: heatmapSnapshot?.valuationQuality ?? 'unavailable',
            dataSources: heatmapSnapshot?.dataSources ?? [],
        };
    }, [selectedIndustry, hotIndustries, filteredHotIndustries, heatmapIndustries]);

    const selectedIndustryWatched = useMemo(
        () => Boolean(selectedIndustry && watchlistIndustries.includes(selectedIndustry)),
        [selectedIndustry, watchlistIndustries]
    );

    const selectedIndustryMarketCapBadge = useMemo(
        () => (selectedIndustrySnapshot ? getMarketCapBadgeMeta(selectedIndustrySnapshot.marketCapSource) : null),
        [selectedIndustrySnapshot]
    );

    const selectedIndustryVolatilityMeta = useMemo(
        () => getIndustryVolatilityMeta(
            selectedIndustrySnapshot?.industryVolatility,
            selectedIndustrySnapshot?.industryVolatilitySource
        ),
        [selectedIndustrySnapshot, getIndustryVolatilityMeta]
    );

    const selectedIndustryLeadStock = useMemo(
        () => (industryStocks || []).find((item) => item?.name || item?.symbol) || (
            selectedIndustrySnapshot?.leadingStock
                ? {
                    name: selectedIndustrySnapshot.leadingStock,
                    total_score: 0,
                    change_pct: selectedIndustrySnapshot.leadingStockChange,
                }
                : null
        ),
        [industryStocks, selectedIndustrySnapshot]
    );

    const selectedIndustryFocusNarrative = useMemo(() => {
        if (!selectedIndustry) {
            return '';
        }
        if (!selectedIndustrySnapshot) {
            return `${selectedIndustry} 已进入研究焦点，可以继续查看行业详情和龙头股联动。`;
        }

        const score = Number(selectedIndustrySnapshot.score || 0);
        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);

        if (score >= 80 && change > 0 && moneyFlow > 0) {
            return `${selectedIndustry} 当前处于强势共振区间，热度、涨幅和资金方向比较一致。`;
        }
        if (score >= 70 && moneyFlow > 0) {
            return `${selectedIndustry} 目前偏强，资金仍在净流入，适合继续顺着龙头和轮动看。`;
        }
        if (change < 0 && moneyFlow < 0) {
            return `${selectedIndustry} 当前偏弱，价格和资金都在承压，更适合先看风险释放是否结束。`;
        }
        if (volatility >= 4) {
            return `${selectedIndustry} 现在波动偏高，适合重点盯节奏和龙头分化，而不是只看静态排名。`;
        }
        return `${selectedIndustry} 目前处于观察区，适合结合行业详情、龙头表现和轮动位置一起判断。`;
    }, [selectedIndustry, selectedIndustrySnapshot]);

    const selectedIndustryReasons = useMemo(() => {
        if (!selectedIndustrySnapshot) return [];

        const reasons = [];
        const score = Number(selectedIndustrySnapshot.score || 0);
        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const stockCount = Number(selectedIndustrySnapshot.stock_count || 0);
        const marketCap = Number(selectedIndustrySnapshot.total_market_cap || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);

        if (score >= 80) {
            reasons.push(`综合得分 ${score.toFixed(1)}，已经属于当前榜单里的高热度行业。`);
        } else if (score >= 65) {
            reasons.push(`综合得分 ${score.toFixed(1)}，仍处在值得持续跟踪的活跃区间。`);
        }

        if (moneyFlow > 0) {
            reasons.push(`主力资金净流入 ${(moneyFlow / 1e8).toFixed(1)} 亿，短线关注度还在。`);
        } else if (moneyFlow < 0) {
            reasons.push(`主力资金净流出 ${Math.abs(moneyFlow / 1e8).toFixed(1)} 亿，需要留意承接是否变弱。`);
        }

        if (change >= 3) {
            reasons.push(`近阶段涨幅 ${change.toFixed(2)}%，价格表现已经明显跑出来了。`);
        } else if (change <= -3) {
            reasons.push(`近阶段回撤 ${Math.abs(change).toFixed(2)}%，更适合结合风险释放视角去看。`);
        }

        if (volatility >= 4) {
            reasons.push(`区间波动率 ${volatility.toFixed(1)}%，行业内部可能已经开始分化。`);
        }

        if (marketCap > 0 && stockCount > 0) {
            reasons.push(`板块总市值约 ${(marketCap / 1e8).toFixed(0)} 亿，覆盖 ${stockCount} 只成分股，具备板块代表性。`);
        }

        if (selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol) {
            const leadName = selectedIndustryLeadStock.name || selectedIndustryLeadStock.symbol;
            const leadScore = Number(selectedIndustryLeadStock.total_score || 0);
            reasons.push(
                leadScore > 0
                    ? `龙头候选 ${leadName} 当前得分 ${leadScore.toFixed(1)}，可以直接往个股层继续下钻。`
                    : `龙头候选 ${leadName} 已经可见，适合继续看个股承接和扩散。`
            );
        }

        return reasons.slice(0, 3);
    }, [selectedIndustrySnapshot, selectedIndustryLeadStock]);

    const selectedIndustryScoreBreakdown = useMemo(() => {
        if (!selectedIndustrySnapshot) return [];

        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const netInflowRatio = Number(selectedIndustrySnapshot.netInflowRatio || 0);
        const turnoverRate = Number(selectedIndustrySnapshot.turnoverRate || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);
        const leadScore = Number(selectedIndustryLeadStock?.total_score || 0);
        const leadChange = Number(selectedIndustryLeadStock?.change_pct || selectedIndustrySnapshot.leadingStockChange || 0);
        const hasLeader = Boolean(selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol || selectedIndustrySnapshot.leadingStock);
        const valuationQuality = selectedIndustrySnapshot.valuationQuality || 'unavailable';
        const pe = Number(selectedIndustrySnapshot.pe_ttm || 0);
        const pb = Number(selectedIndustrySnapshot.pb || 0);

        const priceScore = clampNumeric(((change + 4) / 8) * 100);
        const capitalBase = moneyFlow > 0 ? 58 : moneyFlow < 0 ? 24 : 40;
        const capitalImpulse = clampNumeric(Math.abs(moneyFlow) / 1e9 * 18, 0, 28);
        const capitalRatioAdjustment = clampNumeric(netInflowRatio * 6, -18, 18);
        const capitalScore = clampNumeric(capitalBase + capitalImpulse + capitalRatioAdjustment);
        const turnoverScore = clampNumeric((turnoverRate / 5) * 100);
        const volatilityBalance = volatility > 0 ? clampNumeric(92 - Math.abs(volatility - 3) * 14, 24, 92) : 48;
        const activityScore = clampNumeric(turnoverScore * 0.65 + volatilityBalance * 0.35);
        const leaderBase = leadScore > 0 ? leadScore : (hasLeader ? 64 : 34);
        const leaderScore = clampNumeric(leaderBase + clampNumeric(leadChange * 4, -12, 12));
        const valuationBaseMap = {
            industry_level: 78,
            leader_proxy: 56,
            unavailable: 32,
        };
        let valuationScore = valuationBaseMap[valuationQuality] ?? 40;
        if (pe > 0) {
            if (pe >= 8 && pe <= 35) valuationScore += 12;
            else if (pe > 80) valuationScore -= 10;
        }
        if (pb > 0) {
            if (pb >= 1 && pb <= 4) valuationScore += 8;
            else if (pb > 10) valuationScore -= 6;
        }
        valuationScore = clampNumeric(valuationScore);

        return [
            {
                key: 'price',
                label: '价格强度',
                score: priceScore,
                color: change >= 0 ? '#cf1322' : '#3f8600',
                summary: change >= 0
                    ? `行业涨跌幅 ${change.toFixed(2)}%，价格表现仍在正向贡献。`
                    : `行业涨跌幅 ${change.toFixed(2)}%，价格端正在拖累当前综合分。`,
            },
            {
                key: 'capital',
                label: '资金热度',
                score: capitalScore,
                color: moneyFlow >= 0 ? '#cf1322' : '#3f8600',
                summary: moneyFlow >= 0
                    ? `主力净流入 ${formatIndustryAlertMoneyFlow(moneyFlow)}，净流入占比 ${netInflowRatio.toFixed(2)}%。`
                    : `主力净流出 ${formatIndustryAlertMoneyFlow(moneyFlow)}，短线承接仍需继续确认。`,
            },
            {
                key: 'activity',
                label: '活跃度',
                score: activityScore,
                color: '#1677ff',
                summary: `换手率 ${turnoverRate ? turnoverRate.toFixed(2) : '-'}%，波动率 ${volatility ? volatility.toFixed(2) : '-'}%，体现板块活跃和分化程度。`,
            },
            {
                key: 'leader',
                label: '龙头牵引',
                score: leaderScore,
                color: '#722ed1',
                summary: hasLeader
                    ? `龙头候选 ${selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol || selectedIndustrySnapshot.leadingStock} ${leadScore > 0 ? `当前得分 ${leadScore.toFixed(1)}` : '已进入联动视图'}。`
                    : '当前还没有稳定龙头候选，板块扩散更值得继续观察。',
            },
            {
                key: 'valuation',
                label: '估值支撑',
                score: valuationScore,
                color: '#fa8c16',
                summary: valuationQuality === 'industry_level'
                    ? `估值来自行业级口径，PE ${pe > 0 ? pe.toFixed(2) : '-'}，PB ${pb > 0 ? pb.toFixed(2) : '-'}。`
                    : valuationQuality === 'leader_proxy'
                        ? '估值暂以龙头代理口径为主，更适合辅助判断，不宜单独下结论。'
                        : '当前估值口径较弱，更多适合和价格、资金、龙头一起看。',
            },
        ];
    }, [selectedIndustryLeadStock, selectedIndustrySnapshot]);

    const selectedIndustryScoreSummary = useMemo(() => {
        if (!selectedIndustryScoreBreakdown.length) return '';
        const dominant = [...selectedIndustryScoreBreakdown]
            .sort((left, right) => right.score - left.score)
            .slice(0, 2)
            .map((item) => item.label);
        return dominant.length > 0
            ? `当前综合分主要由${dominant.join('、')}在支撑。`
            : '';
    }, [selectedIndustryScoreBreakdown]);

    return {
        getIndustryVolatilityMeta,
        selectedIndustryFocusNarrative,
        selectedIndustryLeadStock,
        selectedIndustryMarketCapBadge,
        selectedIndustryReasons,
        selectedIndustryScoreBreakdown,
        selectedIndustryScoreSummary,
        selectedIndustrySnapshot,
        selectedIndustryVolatilityMeta,
        selectedIndustryWatched,
    };
}
