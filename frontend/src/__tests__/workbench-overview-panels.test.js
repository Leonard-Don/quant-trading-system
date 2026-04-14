import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import WorkbenchOverviewPanels from '../components/research-workbench/WorkbenchOverviewPanels';

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

describe('WorkbenchOverviewPanels', () => {
  const TYPE_OPTIONS = [
    { label: '全部类型', value: '' },
    { label: 'Pricing', value: 'pricing' },
  ];
  const REFRESH_OPTIONS = [
    { label: '全部更新状态', value: '' },
    { label: '建议更新', value: 'high' },
  ];
  const SNAPSHOT_VIEW_OPTIONS = [
    { label: '全部快照视角', value: '' },
    { label: '带筛选视角快照', value: 'filtered' },
    { label: '带任务焦点快照', value: 'scoped' },
  ];
  const REASON_OPTIONS = [
    { label: '全部更新原因', value: '' },
    { label: '自动排序缓和', value: 'priority_relaxed' },
    { label: '自动排序升档', value: 'priority_escalated' },
    { label: '自动排序首次入列', value: 'priority_new' },
  ];
  const sourceOptions = [
    { label: '全部来源', value: '' },
    { label: 'GodEye', value: 'godeye' },
  ];
  const snapshotSummaryOptions = [
    {
      label: '快速视图：自动排序升档 · 类型：Pricing',
      value: '快速视图：自动排序升档 · 类型：Pricing',
      fingerprint: 'wv_pricing_escalated',
      count: 2,
      scopedCount: 1,
    },
    {
      label: '快速视图：自动排序缓和 · 类型：Cross-Market',
      value: '快速视图：自动排序缓和 · 类型：Cross-Market',
      fingerprint: 'wv_cross_relaxed',
      count: 1,
      scopedCount: 0,
    },
  ];

  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: jest.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });
  });

  it('toggles escalated quick filter from overview cards', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: '' }}
        onCopyViewLink={jest.fn()}
        refreshStats={{
          high: 2,
          medium: 1,
          low: 4,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 1,
          priorityNew: 1,
          priorityEscalated: 3,
          priorityRelaxed: 1,
          priorityUpdated: 2,
          snapshotViewFiltered: 4,
          snapshotViewScoped: 2,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 10, status_counts: { in_progress: 3, blocked: 1, complete: 2 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: '只看升档' })[0]);

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ reason: '', type: '', source: '', refresh: '', snapshotView: '', keyword: '' }).reason).toBe('priority_escalated');
  });

  it('shows active quick-filter banner and clears it', () => {
    const setFilters = jest.fn();
    const onCopyViewLink = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: 'priority_relaxed', snapshotView: 'filtered', snapshotFingerprint: 'wv_cross_relaxed', snapshotSummary: '快速视图：自动排序缓和 · 类型：Cross-Market', keyword: 'hedge' }}
        onCopyViewLink={onCopyViewLink}
        refreshStats={{
          high: 0,
          medium: 0,
          low: 1,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 0,
          priorityEscalated: 0,
          priorityRelaxed: 2,
          priorityUpdated: 1,
          snapshotViewFiltered: 2,
          snapshotViewScoped: 1,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 2, status_counts: { in_progress: 1, blocked: 0, complete: 0 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    expect(screen.getByText('当前工作台筛选已生效')).toBeTruthy();
    expect(screen.getAllByText(/快速视图：自动排序缓和/).length).toBeGreaterThan(0);
    expect(screen.getByText(/快照视角：带筛选视角快照/)).toBeTruthy();
    expect(screen.getByText(/研究视角：快速视图：自动排序缓和/)).toBeTruthy();
    expect(screen.getByText(/关键词：hedge/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '复制当前视图链接' }));
    expect(onCopyViewLink).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '清空全部筛选' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    const nextFilters = updater({ reason: 'priority_relaxed', type: 'pricing', source: 'godeye', refresh: 'high', snapshotView: 'filtered', snapshotFingerprint: 'wv_cross_relaxed', snapshotSummary: '快速视图：自动排序缓和 · 类型：Cross-Market', keyword: 'hedge' });
    expect(nextFilters.reason).toBe('');
    expect(nextFilters.type).toBe('');
    expect(nextFilters.source).toBe('');
    expect(nextFilters.refresh).toBe('');
    expect(nextFilters.snapshotView).toBe('');
    expect(nextFilters.snapshotFingerprint).toBe('');
    expect(nextFilters.snapshotSummary).toBe('');
    expect(nextFilters.keyword).toBe('');
  });

  it('toggles first-time auto-priority quick filter from overview cards', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: '', type: '', source: '', refresh: '', snapshotView: '', keyword: '' }}
        onCopyViewLink={jest.fn()}
        refreshStats={{
          high: 1,
          medium: 0,
          low: 2,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 2,
          priorityEscalated: 1,
          priorityRelaxed: 0,
          priorityUpdated: 1,
          snapshotViewFiltered: 1,
          snapshotViewScoped: 1,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 4, status_counts: { in_progress: 2, blocked: 0, complete: 1 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '只看首次' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ reason: '', type: '', source: '', refresh: '', snapshotView: '', keyword: '' }).reason).toBe('priority_new');
  });

  it('toggles snapshot-view quick filters from overview cards', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: '', type: '', source: '', refresh: '', snapshotView: '', keyword: '' }}
        onCopyViewLink={jest.fn()}
        refreshStats={{
          high: 0,
          medium: 0,
          low: 1,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 0,
          priorityEscalated: 0,
          priorityRelaxed: 0,
          priorityUpdated: 0,
          snapshotViewFiltered: 3,
          snapshotViewScoped: 2,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{
          total: 3,
          status_counts: { in_progress: 1, blocked: 0, complete: 0 },
          snapshot_view_queues: snapshotSummaryOptions,
        }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '只看带视角' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({ reason: '', type: '', source: '', refresh: '', snapshotView: '', keyword: '' }).snapshotView).toBe('filtered');
  });

  it('toggles snapshot-summary review queue from overview cards', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: '', type: '', source: '', refresh: '', snapshotView: '', snapshotFingerprint: '', snapshotSummary: '', keyword: '' }}
        onCopyViewLink={jest.fn()}
        refreshStats={{
          high: 0,
          medium: 0,
          low: 1,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 0,
          priorityEscalated: 0,
          priorityRelaxed: 0,
          priorityUpdated: 0,
          snapshotViewFiltered: 3,
          snapshotViewScoped: 1,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 3, status_counts: { in_progress: 1, blocked: 0, complete: 0 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '查看“快速视图：自动排序升档 · 类型：Pricing”' }));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(updater({
      reason: '',
      type: '',
      source: '',
      refresh: '',
      snapshotView: '',
      snapshotFingerprint: '',
      snapshotSummary: '',
      keyword: '',
    }).snapshotSummary).toBe('快速视图：自动排序升档 · 类型：Pricing');
    expect(updater({
      reason: '',
      type: '',
      source: '',
      refresh: '',
      snapshotView: '',
      snapshotFingerprint: '',
      snapshotSummary: '',
      keyword: '',
    }).snapshotFingerprint).toBe('wv_pricing_escalated');
  });

  it('renders readable active filter tags and clears a single filter tag', () => {
    const setFilters = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{
          reason: 'priority_relaxed',
          type: 'pricing',
          source: 'godeye',
          refresh: 'high',
          snapshotView: 'scoped',
          snapshotFingerprint: 'wv_pricing_escalated',
          snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
          keyword: 'hedge',
        }}
        onCopyViewLink={jest.fn()}
        refreshStats={{
          high: 0,
          medium: 0,
          low: 1,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 0,
          priorityEscalated: 0,
          priorityRelaxed: 2,
          priorityUpdated: 1,
          snapshotViewFiltered: 1,
          snapshotViewScoped: 1,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={setFilters}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 2, status_counts: { in_progress: 1, blocked: 0, complete: 0 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    expect(screen.getByText('快速视图：自动排序缓和')).toBeTruthy();
    expect(screen.getByText('关键词：hedge')).toBeTruthy();
    expect(screen.getByText('更新级别：建议更新')).toBeTruthy();
    expect(screen.getByText('快照视角：带任务焦点快照')).toBeTruthy();
    expect(screen.getByText('研究视角：快速视图：自动排序升档 · 类型：Pricing')).toBeTruthy();
    expect(screen.getByText('类型：Pricing')).toBeTruthy();
    expect(screen.getByText('来源：GodEye')).toBeTruthy();

    fireEvent.click(screen.getByTestId('overview-filter-close-keyword'));

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    const nextFilters = updater({
      reason: 'priority_relaxed',
      type: 'pricing',
      source: 'godeye',
      refresh: 'high',
      snapshotView: 'scoped',
      snapshotFingerprint: 'wv_pricing_escalated',
      snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
      keyword: 'hedge',
    });
    expect(nextFilters.reason).toBe('priority_relaxed');
    expect(nextFilters.keyword).toBe('');
    expect(nextFilters.type).toBe('pricing');
  });

  it('opens queue launch actions from the overview execution card', () => {
    const onOpenQueueLead = jest.fn();
    const onOpenQueuePricing = jest.fn();
    const onOpenQueueCrossMarket = jest.fn();

    render(
      <WorkbenchOverviewPanels
        filters={{ reason: '', type: '', source: '', refresh: '', snapshotView: '', snapshotFingerprint: '', snapshotSummary: '', keyword: '' }}
        onCopyViewLink={jest.fn()}
        onOpenQueueLead={onOpenQueueLead}
        onOpenQueuePricing={onOpenQueuePricing}
        onOpenQueueCrossMarket={onOpenQueueCrossMarket}
        queueLaunchSummary={{
          total: 4,
          launchableCount: 3,
          leadTask: { id: 'task_1', title: 'Lead Research Task' },
          pricingTask: { id: 'task_2', title: 'Pricing Task' },
          crossMarketTask: { id: 'task_3', title: 'Cross Task' },
          pricingCount: 1,
          crossMarketCount: 2,
        }}
        refreshStats={{
          high: 1,
          medium: 0,
          low: 1,
          resonance: 0,
          biasQualityCore: 0,
          selectionQualityActive: 0,
          reviewContext: 0,
          structuralDecayRadar: 0,
          priorityNew: 0,
          priorityEscalated: 0,
          priorityRelaxed: 0,
          priorityUpdated: 0,
          snapshotViewFiltered: 0,
          snapshotViewScoped: 0,
          peopleLayer: 0,
          departmentChaos: 0,
          selectionQuality: 0,
          policySource: 0,
          biasQuality: 0,
        }}
        setFilters={jest.fn()}
        snapshotSummaryOptions={snapshotSummaryOptions}
        sourceOptions={sourceOptions}
        stats={{ total: 4, status_counts: { in_progress: 1, blocked: 0, complete: 0 } }}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />
    );

    expect(screen.getByText('当前复盘队列执行入口')).toBeTruthy();
    expect(screen.getByText('当前排序首条：Lead Research Task')).toBeTruthy();
    expect(screen.getByText('Pricing 1')).toBeTruthy();
    expect(screen.getByText('Cross-Market 2')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '打开队列首条' }));
    fireEvent.click(screen.getByRole('button', { name: '打开首个 Pricing' }));
    fireEvent.click(screen.getByRole('button', { name: '打开首个跨市场' }));

    expect(onOpenQueueLead).toHaveBeenCalledTimes(1);
    expect(onOpenQueuePricing).toHaveBeenCalledTimes(1);
    expect(onOpenQueueCrossMarket).toHaveBeenCalledTimes(1);
  });
});
