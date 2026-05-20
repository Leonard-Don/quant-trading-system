import React, { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, Button, Space, Tabs, Typography, Tag } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, BellOutlined, DollarOutlined } from '@ant-design/icons';
import {
  getRealtimeQuoteBoardDensityMode,
  getRealtimeQuoteListLayoutMode,
} from '../../utils/realtimeQuoteBoardLayout';
import { getRealtimeQuoteSourceMeta } from '../../utils/realtimeFormatters';

const { Text } = Typography;
const VIRTUALIZATION_THRESHOLD = 50;
const VIRTUAL_LIST_HEIGHT = 920;
const VIRTUAL_LIST_ITEM_HEIGHT_DEFAULT = 246;
const VIRTUAL_LIST_OVERSCAN = 4;
const GRID_RENDER_BATCH_SIZE = 24;

const RealtimeQuoteBoard = ({
  EMPTY_NUMERIC_TEXT,
  activeTab,
  categoryOptions,
  onActiveTabChange,
  buildMiniTrendSeries,
  buildSparklinePoints,
  currentTabSymbols,
  draggingSymbol,
  getCategoryLabel,
  getCategoryTheme,
  getDisplayName,
  getQuoteFreshness,
  handleOpenAlerts,
  handleOpenTrade,
  handleShowDetail,
  hasNumericValue,
  inferSymbolCategory,
  onClearSelectedQuotes,
  onMoveSelectedQuotesToCategory,
  onRemoveSelectedQuotes,
  onSelectAllCurrentTab,
  onSetDraggingSymbol,
  onToggleQuoteSelection,
  quoteSortMode,
  onQuoteSortModeChange,
  quoteViewMode,
  onQuoteViewModeChange,
  quotes,
  removeSymbol,
  resolveSymbolCategory,
  reorderWithinCategory,
  selectedCurrentTabSymbols,
  selectedQuoteSymbols,
  sortSymbolsForDisplay,
  tabs,
  formatPrice,
  formatPercent,
  formatQuoteTime,
  formatVolume,
  getSymbolsByCategory,
  quoteSortOptions,
}) => {
  const boardMeasureRef = useRef(null);
  const [virtualScrollByTab, setVirtualScrollByTab] = useState({});
  const [gridVisibleCountByTab, setGridVisibleCountByTab] = useState({});
  const [listLayoutMode, setListLayoutMode] = useState('wide');
  const [boardDensityMode, setBoardDensityMode] = useState('comfortable');

  useEffect(() => {
    setVirtualScrollByTab({});
  }, [activeTab, quoteSortMode, quoteViewMode]);

  useEffect(() => {
    if (quoteViewMode !== 'grid') {
      return;
    }
    setGridVisibleCountByTab((prev) => {
      const currentCount = prev[activeTab];
      const nextCount = currentCount == null
        ? Math.min(currentTabSymbols.length, GRID_RENDER_BATCH_SIZE)
        : Math.min(Math.max(currentCount, GRID_RENDER_BATCH_SIZE), currentTabSymbols.length);
      if (currentCount === nextCount) {
        return prev;
      }
      return {
        ...prev,
        [activeTab]: nextCount,
      };
    });
  }, [activeTab, currentTabSymbols.length, quoteViewMode]);

  useEffect(() => {
    const node = boardMeasureRef.current;
    if (!node) {
      return undefined;
    }

    const updateLayoutMode = (width) => {
      const nextBoardDensityMode = getRealtimeQuoteBoardDensityMode(width);
      setBoardDensityMode((currentBoardDensityMode) => (
        currentBoardDensityMode === nextBoardDensityMode ? currentBoardDensityMode : nextBoardDensityMode
      ));

      if (quoteViewMode !== 'list') {
        return;
      }

      const nextLayoutMode = getRealtimeQuoteListLayoutMode(width);
      setListLayoutMode((currentLayoutMode) => (
        currentLayoutMode === nextLayoutMode ? currentLayoutMode : nextLayoutMode
      ));
    };

    const measureWidth = () => {
      updateLayoutMode(node.getBoundingClientRect().width || node.clientWidth || 0);
    };

    measureWidth();

    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect?.width
          ?? node.getBoundingClientRect().width
          ?? node.clientWidth
          ?? 0;
        updateLayoutMode(width);
      });
      observer.observe(node);
      return () => observer.disconnect();
    }

    window.addEventListener('resize', measureWidth);
    return () => window.removeEventListener('resize', measureWidth);
  }, [quoteViewMode]);

  const itemHeight = VIRTUAL_LIST_ITEM_HEIGHT_DEFAULT;
  const activeTabLabel = tabs.find((tab) => tab.key === activeTab)?.label || getCategoryLabel(activeTab);

  const getVirtualRange = useMemo(() => (symbols) => {
    const scrollTop = virtualScrollByTab[activeTab] || 0;
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - VIRTUAL_LIST_OVERSCAN);
    const visibleCount = Math.ceil(VIRTUAL_LIST_HEIGHT / itemHeight) + VIRTUAL_LIST_OVERSCAN * 2;
    const endIndex = Math.min(symbols.length, startIndex + visibleCount);
    return {
      startIndex,
      endIndex,
      offsetY: startIndex * itemHeight,
      totalHeight: symbols.length * itemHeight,
      visibleSymbols: symbols.slice(startIndex, endIndex),
    };
  }, [activeTab, itemHeight, virtualScrollByTab]);

  const renderQuoteCard = useCallback((symbol, quote) => {
    const hasChange = hasNumericValue(quote.change);
    const isListMode = quoteViewMode === 'list';
    const isPositive = hasChange ? Number(quote.change) >= 0 : null;
    const changeColor = isPositive === null
      ? 'var(--text-secondary)'
      : isPositive
        ? 'var(--accent-success)'
        : 'var(--accent-danger)';
    const changeIcon = isPositive === null ? null : (isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />);
    const categoryType = resolveSymbolCategory(symbol);
    const categoryTheme = getCategoryTheme(categoryType);
    const isMarketIndex = categoryType === 'index';
    const changePercentText = formatPercent(quote.change_percent);
    const changeTagBackground = isPositive === null
      ? 'rgba(100, 116, 139, 0.12)'
      : isPositive
        ? 'rgba(34, 197, 94, 0.14)'
        : 'rgba(239, 68, 68, 0.14)';
    const freshness = getQuoteFreshness(quote);
    const sparklineSeries = buildMiniTrendSeries(quote);
    const sparklineWidth = isListMode ? 168 : 150;
    const sparklineHeight = isListMode ? 54 : 50;
    const sparklinePadding = 6;
    const sparklinePoints = buildSparklinePoints(sparklineSeries, sparklineWidth, sparklineHeight, sparklinePadding);
    const finiteSparklineSeries = sparklineSeries
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0);
    const sparklineFirstValue = finiteSparklineSeries[0];
    const sparklineLatestValue = finiteSparklineSeries[finiteSparklineSeries.length - 1];
    const sparklineMin = finiteSparklineSeries.length ? Math.min(...finiteSparklineSeries) : null;
    const sparklineMax = finiteSparklineSeries.length ? Math.max(...finiteSparklineSeries) : null;
    const sparklineSpan = sparklineMax !== null && sparklineMin !== null
      ? (sparklineMax - sparklineMin || 1)
      : 1;
    const getSparklineY = (value) => (
      sparklineHeight
      - sparklinePadding
      - (((value - sparklineMin) / sparklineSpan) * (sparklineHeight - sparklinePadding * 2))
    );
    const sparklineBaselineY = Number.isFinite(sparklineFirstValue)
      ? getSparklineY(sparklineFirstValue)
      : sparklineHeight / 2;
    const sparklineLatestX = finiteSparklineSeries.length > 1
      ? sparklinePadding
        + ((finiteSparklineSeries.length - 1) * (sparklineWidth - sparklinePadding * 2)) / (finiteSparklineSeries.length - 1)
      : sparklineWidth - sparklinePadding;
    const sparklineLatestY = Number.isFinite(sparklineLatestValue)
      ? getSparklineY(sparklineLatestValue)
      : sparklineHeight / 2;
    const sparklineDeltaPercent = Number.isFinite(sparklineFirstValue)
      && sparklineFirstValue > 0
      && Number.isFinite(sparklineLatestValue)
      ? ((sparklineLatestValue - sparklineFirstValue) / sparklineFirstValue) * 100
      : null;
    const sparklineTrendColor = sparklineDeltaPercent === null
      ? changeColor
      : sparklineDeltaPercent >= 0
        ? 'var(--accent-success)'
        : 'var(--accent-danger)';
    const sparklineDeltaText = sparklineDeltaPercent === null
      ? EMPTY_NUMERIC_TEXT
      : `${sparklineDeltaPercent >= 0 ? '+' : ''}${sparklineDeltaPercent.toFixed(2)}%`;
    const sparklineDirectionLabel = sparklineDeltaPercent === null
      ? '走势待补'
      : sparklineDeltaPercent > 0
        ? '较起点上行'
        : sparklineDeltaPercent < 0
          ? '较起点回落'
          : '较起点持平';
    const sparklineRangeText = sparklineMin !== null && sparklineMax !== null
      ? `${formatPrice(sparklineMin, EMPTY_NUMERIC_TEXT)} - ${formatPrice(sparklineMax, EMPTY_NUMERIC_TEXT)}`
      : EMPTY_NUMERIC_TEXT;
    const sparklineAreaPoints = sparklinePoints
      ? `${sparklinePoints} ${sparklineWidth - sparklinePadding},${sparklineHeight - sparklinePadding} ${sparklinePadding},${sparklineHeight - sparklinePadding}`
      : null;
    const sparklineIdToken = symbol.replace(/[^a-zA-Z0-9_-]/g, '-');
    const sparklineAreaGradientId = `quote-sparkline-area-${sparklineIdToken}`;
    const sparklineLineGradientId = `quote-sparkline-line-${sparklineIdToken}`;
    const sparklineTitle = `盘中走势 · ${sparklineDirectionLabel} ${sparklineDeltaText} · 区间 ${sparklineRangeText}`;
    const isSelected = selectedQuoteSymbols.includes(symbol);
    const isDragging = draggingSymbol === symbol;
    const sourceMeta = getRealtimeQuoteSourceMeta(quote.source);
    const detailTriggerLabel = `打开 ${getDisplayName(symbol)} ${symbol} 深度详情`;
    const handleCardKeyDown = (event) => {
      if (event.target !== event.currentTarget) {
        return;
      }
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handleShowDetail(symbol);
      }
    };

    return (
      <Card
        key={symbol}
        className={`realtime-quote-card realtime-quote-card--${quoteViewMode}${isListMode ? ` realtime-quote-card--list-${listLayoutMode}` : ''}`}
        style={{
          border: isSelected
            ? `1px solid color-mix(in srgb, var(--accent-primary) 54%, ${categoryTheme.accent} 46%)`
            : `1px solid color-mix(in srgb, ${categoryTheme.accent} 28%, var(--border-color) 72%)`,
          background: `linear-gradient(180deg, ${categoryTheme.soft} 0%, color-mix(in srgb, var(--bg-secondary) 92%, white 8%) 100%)`,
          boxShadow: isDragging ? '0 20px 40px rgba(37, 99, 235, 0.18)' : '0 14px 34px rgba(15, 23, 42, 0.08)',
          overflow: 'hidden',
          opacity: isDragging ? 0.82 : 1,
        }}
        styles={{ body: { padding: 0 } }}
        draggable
        onDragStart={() => onSetDraggingSymbol(symbol)}
        onDragEnd={() => onSetDraggingSymbol(null)}
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDrop={(event) => {
          event.preventDefault();
          if (draggingSymbol && draggingSymbol !== symbol) {
            reorderWithinCategory(draggingSymbol, symbol);
          }
          onSetDraggingSymbol(null);
        }}
      >
        <div
          className={`realtime-quote-card__surface realtime-quote-card__surface--${quoteViewMode}`}
          role="button"
          tabIndex={0}
          aria-label={detailTriggerLabel}
          onClick={() => handleShowDetail(symbol)}
          onKeyDown={handleCardKeyDown}
          style={{ cursor: 'pointer', padding: 18, touchAction: 'manipulation' }}
        >
          <div className="realtime-quote-card__header">
            <div>
              <div className="realtime-quote-card__tags">
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    color: categoryTheme.accent,
                    background: categoryTheme.soft,
                    borderColor: 'transparent',
                    fontWeight: 700,
                  }}
                >
                  {categoryTheme.label}
                </Tag>
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    borderColor: 'transparent',
                    color: changeColor,
                    background: changeTagBackground,
                    fontWeight: 700,
                  }}
                >
                  {changePercentText}
                </Tag>
                <Tag
                  style={{
                    margin: 0,
                    borderRadius: 999,
                    borderColor: 'transparent',
                    color: freshness.tone.color,
                    background: freshness.tone.background,
                    fontWeight: 700,
                  }}
                >
                  {freshness.label}
                </Tag>
                <Button
                  size="small"
                  type={isSelected ? 'primary' : 'default'}
                  aria-pressed={isSelected}
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleQuoteSelection(symbol);
                  }}
                >
                  {isSelected ? '已选中' : '选择'}
                </Button>
              </div>
              {freshness.detail && (
                <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: '12px' }}>
                  {freshness.detail}
                </Text>
              )}
              <div className="realtime-quote-card__name">
                <Text strong style={{ fontSize: '17px', color: 'var(--text-primary)' }}>
                  {getDisplayName(symbol)}
                </Text>
              </div>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {symbol} · 行情 {formatQuoteTime(quote.timestamp)} · 接收 {formatQuoteTime(quote._clientReceivedAt)}
              </Text>
              {sparklinePoints && (
                <div
                  className="realtime-quote-card__sparkline"
                  title={sparklineTitle}
                  style={{
                    alignItems: 'stretch',
                    justifyContent: 'space-between',
                    width: '100%',
                    maxWidth: isListMode ? 360 : 312,
                    gap: 12,
                  }}
                >
                  <svg
                    width={sparklineWidth}
                    height={sparklineHeight}
                    viewBox={`0 0 ${sparklineWidth} ${sparklineHeight}`}
                    role="img"
                    aria-label={`${symbol} 盘中走势线，${sparklineDirectionLabel} ${sparklineDeltaText}`}
                    style={{ width: sparklineWidth, height: sparklineHeight }}
                  >
                    <defs>
                      <linearGradient id={sparklineAreaGradientId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={sparklineTrendColor} stopOpacity="0.26" />
                        <stop offset="100%" stopColor={sparklineTrendColor} stopOpacity="0.02" />
                      </linearGradient>
                      <linearGradient id={sparklineLineGradientId} x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor={sparklineTrendColor} stopOpacity="0.58" />
                        <stop offset="100%" stopColor={sparklineTrendColor} stopOpacity="1" />
                      </linearGradient>
                    </defs>
                    <rect
                      x="0.5"
                      y="0.5"
                      width={sparklineWidth - 1}
                      height={sparklineHeight - 1}
                      rx="12"
                      fill="rgba(15, 23, 42, 0.16)"
                      stroke="rgba(148, 163, 184, 0.24)"
                    />
                    <line
                      x1={sparklinePadding}
                      y1={sparklineBaselineY}
                      x2={sparklineWidth - sparklinePadding}
                      y2={sparklineBaselineY}
                      stroke="rgba(148, 163, 184, 0.42)"
                      strokeWidth="1"
                      strokeDasharray="4 4"
                    />
                    {sparklineAreaPoints && (
                      <polygon points={sparklineAreaPoints} fill={`url(#${sparklineAreaGradientId})`} />
                    )}
                    <polyline
                      fill="none"
                      stroke={`url(#${sparklineLineGradientId})`}
                      strokeWidth="2.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      points={sparklinePoints}
                    />
                    <circle
                      cx={sparklineLatestX}
                      cy={sparklineLatestY}
                      r="3.8"
                      fill={sparklineTrendColor}
                      stroke="rgba(255, 255, 255, 0.86)"
                      strokeWidth="1.4"
                    />
                  </svg>
                  <div
                    style={{
                      display: 'grid',
                      alignContent: 'center',
                      gap: 2,
                      minWidth: 0,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <strong style={{ color: 'var(--text-primary)', fontSize: 12, lineHeight: 1.25 }}>
                      盘中走势
                    </strong>
                    <span
                      style={{
                        color: sparklineTrendColor,
                        fontSize: 12,
                        fontWeight: 700,
                        lineHeight: 1.2,
                      }}
                    >
                      {sparklineDeltaText}
                    </span>
                    <small
                      style={{
                        color: 'var(--text-muted)',
                        fontSize: 10,
                        lineHeight: 1.2,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      区间 {sparklineRangeText}
                    </small>
                  </div>
                </div>
              )}
            </div>

            <div
              className="realtime-quote-card__source"
              title={sourceMeta.title}
              aria-label={`数据源 ${sourceMeta.title}`}
            >
              <div className="realtime-quote-card__source-label">
                Source
              </div>
              <div className="realtime-quote-card__source-value">{sourceMeta.label}</div>
              {sourceMeta.detail ? (
                <div className="realtime-quote-card__source-detail">{sourceMeta.detail}</div>
              ) : null}
            </div>
          </div>

          <div className="realtime-quote-card__price-row">
            <div>
              <div className="realtime-quote-card__price">{formatPrice(quote.price)}</div>
              <div className="realtime-quote-card__delta" style={{ color: changeColor }}>
                {changeIcon ? <>{changeIcon} </> : null}
                {hasChange ? formatPrice(Math.abs(Number(quote.change))) : EMPTY_NUMERIC_TEXT} · {changePercentText}
              </div>
            </div>
            <div className="realtime-quote-card__focus">
              <div className="realtime-quote-card__focus-label">点击卡片</div>
              <div className="realtime-quote-card__focus-value">查看深度详情</div>
            </div>
          </div>

          <div className="realtime-quote-card__metrics">
            <div className="realtime-quote-card__metric">
              <span>日内区间</span>
              <strong>{formatPrice(quote.low, EMPTY_NUMERIC_TEXT)} - {formatPrice(quote.high, EMPTY_NUMERIC_TEXT)}</strong>
            </div>
            <div className="realtime-quote-card__metric">
              <span>开盘 / 昨收</span>
              <strong>{formatPrice(quote.open, EMPTY_NUMERIC_TEXT)} / {formatPrice(quote.previous_close, EMPTY_NUMERIC_TEXT)}</strong>
            </div>
            <div className="realtime-quote-card__metric">
              <span>成交量</span>
              <strong>{formatVolume(quote.volume)}</strong>
            </div>
          </div>

          <div className="realtime-quote-card__footer">
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {isListMode
                ? `${isMarketIndex ? '指数联动分析' : '详情 / 分析 / 交易'} · ${freshness.label}`
                : (isMarketIndex ? '指数详情与分析面板联动' : '支持查看实时快照、分析与交易入口')}
            </Text>
            <Space>
              <Button
                type="text"
                size="small"
                icon={<BellOutlined />}
                aria-label={`为 ${getDisplayName(symbol)} 打开价格提醒`}
                onClick={(event) => {
                  event.stopPropagation();
                  handleOpenAlerts(symbol);
                }}
              >
                提醒
              </Button>
              {!isMarketIndex && categoryType !== 'bond' && (
                <Button
                  type="primary"
                  size="small"
                  aria-label={`为 ${getDisplayName(symbol)} 打开交易面板`}
                  onClick={(event) => {
                    event.stopPropagation();
                    handleOpenTrade(symbol);
                  }}
                  icon={<DollarOutlined />}
                >
                  交易
                </Button>
              )}
              <Button
                type="text"
                size="small"
                danger
                aria-label={`移除 ${getDisplayName(symbol)}`}
                onClick={(event) => {
                  event.stopPropagation();
                  removeSymbol(symbol);
                }}
              >
                ×
              </Button>
            </Space>
          </div>
        </div>
      </Card>
    );
  }, [
    EMPTY_NUMERIC_TEXT,
    buildMiniTrendSeries,
    buildSparklinePoints,
    draggingSymbol,
    formatPercent,
    formatPrice,
    formatQuoteTime,
    formatVolume,
    getCategoryTheme,
    getDisplayName,
    getQuoteFreshness,
    handleOpenAlerts,
    handleOpenTrade,
    handleShowDetail,
    hasNumericValue,
    onSetDraggingSymbol,
    onToggleQuoteSelection,
    quoteViewMode,
    listLayoutMode,
    removeSymbol,
    reorderWithinCategory,
    resolveSymbolCategory,
    selectedQuoteSymbols,
  ]);

  const renderLoadingCard = useCallback((symbol) => (
    <Card
      key={symbol}
      loading
      style={{
        minHeight: 220,
        borderRadius: 22,
        border: '1px solid var(--border-color)',
      }}
    />
  ), []);

  const handleLoadMoreGridCards = useCallback((key, totalCount) => {
    startTransition(() => {
      setGridVisibleCountByTab((prev) => {
        const currentCount = prev[key] ?? Math.min(totalCount, GRID_RENDER_BATCH_SIZE);
        const nextCount = Math.min(totalCount, currentCount + GRID_RENDER_BATCH_SIZE);
        if (currentCount === nextCount) {
          return prev;
        }
        return {
          ...prev,
          [key]: nextCount,
        };
      });
    });
  }, []);

  const renderTabContent = useCallback((key, label, symbols) => {
    const sortedSymbols = sortSymbolsForDisplay(symbols);
    const shouldVirtualizeList = quoteViewMode === 'list' && sortedSymbols.length > VIRTUALIZATION_THRESHOLD;
    const shouldProgressivelyRenderGrid = quoteViewMode === 'grid' && sortedSymbols.length > VIRTUALIZATION_THRESHOLD;
    const virtualRange = shouldVirtualizeList ? getVirtualRange(sortedSymbols) : null;
    const gridVisibleCount = shouldProgressivelyRenderGrid
      ? Math.min(sortedSymbols.length, gridVisibleCountByTab[key] ?? GRID_RENDER_BATCH_SIZE)
      : sortedSymbols.length;
    const visibleGridSymbols = shouldProgressivelyRenderGrid
      ? sortedSymbols.slice(0, gridVisibleCount)
      : sortedSymbols;
    if (symbols.length === 0) {
      return (
        <div style={{ textAlign: 'center', padding: '56px 20px' }}>
          <Text type="secondary">暂无{label}数据，请添加</Text>
        </div>
      );
    }

    if (shouldVirtualizeList) {
      return (
        <div
          className="realtime-quote-grid realtime-quote-grid--list"
          style={{ height: VIRTUAL_LIST_HEIGHT, overflowY: 'auto' }}
          onScroll={(event) => {
            const nextScrollTop = event.currentTarget.scrollTop;
            setVirtualScrollByTab((prev) => ({ ...prev, [key]: nextScrollTop }));
          }}
        >
          <div style={{ height: virtualRange.totalHeight, position: 'relative' }}>
            <div style={{ transform: `translateY(${virtualRange.offsetY}px)` }}>
              {virtualRange.visibleSymbols.map((symbol) => {
                const quote = quotes[symbol];
                return quote ? renderQuoteCard(symbol, quote) : renderLoadingCard(symbol);
              })}
            </div>
          </div>
        </div>
      );
    }

    return (
      <>
        <div className={`realtime-quote-grid realtime-quote-grid--${quoteViewMode}`}>
          {visibleGridSymbols.map((symbol) => {
            const quote = quotes[symbol];
            return quote ? renderQuoteCard(symbol, quote) : renderLoadingCard(symbol);
          })}
        </div>
        {shouldProgressivelyRenderGrid && gridVisibleCount < sortedSymbols.length ? (
          <div
            className="realtime-quote-grid__progress"
            style={{
              marginTop: 16,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              padding: '14px 16px',
              borderRadius: 18,
              border: '1px solid color-mix(in srgb, var(--border-color) 80%, white 20%)',
              background: 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)',
            }}
          >
            <Text type="secondary">
              已渲染 {gridVisibleCount} / {sortedSymbols.length} 个卡片，继续加载以展开完整分组。
            </Text>
            <Button size="small" onClick={() => handleLoadMoreGridCards(key, sortedSymbols.length)}>
              再加载 {Math.min(GRID_RENDER_BATCH_SIZE, sortedSymbols.length - gridVisibleCount)} 个
            </Button>
          </div>
        ) : null}
      </>
    );
  }, [
    gridVisibleCountByTab,
    getVirtualRange,
    handleLoadMoreGridCards,
    quoteViewMode,
    quotes,
    renderLoadingCard,
    renderQuoteCard,
    sortSymbolsForDisplay,
  ]);

  const activeTabContent = useMemo(
    () => renderTabContent(activeTab, activeTabLabel, currentTabSymbols),
    [activeTab, activeTabLabel, currentTabSymbols, renderTabContent]
  );

  const tabItems = useMemo(() => tabs.map((tab) => {
    const symbols = tab.key === activeTab ? currentTabSymbols : getSymbolsByCategory(tab.key);
    const manuallyMovedCount = symbols.filter((symbol) => resolveSymbolCategory(symbol) !== inferSymbolCategory(symbol)).length;
    return {
      key: tab.key,
      label: (
        <Space size={6}>
          <span>{tab.icon} {tab.label}</span>
          {manuallyMovedCount > 0 ? (
            <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(37, 99, 235, 0.08)', color: '#1d4ed8' }}>
              自定义 {manuallyMovedCount}
            </Tag>
          ) : null}
        </Space>
      ),
      children: tab.key === activeTab ? activeTabContent : null,
    };
  }), [
    activeTab,
    activeTabContent,
    currentTabSymbols,
    getSymbolsByCategory,
    inferSymbolCategory,
    resolveSymbolCategory,
    tabs,
  ]);

  return (
    <Card
      className="realtime-board-card"
      style={{
        borderRadius: 28,
        border: '1px solid var(--border-color)',
        boxShadow: '0 18px 42px rgba(15, 23, 42, 0.07)',
      }}
    >
      <div
        ref={boardMeasureRef}
        data-realtime-board-density={boardDensityMode}
        data-realtime-list-layout={quoteViewMode === 'list' ? listLayoutMode : 'grid'}
      >
        <div className="realtime-board-head">
          <div className="realtime-board-headline">
            <div className="realtime-block-title">多市场看盘面板</div>
            <div className="realtime-block-subtitle">
              选中不同市场后按卡片浏览，点开即可进入完整的实时快照与全维分析详情。
            </div>
            <div className="realtime-board-badges">
              <div className="realtime-board-summary">
                <span>当前 {getCategoryLabel(activeTab)}</span>
                <strong>{currentTabSymbols.length}</strong>
              </div>
              <div className="realtime-board-summary">
                <span>已选</span>
                <strong>{selectedCurrentTabSymbols.length}</strong>
              </div>
            </div>
          </div>
          <div className="realtime-board-controls">
            <div className="realtime-board-control-group">
              <Text type="secondary" className="realtime-board-control-label">排序</Text>
              <Space wrap>
                {quoteSortOptions.map((option) => (
                  <Button
                    key={option.key}
                    size="small"
                    type={quoteSortMode === option.key ? 'primary' : 'default'}
                    onClick={() => onQuoteSortModeChange(option.key)}
                  >
                    {option.label}
                  </Button>
                ))}
              </Space>
            </div>
            <div className="realtime-board-control-group">
              <Text type="secondary" className="realtime-board-control-label">视图</Text>
              <Space wrap>
                <Button
                  size="small"
                  type={quoteViewMode === 'grid' ? 'primary' : 'default'}
                  onClick={() => onQuoteViewModeChange('grid')}
                >
                  网格模式
                </Button>
                <Button
                  size="small"
                  type={quoteViewMode === 'list' ? 'primary' : 'default'}
                  onClick={() => onQuoteViewModeChange('list')}
                >
                  列表模式
                </Button>
              </Space>
            </div>
            <div className={`realtime-board-control-group realtime-board-control-group--selection${selectedCurrentTabSymbols.length > 0 ? ' realtime-board-control-group--selection-active' : ''}`}>
              <Text type="secondary" className="realtime-board-control-label">批量</Text>
              <Space wrap>
                <Button size="small" onClick={onSelectAllCurrentTab}>
                  全选当前分组
                </Button>
                {selectedCurrentTabSymbols.length > 0 && (
                  <Button size="small" onClick={onClearSelectedQuotes}>
                    清空选择
                  </Button>
                )}
                {selectedCurrentTabSymbols.length > 0 ? categoryOptions
                  .filter((option) => option.key !== activeTab)
                  .slice(0, 4)
                  .map((option) => (
                    <Button
                      key={option.key}
                      size="small"
                      onClick={() => onMoveSelectedQuotesToCategory(option.key)}
                    >
                      移到{option.label}
                    </Button>
                  )) : null}
                {selectedCurrentTabSymbols.length > 0 && (
                  <Button size="small" danger onClick={onRemoveSelectedQuotes}>
                    批量删除
                  </Button>
                )}
              </Space>
            </div>
          </div>
        </div>

        <Tabs
          type="card"
          activeKey={activeTab}
          onChange={onActiveTabChange}
          size="large"
          className="market-tabs"
          destroyOnHidden
          items={tabItems}
        />
      </div>
    </Card>
  );
};

export default RealtimeQuoteBoard;
