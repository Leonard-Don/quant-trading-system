export const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return numeric.toFixed(digits);
};

export const formatPercent = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${(numeric * 100).toFixed(digits)}%`;
};

export const formatPercentPoints = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${numeric.toFixed(digits)}%`;
};

export const formatSignedDelta = (left, right, formatter = formatNumber) => {
  if (left === null || left === undefined || right === null || right === undefined) return null;
  const leftNumeric = Number(left);
  const rightNumeric = Number(right);
  if (Number.isNaN(leftNumeric) || Number.isNaN(rightNumeric)) return null;
  const delta = rightNumeric - leftNumeric;
  const prefix = delta > 0 ? '+' : '';
  return `${prefix}${formatter(delta)}`;
};

export const buildNumericRow = (key, label, baseVal, targetVal, formatter = formatNumber) => ({
  key,
  label,
  left: formatter(baseVal),
  right: formatter(targetVal),
  delta: formatSignedDelta(baseVal, targetVal, formatter),
});

export const buildTextRow = (key, label, baseVal, targetVal, changeLabel) => ({
  key,
  label,
  left: baseVal,
  right: targetVal,
  delta: baseVal === targetVal ? '不变' : (changeLabel || `${baseVal} -> ${targetVal}`),
});

export const extractViewContextMetrics = (payload = {}) => {
  const viewContext = payload.view_context || payload.workbench_view_context || {};
  return {
    viewContextSummary: viewContext.summary || '-',
    viewContextTask: viewContext.scoped_task_label || '-',
  };
};

export const buildDriverLookup = (items = []) =>
  Object.fromEntries((items || []).map((item) => [item.key, item]));

export const buildDriverTrendRows = (baseDrivers = [], targetDrivers = []) => {
  const baseLookup = buildDriverLookup(baseDrivers);
  const targetLookup = buildDriverLookup(targetDrivers);
  const keys = Array.from(new Set([...Object.keys(baseLookup), ...Object.keys(targetLookup)]));

  return keys
    .map((key) => {
      const left = Number(baseLookup[key]?.value || 0);
      const right = Number(targetLookup[key]?.value || 0);
      return {
        key: `driver-${key}`,
        label: `Driver: ${targetLookup[key]?.label || baseLookup[key]?.label || key}`,
        left: formatNumber(left),
        right: formatNumber(right),
        delta: formatSignedDelta(left, right, (value) => formatNumber(value)),
        magnitude: Math.abs(right - left),
      };
    })
    .sort((a, b) => b.magnitude - a.magnitude)
    .slice(0, 3)
    .map(({ magnitude, ...row }) => row);
};
