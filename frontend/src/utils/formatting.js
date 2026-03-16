export const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
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
