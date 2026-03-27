import { resolveAnalysisSymbol } from '../utils/pricingResearch';

describe('pricingResearch symbol normalization', () => {
  it('uses the fallback symbol when button click passes an event object', () => {
    const syntheticEvent = { type: 'click', target: {} };

    expect(resolveAnalysisSymbol(syntheticEvent, ' aapl ')).toBe('AAPL');
  });

  it('prefers an explicit override symbol when provided', () => {
    expect(resolveAnalysisSymbol(' msft ', 'aapl')).toBe('MSFT');
  });
});
