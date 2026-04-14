const mockPost = jest.fn();
const mockGet = jest.fn();
const mockPut = jest.fn();
const mockDelete = jest.fn();

jest.mock('axios', () => ({
  create: jest.fn(() => ({
    post: mockPost,
    get: mockGet,
    put: mockPut,
    delete: mockDelete,
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  })),
  isCancel: jest.fn(() => false),
}));

describe('super pricing api timeouts', () => {
  beforeEach(() => {
    mockPost.mockClear();
    mockGet.mockClear();
    mockPut.mockClear();
    mockDelete.mockClear();
    mockPost.mockResolvedValue({ data: {} });
    mockGet.mockResolvedValue({ data: {} });
    mockPut.mockResolvedValue({ data: {} });
    mockDelete.mockResolvedValue({ data: {} });
  });

  it('uses analysis timeout profile for gap analysis and screener', async () => {
    const { API_TIMEOUT_PROFILES, getGapAnalysis, runPricingScreener } = require('../services/api');

    await getGapAnalysis('AAPL', '1y');
    await runPricingScreener(['AAPL', 'MSFT'], '1y', 10, 3);

    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      '/pricing/gap-analysis',
      { symbol: 'AAPL', period: '1y' },
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.analysis })
    );
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      '/pricing/screener',
      { symbols: ['AAPL', 'MSFT'], period: '1y', limit: 10, max_workers: 3 },
      expect.objectContaining({ timeout: Math.max(API_TIMEOUT_PROFILES.analysis, 180000) })
    );
  });

  it('uses dashboard and workbench timeout profiles for overview data', async () => {
    const { API_TIMEOUT_PROFILES, getMacroOverview, getResearchTasks } = require('../services/api');

    await getMacroOverview(true);
    await getResearchTasks({ limit: 20, type: 'pricing' });

    expect(mockGet).toHaveBeenNthCalledWith(
      1,
      '/macro/overview?refresh=true',
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.dashboard })
    );
    expect(mockGet).toHaveBeenNthCalledWith(
      2,
      '/research-workbench/tasks?limit=20&type=pricing',
      expect.objectContaining({ timeout: API_TIMEOUT_PROFILES.workbench })
    );
  });
});
