import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import useResearchWorkbenchData from '../components/research-workbench/useResearchWorkbenchData';

jest.mock('../services/api', () => ({
  getAltDataSnapshot: jest.fn(),
  getMacroOverview: jest.fn(),
  getResearchTask: jest.fn(),
  getResearchTaskStats: jest.fn(),
  getResearchTasks: jest.fn(),
  getResearchTaskTimeline: jest.fn(),
}));

jest.mock('../utils/researchTaskSignals', () => ({
  buildResearchTaskRefreshSignals: jest.fn(({ researchTasks }) => ({
    prioritized: [],
    byTaskId: Object.fromEntries((researchTasks || []).map((task) => [task.id, { severity: 'low' }])),
  })),
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

const {
  getAltDataSnapshot,
  getMacroOverview,
  getResearchTask,
  getResearchTaskStats,
  getResearchTasks,
  getResearchTaskTimeline,
} = require('../services/api');

function WorkbenchHookHarness() {
  const {
    filters,
    selectedTaskId,
    setFilters,
    snapshotSummaryOptions,
    workbenchQueueMode,
    workbenchQueueAction,
  } = useResearchWorkbenchData();

  return (
    <div>
      <div data-testid="reason">{filters.reason}</div>
      <div data-testid="snapshot-view">{filters.snapshotView}</div>
      <div data-testid="snapshot-fingerprint">{filters.snapshotFingerprint}</div>
      <div data-testid="snapshot-summary">{filters.snapshotSummary}</div>
      <div data-testid="snapshot-option-label">{snapshotSummaryOptions?.[0]?.label || ''}</div>
      <div data-testid="snapshot-option-fingerprint">{snapshotSummaryOptions?.[0]?.fingerprint || ''}</div>
      <div data-testid="keyword">{filters.keyword}</div>
      <div data-testid="queue-mode">{workbenchQueueMode}</div>
      <div data-testid="queue-action">{workbenchQueueAction}</div>
      <div data-testid="task">{selectedTaskId}</div>
      <button
        type="button"
        onClick={() => setFilters((prev) => ({
          ...prev,
          reason: 'priority_updated',
          snapshotView: 'scoped',
          snapshotFingerprint: 'wv_pricing_escalated',
          snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
          keyword: 'decay',
        }))}
      >
        set-workbench-filters
      </button>
    </div>
  );
}

describe('useResearchWorkbenchData url sync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.history.replaceState(
      null,
      '',
      '/?view=workbench&workbench_reason=priority_relaxed&workbench_snapshot_view=filtered&workbench_snapshot_fingerprint=wv_cross_relaxed&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E5%9B%BE%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E7%BC%93%E5%92%8C%20%C2%B7%20%E7%B1%BB%E5%9E%8B%EF%BC%9ACross-Market&workbench_keyword=hedge&task=task_2'
    );

    const tasks = [
      {
        id: 'task_1',
        title: 'Policy Task',
        status: 'new',
        type: 'pricing',
        source: 'manual',
        updated_at: '2026-04-11T09:00:00Z',
        snapshot: {
          payload: {
            view_context: {
              summary: '快速视图：自动排序首次入列 · 类型：Pricing',
              scoped_task_label: '当前定位：task_1',
              has_filters: true,
            },
          },
        },
        timeline: [{ type: 'refresh_priority', meta: { change_type: 'new' } }],
      },
      {
        id: 'task_2',
        title: 'Hedge Task',
        status: 'in_progress',
        type: 'cross_market',
        source: 'godeye',
        updated_at: '2026-04-11T10:00:00Z',
        snapshot: {
          payload: {
            view_context: {
              summary: '快速视图：自动排序缓和 · 类型：Cross-Market',
              scoped_task_label: '当前定位：task_2',
              has_filters: true,
            },
          },
        },
        timeline: [{ type: 'refresh_priority', meta: { change_type: 'relaxed' } }],
      },
    ];

    getResearchTasks.mockResolvedValue({ data: tasks });
    getResearchTaskStats.mockResolvedValue({
      data: {
        total: 2,
        status_counts: { new: 1, in_progress: 1 },
        snapshot_view_queues: [
          {
            label: '快速视图：自动排序升档 · 类型：Pricing',
            value: '快速视图：自动排序升档 · 类型：Pricing',
            fingerprint: 'wv_pricing_global',
            count: 5,
            scoped_count: 2,
          },
        ],
      },
    });
    getMacroOverview.mockResolvedValue({});
    getAltDataSnapshot.mockResolvedValue({});
    getResearchTask.mockImplementation(async (taskId) => ({
      data: tasks.find((task) => task.id === taskId) || null,
    }));
    getResearchTaskTimeline.mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('hydrates filters from the url and syncs keyword changes back into the url', async () => {
    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('reason').textContent).toBe('priority_relaxed');
    });
    expect(screen.getByTestId('snapshot-view').textContent).toBe('filtered');
    expect(screen.getByTestId('snapshot-fingerprint').textContent).toBe('wv_cross_relaxed');
    expect(screen.getByTestId('snapshot-summary').textContent).toBe('快速视图：自动排序缓和 · 类型：Cross-Market');
    await waitFor(() => {
      expect(screen.getByTestId('snapshot-option-label').textContent).toBe('快速视图：自动排序升档 · 类型：Pricing');
    });
    expect(screen.getByTestId('snapshot-option-fingerprint').textContent).toBe('wv_pricing_global');
    expect(screen.getByTestId('keyword').textContent).toBe('hedge');
    await waitFor(() => {
      expect(screen.getByTestId('task').textContent).toBe('task_2');
    });

    fireEvent.click(screen.getByRole('button', { name: 'set-workbench-filters' }));

    await waitFor(() => {
      expect(window.location.search).toContain('workbench_reason=priority_updated');
    });
    expect(window.location.search).toContain('workbench_snapshot_view=scoped');
    expect(window.location.search).toContain('workbench_snapshot_fingerprint=wv_pricing_escalated');
    expect(window.location.search).toContain('workbench_snapshot_summary=');
    expect(window.location.search).toContain('workbench_keyword=decay');
  });

  it('replays workbench filters from browser popstate events', async () => {
    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('task').textContent).toBe('task_2');
    });

    await act(async () => {
      window.history.pushState(
        null,
        '',
        '/?view=workbench&workbench_reason=priority_new&workbench_snapshot_view=scoped&workbench_snapshot_fingerprint=wv_pricing_first&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E5%9B%BE%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E9%A6%96%E6%AC%A1%E5%85%A5%E5%88%97%20%C2%B7%20%E7%B1%BB%E5%9E%8B%EF%BC%9APricing&workbench_keyword=policy&task=task_1'
      );
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('reason').textContent).toBe('priority_new');
    });
    expect(screen.getByTestId('snapshot-view').textContent).toBe('scoped');
    expect(screen.getByTestId('snapshot-fingerprint').textContent).toBe('wv_pricing_first');
    expect(screen.getByTestId('snapshot-summary').textContent).toBe('快速视图：自动排序首次入列 · 类型：Pricing');
    expect(screen.getByTestId('keyword').textContent).toBe('policy');
    expect(screen.getByTestId('task').textContent).toBe('task_1');
  });

  it('falls back to local snapshot summary buckets when stats do not provide global queues', async () => {
    getResearchTaskStats.mockResolvedValueOnce({
      data: {
        total: 2,
        status_counts: { new: 1, in_progress: 1 },
      },
    });

    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('snapshot-option-label').textContent).toBe('快速视图：自动排序缓和 · 类型：Cross-Market');
    });
    expect(screen.getByTestId('snapshot-option-fingerprint').textContent).toBe('');
  });

  it('preserves a deep-linked task even when it is outside the initial board task page', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=workbench&task=task_999&workbench_type=pricing&workbench_source=pricing_playbook'
    );
    getResearchTasks.mockResolvedValueOnce({
      data: [
        {
          id: 'task_1',
          title: '可见页内任务',
          status: 'new',
          type: 'pricing',
          source: 'pricing_playbook',
          updated_at: '2026-04-11T09:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
      ],
    });
    getResearchTask.mockImplementation(async (taskId) => ({
      data: taskId === 'task_999'
        ? {
            id: 'task_999',
            title: '深链任务',
            status: 'new',
            type: 'pricing',
            source: 'pricing_playbook',
            updated_at: '2026-04-12T09:00:00Z',
            snapshot: { payload: {} },
            timeline: [],
          }
        : null,
    }));

    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('task').textContent).toBe('task_999');
    });
    expect(window.location.search).toContain('task=task_999');
  });

  it('advances to the next same-type task when the url requests a queue handoff', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=workbench&workbench_queue_mode=pricing&workbench_queue_action=next_same_type&task=task_1'
    );
    getResearchTasks.mockResolvedValueOnce({
      data: [
        {
          id: 'task_1',
          title: '当前 Pricing 任务',
          status: 'new',
          type: 'pricing',
          symbol: 'AAPL',
          source: 'manual',
          updated_at: '2026-04-11T09:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
        {
          id: 'task_2',
          title: '下一条 Pricing 任务',
          status: 'in_progress',
          type: 'pricing',
          symbol: 'NVDA',
          source: 'godeye',
          updated_at: '2026-04-11T10:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
        {
          id: 'task_3',
          title: '跨市场任务',
          status: 'new',
          type: 'cross_market',
          template: 'energy_grid',
          source: 'godeye',
          updated_at: '2026-04-11T08:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
      ],
    });

    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('task').textContent).toBe('task_2');
    });
    expect(screen.getByTestId('queue-mode').textContent).toBe('pricing');
    expect(screen.getByTestId('queue-action').textContent).toBe('');
    expect(window.location.search).toContain('workbench_queue_mode=pricing');
    expect(window.location.search).not.toContain('workbench_queue_action=next_same_type');
  });

  it('keeps continuous review handoff inside the same workbench source queue', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=workbench&workbench_type=pricing&workbench_source=e2e_suite&workbench_queue_mode=pricing&workbench_queue_action=next_same_type&task=task_1'
    );
    getResearchTasks.mockResolvedValueOnce({
      data: [
        {
          id: 'other_task',
          title: '别的来源任务',
          status: 'new',
          type: 'pricing',
          symbol: 'MSFT',
          source: 'manual',
          board_order: 0,
          updated_at: '2026-04-11T11:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
        {
          id: 'task_1',
          title: '当前 E2E Pricing 任务',
          status: 'new',
          type: 'pricing',
          symbol: 'AAPL',
          source: 'e2e_suite',
          board_order: 0,
          updated_at: '2026-04-11T09:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
        {
          id: 'task_2',
          title: '下一条 E2E Pricing 任务',
          status: 'new',
          type: 'pricing',
          symbol: 'NVDA',
          source: 'e2e_suite',
          board_order: 1,
          updated_at: '2026-04-11T10:00:00Z',
          snapshot: { payload: {} },
          timeline: [],
        },
      ],
    });

    render(<WorkbenchHookHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('task').textContent).toBe('task_2');
    });
    expect(window.location.search).toContain('workbench_source=e2e_suite');
    expect(window.location.search).toContain('task=task_2');
    expect(window.location.search).not.toContain('task=other_task');
    expect(window.location.search).not.toContain('workbench_queue_action=next_same_type');
  });
});
