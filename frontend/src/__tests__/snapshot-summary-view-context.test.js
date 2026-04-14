import { render, screen } from '@testing-library/react';

import { SnapshotSummary } from '../components/research-workbench/SnapshotSummary';

describe('SnapshotSummary view context', () => {
  it('renders persisted workbench view context for pricing snapshots', () => {
    render(
      <SnapshotSummary
        task={{
          type: 'pricing',
          snapshot: {
            headline: 'AAPL 定价研究任务',
            summary: '当前结果已更新。',
            highlights: [],
            payload: {
              gap_analysis: { current_price: 200, fair_value_mid: 180, gap_pct: 12.4 },
              implications: {
                primary_view: '高估',
                factor_alignment: { summary: '证据方向一致' },
              },
              view_context: {
                summary: '快速视图：自动排序升档 · 关键词：defense',
                scoped_task_label: '当前定位：rw_focus_1',
                note: '这次快照是在带筛选的工作台视图下保存的。',
              },
            },
          },
        }}
      />
    );

    expect(screen.getByText('工作台视图 快速视图：自动排序升档 · 关键词：defense')).toBeTruthy();
    expect(screen.getByText('当前定位：rw_focus_1')).toBeTruthy();
    expect(screen.getByText('这次快照是在带筛选的工作台视图下保存的。')).toBeTruthy();
  });
});
