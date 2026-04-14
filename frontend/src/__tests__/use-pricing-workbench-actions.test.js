import { act, renderHook } from '@testing-library/react';

import usePricingWorkbenchActions from '../components/pricing/usePricingWorkbenchActions';

jest.mock('../services/api', () => ({
  addResearchTaskSnapshot: jest.fn(),
  createResearchTask: jest.fn(),
}));

jest.mock('../components/research-playbook/playbookViewModels', () => ({
  buildPricingWorkbenchPayload: jest.fn(),
}));

const mockMessageApi = {
  error: jest.fn(),
  info: jest.fn(),
  success: jest.fn(),
  warning: jest.fn(),
};

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
}));

const { addResearchTaskSnapshot, createResearchTask } = require('../services/api');
const { buildPricingWorkbenchPayload } = require('../components/research-playbook/playbookViewModels');

describe('usePricingWorkbenchActions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    buildPricingWorkbenchPayload.mockReturnValue({
      title: 'AAPL 定价研究',
      snapshot: {
        title: 'AAPL 快照',
        payload: {
          symbol: 'AAPL',
        },
      },
      refresh_priority_event: {
        reason: 'priority_escalated',
      },
    });
    createResearchTask.mockResolvedValue({
      data: { id: 'rw_123', title: 'AAPL 定价研究' },
    });
    addResearchTaskSnapshot.mockResolvedValue({
      data: { id: 'snapshot_1' },
    });
  });

  it('calls queue continuation callbacks after save and snapshot update succeed', async () => {
    const onSaveSuccess = jest.fn();
    const onUpdateSnapshotSuccess = jest.fn();

    const { result } = renderHook(() => usePricingWorkbenchActions({
      data: { symbol: 'AAPL' },
      gapHistory: null,
      mergedContext: { view: 'pricing', symbol: 'AAPL' },
      onSaveSuccess,
      onUpdateSnapshotSuccess,
      peerComparison: null,
      period: '1y',
      playbook: { headline: 'AAPL 定价研究剧本' },
      sensitivity: null,
      symbol: 'AAPL',
    }));

    await act(async () => {
      await result.current.handleSaveTask();
    });

    expect(onSaveSuccess).toHaveBeenCalledWith('rw_123');
    expect(result.current.savedTaskId).toBe('rw_123');

    await act(async () => {
      await result.current.handleUpdateSnapshot();
    });

    expect(addResearchTaskSnapshot).toHaveBeenCalledWith('rw_123', expect.objectContaining({
      snapshot: expect.any(Object),
      refresh_priority_event: { reason: 'priority_escalated' },
    }));
    expect(onUpdateSnapshotSuccess).toHaveBeenCalledWith('rw_123');
  });
});
