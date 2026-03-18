/**
 * 图表工具函数模块
 * 提供格式化、颜色常量等共用功能
 */

/**
 * 价格格式化
 * @param {number} value - 价格值
 * @param {string} currency - 货币代码
 * @returns {string} 格式化后的价格字符串
 */
export const formatPrice = (value, currency = 'USD') => {
  if (value === null || value === undefined || isNaN(value)) return '暂无';
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
};

/**
 * 成交量格式化
 * @param {number} value - 成交量
 * @returns {string} 格式化后的成交量字符串
 */
export const formatVolume = (value) => {
  if (value === null || value === undefined || isNaN(value)) return '暂无';
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return value.toString();
};

/**
 * 百分比格式化
 * @param {number} value - 小数值 (0.05 = 5%)
 * @param {number} digits - 小数位数
 * @returns {string} 格式化后的百分比字符串
 */
export const formatPercent = (value, digits = 2) => {
  if (value === null || value === undefined || isNaN(value)) return '暂无';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(digits)}%`;
};

/**
 * 百分比格式化（不带符号）
 * @param {number} value - 小数值
 * @param {number} digits - 小数位数
 * @returns {string} 格式化后的百分比字符串
 */
export const formatPercentNoSign = (value, digits = 2) => {
  if (value === null || value === undefined || isNaN(value)) return '暂无';
  return `${(value * 100).toFixed(digits)}%`;
};

/**
 * 日期格式化
 * @param {Date|string} date - 日期
 * @param {string} format - 格式类型 'short' | 'long' | 'time'
 * @returns {string} 格式化后的日期字符串
 */
export const formatDate = (date, format = 'short') => {
  const d = new Date(date);
  if (isNaN(d.getTime())) return '暂无';
  
  switch (format) {
    case 'short':
      return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
    case 'long':
      return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
    case 'time':
      return d.toLocaleString('zh-CN', { 
        month: '2-digit', 
        day: '2-digit', 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    default:
      return d.toLocaleDateString('zh-CN');
  }
};

/**
 * 数值格式化（带千分位）
 * @param {number} value - 数值
 * @param {number} digits - 小数位数
 * @returns {string} 格式化后的数值字符串
 */
export const formatNumber = (value, digits = 0) => {
  if (value === null || value === undefined || isNaN(value)) return '暂无';
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value);
};

/**
 * 图表颜色常量
 */
export const CHART_COLORS = {
  // 涨跌颜色
  positive: '#10b981',      // 绿色 - 上涨
  negative: '#ef4444',      // 红色 - 下跌
  neutral: '#6b7280',       // 灰色 - 持平
  
  // 主题色
  primary: '#38bdf8',       // 天蓝色
  secondary: '#8b5cf6',     // 紫色
  accent: '#f59e0b',        // 橙色
  
  // 图表元素
  grid: 'rgba(255, 255, 255, 0.06)',
  axis: 'rgba(255, 255, 255, 0.4)',
  tooltip: 'rgba(15, 23, 42, 0.95)',
  
  // 技术指标
  sma5: '#fbbf24',          // 黄色 - 5日均线
  sma10: '#38bdf8',         // 蓝色 - 10日均线
  sma20: '#a855f7',         // 紫色 - 20日均线
  volume: '#60a5fa',        // 浅蓝 - 成交量
  
  // K线颜色
  candleUp: '#10b981',      // 阳线
  candleDown: '#ef4444',    // 阴线
  candleWick: '#94a3b8'     // 影线
};

/**
 * 根据涨跌获取颜色
 * @param {number} change - 变化值
 * @returns {string} 颜色代码
 */
export const getChangeColor = (change) => {
  if (change > 0) return CHART_COLORS.positive;
  if (change < 0) return CHART_COLORS.negative;
  return CHART_COLORS.neutral;
};

/**
 * 计算价格变化百分比
 * @param {number} current - 当前价格
 * @param {number} previous - 之前价格
 * @returns {number} 变化百分比（小数形式）
 */
export const calculateChange = (current, previous) => {
  if (!previous || previous === 0) return 0;
  return (current - previous) / previous;
};

/**
 * Y轴刻度格式化（自动缩写大数值）
 * @param {number} value - 数值
 * @returns {string} 格式化后的字符串
 */
export const formatAxisValue = (value) => {
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return value.toFixed(0);
};

/**
 * 生成渐变色数组
 * @param {string} baseColor - 基础颜色（hex格式）
 * @param {number} steps - 步数
 * @returns {string[]} 颜色数组
 */
export const generateGradient = (baseColor, steps = 5) => {
  const colors = [];
  for (let i = 0; i < steps; i++) {
    const opacity = 1 - (i / steps) * 0.6;
    colors.push(`${baseColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')}`);
  }
  return colors;
};

export default {
  formatPrice,
  formatVolume,
  formatPercent,
  formatPercentNoSign,
  formatDate,
  formatNumber,
  formatAxisValue,
  getChangeColor,
  calculateChange,
  generateGradient,
  CHART_COLORS
};
