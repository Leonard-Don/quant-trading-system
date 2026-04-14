import { fireEvent, render, screen } from '@testing-library/react';

import WorkbenchDetailPanel from '../components/research-workbench/WorkbenchDetailPanel';

jest.mock('../components/research-workbench/SnapshotComparePanel', () => () => <div>snapshot-compare-panel</div>);
jest.mock('../components/research-workbench/WorkbenchDetailSections', () => ({
  WorkbenchTaskActivitySection: () => <div>activity-section</div>,
  WorkbenchTaskEditorSection: () => <div>editor-section</div>,
  WorkbenchTaskSummarySection: () => <div>summary-section</div>,
}));

describe('WorkbenchDetailPanel queue navigation', () => {
  it('shows queue position and wires queue navigation actions', () => {
    const handleSelectQueuePrevious = jest.fn();
    const handleSelectQueueNext = jest.fn();
    const handleOpenNextTask = jest.fn();
    const handleSelectMatchingQueuePrevious = jest.fn();
    const handleSelectMatchingQueueNext = jest.fn();
    const handleOpenMatchingQueueNext = jest.fn();

    render(
      <WorkbenchDetailPanel
        commentDraft=""
        detailLoading={false}
        handleAddComment={() => {}}
        handleCopyViewLink={() => {}}
        handleDelete={() => {}}
        handleDeleteComment={() => {}}
        handleMetaSave={() => {}}
        handleOpenMatchingQueueNext={handleOpenMatchingQueueNext}
        handleOpenNextTask={handleOpenNextTask}
        handleOpenTask={() => {}}
        handleRestoreArchived={() => {}}
        handleSelectMatchingQueueNext={handleSelectMatchingQueueNext}
        handleSelectMatchingQueuePrevious={handleSelectMatchingQueuePrevious}
        handleSelectQueueNext={handleSelectQueueNext}
        handleSelectQueuePrevious={handleSelectQueuePrevious}
        handleStatusUpdate={() => {}}
        latestSnapshotComparison={null}
        noteDraft=""
        openTaskPriorityLabel="打开研究页"
        saving={false}
        selectedMatchingQueueMeta={{
          mode: 'pricing',
          title: 'Pricing 执行队列',
          total: 2,
          index: 0,
          label: '第 1 / 2 条',
          currentTask: { id: 'task_2', title: '当前 Pricing 任务' },
          previousTask: null,
          nextTask: { id: 'task_4', title: '下一条 Pricing 任务' },
          hasPrevious: false,
          hasNext: true,
        }}
        selectedTask={{ id: 'task_2', status: 'new', title: '队列中的第二条任务' }}
        selectedTaskPriorityMeta={null}
        selectedTaskQueueMeta={{
          total: 3,
          index: 1,
          position: 2,
          label: '第 2 / 3 条',
          currentTask: { id: 'task_2', title: '队列中的第二条任务' },
          previousTask: { id: 'task_1', title: '上一条任务' },
          nextTask: { id: 'task_3', title: '下一条任务' },
          hasPrevious: true,
          hasNext: true,
        }}
        selectedTaskRefreshSignal={null}
        setCommentDraft={() => {}}
        setNoteDraft={() => {}}
        setShowAllTimeline={() => {}}
        setTitleDraft={() => {}}
        showAllTimeline={false}
        timeline={[]}
        timelineItems={[]}
        titleDraft=""
        workbenchViewSummary={null}
      />
    );

    expect(screen.getByText('当前复盘队列')).toBeTruthy();
    expect(screen.getByText('Pricing 执行队列')).toBeTruthy();
    expect(screen.getByText('第 2 / 3 条')).toBeTruthy();
    expect(screen.getByText('第 1 / 2 条')).toBeTruthy();
    expect(screen.getByText('队列中的第二条任务')).toBeTruthy();
    expect(screen.getByText('下一条：下一条任务')).toBeTruthy();
    expect(screen.getByText('下一条同类型：下一条 Pricing 任务')).toBeTruthy();

    fireEvent.click(screen.getAllByRole('button', { name: /上一条/ })[0]);
    fireEvent.click(screen.getAllByRole('button', { name: /下一条/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: '打开下一条研究页' }));
    fireEvent.click(screen.getAllByRole('button', { name: /下一条同类型/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: '打开下一条同类型研究页' }));

    expect(handleSelectQueuePrevious).toHaveBeenCalledTimes(1);
    expect(handleSelectQueueNext).toHaveBeenCalledTimes(1);
    expect(handleOpenNextTask).toHaveBeenCalledTimes(1);
    expect(handleSelectMatchingQueueNext).toHaveBeenCalledTimes(1);
    expect(handleOpenMatchingQueueNext).toHaveBeenCalledTimes(1);
    expect(handleSelectMatchingQueuePrevious).toHaveBeenCalledTimes(0);
  });
});
