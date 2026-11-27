export const formatCurrency = (value, currency = 'USD') => {
  return new Intl.NumberFormat(currency === 'CNY' ? 'zh-CN' : 'en-US', {
    style: 'currency',
    currency,
  }).format(value);
};

export const formatPercentage = (value) => {
  if (value === undefined || value === null) return '-';
  return `${(value * 100).toFixed(2)}%`;
};

export const getValueColor = (value) => {
  if (value > 0) return 'var(--accent-success, #52c41a)';
  if (value < 0) return 'var(--accent-danger, #ff4d4f)';
  return 'var(--text-muted, #999)';
};
