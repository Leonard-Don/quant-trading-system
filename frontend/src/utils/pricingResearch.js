export const resolveAnalysisSymbol = (input, fallbackSymbol = '') => {
  const candidate = typeof input === 'string' ? input : fallbackSymbol;
  return String(candidate || '').trim().toUpperCase();
};
