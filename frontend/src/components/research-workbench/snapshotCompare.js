import { extractPricingMetrics, buildPricingComparisonRows } from './snapshotComparePricing';
import { extractCrossMarketMetrics, buildCrossMarketComparisonRows } from './snapshotCompareCrossMarket';

export const buildSnapshotComparison = (taskType, baseSnapshot, targetSnapshot) => {
  if (!baseSnapshot || !targetSnapshot) {
    return null;
  }

  if (taskType === 'pricing' || taskType === 'macro_mispricing') {
    const base = extractPricingMetrics(baseSnapshot);
    const target = extractPricingMetrics(targetSnapshot);
    return buildPricingComparisonRows(base, target);
  }

  const base = extractCrossMarketMetrics(baseSnapshot);
  const target = extractCrossMarketMetrics(targetSnapshot);
  return buildCrossMarketComparisonRows(base, target);
};
