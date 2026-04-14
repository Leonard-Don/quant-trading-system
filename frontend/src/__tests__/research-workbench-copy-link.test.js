import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import ResearchWorkbench from '../components/ResearchWorkbench';

jest.mock('../components/research-workbench/useResearchWorkbenchData', () => jest.fn());
jest.mock('../components/research-workbench/WorkbenchDetailPanel', () => (props) => (
  <div>
    <div>detail-panel</div>
    <div>{props.selectedTaskQueueMeta?.label || ''}</div>
    <div>{props.selectedMatchingQueueMeta?.label || ''}</div>
    <button type="button" onClick={props.handleSelectQueuePrevious}>
      detail-prev
    </button>
    <button type="button" onClick={props.handleSelectQueueNext}>
      detail-next
    </button>
    <button type="button" onClick={props.handleOpenNextTask}>
      detail-open-next
    </button>
    <button type="button" onClick={props.handleSelectMatchingQueuePrevious}>
      detail-mode-prev
    </button>
    <button type="button" onClick={props.handleSelectMatchingQueueNext}>
      detail-mode-next
    </button>
    <button type="button" onClick={props.handleOpenMatchingQueueNext}>
      detail-open-mode-next
    </button>
  </div>
));
jest.mock('../components/research-workbench/WorkbenchTaskCard', () => () => <div>task-card</div>);
jest.mock('../components/research-workbench/WorkbenchOverviewPanels', () => (props) => (
  <div>
    <button type="button" onClick={props.onCopyViewLink}>
      overview-copy-link
    </button>
    <button type="button" onClick={props.onOpenQueueLead}>
      overview-open-lead
    </button>
    <button type="button" onClick={props.onOpenQueuePricing}>
      overview-open-pricing
    </button>
    <button type="button" onClick={props.onOpenQueueCrossMarket}>
      overview-open-cross
    </button>
  </div>
));
jest.mock('../components/research-workbench/WorkbenchBoardSection', () => (props) => (
  <button type="button" onClick={props.onCopyViewLink}>
    board-copy-link
  </button>
));
jest.mock('../services/api', () => ({
  addResearchTaskComment: jest.fn(),
  bulkUpdateResearchTasks: jest.fn(),
  deleteResearchTask: jest.fn(),
  deleteResearchTaskComment: jest.fn(),
  reorderResearchBoard: jest.fn(),
  updateResearchTask: jest.fn(),
}));
jest.mock('../utils/macroMispricingDraft', () => ({
  buildMacroMispricingDraft: jest.fn(),
  saveMacroMispricingDraft: jest.fn(),
}));
jest.mock('../utils/researchContext', () => {
  const actual = jest.requireActual('../utils/researchContext');
  return {
    ...actual,
    buildCrossMarketLink: jest.fn(),
    navigateByResearchAction: jest.fn(),
    navigateToAppUrl: jest.fn(),
  };
});
jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

const mockMessageApi = {
  success: jest.fn(),
  info: jest.fn(),
  warning: jest.fn(),
  error: jest.fn(),
};

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
}));

const useResearchWorkbenchData = require('../components/research-workbench/useResearchWorkbenchData');
const { bulkUpdateResearchTasks } = require('../services/api');
const { navigateByResearchAction } = require('../utils/researchContext');

const buildWorkbenchHookState = (overrides = {}) => ({
  archivedTasks: [],
  boardColumns: [],
  detailLoading: false,
  dragState: null,
  filters: {
    type: 'pricing',
    source: 'godeye',
    refresh: 'high',
    reason: 'priority_relaxed',
    keyword: 'hedge',
  },
  filteredTasks: [
    { id: 'task_2', status: 'new' },
    { id: 'task_3', status: 'blocked' },
  ],
  latestSnapshotComparison: null,
  loadTaskDetail: jest.fn(),
  loadWorkbench: jest.fn(),
  loading: false,
  openTaskPriorityLabel: '',
  openTaskPriorityNote: '',
  refreshCurrentTask: jest.fn(),
  refreshSignals: { byTaskId: {} },
  refreshStats: { high: 1, medium: 0, low: 0, priorityNew: 0, priorityEscalated: 0, priorityRelaxed: 1, priorityUpdated: 0 },
  selectedTask: null,
  selectedTaskId: 'task_2',
  selectedTaskRefreshSignal: null,
  selectedTaskPriorityEventPayload: null,
  selectedTaskPriorityMeta: null,
  setDragState: jest.fn(),
  setFilters: jest.fn(),
  setSelectedTaskId: jest.fn(),
  setShowAllTimeline: jest.fn(),
  setShowArchived: jest.fn(),
  showAllTimeline: false,
  showArchived: false,
  sourceOptions: [{ label: 'GodEye', value: 'godeye' }],
  stats: { total: 1, status_counts: { new: 1 } },
  tasks: [],
  setTasks: jest.fn(),
  timeline: [],
  timelineItems: [],
  ...overrides,
});

