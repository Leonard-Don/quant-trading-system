import { useCallback, useEffect, useRef, useState } from 'react';

import {
    getIndustryStockBuildStatus,
    getIndustryStocks,
    getLeaderDetail,
} from '../../services/api';

const INDUSTRY_STOCK_FULL_POLL_ATTEMPTS = 30;
const INDUSTRY_STOCK_FULL_POLL_INTERVAL_MS = 900;
const INDUSTRY_API_BASE_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

const INDUSTRY_STOCK_DISPLAY_ROW_TARGET = 5;
const INDUSTRY_STOCK_DISPLAY_DETAIL_ROW_TARGET = 2;

const getIndustryStockScoreStage = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return null;
    if (stocks.some((stock) => stock?.scoreStage === 'full')) return 'full';
    if (stocks.some((stock) => stock?.scoreStage === 'quick')) return 'quick';
    return stocks.some((stock) => Number(stock?.total_score || 0) > 0) ? 'full' : 'quick';
};

const hasDisplayReadyIndustryStockDetailValue = (value, { positiveOnly = false } = {}) => {
    if (value === null || value === undefined || value === '') return false;
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return false;
    return positiveOnly ? numericValue > 0 : true;
};

const getIndustryStockDetailFieldCount = (stock = {}) => (
    [
        hasDisplayReadyIndustryStockDetailValue(stock?.market_cap, { positiveOnly: true }),
        hasDisplayReadyIndustryStockDetailValue(stock?.pe_ratio, { positiveOnly: true }),
        hasDisplayReadyIndustryStockDetailValue(stock?.money_flow),
        hasDisplayReadyIndustryStockDetailValue(stock?.turnover_rate, { positiveOnly: true })
            || hasDisplayReadyIndustryStockDetailValue(stock?.turnover, { positiveOnly: true }),
    ].filter(Boolean).length
);

export const hasDisplayReadyIndustryStockDetails = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return false;
    const visibleRows = stocks.slice(0, Math.min(INDUSTRY_STOCK_DISPLAY_ROW_TARGET, stocks.length));
    const strongDetailRows = visibleRows.filter((stock) => getIndustryStockDetailFieldCount(stock) >= 2);
    if (strongDetailRows.length >= 1) {
        return true;
    }
    const visibleDetailedRows = visibleRows.filter((stock) => getIndustryStockDetailFieldCount(stock) >= 1);
    return visibleDetailedRows.length >= Math.min(INDUSTRY_STOCK_DISPLAY_DETAIL_ROW_TARGET, visibleRows.length);
};

const waitForAbortableDelay = (signal, timeoutMs) => (
    new Promise((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
        }
        const timer = window.setTimeout(() => {
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }
            resolve();
        }, timeoutMs);
        const onAbort = () => {
            window.clearTimeout(timer);
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }
            reject(new DOMException('Aborted', 'AbortError'));
        };
        if (signal) {
            signal.addEventListener('abort', onAbort, { once: true });
        }
    })
);

