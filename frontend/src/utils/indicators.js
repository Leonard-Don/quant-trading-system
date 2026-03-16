/**
 * 技术指标计算工具函数
 */

/**
 * 计算简单移动平均线 (SMA)
 * @param {number[]} prices - 价格数组
 * @param {number} period - 周期
 * @returns {Array<number|null>} SMA数组
 */
export const calculateSMA = (prices, period) => {
    if (!prices || prices.length === 0) return [];

    const result = [];
    for (let i = 0; i < prices.length; i++) {
        if (i < period - 1) {
            result.push(null);
        } else {
            const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
            result.push(sum / period);
        }
    }
    return result;
};

/**
 * 计算指数移动平均线 (EMA)
 * @param {number[]} prices - 价格数组
 * @param {number} period - 周期
 * @returns {Array<number|null>} EMA数组
 */
export const calculateEMA = (prices, period) => {
    if (!prices || prices.length === 0) return [];

    const result = [];
    const multiplier = 2 / (period + 1);

    // 首个EMA通常使用SMA作为初始值
    let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;

    for (let i = 0; i < prices.length; i++) {
        if (i < period - 1) {
            result.push(null);
        } else if (i === period - 1) {
            result.push(ema); // 初始EMA值
        } else {
            ema = (prices[i] - ema) * multiplier + ema;
            result.push(ema);
        }
    }
    return result;
};

/**
 * 计算布林带 (Bollinger Bands)
 * @param {number[]} prices - 价格数组
 * @param {number} period - 周期
 * @param {number} stdDev - 标准差倍数
 * @returns {Object} { upper, middle, lower } 数组对象
 */
export const calculateBollinger = (prices, period = 20, stdDev = 2) => {
    if (!prices || prices.length === 0) return { upper: [], middle: [], lower: [] };

    // 获取SMA (中轨)
    const sma = calculateSMA(prices, period);
    const upper = [];
    const lower = [];

    for (let i = 0; i < prices.length; i++) {
        if (i < period - 1) {
            upper.push(null);
            lower.push(null);
        } else {
            const slice = prices.slice(i - period + 1, i + 1);
            const mean = sma[i];
            const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
            const std = Math.sqrt(variance);

            upper.push(mean + stdDev * std);
            lower.push(mean - stdDev * std);
        }
    }

    return { upper, middle: sma, lower };
};

/**
 * 计算RSI相对强弱指标 (简化版作为备用)
 * @param {number[]} prices - 价格数组
 * @param {number} period - 周期
 * @returns {Array<number|null>} RSI数组
 */
export const calculateRSI = (prices, period = 14) => {
    if (!prices || prices.length === 0) return [];

    const result = [];
    // 更多指标可在此扩展
    return result;
}

const indicators = {
    calculateSMA,
    calculateEMA,
    calculateBollinger,
    calculateRSI
};

export default indicators;
