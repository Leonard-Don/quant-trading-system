import { useState } from 'react';
import {
    Row,
    Col,
    Tabs,
    Empty,
    Button,
    Select,
    Space,
    Modal,
} from 'antd';
import {
    ReloadOutlined,
} from '@ant-design/icons';
import { Panel } from '../design/components';
import IndustryHeatmap from './IndustryHeatmap';
import IndustryTrendPanel from './IndustryTrendPanel';
import LeaderStockPanel from './LeaderStockPanel';
import IndustryRotationChart from './IndustryRotationChart';
import ApiStatusIndicator from './ApiStatusIndicator';
import StockDetailModal from './StockDetailModal';
import IndustryScoreRadarModal from './industry/IndustryScoreRadarModal';
import IndustrySavedViewsPanel from './industry/IndustrySavedViewsPanel';
import IndustryRankingPanel from './industry/IndustryRankingPanel';
import IndustryAlertsPanel from './industry/IndustryAlertsPanel';
import IndustryWatchlistPanel from './industry/IndustryWatchlistPanel';
import IndustryMarketSnapshotBar from './industry/IndustryMarketSnapshotBar';
import IndustryResearchFocusPanel from './industry/IndustryResearchFocusPanel';
import IndustryReplayPanel from './industry/IndustryReplayPanel';
import IndustryHeatmapStateBar from './industry/IndustryHeatmapStateBar';
import PolicyRadarPanel from './industry/PolicyRadarPanel';
import IndustryClusterPanel from './industry/IndustryClusterPanel';
import IndustryDashboardHero from './industry/IndustryDashboardHero';
import buildHotIndustryColumns from './industry/buildHotIndustryColumns';
import buildStockColumns from './industry/buildStockColumns';
import { INDUSTRY_URL_DEFAULTS } from './industry/useIndustryUrlState';
import useIndustryDashboardData from './industry/useIndustryDashboardData';
import { useSafeMessageApi } from '../utils/messageApi';
import { getDefaultBacktestDateRangeStrings } from '../utils/backtestDefaults';
import { saveBacktestWorkspaceDraft } from '../utils/backtestWorkspace';
import { buildBacktestLink, navigateToAppUrl } from '../utils/researchContext';
import {
    INDUSTRY_ALERT_RECENCY_OPTIONS,
    INDUSTRY_ALERT_KIND_OPTIONS,
    formatIndustryAlertMoneyFlow,
    getIndustryScoreTone,
    formatIndustryAlertSeenLabel,
} from './industry/industryShared';

