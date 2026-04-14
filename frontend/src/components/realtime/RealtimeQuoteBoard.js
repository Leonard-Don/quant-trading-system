import React, { useEffect, useMemo, useState } from 'react';
import { Card, Button, Space, Tabs, Typography, Tag } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, BellOutlined, DollarOutlined } from '@ant-design/icons';

const { Text } = Typography;
const VIRTUALIZATION_THRESHOLD = 50;
const VIRTUAL_LIST_HEIGHT = 920;
const VIRTUAL_LIST_ITEM_HEIGHT_DEFAULT = 246;
const VIRTUAL_LIST_OVERSCAN = 4;

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
  const [virtualScrollByTab, setVirtualScrollByTab] = useState({});

  useEffect(() => {
    setVirtualScrollByTab({});
  }, [activeTab, quoteSortMode, quoteViewMode]);

  const itemHeight = VIRTUAL_LIST_ITEM_HEIGHT_DEFAULT;

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

  const renderQuoteCard = (symbol, quote) => {
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
    const sparklinePoints = buildSparklinePoints(sparklineSeries);
    const isSelected = selectedQuoteSymbols.includes(symbol);
    const isDragging = draggingSymbol === symbol;

    return (
      <div key={symbol}>
      <Card
        className={`realtime-quote-card realtime-quote-card--${quoteViewMode}`}
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
          onClick={() => handleShowDetail(symbol)}
          style={{ cursor: 'pointer', padding: 18 }}
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
                <div className="realtime-quote-card__sparkline">
                  <svg width="144" height="44" viewBox="0 0 144 44" role="img" aria-label={`${symbol} 价格轨迹`}>
                    <polyline
                      fill="none"
                      stroke={changeColor}
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      points={sparklinePoints}
                    />
                  </svg>
                  <span>{isListMode ? '快照轨迹' : '昨收 / 开盘 / 区间 / 现价'}</span>
                </div>
              )}
            </div>

            <div className="realtime-quote-card__source">
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', opacity: 0.72 }}>
                Source
              </div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                {quote.source || '--'}
              </div>
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
      </div>
    );
  };

  const renderTabItem = (key, label, icon) => {
    const symbols = getSymbolsByCategory(key);
    const sortedSymbols = sortSymbolsForDisplay(symbols);
    const manuallyMovedCount = symbols.filter((symbol) => resolveSymbolCategory(symbol) !== inferSymbolCategory(symbol)).length;
    const shouldVirtualizeList = quoteViewMode === 'list' && sortedSymbols.length > VIRTUALIZATION_THRESHOLD;
    const virtualRange = shouldVirtualizeList ? getVirtualRange(sortedSymbols) : null;
    return {
      key,
      label: (
        <Space size={6}>
          <span>{icon} {label}</span>
          {manuallyMovedCount > 0 ? (
            <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(37, 99, 235, 0.08)', color: '#1d4ed8' }}>
              自定义 {manuallyMovedCount}
            </Tag>
          ) : null}
        </Space>
      ),
      children: symbols.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '56px 20px' }}>
          <Text type="secondary">暂无{label}数据，请添加</Text>
        </div>
      ) : shouldVirtualizeList ? (
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
                return quote ? renderQuoteCard(symbol, quote) : (
                  <Card
                    key={symbol}
                    loading
                    style={{
                      minHeight: 220,
                      borderRadius: 22,
                      border: '1px solid var(--border-color)',
                    }}
                  />
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className={`realtime-quote-grid realtime-quote-grid--${quoteViewMode}`}>
          {sortedSymbols.map((symbol) => {
            const quote = quotes[symbol];
            return quote ? renderQuoteCard(symbol, quote) : (
              <Card
                key={symbol}
                loading
                style={{
                  minHeight: 220,
                  borderRadius: 22,
                  border: '1px solid var(--border-color)',
                }}
              />
            );
          })}
        </div>
      ),
    };
  };

  return (
    <Card
      className="realtime-board-card"
      style={{
        borderRadius: 28,
        border: '1px solid var(--border-color)',
        boxShadow: '0 18px 42px rgba(15, 23, 42, 0.07)',
      }}
    >
      <div className="realtime-board-head">
        <div>
          <div className="realtime-block-title">多市场看盘面板</div>
          <div className="realtime-block-subtitle">
            选中不同市场后按卡片浏览，点开即可进入完整的实时快照与全维分析详情。
          </div>
        </div>
        <div className="realtime-board-controls">
          <Space wrap>
            <Text type="secondary" style={{ fontSize: '12px' }}>排序</Text>
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
          <Space wrap>
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
            <Button size="small" onClick={onSelectAllCurrentTab}>
              全选当前分组
            </Button>
            <Button size="small" onClick={onClearSelectedQuotes}>
              清空选择
            </Button>
            <Button size="small" danger onClick={onRemoveSelectedQuotes}>
              批量删除
            </Button>
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
            <div className="realtime-board-summary">
              <span>当前 {getCategoryLabel(activeTab)}</span>
              <strong>{currentTabSymbols.length}</strong>
            </div>
            <div className="realtime-board-summary">
              <span>已选</span>
              <strong>{selectedCurrentTabSymbols.length}</strong>
            </div>
          </Space>
        </div>
      </div>

      <Tabs
        type="card"
        activeKey={activeTab}
        onChange={onActiveTabChange}
        size="large"
        className="market-tabs"
        items={tabs.map((tab) => renderTabItem(tab.key, tab.label, tab.icon))}
      />
    </Card>
  );
};

export default RealtimeQuoteBoard;
