import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import WorkbenchBoardSection from '../components/research-workbench/WorkbenchBoardSection';

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

describe('WorkbenchBoardSection', () => {
  const baseProps = {
    archivedTasks: [],
    dragState: null,
    filters: { type: '', source: '', refresh: '', reason: '', snapshotView: '', snapshotSummary: '', keyword: '' },
    handleDrop: jest.fn(),
    onCopyViewLink: jest.fn(),
    handleRestoreArchived: jest.fn(),
    loading: false,
    renderBoardCard: (task) => <div key={task.id}>{task.title}</div>,
    refreshStats: {
      priorityNew: 2,
      priorityEscalated: 1,
      priorityRelaxed: 1,
      priorityUpdated: 3,
    },
    saving: false,
    setDragState: jest.fn(),
    setFilters: jest.fn(),
    setSelectedTaskId: jest.fn(),
    setShowArchived: jest.fn(),
    showArchived: false,
    sourceOptions: [
      { label: '全部来源', value: '' },
      { label: 'GodEye', value: 'godeye' },
    ],
    TYPE_OPTIONS: [
      { label: '全部类型', value: '' },
      { label: 'Pricing', value: 'pricing' },
    ],
    REFRESH_OPTIONS: [
      { label: '全部更新状态', value: '' },
      { label: '建议更新', value: 'high' },
    ],
    SNAPSHOT_VIEW_OPTIONS: [
      { label: '全部快照视角', value: '' },
      { label: '带筛选视角快照', value: 'filtered' },
      { label: '带任务焦点快照', value: 'scoped' },
    ],
    snapshotSummaryOptions: [
      {
        label: '快速视图：自动排序升档 · 类型：Pricing',
        value: '快速视图：自动排序升档 · 类型：Pricing',
        count: 2,
        scopedCount: 1,
      },
    ],
    REASON_OPTIONS: [
      { label: '全部更新原因', value: '' },
      { label: '自动排序首次入列', value: 'priority_new' },
      { label: '自动排序升档', value: 'priority_escalated' },
      { label: '自动排序缓和', value: 'priority_relaxed' },
      { label: '自动排序同类更新', value: 'priority_updated' },
    ],
  };

  const boardColumns = [
    {
      status: 'new',
      title: '新建',
      tasks: [
        {
          id: 'task_new',
          title: 'Fresh signal',
          timeline: [{ type: 'refresh_priority', meta: { change_type: 'new' } }],
        },
        {
          id: 'task_escalated',
          title: 'Escalated signal',
          timeline: [{ type: 'refresh_priority', meta: { change_type: 'escalated' } }],
        },
      ],
    },
    {
      status: 'in_progress',
      title: '进行中',
      tasks: [
        {
          id: 'task_updated',
          title: 'Updated signal',
          timeline: [{ type: 'refresh_priority', meta: { change_type: 'updated' } }],
        },
        {
          id: 'task_relaxed',
          title: 'Relaxed signal',
          timeline: [{ type: 'refresh_priority', meta: { change_type: 'relaxed' } }],
        },
      ],
    },
    {
      status: 'blocked',
      title: '阻塞',
      tasks: [],
    },
  ];

  it('toggles quick filter chips from the board toolbar', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        boardColumns={boardColumns}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '首次 2' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ type: '', source: '', refresh: '', reason: '', snapshotView: '', snapshotSummary: '', keyword: '' }).reason).toBe('priority_new');
  });

  it('copies the current workbench view link from the board toolbar', () => {
    const onCopyViewLink = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        onCopyViewLink={onCopyViewLink}
        boardColumns={boardColumns}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '复制当前视图链接' }));

    expect(onCopyViewLink).toHaveBeenCalledTimes(1);
  });

  it('shows active quick filter summary and clears it', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        filters={{ type: '', source: '', refresh: '', reason: 'priority_updated', snapshotView: 'filtered', snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing', keyword: 'decay' }}
        boardColumns={boardColumns}
      />
    );

    expect(screen.getByText('快速视图：自动排序同类更新')).toBeTruthy();
    expect(screen.getByText('快照视角：带筛选视角快照')).toBeTruthy();
    expect(screen.getByText('研究视角：快速视图：自动排序升档 · 类型：Pricing')).toBeTruthy();
    expect(screen.getByText('关键词：decay')).toBeTruthy();

    fireEvent.click(screen.getByTestId('board-filter-close-reason'));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ type: '', source: '', refresh: '', reason: 'priority_updated', snapshotView: 'filtered', snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing', keyword: 'decay' }).reason).toBe('');
  });

  it('clears all filters from the board toolbar', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        filters={{ type: 'pricing', source: 'godeye', refresh: 'high', reason: 'priority_updated', snapshotView: 'scoped', snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing', keyword: 'decay' }}
        boardColumns={boardColumns}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '清空全部筛选' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    const nextFilters = updater({ type: 'pricing', source: 'godeye', refresh: 'high', reason: 'priority_updated', snapshotView: 'scoped', snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing', keyword: 'decay' });
    expect(nextFilters.type).toBe('');
    expect(nextFilters.source).toBe('');
    expect(nextFilters.refresh).toBe('');
    expect(nextFilters.reason).toBe('');
    expect(nextFilters.snapshotView).toBe('');
    expect(nextFilters.snapshotSummary).toBe('');
    expect(nextFilters.keyword).toBe('');
  });

  it('renders readable filter tags and clears a single keyword filter', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        filters={{ type: 'pricing', source: 'godeye', refresh: 'high', reason: 'priority_updated', snapshotView: 'scoped', snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing', keyword: 'decay' }}
        boardColumns={boardColumns}
      />
    );

    expect(screen.getByText('类型：Pricing')).toBeTruthy();
    expect(screen.getByText('来源：GodEye')).toBeTruthy();
    expect(screen.getByText('更新级别：建议更新')).toBeTruthy();
    expect(screen.getByText('快照视角：带任务焦点快照')).toBeTruthy();
    expect(screen.getByText('研究视角：快速视图：自动排序升档 · 类型：Pricing')).toBeTruthy();

    fireEvent.click(screen.getByTestId('board-filter-close-keyword'));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    const nextFilters = updater({
      type: 'pricing',
      source: 'godeye',
      refresh: 'high',
      reason: 'priority_updated',
      snapshotView: 'scoped',
      snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
      keyword: 'decay',
    });
    expect(nextFilters.keyword).toBe('');
    expect(nextFilters.type).toBe('pricing');
    expect(nextFilters.reason).toBe('priority_updated');
  });

  it('updates snapshot-view filter from the board toolbar select', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        boardColumns={boardColumns}
      />
    );

    fireEvent.mouseDown(screen.getByText('全部快照视角'));
    fireEvent.click(screen.getByText('带任务焦点快照'));

    expect(setFilters).toHaveBeenCalled();
    const updater = setFilters.mock.calls.at(-1)[0];
    expect(updater({ type: '', source: '', refresh: '', reason: '', snapshotView: '', snapshotSummary: '', keyword: '' }).snapshotView).toBe('scoped');
  });

  it('renders current snapshot-summary filter in the board toolbar tags', () => {
    render(
      <WorkbenchBoardSection
        {...baseProps}
        filters={{
          type: '',
          source: '',
          refresh: '',
          reason: '',
          snapshotView: '',
          snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
          keyword: '',
        }}
        boardColumns={boardColumns}
      />
    );

    expect(screen.getByText('研究视角：快速视图：自动排序升档 · 类型：Pricing')).toBeTruthy();
  });

  it('shows per-column auto-priority tags in column headers', () => {
    render(
      <WorkbenchBoardSection
        {...baseProps}
        boardColumns={boardColumns}
      />
    );

    expect(screen.getByTestId('workbench-column-priority-new-escalated').textContent).toContain('升档 1');
    expect(screen.getByTestId('workbench-column-priority-new-new').textContent).toContain('首次 1');
    expect(screen.getByTestId('workbench-column-priority-in_progress-relaxed').textContent).toContain('缓和 1');
    expect(screen.getByTestId('workbench-column-priority-in_progress-updated').textContent).toContain('更新 1');
  });

  it('toggles quick filter when clicking a column priority tag', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchBoardSection
        {...baseProps}
        setFilters={setFilters}
        boardColumns={boardColumns}
      />
    );

    fireEvent.click(screen.getByTestId('workbench-column-priority-new-escalated'));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ type: '', source: '', refresh: '', reason: '', snapshotView: '', snapshotSummary: '', keyword: '' }).reason).toBe('priority_escalated');
  });

  it('shows quick-filter-aware empty state descriptions', () => {
    render(
      <WorkbenchBoardSection
        {...baseProps}
        filters={{ type: '', source: '', refresh: '', reason: 'priority_new', snapshotView: '', keyword: '' }}
        boardColumns={boardColumns}
      />
    );

    expect(screen.getByText('阻塞暂无自动排序首次入列任务')).toBeTruthy();
  });
});