export default function useIndustryStocks({
    message,
    setSelectedIndustry,
}) {
    const [industryStocks, setIndustryStocks] = useState([]);
    const [loadingStocks, setLoadingStocks] = useState(false);
    const [stocksRefining, setStocksRefining] = useState(false);
    const [stocksScoreStage, setStocksScoreStage] = useState(null);
    const [stocksDisplayReady, setStocksDisplayReady] = useState(false);
    const [stockDetailVisible, setStockDetailVisible] = useState(false);
    const [stockDetailSymbol, setStockDetailSymbol] = useState(null);
    const [stockDetailData, setStockDetailData] = useState(null);
    const [stockDetailLoading, setStockDetailLoading] = useState(false);
    const [stockDetailError, setStockDetailError] = useState(null);

    const industryStocksAbortRef = useRef(null);
    const industryStocksStreamRef = useRef(null);
    const stockDetailAbortRef = useRef(null);
    const industryStocksRequestIdRef = useRef(0);
    const stockDetailRequestIdRef = useRef(0);

    const loadIndustryStocks = useCallback(async (industryName) => {
        if (industryStocksAbortRef.current) {
            industryStocksAbortRef.current.abort();
        }
        if (industryStocksStreamRef.current) {
            industryStocksStreamRef.current.close();
            industryStocksStreamRef.current = null;
        }
        const currentAbort = new AbortController();
        industryStocksAbortRef.current = currentAbort;
        const requestId = industryStocksRequestIdRef.current + 1;
        industryStocksRequestIdRef.current = requestId;

        let isCanceled = false;
        try {
            setLoadingStocks(true);
            setStocksRefining(false);
            setStocksScoreStage(null);
            setStocksDisplayReady(false);
            setIndustryStocks([]);
            setSelectedIndustry(industryName);
            const quickResult = await getIndustryStocks(industryName, 20, {
                signal: currentAbort.signal,
            });
            if (
                industryStocksAbortRef.current !== currentAbort ||
                industryStocksRequestIdRef.current !== requestId
            ) {
                return;
            }

            const quickRows = quickResult || [];
            setIndustryStocks(quickRows);
            setLoadingStocks(false);
            const quickStage = getIndustryStockScoreStage(quickRows);
            setStocksScoreStage(quickStage);
            setStocksDisplayReady(
                quickRows.length === 0
                || quickStage === 'full'
                || hasDisplayReadyIndustryStockDetails(quickRows)
            );

            if (quickRows.length === 0 || quickStage !== 'quick') {
                setStocksRefining(false);
                return;
            }

            setStocksRefining(true);
            const fetchAndApplyRefinedRows = async (displayReadyGrace = false) => {
                const refinedResult = await getIndustryStocks(industryName, 20, {
                    signal: currentAbort.signal,
                });
                if (
                    industryStocksAbortRef.current !== currentAbort ||
                    industryStocksRequestIdRef.current !== requestId
                ) {
                    return false;
                }

                const refinedRows = refinedResult || [];
                if (refinedRows.length > 0) {
                    setIndustryStocks(refinedRows);
                }
                const refinedStage = getIndustryStockScoreStage(refinedRows);
                setStocksScoreStage(refinedStage);
                setStocksDisplayReady(
                    refinedRows.length === 0
                    || refinedStage === 'full'
                    || (displayReadyGrace && hasDisplayReadyIndustryStockDetails(refinedRows))
                );
                return refinedStage === 'full';
            };

            const pollForFullBuild = async () => {
                for (let attempt = 0; attempt < INDUSTRY_STOCK_FULL_POLL_ATTEMPTS; attempt += 1) {
                    await waitForAbortableDelay(currentAbort.signal, INDUSTRY_STOCK_FULL_POLL_INTERVAL_MS);
                    const buildStatus = await getIndustryStockBuildStatus(industryName, 20, {
                        signal: currentAbort.signal,
                    });
                    if (
                        industryStocksAbortRef.current !== currentAbort ||
                        industryStocksRequestIdRef.current !== requestId
                    ) {
                        return false;
                    }

                    if (buildStatus?.status === 'ready') {
                        return fetchAndApplyRefinedRows(true);
                    }
                    if (buildStatus?.status === 'failed') {
                        await fetchAndApplyRefinedRows(attempt >= 1);
                        return false;
                    }
                }
                await fetchAndApplyRefinedRows(true);
                return false;
            };

            let streamHandled = false;
            if (typeof window !== 'undefined' && typeof window.EventSource === 'function') {
                const streamUrl = `${INDUSTRY_API_BASE_URL}/industry/industries/${encodeURIComponent(industryName)}/stocks/stream?top_n=20`;
                streamHandled = await new Promise((resolve) => {
                    let timeoutId = null;
                    const stream = new window.EventSource(streamUrl);
                    industryStocksStreamRef.current = stream;

                    const closeStream = () => {
                        if (timeoutId != null) {
                            window.clearTimeout(timeoutId);
                            timeoutId = null;
                        }
                        if (industryStocksStreamRef.current === stream) {
                            industryStocksStreamRef.current = null;
                        }
                        stream.close();
                    };

                    const settle = async (status) => {
                        closeStream();
                        if (status === 'ready') {
                            const completed = await fetchAndApplyRefinedRows(true);
                            resolve(completed);
                            return;
                        }
                        resolve(false);
                    };

                    timeoutId = window.setTimeout(() => {
                        closeStream();
                        resolve(false);
                    }, 12000);

                    stream.onmessage = async (event) => {
                        try {
                            const payload = JSON.parse(event.data || '{}');
                            if (payload?.status === 'ready' || payload?.status === 'failed') {
                                await settle(payload.status);
                            }
                        } catch (streamError) {
                            console.warn('Failed to parse industry stocks SSE payload:', streamError);
                            closeStream();
                            resolve(false);
                        }
                    };

                    stream.onerror = () => {
                        closeStream();
                        resolve(false);
                    };
                });
            }

            if (!streamHandled) {
                await pollForFullBuild();
            }
            setStocksRefining(false);
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') {
                isCanceled = true;
                return;
            }
            if (
                industryStocksAbortRef.current !== currentAbort ||
                industryStocksRequestIdRef.current !== requestId
            ) {
                return;
            }
            console.error('Failed to load industry stocks:', err);
            message.error('加载行业成分股失败');
        } finally {
            if (
                !isCanceled &&
                industryStocksAbortRef.current === currentAbort &&
                industryStocksRequestIdRef.current === requestId
            ) {
                setLoadingStocks(false);
                setStocksRefining(false);
            }
        }
    }, [message, setSelectedIndustry]);

    const handleLeadingStockClick = useCallback(async (stockName) => {
        if (stockDetailAbortRef.current) {
            stockDetailAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        stockDetailAbortRef.current = currentAbort;
        const requestId = stockDetailRequestIdRef.current + 1;
        stockDetailRequestIdRef.current = requestId;

        let isCanceled = false;
        try {
            setStockDetailLoading(true);
            setStockDetailVisible(true);
            setStockDetailSymbol(stockName);
            setStockDetailError(null);
            setStockDetailData(null);
            const result = await getLeaderDetail(stockName, 'hot', {
                signal: currentAbort.signal,
            });
            if (
                stockDetailAbortRef.current !== currentAbort ||
                stockDetailRequestIdRef.current !== requestId
            ) {
                return;
            }
            setStockDetailData(result);
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') {
                isCanceled = true;
                return;
            }
            if (
                stockDetailAbortRef.current !== currentAbort ||
                stockDetailRequestIdRef.current !== requestId
            ) {
                return;
            }
            console.error('Failed to load stock detail:', err);
            setStockDetailError(err.userMessage || '加载股票详情失败');
        } finally {
            if (
                !isCanceled &&
                stockDetailAbortRef.current === currentAbort &&
                stockDetailRequestIdRef.current === requestId
            ) {
                setStockDetailLoading(false);
            }
        }
    }, []);

    const closeStockDetail = useCallback(() => {
        if (stockDetailAbortRef.current) {
            stockDetailAbortRef.current.abort();
            stockDetailAbortRef.current = null;
        }
        setStockDetailVisible(false);
        setStockDetailSymbol(null);
        setStockDetailError(null);
        setStockDetailData(null);
        setStockDetailLoading(false);
    }, []);

    useEffect(() => () => {
        if (industryStocksAbortRef.current) industryStocksAbortRef.current.abort();
        if (industryStocksStreamRef.current) industryStocksStreamRef.current.close();
        if (stockDetailAbortRef.current) stockDetailAbortRef.current.abort();
    }, []);

    return {
        closeStockDetail,
        handleLeadingStockClick,
        industryStocks,
        loadIndustryStocks,
        loadingStocks,
        setStockDetailVisible,
        stockDetailData,
        stockDetailError,
        stockDetailLoading,
        stockDetailSymbol,
        stockDetailVisible,
        stocksDisplayReady,
        stocksRefining,
        stocksScoreStage,
    };
}