describe('ResearchWorkbench copy current view link', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState());
    window.history.replaceState(null, '', '/?view=workbench');
  });

  it('copies the current workbench view link with active filters', async () => {
    const clipboardWriteText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteText },
    });

    render(<ResearchWorkbench />);

    expect(screen.getByText('当前共享视图')).toBeTruthy();
    expect(screen.getByText('快速视图：自动排序缓和 · 关键词：hedge · 更新级别：建议更新 · 类型：Pricing · 来源：GodEye')).toBeTruthy();
    expect(screen.getByText('当前定位：task_2')).toBeTruthy();
    expect(screen.getByText('打开这个链接后，工作台会恢复到同一组筛选条件和当前任务焦点。')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'overview-copy-link' }));

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalledTimes(1);
    });

    const copiedUrl = clipboardWriteText.mock.calls[0][0];
    expect(copiedUrl).toContain('view=workbench');
    expect(copiedUrl).toContain('workbench_refresh=high');
    expect(copiedUrl).toContain('workbench_type=pricing');
    expect(copiedUrl).toContain('workbench_source=godeye');
    expect(copiedUrl).toContain('workbench_reason=priority_relaxed');
    expect(copiedUrl).toContain('workbench_keyword=hedge');
    expect(copiedUrl).toContain('task=task_2');
    expect(mockMessageApi.success).toHaveBeenCalledWith('当前工作台视图链接已复制');
  });

  it('warns when the environment does not support clipboard copying', async () => {
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: 'board-copy-link' }));

    await waitFor(() => {
      expect(mockMessageApi.warning).toHaveBeenCalledWith('当前环境不支持复制工作台链接');
    });
  });

  it('shows default shared-view copy when no filter is active', () => {
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      filters: {
        type: '',
        source: '',
        refresh: '',
        reason: '',
        keyword: '',
      },
      filteredTasks: [],
      selectedTaskId: '',
    }));

    render(<ResearchWorkbench />);

    expect(screen.getByText('全部任务视图')).toBeTruthy();
    expect(screen.getByText('当前没有额外筛选，分享后会打开完整工作台视图。')).toBeTruthy();
  });

  it('bulk queues filtered tasks into in-progress status', async () => {
    bulkUpdateResearchTasks.mockResolvedValue({ total: 2, data: [] });
    const refreshCurrentTask = jest.fn().mockResolvedValue(undefined);
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({ refreshCurrentTask }));

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: '批量推进到进行中 (2)' }));

    await waitFor(() => {
      expect(bulkUpdateResearchTasks).toHaveBeenCalledWith({
        task_ids: ['task_2', 'task_3'],
        status: 'in_progress',
      });
    });
    expect(mockMessageApi.success).toHaveBeenCalledWith('已将 2 个任务推进到进行中');
    expect(refreshCurrentTask).toHaveBeenCalled();
  });

  it('bulk writes review comments for the current filtered view', async () => {
    bulkUpdateResearchTasks.mockResolvedValue({ total: 2, data: [] });
    const refreshCurrentTask = jest.fn().mockResolvedValue(undefined);
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({ refreshCurrentTask }));

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: '批量写入复盘评论 (2)' }));

    await waitFor(() => {
      expect(bulkUpdateResearchTasks).toHaveBeenCalledWith({
        task_ids: ['task_2', 'task_3'],
        comment: '批量复盘：快速视图：自动排序缓和 · 关键词：hedge · 更新级别：建议更新 · 类型：Pricing · 来源：GodEye · 当前定位：task_2',
        author: 'local',
      });
    });
    expect(mockMessageApi.success).toHaveBeenCalledWith('已为 2 个任务写入复盘评论');
    expect(refreshCurrentTask).toHaveBeenCalled();
  });

  it('moves within the current filtered queue from detail navigation', () => {
    const setSelectedTaskId = jest.fn();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      selectedTask: {
        id: 'task_2',
        type: 'pricing',
        title: 'Current Task',
        symbol: 'AAPL',
        status: 'new',
      },
      selectedTaskId: 'task_2',
      filteredTasks: [
        { id: 'task_1', title: 'Previous Task', type: 'pricing', symbol: 'MSFT', status: 'new' },
        { id: 'task_2', title: 'Current Task', type: 'pricing', symbol: 'AAPL', status: 'new' },
        { id: 'task_3', title: 'Next Task', type: 'cross_market', template: 'growth_template', status: 'new' },
      ],
      setSelectedTaskId,
    }));

    render(<ResearchWorkbench />);

    expect(screen.getByText('第 2 / 3 条')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'detail-prev' }));
    fireEvent.click(screen.getByRole('button', { name: 'detail-next' }));

    expect(setSelectedTaskId).toHaveBeenNthCalledWith(1, 'task_1');
    expect(setSelectedTaskId).toHaveBeenNthCalledWith(2, 'task_3');
  });

  it('opens the next queue task with preserved workbench filters in the url context', () => {
    const setSelectedTaskId = jest.fn();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      selectedTask: {
        id: 'task_2',
        type: 'pricing',
        title: 'Current Task',
        symbol: 'AAPL',
        status: 'new',
      },
      selectedTaskId: 'task_2',
      filteredTasks: [
        { id: 'task_2', title: 'Current Task', type: 'pricing', symbol: 'AAPL', status: 'new' },
        { id: 'task_3', title: 'Next Task', type: 'cross_market', template: 'growth_template', status: 'new' },
      ],
      setSelectedTaskId,
    }));

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: 'detail-open-next' }));

    expect(setSelectedTaskId).toHaveBeenCalledWith('task_3');
    expect(navigateByResearchAction).toHaveBeenCalledWith(
      expect.objectContaining({
        target: 'cross-market',
        template: 'growth_template',
        source: 'research_workbench',
      }),
      expect.stringContaining('task=task_3')
    );
    expect(navigateByResearchAction).toHaveBeenCalledWith(
      expect.any(Object),
      expect.stringContaining('workbench_reason=priority_relaxed')
    );
  });

  it('opens the next task in the same execution mode queue', () => {
    const setSelectedTaskId = jest.fn();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      selectedTask: {
        id: 'task_2',
        type: 'pricing',
        title: 'Current Pricing Task',
        symbol: 'AAPL',
        status: 'new',
      },
      selectedTaskId: 'task_2',
      filteredTasks: [
        { id: 'task_1', title: 'Cross Queue Lead', type: 'cross_market', template: 'macro_theme', status: 'new' },
        { id: 'task_2', title: 'Current Pricing Task', type: 'pricing', symbol: 'AAPL', status: 'new' },
        { id: 'task_4', title: 'Next Pricing Task', type: 'pricing', symbol: 'NVDA', status: 'new' },
      ],
      setSelectedTaskId,
    }));

    render(<ResearchWorkbench />);

    expect(screen.getByText('第 1 / 2 条')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'detail-open-mode-next' }));

    expect(setSelectedTaskId).toHaveBeenCalledWith('task_4');
    expect(navigateByResearchAction).toHaveBeenCalledWith(
      expect.objectContaining({
        target: 'pricing',
        symbol: 'NVDA',
        source: 'research_workbench',
      }),
      expect.stringContaining('task=task_4')
    );
  });

  it('opens the first pricing task from the current filtered queue via overview actions', () => {
    const setSelectedTaskId = jest.fn();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      selectedTask: {
        id: 'task_9',
        type: 'cross_market',
        title: 'Current Task',
        template: 'macro_theme',
        status: 'new',
      },
      selectedTaskId: 'task_9',
      filteredTasks: [
        { id: 'task_4', title: 'Cross Task', type: 'cross_market', template: 'macro_theme', status: 'new' },
        { id: 'task_5', title: 'Pricing Task', type: 'pricing', symbol: 'NVDA', status: 'new' },
      ],
      setSelectedTaskId,
    }));

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: 'overview-open-pricing' }));

    expect(setSelectedTaskId).toHaveBeenCalledWith('task_5');
    expect(navigateByResearchAction).toHaveBeenCalledWith(
      expect.objectContaining({
        target: 'pricing',
        symbol: 'NVDA',
        source: 'research_workbench',
      }),
      expect.stringContaining('task=task_5')
    );
  });

  it('opens the queue lead task from overview actions', () => {
    const setSelectedTaskId = jest.fn();
    useResearchWorkbenchData.mockReturnValue(buildWorkbenchHookState({
      selectedTask: {
        id: 'task_9',
        type: 'pricing',
        title: 'Current Task',
        symbol: 'AAPL',
        status: 'new',
      },
      selectedTaskId: 'task_9',
      filteredTasks: [
        { id: 'task_6', title: 'Lead Task', type: 'cross_market', template: 'defensive_beta_hedge', status: 'new' },
        { id: 'task_7', title: 'Next Task', type: 'pricing', symbol: 'MSFT', status: 'new' },
      ],
      setSelectedTaskId,
    }));

    render(<ResearchWorkbench />);

    fireEvent.click(screen.getByRole('button', { name: 'overview-open-lead' }));

    expect(setSelectedTaskId).toHaveBeenCalledWith('task_6');
    expect(navigateByResearchAction).toHaveBeenCalledWith(
      expect.objectContaining({
        target: 'cross-market',
        template: 'defensive_beta_hedge',
        source: 'research_workbench',
      }),
      expect.stringContaining('task=task_6')
    );
  });
});
