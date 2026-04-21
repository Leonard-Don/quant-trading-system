import dayjs from './dayjs';

const ROLLING_ONE_YEAR_MODE = 'rolling_one_year';
const CUSTOM_MODE = 'custom';

const normalizeDateValue = (value) => {
  if (!value) {
    return null;
  }

  if (dayjs.isDayjs(value)) {
    return value.startOf('day');
  }

  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.startOf('day') : null;
};

const normalizeDateRange = (dateRange) => {
  if (!Array.isArray(dateRange) || dateRange.length < 2) {
    return null;
  }

  const start = normalizeDateValue(dateRange[0]);
  const end = normalizeDateValue(dateRange[1]);
  if (!start || !end) {
    return null;
  }

  return [start, end];
};

export const getDefaultBacktestDateRange = (anchor = dayjs()) => {
  const end = normalizeDateValue(anchor) || dayjs().startOf('day');
  return [end.subtract(1, 'year'), end];
};

export const getDefaultBacktestDateRangeStrings = (anchor = dayjs(), format = 'YYYY-MM-DD') => {
  const [start, end] = getDefaultBacktestDateRange(anchor);
  return [start.format(format), end.format(format)];
};

export const getBacktestDraftDateRangeMode = (dateRange, anchor = dayjs()) => {
  const normalizedDateRange = normalizeDateRange(dateRange);
  if (!normalizedDateRange) {
    return CUSTOM_MODE;
  }

  const [expectedStart, expectedEnd] = getDefaultBacktestDateRange(anchor);
  const [start, end] = normalizedDateRange;
  if (start.isSame(expectedStart, 'day') && end.isSame(expectedEnd, 'day')) {
    return ROLLING_ONE_YEAR_MODE;
  }

  return CUSTOM_MODE;
};

export const resolveBacktestDraftDateRange = (draft = {}, anchor = dayjs()) => {
  const fallback = getDefaultBacktestDateRange(anchor);
  const normalizedDateRange = normalizeDateRange(draft?.dateRange);
  if (!normalizedDateRange) {
    return fallback;
  }

  if (draft?.dateRangeMode === ROLLING_ONE_YEAR_MODE) {
    return fallback;
  }

  const updatedAt = normalizeDateValue(draft?.updated_at);
  const [start, end] = normalizedDateRange;
  const durationDays = end.diff(start, 'day');
  const looksLikeLegacyRollingDefault = (
    updatedAt
    && end.isSame(updatedAt, 'day')
    && durationDays >= 360
    && durationDays <= 370
  );

  return looksLikeLegacyRollingDefault ? fallback : normalizedDateRange;
};

