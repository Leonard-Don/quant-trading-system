export const REALTIME_QUOTE_LIST_LAYOUT_BREAKPOINTS = Object.freeze({
  stackedMinWidth: 820,
  wideMinWidth: 1180,
});
export const REALTIME_QUOTE_BOARD_DENSITY_BREAKPOINTS = Object.freeze({
  compactMaxWidth: 1040,
});

export const getRealtimeQuoteListLayoutMode = (containerWidth) => {
  const numericWidth = Number(containerWidth);

  if (!Number.isFinite(numericWidth) || numericWidth <= 0) {
    return 'wide';
  }

  if (numericWidth < REALTIME_QUOTE_LIST_LAYOUT_BREAKPOINTS.stackedMinWidth) {
    return 'stacked';
  }

  if (numericWidth < REALTIME_QUOTE_LIST_LAYOUT_BREAKPOINTS.wideMinWidth) {
    return 'split';
  }

  return 'wide';
};

export const getRealtimeQuoteBoardDensityMode = (containerWidth) => {
  const numericWidth = Number(containerWidth);

  if (!Number.isFinite(numericWidth) || numericWidth <= 0) {
    return 'comfortable';
  }

  if (numericWidth <= REALTIME_QUOTE_BOARD_DENSITY_BREAKPOINTS.compactMaxWidth) {
    return 'compact';
  }

  return 'comfortable';
};
