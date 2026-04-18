jest.mock('../services/api', () => ({
  getIndustryStockBuildStatus: jest.fn(),
  getIndustryStocks: jest.fn(),
  getLeaderDetail: jest.fn(),
}));

import { hasDisplayReadyIndustryStockDetails } from '../components/industry/useIndustryStocks';

describe('industry stock display readiness', () => {
  it('treats the table as ready when the first visible rows already contain usable detail fields', () => {
    const stocks = [
      { symbol: '600519', total_score: 95, market_cap: 2_100_000_000_000, pe_ratio: 23.4, change_pct: 1.8 },
      { symbol: '000858', total_score: 88, market_cap: 980_000_000_000 },
      { symbol: '600036', total_score: 82 },
      { symbol: '601166', total_score: 77 },
      { symbol: '601398', total_score: 75 },
    ];

    expect(hasDisplayReadyIndustryStockDetails(stocks)).toBe(true);
  });

  it('keeps quick rows marked as not ready when the first visible rows still have no real details', () => {
    const stocks = [
      { symbol: '600519', total_score: 95 },
      { symbol: '000858', total_score: 88 },
      { symbol: '600036', total_score: 82 },
      { symbol: '601166', total_score: 77 },
      { symbol: '601398', total_score: 75 },
      { symbol: '300750', total_score: 70, market_cap: 910_000_000_000, pe_ratio: 26.2 },
    ];

    expect(hasDisplayReadyIndustryStockDetails(stocks)).toBe(false);
  });
});