const { Option } = Select;
const INDUSTRY_TIMEFRAME_LABELS = { 1: '1日', 5: '5日', 10: '10日', 20: '20日', 60: '60日' };
const INDUSTRY_SIZE_METRIC_LABELS = { market_cap: '按市值', net_inflow: '按净流入', turnover: '按成交额(估)' };
const INDUSTRY_COLOR_METRIC_LABELS = {
    change_pct: '看涨跌',
    net_inflow_ratio: '看净流入%',
    turnover_rate: '看换手率',
    pe_ttm: '看市盈率',
    pb: '看市净率',
};
const INDUSTRY_FILTER_LABELS = {
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const INDUSTRY_RANK_TYPE_LABELS = {
    gainers: '涨幅榜',
    losers: '跌幅榜',
};
const INDUSTRY_RANK_SORT_LABELS = {
    change_pct: '按涨跌幅',
    total_score: '按综合得分',
    money_flow: '按资金流向',
    industry_volatility: '按波动率',
};
const INDUSTRY_VOLATILITY_FILTER_LABELS = {
    all: '全部波动',
    low: '低波动',
    medium: '中波动',
    high: '高波动',
};
const INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS = {
    all: '全部市值来源',
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const PANEL_SURFACE = 'var(--bg-secondary)';
const PANEL_BORDER = '1px solid var(--border-color)';
const PANEL_SHADOW = '0 1px 2px rgba(0,0,0,0.03)';
const PANEL_MUTED = 'var(--text-muted)';
const TEXT_PRIMARY = 'var(--text-primary)';
const TEXT_SECONDARY = 'var(--text-secondary)';

/**
 * 行业分析主 Dashboard
 * 整合热力图、行业趋势、龙头股面板、行业排名等功能
 */
const IndustryDashboard = () => {
    const message = useSafeMessageApi();
    const [detailVisible, setDetailVisible] = useState(false);
    const [heatmapFullscreen, setHeatmapFullscreen] = useState(false);
    const [scoreRadarRecord, setScoreRadarRecord] = useState(null);
    const [workspaceTab, setWorkspaceTab] = useState('alerts');

    const data = useIndustryDashboardData({ message });

    const handleIndustryClickWithDetail = (industryName) => {
        data.handleIndustryClick(industryName);
        setDetailVisible(true);
    };

    const openSelectedIndustryDetailWithModal = () => {
        data.openSelectedIndustryDetail();
        setDetailVisible(true);
    };

    const handleBacktestStock = (record, source = 'industry_stock_table') => {
        const symbol = String(record?.symbol || record?.code || '').trim().toUpperCase();
        if (!symbol) {
            message.warning('当前标的缺少代码，暂时无法带入回测。');
            return;
        }

        const industryName = record?.industry || data.selectedIndustry || record?.industry_name || '';
        const [startDate, endDate] = getDefaultBacktestDateRangeStrings();
        saveBacktestWorkspaceDraft({
            symbol,
            strategy: 'buy_and_hold',
            dateRange: [startDate, endDate],
            dateRangeMode: 'rolling_one_year',
            initial_capital: 10000,
            commission: 0.1,
            slippage: 0.1,
            fixed_commission: 0,
            min_commission: 0,
            market_impact_bps: 0,
            market_impact_model: 'constant',
            execution_lag: 1,
            parameters: {},
            source,
            industry_name: industryName,
            stock_name: record?.name || '',
            updated_at: new Date().toISOString(),
        });
        navigateToAppUrl(buildBacktestLink(
            symbol,
            source,
            industryName ? `${industryName} 龙头/成分股` : '行业成分股'
        ));
        message.success(`已将 ${symbol} 带入主回测`);
    };

    const heatmapCoveragePct = data.heatmapSummary?.marketCapHealth?.coveragePct;
    const sentimentTone = data.heatmapSummary?.sentiment;
    const actionLevelColor = data.industryActionPosture.level === 'warning'
        ? 'gold'
        : data.industryActionPosture.level === 'info'
            ? 'processing'
            : 'success';

    // 热门行业表格列
    const hotIndustryColumns = buildHotIndustryColumns({
        getIndustryVolatilityMeta: data.getIndustryVolatilityMeta,
        onIndustryClick: handleIndustryClickWithDetail,
        onJumpToMarketCapFilter: data.jumpToMarketCapFilter,
        onScoreRadarRecord: setScoreRadarRecord,
        onAddToComparison: data.handleAddToComparison,
    });

    // 行业成分股表格列
    const stockColumns = buildStockColumns({ onBacktestStock: handleBacktestStock });

    const activeHeatmapStateTags = [];
    if (data.marketCapFilter !== INDUSTRY_URL_DEFAULTS.marketCapFilter) {
        activeHeatmapStateTags.push({ key: 'market_cap_filter', label: '来源', value: INDUSTRY_FILTER_LABELS[data.marketCapFilter] || data.marketCapFilter });
    }
    if (data.heatmapViewState.timeframe !== INDUSTRY_URL_DEFAULTS.timeframe) {
        activeHeatmapStateTags.push({ key: 'timeframe', label: '周期', value: INDUSTRY_TIMEFRAME_LABELS[data.heatmapViewState.timeframe] || `${data.heatmapViewState.timeframe}日` });
    }
    if (data.heatmapViewState.sizeMetric !== INDUSTRY_URL_DEFAULTS.sizeMetric) {
        activeHeatmapStateTags.push({ key: 'size_metric', label: '大小', value: INDUSTRY_SIZE_METRIC_LABELS[data.heatmapViewState.sizeMetric] || data.heatmapViewState.sizeMetric });
    }
    if (data.heatmapViewState.colorMetric !== INDUSTRY_URL_DEFAULTS.colorMetric) {
        activeHeatmapStateTags.push({ key: 'color_metric', label: '颜色', value: INDUSTRY_COLOR_METRIC_LABELS[data.heatmapViewState.colorMetric] || data.heatmapViewState.colorMetric });
    }
    if (data.heatmapViewState.displayCount !== INDUSTRY_URL_DEFAULTS.displayCount) {
        activeHeatmapStateTags.push({ key: 'display_count', label: '范围', value: data.heatmapViewState.displayCount === 0 ? '全部' : `Top ${data.heatmapViewState.displayCount}` });
    }
    if (data.heatmapViewState.searchTerm !== INDUSTRY_URL_DEFAULTS.searchTerm) {
        activeHeatmapStateTags.push({ key: 'search', label: '搜索', value: data.heatmapViewState.searchTerm });
    }
    if (Array.isArray(data.heatmapLegendRange) && data.heatmapLegendRange.length === 2) {
        activeHeatmapStateTags.push({
            key: 'legend_range',
            label: '色阶',
            value: `${Number(data.heatmapLegendRange[0]).toFixed(1)} ~ ${Number(data.heatmapLegendRange[1]).toFixed(1)}`,
        });
    }
    const hasActiveHeatmapState = activeHeatmapStateTags.length > 0;
    const shouldShowHeatmapStateBar = hasActiveHeatmapState && ['heatmap', 'clusters'].includes(data.activeTab);

    const activeRankingStateTags = [];
    if (data.rankType !== INDUSTRY_URL_DEFAULTS.rankType) {
        activeRankingStateTags.push({ key: 'rank_type', label: '榜单', value: INDUSTRY_RANK_TYPE_LABELS[data.rankType] || data.rankType });
    }
    if (data.sortBy !== INDUSTRY_URL_DEFAULTS.sortBy) {
        activeRankingStateTags.push({ key: 'sort_by', label: '排序', value: INDUSTRY_RANK_SORT_LABELS[data.sortBy] || data.sortBy });
    }
    if (data.lookbackDays !== INDUSTRY_URL_DEFAULTS.lookbackDays) {
        activeRankingStateTags.push({ key: 'lookback', label: '周期', value: `近${data.lookbackDays}日` });
    }
    if (data.volatilityFilter !== INDUSTRY_URL_DEFAULTS.volatilityFilter) {
        activeRankingStateTags.push({ key: 'volatility_filter', label: '波动', value: INDUSTRY_VOLATILITY_FILTER_LABELS[data.volatilityFilter] || data.volatilityFilter });
    }
    if (data.rankingMarketCapFilter !== INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter) {
        activeRankingStateTags.push({ key: 'market_cap_filter', label: '市值来源', value: INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS[data.rankingMarketCapFilter] || data.rankingMarketCapFilter });
    }

    const tabItems = [
        {
            label: '热力图',
            key: 'heatmap',
            children: (
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClickWithDetail}
                    onDataLoad={data.handleHeatmapDataLoad}
                    onLeadingStockClick={data.handleLeadingStockClick}
                    replaySnapshot={data.activeReplaySnapshot}
                    initialData={data.industryBootstrap?.heatmap || null}
                    bootstrapLoading={data.industryBootstrapLoading}
                    marketCapFilter={data.marketCapFilter}
                    onClearMarketCapFilter={() => data.setMarketCapFilter('all')}
                    onSelectMarketCapFilter={data.jumpToMarketCapFilter}
                    timeframeValue={data.heatmapViewState.timeframe}
                    sizeMetricValue={data.heatmapViewState.sizeMetric}
                    colorMetricValue={data.heatmapViewState.colorMetric}
                    displayCountValue={data.heatmapViewState.displayCount}
                    searchTermValue={data.heatmapViewState.searchTerm}
                    legendRangeValue={data.heatmapLegendRange}
                    onTimeframeChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={data.setHeatmapLegendRange}
                    focusControlKey={data.focusedHeatmapControlKey}
                    showStats={false}
                    onToggleFullscreen={() => setHeatmapFullscreen((current) => !current)}
                    isFullscreen={false}
                />
            )
        },
        {
            label: '排行榜',
            key: 'ranking',
            children: (
                <IndustryRankingPanel
                    rankType={data.rankType}
                    onRankTypeChange={data.setRankType}
                    sortBy={data.sortBy}
                    onSortByChange={data.setSortBy}
                    lookbackDays={data.lookbackDays}
                    onLookbackDaysChange={data.setLookbackDays}
                    volatilityFilter={data.volatilityFilter}
                    onVolatilityFilterChange={data.setVolatilityFilter}
                    rankingMarketCapFilter={data.rankingMarketCapFilter}
                    onRankingMarketCapFilterChange={data.setRankingMarketCapFilter}
                    loadingHot={data.loadingHot}
                    focusedRankingControlKey={data.focusedRankingControlKey}
                    filteredHotIndustries={data.filteredHotIndustries}
                    hotIndustryColumns={hotIndustryColumns}
                    onReload={() => data.loadHotIndustries(50, data.rankType, data.sortBy, data.lookbackDays)}
                    onIndustryClick={handleIndustryClickWithDetail}
                    activeRankingStateTags={activeRankingStateTags}
                    onFocusRankingControl={data.focusRankingControl}
                    onClearRankingStateTag={data.clearRankingStateTag}
                    onResetRankingViewState={data.resetRankingViewState}
                    panelSurface={PANEL_SURFACE}
                    panelBorder={PANEL_BORDER}
                    panelShadow={PANEL_SHADOW}
                    panelMuted={PANEL_MUTED}
                />
            )
        },
        {
            label: '聚类分析',
            key: 'clusters',
            children: (
                <Panel
                    title="行业聚类分析"
                    actions={
                        <Space size={8} wrap>
                            <Select
                                value={data.clusterCount}
                                onChange={data.setClusterCount}
                                size="small"
                                style={{ width: 108 }}
                                disabled={data.loadingClusters}
                                aria-label="选择行业聚类数量"
                            >
                                <Option value={3}>3 个聚类</Option>
                                <Option value={4}>4 个聚类</Option>
                                <Option value={5}>5 个聚类</Option>
                                <Option value={6}>6 个聚类</Option>
                            </Select>
                            {data.clusters && (
                                <Button
                                    className="industry-inline-link"
                                    icon={<ReloadOutlined />}
                                    onClick={() => data.loadClusters(false)}
                                    size="small"
                                >
                                    重新分析
                                </Button>
                            )}
                        </Space>
                    }
                >
                    <IndustryClusterPanel
                        loadingClusters={data.loadingClusters}
                        clusterError={data.clusterError}
                        clusters={data.clusters}
                        selectedClusterPoint={data.selectedClusterPoint}
                        onLoadClusters={data.loadClusters}
                        onSetSelectedClusterPoint={data.setSelectedClusterPoint}
                        onIndustryClick={handleIndustryClickWithDetail}
                        onSetSelectedIndustry={data.setSelectedIndustry}
                        onAddToComparison={data.handleAddToComparison}
                    />
                </Panel>
            )
        },
        {
            label: '轮动对比',
            key: 'rotation',
            children: (
                <IndustryRotationChart
                    initialIndustries={data.comparisonIndustries.length > 0
                        ? data.comparisonIndustries
                        : (data.hotIndustries || []).slice(0, 3).map(i => i.industry_name)
                    }
                />
            )
        }
    ];

    const workspaceTabMeta = {
        alerts: {
            title: '提醒中心',
            summary: '集中处理订阅范围、提醒规则和时间线，先判断哪些行业需要从扫描升级到跟踪。'
        },
        replay: {
            title: '历史回放',
            summary: '回看最近快照、切换对比基线，确认哪些行业是在持续升温，哪些只是短时异动。'
        },
        views: {
            title: '视图沉淀',
            summary: '把常用的热力图、排行和提醒配置存成视图，下次可以直接回到熟悉的工作面。'
        },
    };
    const industryScanInsightTabItems = [
        {
            key: 'leaders',
            label: '龙头股',
            children: (
                <LeaderStockPanel
                    topN={5}
                    topIndustries={5}
                    perIndustry={3}
                    bootstrappedOverview={data.industryBootstrap?.leaders || null}
                    bootstrapLoading={data.industryBootstrapLoading}
                    focusIndustry={data.selectedIndustry}
                    onClearFocusIndustry={() => data.setSelectedIndustry(null)}
                    onBacktestStock={(record) => handleBacktestStock(record, 'leader_stock_panel')}
                />
            ),
        },
        {
            key: 'watchlist',
            label: `观察列表${data.watchlistEntries.length > 0 ? ` (${data.watchlistEntries.length})` : ''}`,
            children: (
                <IndustryWatchlistPanel
                    watchlistEntries={data.watchlistEntries}
                    watchlistSuggestions={data.watchlistSuggestions}
                    selectedIndustry={data.selectedIndustry}
                    maxWatchlistIndustries={data.maxWatchlistIndustries}
                    toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                    setSelectedIndustry={data.setSelectedIndustry}
                    handleIndustryClick={handleIndustryClickWithDetail}
                    handleAddToComparison={data.handleAddToComparison}
                    formatIndustryAlertMoneyFlow={formatIndustryAlertMoneyFlow}
                />
            ),
        },
    ];
    const activeWorkspaceMeta = workspaceTabMeta[workspaceTab] || workspaceTabMeta.alerts;
    const hasAlertsWorkspace = data.industryAlertsWithSeverity.length > 0 || data.rawIndustryAlerts.length > 0 || data.focusIndustrySuggestions.length > 0;
    const workspaceTabItems = [
        {
            key: 'alerts',
            label: `提醒中心${data.subscribedAlertNewCount > 0 ? ` (${data.subscribedAlertNewCount})` : ''}`,
            children: hasAlertsWorkspace ? (
                <IndustryAlertsPanel
                    industryAlertsWithSeverity={data.industryAlertsWithSeverity}
                    rawIndustryAlerts={data.rawIndustryAlerts}
                    focusIndustrySuggestions={data.focusIndustrySuggestions}
                    subscribedAlertNewCount={data.subscribedAlertNewCount}
                    industryAlertSubscription={data.industryAlertSubscription}
                    desktopAlertNotifications={data.desktopAlertNotifications}
                    industryAlertRule={data.industryAlertRule}
                    setIndustryAlertRule={data.setIndustryAlertRule}
                    industryAlertRecency={data.industryAlertRecency}
                    setIndustryAlertRecency={data.setIndustryAlertRecency}
                    industryAlertKindOptions={INDUSTRY_ALERT_KIND_OPTIONS}
                    industryAlertRecencyOptions={INDUSTRY_ALERT_RECENCY_OPTIONS}
                    setIndustryAlertSubscription={data.setIndustryAlertSubscription}
                    industryAlertThresholds={data.industryAlertThresholds}
                    setIndustryAlertThresholds={data.setIndustryAlertThresholds}
                    requestDesktopAlertPermission={data.requestDesktopAlertPermission}
                    toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                    watchlistIndustries={data.watchlistIndustries}
                    selectedIndustry={data.selectedIndustry}
                    setSelectedIndustry={data.setSelectedIndustry}
                    handleIndustryClick={handleIndustryClickWithDetail}
                    handleAddToComparison={data.handleAddToComparison}
                    alertTimelineEntries={data.alertTimelineEntries}
                    formatIndustryAlertSeenLabel={formatIndustryAlertSeenLabel}
                    message={message}
                />
            ) : (
                <Panel>
                    <Empty description="当前没有需要升级处理的行业提醒" />
                </Panel>
            ),
        },
        {
            key: 'replay',
            label: `历史回放${data.heatmapReplaySnapshots.length > 0 ? ` (${data.heatmapReplaySnapshots.length})` : ''}`,
            children: data.heatmapReplaySnapshots.length > 0 ? (
                <IndustryReplayPanel
                    heatmapReplaySnapshots={data.heatmapReplaySnapshots}
                    activeReplaySnapshot={data.activeReplaySnapshot}
                    latestReplaySnapshot={data.latestReplaySnapshot}
                    replayWindow={data.replayWindow}
                    setReplayWindow={data.setReplayWindow}
                    heatmapReplayWindowOptions={data.heatmapReplayWindowOptions}
                    comparisonBaseSnapshotId={data.comparisonBaseSnapshotId}
                    setComparisonBaseSnapshotId={data.setComparisonBaseSnapshotId}
                    filteredReplaySnapshots={data.filteredReplaySnapshots}
                    replayTargetSnapshot={data.replayTargetSnapshot}
                    formatReplaySnapshotTime={data.formatReplaySnapshotTime}
                    industryTimeframeLabels={INDUSTRY_TIMEFRAME_LABELS}
                    setActiveTab={data.setActiveTab}
                    setSelectedReplaySnapshotId={data.setSelectedReplaySnapshotId}
                    setHeatmapViewState={data.setHeatmapViewState}
                    setMarketCapFilter={data.setMarketCapFilter}
                    panelSurface={PANEL_SURFACE}
                    panelBorder={PANEL_BORDER}
                    panelShadow={PANEL_SHADOW}
                    panelMuted={PANEL_MUTED}
                    textPrimary={TEXT_PRIMARY}
                    textSecondary={TEXT_SECONDARY}
                    replayComparison={data.replayComparison}
                    activeReplayDiffIndustry={data.activeReplayDiffIndustry}
                    handleReplayDiffIndustrySelect={data.handleReplayDiffIndustrySelect}
                    handleIndustryClick={handleIndustryClickWithDetail}
                    getIndustryScoreTone={getIndustryScoreTone}
                    formatReplayDelta={data.formatReplayDelta}
                    replayIndustryDiffDetail={data.replayIndustryDiffDetail}
                    watchlistIndustries={data.watchlistIndustries}
                    toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                    formatReplayMetricPercent={data.formatReplayMetricPercent}
                    formatReplayMetricMoney={data.formatReplayMetricMoney}
                />
            ) : (
                <Panel>
                    <Empty description="当前还没有可用的行业历史快照" />
                </Panel>
            ),
        },
        {
            key: 'views',
            label: `视图沉淀${data.savedIndustryViews.length > 0 ? ` (${data.savedIndustryViews.length})` : ''}`,
            children: (
                <IndustrySavedViewsPanel
                    draftName={data.savedViewDraftName}
                    onDraftNameChange={data.setSavedViewDraftName}
                    onSave={data.saveCurrentIndustryView}
                    savedViews={data.savedIndustryViews}
                    onApply={data.applySavedIndustryView}
                    onOverwrite={data.overwriteSavedIndustryView}
                    onRemove={data.removeSavedIndustryView}
                    onExport={data.handleExportSavedViews}
                    onImportClick={data.handleImportSavedViewsClick}
                />
            ),
        },
        {
            key: 'policy',
            label: '政策雷达',
            children: (
                <PolicyRadarPanel timeframe="30d" limit={15} />
            ),
        },
    ];

    return (
        <div className="app-page-shell app-page-shell--wide industry-page-shell">
            <IndustryDashboardHero
                sentimentTone={sentimentTone}
                heatmapCoveragePct={heatmapCoveragePct}
                actionLevelColor={actionLevelColor}
                industryActionPosture={data.industryActionPosture}
                selectedIndustry={data.selectedIndustry}
                heatmapIndustries={data.heatmapIndustries}
                heatmapSummary={data.heatmapSummary}
                watchlistEntries={data.watchlistEntries}
                subscribedAlertNewCount={data.subscribedAlertNewCount}
            />

            <div className="app-page-section-block">
                <div className="app-page-section-kicker">行业扫描与轮动</div>
                <div className="industry-scan-layout">
                    <Row gutter={[20, 20]} className="industry-scan-layout__row">
                        <Col xs={24} lg={15} xl={16}>
                            <IndustryHeatmapStateBar
                                visible={shouldShowHeatmapStateBar}
                                activeHeatmapStateTags={activeHeatmapStateTags}
                                onFocusHeatmapControl={data.focusHeatmapControl}
                                onClearHeatmapStateTag={data.clearHeatmapStateTag}
                                onResetHeatmapViewState={data.resetHeatmapViewState}
                                panelSurface={PANEL_SURFACE}
                                panelBorder={PANEL_BORDER}
                                panelShadow={PANEL_SHADOW}
                                panelMuted={PANEL_MUTED}
                            />

                            <Tabs
                                activeKey={data.activeTab}
                                onChange={data.setActiveTab}
                                items={tabItems}
                            />

                            <div className="industry-scan-summary">
                                <IndustryMarketSnapshotBar
                                    heatmapSummary={data.heatmapSummary}
                                    focusedHeatmapControlKey={data.focusedHeatmapControlKey}
                                    marketCapFilter={data.marketCapFilter}
                                    onIndustryClick={handleIndustryClickWithDetail}
                                    onToggleMarketCapFilter={data.toggleMarketCapFilter}
                                    onResetMarketCapFilter={() => data.setMarketCapFilter('all')}
                                    statusIndicator={<ApiStatusIndicator />}
                                />
                            </div>
                        </Col>

                        <Col xs={24} lg={9} xl={8}>
                            <IndustryResearchFocusPanel
                                selectedIndustry={data.selectedIndustry}
                                selectedIndustrySnapshot={data.selectedIndustrySnapshot}
                                selectedIndustryMarketCapBadge={data.selectedIndustryMarketCapBadge}
                                selectedIndustryVolatilityMeta={data.selectedIndustryVolatilityMeta}
                                selectedIndustryFocusNarrative={data.selectedIndustryFocusNarrative}
                                selectedIndustryScoreBreakdown={data.selectedIndustryScoreBreakdown}
                                selectedIndustryScoreSummary={data.selectedIndustryScoreSummary}
                                selectedIndustryReasons={data.selectedIndustryReasons}
                                selectedIndustryWatched={data.selectedIndustryWatched}
                                focusIndustrySuggestions={data.focusIndustrySuggestions}
                                onClearIndustry={() => data.setSelectedIndustry(null)}
                                onOpenIndustryDetail={openSelectedIndustryDetailWithModal}
                                onToggleWatchlist={() => data.toggleWatchlistIndustry(data.selectedIndustry)}
                                onAddToComparison={() => data.handleAddToComparison(data.selectedIndustry)}
                                onSelectIndustry={handleIndustryClickWithDetail}
                            />
                        </Col>
                    </Row>

                    <div className="industry-scan-insight-shell">
                        <div className="industry-scan-insight-shell__header">
                            <div>
                                <div className="industry-scan-insight-shell__title">龙头与观察工作台</div>
                                <div className="industry-scan-insight-shell__summary">
                                    把龙头承接和观察列表放到同一条宽画布里，先看行业主线，再决定是否继续下钻。
                                </div>
                            </div>
                        </div>
                        <Tabs
                            defaultActiveKey="leaders"
                            items={industryScanInsightTabItems}
                        />
                    </div>
                </div>
            </div>

            <div className="app-page-section-block">
                <div className="app-page-section-kicker">行业工作台</div>
                <div className="industry-workspace-shell">
                    <div className="industry-workspace-shell__header">
                        <div>
                            <div className="industry-workspace-shell__title">{activeWorkspaceMeta.title}</div>
                            <div className="industry-workspace-shell__summary">{activeWorkspaceMeta.summary}</div>
                        </div>
                    </div>
                    <Tabs
                        activeKey={workspaceTab}
                        onChange={setWorkspaceTab}
                        items={workspaceTabItems}
                    />
                    <input
                        ref={data.savedViewImportInputRef}
                        type="file"
                        accept="application/json,.json"
                        onChange={data.handleImportSavedViews}
                        style={{ display: 'none' }}
                    />
                </div>
            </div>

            <Modal
                title="行业热力图全屏"
                open={heatmapFullscreen}
                onCancel={() => setHeatmapFullscreen(false)}
                footer={null}
                width="92vw"
                style={{ top: 20 }}
                destroyOnHidden
                modalRender={(node) => <div data-testid="industry-heatmap-fullscreen-modal">{node}</div>}
                styles={{ body: { paddingTop: 8 } }}
            >
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClickWithDetail}
                    onDataLoad={data.handleHeatmapDataLoad}
                    onLeadingStockClick={data.handleLeadingStockClick}
                    replaySnapshot={data.activeReplaySnapshot}
                    initialData={data.industryBootstrap?.heatmap || null}
                    bootstrapLoading={data.industryBootstrapLoading}
                    marketCapFilter={data.marketCapFilter}
                    onClearMarketCapFilter={() => data.setMarketCapFilter('all')}
                    onSelectMarketCapFilter={data.jumpToMarketCapFilter}
                    timeframeValue={data.heatmapViewState.timeframe}
                    sizeMetricValue={data.heatmapViewState.sizeMetric}
                    colorMetricValue={data.heatmapViewState.colorMetric}
                    displayCountValue={data.heatmapViewState.displayCount}
                    searchTermValue={data.heatmapViewState.searchTerm}
                    legendRangeValue={data.heatmapLegendRange}
                    onTimeframeChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={data.setHeatmapLegendRange}
                    focusControlKey={data.focusedHeatmapControlKey}
                    showStats
                    onToggleFullscreen={() => setHeatmapFullscreen(false)}
                    isFullscreen
                />
            </Modal>

            {/* 行业详情弹窗 */}
            <Modal
                title={`${data.selectedIndustry} 行业详情`}
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                footer={null}
                width={1120}
                destroyOnHidden
                modalRender={(node) => <div className="industry-detail-modal-shell" data-testid="industry-detail-modal">{node}</div>}
                styles={{ body: { padding: '0 20px 20px', maxHeight: 'calc(100vh - 160px)', overflowY: 'auto', overscrollBehavior: 'contain' } }}
            >
                <IndustryTrendPanel
                    industryName={data.selectedIndustry}
                    days={30}
                    industrySnapshot={data.selectedIndustrySnapshot}
                    stocks={data.industryStocks}
                    loadingStocks={data.loadingStocks}
                    stocksRefining={data.stocksRefining}
                    stocksScoreStage={data.stocksScoreStage}
                    stocksDisplayReady={data.stocksDisplayReady}
                    stockColumns={stockColumns}
                />
            </Modal>

            <StockDetailModal
                open={data.stockDetailVisible}
                onCancel={data.closeStockDetail}
                loading={data.stockDetailLoading}
                error={data.stockDetailError}
                detailData={data.stockDetailData}
                selectedStock={data.stockDetailData?.symbol || data.stockDetailSymbol}
                onRetry={data.stockDetailSymbol ? () => data.handleLeadingStockClick(data.stockDetailSymbol) : undefined}
            />

            <IndustryScoreRadarModal
                visible={Boolean(scoreRadarRecord)}
                onClose={() => setScoreRadarRecord(null)}
                record={scoreRadarRecord}
                snapshot={scoreRadarRecord ? data.selectedIndustrySnapshot?.industry_name === scoreRadarRecord.industry_name
                    ? data.selectedIndustrySnapshot
                    : (data.heatmapIndustries || []).find((item) => item?.name === scoreRadarRecord.industry_name) : null}
            />
        </div>
    );
};

export default IndustryDashboard;
