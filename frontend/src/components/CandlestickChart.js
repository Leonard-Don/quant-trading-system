import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Space, Button, Spin, Row, Col, Statistic, Popover, Checkbox, Divider } from 'antd';
import { ReloadOutlined, RiseOutlined, FallOutlined, LineChartOutlined, SettingOutlined } from '@ant-design/icons';
import { createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';

import { getMarketData } from '../services/api';

const CandlestickChart = ({ symbol, embedMode = false }) => {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRef = useRef({}); // Store all series references

    const [loading, setLoading] = useState(false);

    const [stats, setStats] = useState(null);
    const [originalData, setOriginalData] = useState([]);

    // Indicators configuration
    const [indicators, setIndicators] = useState({
        ma5: true,
        ma10: true,
        ma20: true,
        ma30: true,
        ema12: false,
        ema26: false,
        boll: true
    });

    const fetchKlineData = useCallback(async () => {
        if (!symbol) return;
        setLoading(true);
        try {
            const result = await getMarketData({ symbol });
            if (result && result.data && result.data.data && result.data.data.length > 0) {
                const rawData = Array.isArray(result.data.data) ? result.data.data : [];
                setOriginalData(rawData);
            } else {
                setOriginalData([]);
            }
        } catch (err) {
            console.error('Fetch error:', err);
        } finally {
            setLoading(false);
        }
    }, [symbol]);

    useEffect(() => {
        fetchKlineData();
    }, [fetchKlineData]);


    // Initialize Chart
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#141414' },
                textColor: '#d9d9d9',
            },
            grid: {
                vertLines: { color: '#262626' },
                horzLines: { color: '#262626' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            crosshair: { mode: CrosshairMode.Normal },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: '#434343',
            },
            rightPriceScale: { borderColor: '#434343' },
        });

        chartRef.current = chart;

        // --- Core Series ---
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#00b578', downColor: '#ff3030',
            borderUpColor: '#00b578', borderDownColor: '#ff3030',
            wickUpColor: '#00b578', wickDownColor: '#ff3030',
        });
        seriesRef.current.candle = candlestickSeries;

        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: '#26a69a',
            priceFormat: { type: 'volume' },
            priceScaleId: '', // Overlay
        });
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });
        seriesRef.current.volume = volumeSeries;

        // --- Indicators ---
        // Basic MAs
        seriesRef.current.ma5 = chart.addSeries(LineSeries, { color: '#9c27b0', lineWidth: 1, title: 'MA 5', visible: false });
        seriesRef.current.ma10 = chart.addSeries(LineSeries, { color: '#ff9800', lineWidth: 1, title: 'MA 10', visible: false });
        seriesRef.current.ma20 = chart.addSeries(LineSeries, { color: '#2962FF', lineWidth: 1, title: 'MA 20', visible: false });
        seriesRef.current.ma30 = chart.addSeries(LineSeries, { color: '#e91e63', lineWidth: 1, title: 'MA 30', visible: false });

        // EMAs
        seriesRef.current.ema12 = chart.addSeries(LineSeries, { color: '#00bcd4', lineWidth: 1, title: 'EMA 12', visible: false });
        seriesRef.current.ema26 = chart.addSeries(LineSeries, { color: '#ff5722', lineWidth: 1, title: 'EMA 26', visible: false });

        // Bollinger Bands
        seriesRef.current.bollUpper = chart.addSeries(LineSeries, { color: '#607d8b', lineWidth: 1, title: 'BOLL Upper', lineStyle: 2, visible: false });
        seriesRef.current.bollMid = chart.addSeries(LineSeries, { color: '#607d8b', lineWidth: 1, title: 'BOLL Mid', lineStyle: 0, visible: false });
        seriesRef.current.bollLower = chart.addSeries(LineSeries, { color: '#607d8b', lineWidth: 1, title: 'BOLL Lower', lineStyle: 2, visible: false });


        // Crosshair handler
        chart.subscribeCrosshairMove(param => {
            if (!param.point || !param.time || param.point.x < 0 || param.point.x > chart.timeScale().width()) {
                updateStatsToLatest();
                return;
            }

            const time = param.time;
            const candleData = param.seriesData.get(candlestickSeries);
            const volumeData = param.seriesData.get(volumeSeries);

            if (candleData) {
                const priceChange = candleData.close - candleData.open;
                const percentChange = (priceChange / candleData.open) * 100;

                const avgVol = chartRef.current?._avgVolMap?.[time] || (volumeData ? volumeData.value : 0);

                setStats({
                    latestPrice: candleData.close,
                    change: percentChange,
                    high: candleData.high,
                    low: candleData.low,
                    open: candleData.open,
                    volume: volumeData ? volumeData.value : 0,
                    avgVolume: avgVol,
                    time: time
                });
            }
        });

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    // Handling Data Updates & Indicator Calculation
    useEffect(() => {
        if (!originalData.length || !seriesRef.current.candle) return;

        // 1. Prepare Core Data
        const mappedData = originalData.map(item => {
            // Optimization: avoid moment.js in loop
            const dateStr = new Date(item.date).toISOString().split('T')[0];
            return {
                time: dateStr,
                open: parseFloat(item.open),
                high: parseFloat(item.high),
                low: parseFloat(item.low),
                close: parseFloat(item.close),
                volume: parseFloat(item.volume || 0),
            };
        }).sort((a, b) => a.time.localeCompare(b.time));

        const uniqueData = [];
        let lastTime = null;
        mappedData.forEach(d => {
            if (d.time !== lastTime && !isNaN(d.open)) {
                uniqueData.push(d);
                lastTime = d.time;
            }
        });

        if (uniqueData.length === 0) return;

        // Set Candle Data
        seriesRef.current.candle.setData(uniqueData);

        // Set Volume Data
        const volData = uniqueData.map(d => ({
            time: d.time,
            value: d.volume,
            color: d.close >= d.open ? 'rgba(0, 181, 120, 0.5)' : 'rgba(255, 48, 48, 0.5)',
        }));
        seriesRef.current.volume.setData(volData);

        // Calculate Indicators
        const closes = uniqueData.map(d => d.close);

        // MAs
        const ma5 = calculateSMA(uniqueData, 5);
        const ma10 = calculateSMA(uniqueData, 10);
        const ma20 = calculateSMA(uniqueData, 20);
        const ma30 = calculateSMA(uniqueData, 30);

        // Avg Volume (SMA 20 of Volume) - calculated manually here or helper?
        // Helper expects {time, close} structure usually, but calculateSMA splits it?
        // My calculateSMA helper: uses `data[i-j].close`. 
        // Need a calculateVolumeSMA helper or modify calculateSMA to accept 'key'.
        // Or just map uniqueData to { ..., close: volume } temporarily? 
        // Cleaner to make calculateSMA accept key. But for now, let's map.
        const volDataForSma = uniqueData.map(d => ({ ...d, close: d.volume }));
        const avgVolData = calculateSMA(volDataForSma, 20);

        // We need to store this accessible for crosshair.
        // Can attach to chart data? Or just quick look up map? 
        // Easiest is to create a map: time -> avgVol
        const avgVolMap = {};
        avgVolData.forEach(d => { avgVolMap[d.time] = d.value; });
        chartRef.current._avgVolMap = avgVolMap; // Attach to ref for easy access

        seriesRef.current.ma5.setData(ma5);
        seriesRef.current.ma10.setData(ma10);
        seriesRef.current.ma20.setData(ma20);
        seriesRef.current.ma30.setData(ma30);

        // EMAs
        const ema12 = calculateEMA(uniqueData, 12);
        const ema26 = calculateEMA(uniqueData, 26);

        seriesRef.current.ema12.setData(ema12);
        seriesRef.current.ema26.setData(ema26);

        // Bollinger
        const boll = calculateBollinger(uniqueData, 20, 2);
        seriesRef.current.bollUpper.setData(boll.upper);
        seriesRef.current.bollMid.setData(boll.mid);
        seriesRef.current.bollLower.setData(boll.lower);

        // Fit Content
        chartRef.current.timeScale().fitContent();

        updateStatsToLatest(uniqueData);

    }, [originalData]);

    // Handling Visibility Toggle
    useEffect(() => {
        if (!seriesRef.current.ma5) return; // Wait for init

        seriesRef.current.ma5.applyOptions({ visible: indicators.ma5 });
        seriesRef.current.ma10.applyOptions({ visible: indicators.ma10 });
        seriesRef.current.ma20.applyOptions({ visible: indicators.ma20 });
        seriesRef.current.ma30.applyOptions({ visible: indicators.ma30 });

        seriesRef.current.ema12.applyOptions({ visible: indicators.ema12 });
        seriesRef.current.ema26.applyOptions({ visible: indicators.ema26 });

        seriesRef.current.bollUpper.applyOptions({ visible: indicators.boll });
        seriesRef.current.bollMid.applyOptions({ visible: indicators.boll });
        seriesRef.current.bollLower.applyOptions({ visible: indicators.boll });

    }, [indicators]);


    const updateStatsToLatest = (data = null) => {
        const currentData = data || (originalData.map(d => ({ ...d, time: new Date(d.date).toISOString().split('T')[0] })) || []);
        if (currentData.length > 0) {
            const last = currentData[currentData.length - 1];
            let prevClose = last.open;
            if (currentData.length > 1) {
                prevClose = currentData[currentData.length - 2].close;
            }
            const change = ((last.close - prevClose) / prevClose) * 100;

            const avgVol = chartRef.current?._avgVolMap?.[last.time] || last.volume; // Fallback to volume if no MA yet

            setStats({
                latestPrice: last.close,
                change: change,
                high: last.high,
                low: last.low,
                avgVolume: avgVol
            });
        }
    };

    // --- Math Helpers ---
    const calculateSMA = (data, windowSize) => {
        let result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < windowSize - 1) continue;
            let sum = 0;
            for (let j = 0; j < windowSize; j++) {
                sum += data[i - j].close;
            }
            result.push({ time: data[i].time, value: sum / windowSize });
        }
        return result;
    };

    const calculateEMA = (data, windowSize) => {
        let result = [];
        const k = 2 / (windowSize + 1);
        // Start with SMA for first point or just close
        let ema = data[0].close;
        result.push({ time: data[0].time, value: ema });

        for (let i = 1; i < data.length; i++) {
            ema = data[i].close * k + ema * (1 - k);
            result.push({ time: data[i].time, value: ema });
        }
        return result;
    };

    const calculateBollinger = (data, windowSize, multiplier) => {
        let upper = [], mid = [], lower = [];

        for (let i = 0; i < data.length; i++) {
            if (i < windowSize - 1) continue;

            // SMA
            let sum = 0;
            for (let j = 0; j < windowSize; j++) {
                sum += data[i - j].close;
            }
            const sma = sum / windowSize;

            // StdDev
            let sumSqDiff = 0;
            for (let j = 0; j < windowSize; j++) {
                sumSqDiff += Math.pow(data[i - j].close - sma, 2);
            }
            const stdDev = Math.sqrt(sumSqDiff / windowSize);

            upper.push({ time: data[i].time, value: sma + multiplier * stdDev });
            mid.push({ time: data[i].time, value: sma });
            lower.push({ time: data[i].time, value: sma - multiplier * stdDev });
        }
        return { upper, mid, lower };
    };

    // --- UI Content ---
    const indicatorContent = (
        <Space direction="vertical">
            <Divider orientation="left" style={{ margin: '5px 0' }}>均线 (MA)</Divider>
            <Checkbox checked={indicators.ma5} onChange={(e) => setIndicators({ ...indicators, ma5: e.target.checked })}>MA 5 (周)</Checkbox>
            <Checkbox checked={indicators.ma10} onChange={(e) => setIndicators({ ...indicators, ma10: e.target.checked })}>MA 10 (双周)</Checkbox>
            <Checkbox checked={indicators.ma20} onChange={(e) => setIndicators({ ...indicators, ma20: e.target.checked })}>MA 20 (月)</Checkbox>
            <Checkbox checked={indicators.ma30} onChange={(e) => setIndicators({ ...indicators, ma30: e.target.checked })}>MA 30 (生命线)</Checkbox>

            <Divider orientation="left" style={{ margin: '5px 0' }}>指数均线 (EMA)</Divider>
            <Checkbox checked={indicators.ema12} onChange={(e) => setIndicators({ ...indicators, ema12: e.target.checked })}>EMA 12</Checkbox>
            <Checkbox checked={indicators.ema26} onChange={(e) => setIndicators({ ...indicators, ema26: e.target.checked })}>EMA 26</Checkbox>

            <Divider orientation="left" style={{ margin: '5px 0' }}>通道指标</Divider>
            <Checkbox checked={indicators.boll} onChange={(e) => setIndicators({ ...indicators, boll: e.target.checked })}>Bollinger Bands</Checkbox>
        </Space>
    );

    return (
        <Card
            bordered={!embedMode}
            title={
                embedMode ? null : (
                    <Space>
                        <LineChartOutlined />
                        <span>K线图表</span>
                        {symbol && <span style={{ fontSize: '14px', color: '#888' }}>({symbol})</span>}
                    </Space>
                )
            }
            extra={
                <Space>
                    <Popover content={indicatorContent} title="技术指标设置" trigger="click" placement="bottomRight">
                        <Button icon={<SettingOutlined />}>指标</Button>
                    </Popover>
                    <Button icon={<ReloadOutlined />} onClick={fetchKlineData} loading={loading} />
                </Space>
            }
            styles={embedMode ? { body: { padding: 0 } } : undefined}
            style={embedMode ? { background: 'transparent' } : {}}
        >
            {
                stats && (
                    <Row gutter={[24, 24]} style={{ marginBottom: 16, padding: '0 12px' }}>
                        <Col span={6}>
                            <Statistic title="最新价" value={stats.latestPrice} precision={2} prefix="$" valueStyle={{ fontSize: 16, fontWeight: 500 }} />
                        </Col>
                        <Col span={6}>
                            <Statistic
                                title="涨跌幅"
                                value={stats.change}
                                precision={2}
                                suffix="%"
                                valueStyle={{ fontSize: 16, fontWeight: 500, color: stats.change >= 0 ? '#00b578' : '#ff3030' }}
                                prefix={stats.change >= 0 ? <RiseOutlined /> : <FallOutlined />}
                            />
                        </Col>
                        <Col span={6}>
                            <Statistic title="最高价" value={stats.high} precision={2} prefix="$" valueStyle={{ fontSize: 16, fontWeight: 500, color: '#00b578' }} />
                        </Col>
                        <Col span={6}>
                            <Statistic title="最低价" value={stats.low} precision={2} prefix="$" valueStyle={{ fontSize: 16, fontWeight: 500, color: '#ff3030' }} />
                        </Col>
                        <Col span={6}>
                            <Statistic title="均量" value={(stats.avgVolume / 1000000).toFixed(1)} suffix="M" valueStyle={{ fontSize: 16, fontWeight: 500 }} />
                        </Col>
                    </Row>
                )
            }

            {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 10 }}><Spin size="large" /></div>}

            <div ref={chartContainerRef} style={{ width: '100%', height: 400, position: 'relative' }} />
        </Card>
    );
};

export default CandlestickChart;
