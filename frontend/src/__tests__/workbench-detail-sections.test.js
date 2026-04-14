import { fireEvent, render, screen } from '@testing-library/react';

import {
  WorkbenchTaskActivitySection,
  WorkbenchTaskSummarySection,
} from '../components/research-workbench/WorkbenchDetailSections';

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

jest.mock('../components/research-workbench/SelectedTaskRefreshPanel', () => () => <div>refresh-panel</div>);
jest.mock('../components/research-workbench/SnapshotSummary', () => ({
  SnapshotHistoryList: () => <div>snapshot-history</div>,
  SnapshotSummary: () => <div>snapshot-summary</div>,
}));

describe('WorkbenchTaskSummarySection', () => {
  it('shows the current shared-view context and copy action in the detail sidebar', () => {
    const handleCopyViewLink = jest.fn();

    render(
      <WorkbenchTaskSummarySection
        handleCopyViewLink={handleCopyViewLink}
        latestSnapshotComparison={null}
        selectedTask={{
          type: 'pricing',
          sourceLabel: 'GodEye',
          symbol: 'AAPL',
          template: '',
          context: {
            source: 'godeye',
            note: 'focus on risk budget',
          },
        }}
        selectedTaskRefreshSignal={null}
        workbenchViewSummary={{
          hasActiveFilters: true,
          headline: '快速视图：自动排序升档 · 关键词：defense',
          note: '打开这个链接后，工作台会恢复到同一组筛选条件和当前任务焦点。',
          scopedTaskLabel: '当前定位：AAPL defensive hedge',
        }}
      />
    );

    expect(screen.getByText('当前共享视图上下文')).toBeTruthy();
    expect(screen.getByText('已带筛选视角')).toBeTruthy();
    expect(screen.getByText('快速视图：自动排序升档 · 关键词：defense')).toBeTruthy();
    expect(screen.getByText('当前定位：AAPL defensive hedge')).toBeTruthy();
    expect(screen.getByText('打开这个链接后，工作台会恢复到同一组筛选条件和当前任务焦点。')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '复制当前视图链接' }));
    expect(handleCopyViewLink).toHaveBeenCalledTimes(1);
  });

  it('renders snapshot view context inside timeline activity items', () => {
    render(
      <WorkbenchTaskActivitySection
        commentDraft=""
        handleAddComment={() => {}}
        handleDeleteComment={() => {}}
        handleRestoreArchived={() => {}}
        handleStatusUpdate={() => {}}
        saving={false}
        selectedTask={{ comments: [], status: 'new' }}
        selectedTaskPriorityMeta={null}
        setCommentDraft={() => {}}
        setShowAllTimeline={() => {}}
        showAllTimeline={false}
        timeline={[
          {
            id: 'event_snapshot',
            type: 'snapshot_saved',
          },
        ]}
        timelineItems={[
          {
            color: 'green',
            dot: 'clock',
            children: {
              label: '研究快照已更新',
              type: '快照',
              color: 'green',
              createdAt: '2026-04-12T10:00:00Z',
              detail: 'MSFT snapshot · 视图 快速视图：自动排序升档 · 类型：Pricing',
              snapshotViewSummary: '快速视图：自动排序升档 · 类型：Pricing',
              snapshotViewFocus: '当前定位：rw_msft',
              snapshotViewNote: '这次快照是在带筛选的工作台视图下保存的。',
            },
          },
        ]}
      />
    );

    expect(screen.getByText('研究视角')).toBeTruthy();
    expect(screen.getByText('工作台视角 快速视图：自动排序升档 · 类型：Pricing')).toBeTruthy();
    expect(screen.getByText('当前定位：rw_msft')).toBeTruthy();
    expect(screen.getByText('这次快照是在带筛选的工作台视图下保存的。')).toBeTruthy();
  });
});
