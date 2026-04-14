import {
  buildBoardReorderItems,
  buildOpenTaskPriorityLabel,
  buildOpenTaskPriorityNote,
  buildRefreshPriorityEventPayload,
  buildRefreshPriorityMeta,
  buildRefreshStats,
  buildTimelineItems,
  filterWorkbenchTasks,
} from '../components/research-workbench/workbenchSelectors';

describe('workbenchSelectors', () => {
  it('counts structural decay radar tasks inside refresh stats', () => {
    const stats = buildRefreshStats({
      prioritized: [
        {
          severity: 'high',
          structuralDecayRadarDriven: true,
          structuralDecayDriven: false,
        },
        {
          severity: 'medium',
          structuralDecayRadarDriven: false,
          structuralDecayDriven: true,
        },
      ],
    }, [
      {
        id: 'task_new',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'new',
            },
          },
        ],
      },
      {
        id: 'task_escalated',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'escalated',
            },
          },
        ],
      },
      {
        id: 'task_relaxed',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'relaxed',
            },
          },
        ],
      },
      {
        id: 'task_updated',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'updated',
            },
          },
        ],
      },
    ]);

    expect(stats.structuralDecayRadar).toBe(1);
    expect(stats.structuralDecay).toBe(2);
    expect(stats.priorityNew).toBe(1);
    expect(stats.priorityEscalated).toBe(1);
    expect(stats.priorityRelaxed).toBe(1);
    expect(stats.priorityUpdated).toBe(1);
  });

  it('allows structural decay filter to match radar-driven tasks', () => {
    const tasks = [
      {
        id: 'cross_task_1',
        type: 'cross_market',
        status: 'in_progress',
        title: 'Utilities vs Growth',
        updated_at: '2026-04-11T10:00:00Z',
      },
    ];
    const filtered = filterWorkbenchTasks(
      tasks,
      { type: '', source: '', refresh: '', reason: 'structural_decay', keyword: '' },
      {
        cross_task_1: {
          severity: 'high',
          urgencyScore: 5,
          priorityWeight: 3.4,
          structuralDecayRadarDriven: true,
          structuralDecayDriven: false,
        },
      }
    );

    expect(filtered).toHaveLength(1);
    expect(filtered[0].id).toBe('cross_task_1');
  });

  it('allows priority-escalated filter to match tasks with escalated auto-priority events', () => {
    const tasks = [
      {
        id: 'cross_task_1',
        type: 'cross_market',
        status: 'in_progress',
        title: 'Utilities vs Growth',
        updated_at: '2026-04-11T10:00:00Z',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'escalated',
            },
          },
        ],
      },
      {
        id: 'cross_task_2',
        type: 'cross_market',
        status: 'in_progress',
        title: 'Defensive Hedge',
        updated_at: '2026-04-11T09:00:00Z',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'relaxed',
            },
          },
        ],
      },
    ];

    const filtered = filterWorkbenchTasks(
      tasks,
      { type: '', source: '', refresh: '', reason: 'priority_escalated', keyword: '' },
      {}
    );

    expect(filtered).toHaveLength(1);
    expect(filtered[0].id).toBe('cross_task_1');
  });

  it('allows snapshot-summary filter to match tasks saved from the same research view', () => {
    const tasks = [
      {
        id: 'pricing_task_1',
        type: 'pricing',
        status: 'new',
        title: 'AAPL pricing refresh',
        updated_at: '2026-04-11T10:00:00Z',
        snapshot: {
          payload: {
            view_context: {
              summary: '快速视图：自动排序升档 · 类型：Pricing',
              scoped_task_label: '当前定位：pricing_task_1',
              note: '这次快照是在带筛选的工作台视图下保存的。',
            },
          },
        },
      },
      {
        id: 'pricing_task_2',
        type: 'pricing',
        status: 'new',
        title: 'MSFT pricing refresh',
        updated_at: '2026-04-11T09:00:00Z',
        snapshot: {
          payload: {
            view_context: {
              summary: '快速视图：自动排序缓和 · 类型：Pricing',
            },
          },
        },
      },
    ];

    const filtered = filterWorkbenchTasks(
      tasks,
      {
        type: '',
        source: '',
        refresh: '',
        reason: '',
        snapshotView: '',
        snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
        keyword: '',
      },
      {}
    );

    expect(filtered).toHaveLength(1);
    expect(filtered[0].id).toBe('pricing_task_1');
  });

  it('allows priority-new filter to match tasks with first-time auto-priority events', () => {
    const tasks = [
      {
        id: 'cross_task_1',
        type: 'cross_market',
        status: 'in_progress',
        title: 'Utilities vs Growth',
        updated_at: '2026-04-11T10:00:00Z',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'new',
            },
          },
        ],
      },
      {
        id: 'cross_task_2',
        type: 'cross_market',
        status: 'in_progress',
        title: 'Defensive Hedge',
        updated_at: '2026-04-11T09:00:00Z',
        timeline: [
          {
            type: 'refresh_priority',
            meta: {
              change_type: 'updated',
            },
          },
        ],
      },
    ];

    const filtered = filterWorkbenchTasks(
      tasks,
      { type: '', source: '', refresh: '', reason: 'priority_new', keyword: '' },
      {}
    );

    expect(filtered).toHaveLength(1);
    expect(filtered[0].id).toBe('cross_task_1');
  });

  it('prioritizes radar-driven open-task label and note', () => {
    const selectedTask = {
      title: 'Utilities vs Growth',
      note: '原始备注',
    };
    const selectedTaskRefreshSignal = {
      structuralDecayRadarDriven: true,
      structuralDecayDriven: true,
      structuralDecayRadarShift: {
        actionHint: '建议先收缩风险预算，再确认是否保留现有多空表达。',
      },
      structuralDecayShift: {
        actionHint: '建议复核结构性衰败判断。',
      },
    };

    expect(buildOpenTaskPriorityLabel(selectedTaskRefreshSignal)).toBe('优先复核系统衰败雷达');
    expect(buildOpenTaskPriorityNote(selectedTask, selectedTaskRefreshSignal)).toContain('收缩风险预算');
  });

  it('builds readable priority meta for radar-driven tasks', () => {
    const meta = buildRefreshPriorityMeta({
      severity: 'high',
      priorityReason: 'structural_decay',
      urgencyScore: 5,
      priorityWeight: 3.4,
      recommendation: '建议优先复核系统级防御构造。',
      structuralDecayRadarDriven: true,
      structuralDecayRadarShift: {
        lead: '系统级结构衰败雷达已升级到警报区',
        topSignalSummary: '组织脆弱 · 部门混乱',
        actionHint: '建议先收缩风险预算，再确认是否保留现有多空表达。',
      },
    });

    expect(meta.reasonLabel).toBe('结构衰败/系统雷达');
    expect(meta.reasonKey).toBe('structural_decay');
    expect(meta.severity).toBe('high');
    expect(meta.lead).toContain('警报区');
    expect(meta.detail).toContain('紧急度 5.0');
    expect(meta.detail).toContain('组织脆弱');
    expect(meta.detail).toContain('风险预算');
  });

  it('prepends synthetic refresh-priority event into timeline items', () => {
    const refreshSignal = {
      severity: 'high',
      priorityReason: 'structural_decay',
      urgencyScore: 5,
      priorityWeight: 3.4,
      recommendation: '建议优先复核系统级防御构造。',
    };
    const items = buildTimelineItems(
      [
        {
          id: 'event_1',
          type: 'snapshot_saved',
          label: '研究快照已更新',
          detail: '保存了新的研究快照',
          created_at: '2026-04-10T10:00:00Z',
          meta: {
            view_context_summary: '快速视图：自动排序升档 · 关键词：defense',
            view_context_scoped_task_label: '当前定位：rw_focus_1',
            view_context_note: '这次快照是在带筛选的工作台视图下保存的。',
          },
        },
      ],
      false,
      {
        id: 'cross_task_1',
        updated_at: '2026-04-11T11:00:00Z',
      },
      refreshSignal,
      {
        reasonKey: 'structural_decay',
        reasonLabel: '结构衰败/系统雷达',
        severity: 'high',
        urgencyScore: 5,
        priorityWeight: 3.4,
        lead: '系统级结构衰败雷达已升级到警报区',
        detail: '紧急度 5.0；建议先收缩风险预算。',
      }
    );

    expect(items[0].children.label).toBe('系统自动重排：结构衰败/系统雷达');
    expect(items[0].children.type).toBe('自动排序');
    expect(items[0].children.detail).toContain('系统级结构衰败雷达已升级到警报区');
    expect(items[1].children.snapshotViewSummary).toBe('快速视图：自动排序升档 · 关键词：defense');
    expect(items[1].children.snapshotViewFocus).toBe('当前定位：rw_focus_1');
    expect(items[1].children.snapshotViewNote).toBe('这次快照是在带筛选的工作台视图下保存的。');
  });

  it('builds persistable refresh-priority payload for backend timeline writes', () => {
    const refreshSignal = {
      severity: 'high',
      priorityReason: 'structural_decay',
      urgencyScore: 5,
      priorityWeight: 3.4,
      recommendation: '建议优先复核系统级防御构造。',
      summary: '系统雷达正在驱动当前任务排序。',
    };
    const meta = {
      reasonKey: 'structural_decay',
      reasonLabel: '结构衰败/系统雷达',
      severity: 'high',
      urgencyScore: 5,
      priorityWeight: 3.4,
      lead: '系统级结构衰败雷达已升级到警报区',
      detail: '紧急度 5.0；建议先收缩风险预算。',
    };

    expect(buildRefreshPriorityEventPayload(refreshSignal, meta)).toEqual({
      reason_key: 'structural_decay',
      reason_label: '结构衰败/系统雷达',
      severity: 'high',
      urgency_score: 5,
      priority_weight: 3.4,
      lead: '系统级结构衰败雷达已升级到警报区',
      detail: '紧急度 5.0；建议先收缩风险预算。',
      recommendation: '建议优先复核系统级防御构造。',
      summary: '系统雷达正在驱动当前任务排序。',
    });
  });

  it('does not duplicate synthetic refresh-priority event when persisted event already exists', () => {
    const items = buildTimelineItems(
      [
        {
          id: 'event_refresh',
          type: 'refresh_priority',
          label: '系统自动重排：结构衰败/系统雷达',
          detail: '系统级结构衰败雷达已升级到警报区；紧急度 5.0；建议先收缩风险预算。',
          created_at: '2026-04-11T11:00:00Z',
          meta: {
            priority_reason: 'structural_decay',
          },
        },
      ],
      false,
      {
        id: 'cross_task_1',
        updated_at: '2026-04-11T11:00:00Z',
      },
      {
        severity: 'high',
        priorityReason: 'structural_decay',
        urgencyScore: 5,
        priorityWeight: 3.4,
      },
      {
        reasonKey: 'structural_decay',
        reasonLabel: '结构衰败/系统雷达',
        severity: 'high',
        urgencyScore: 5,
        priorityWeight: 3.4,
        lead: '系统级结构衰败雷达已升级到警报区',
        detail: '紧急度 5.0；建议先收缩风险预算。',
      }
    );

    expect(items).toHaveLength(1);
    expect(items[0].children.label).toBe('系统自动重排：结构衰败/系统雷达');
  });

  it('marks synthetic refresh-priority timeline events as escalated when urgency increases', () => {
    const items = buildTimelineItems(
      [
        {
          id: 'event_refresh',
          type: 'refresh_priority',
          label: '系统自动重排：人的维度',
          detail: '人的维度开始走弱；紧急度 3.0；建议关注关键岗位变化。',
          created_at: '2026-04-11T11:00:00Z',
          meta: {
            priority_reason: 'people_layer',
            reason_label: '人的维度',
            severity: 'medium',
            urgency_score: 3,
            priority_weight: 2,
          },
        },
      ],
      false,
      {
        id: 'cross_task_1',
        updated_at: '2026-04-11T12:00:00Z',
      },
      {
        severity: 'high',
        priorityReason: 'structural_decay',
        urgencyScore: 5,
        priorityWeight: 3.4,
      },
      {
        reasonKey: 'structural_decay',
        reasonLabel: '结构衰败/系统雷达',
        severity: 'high',
        urgencyScore: 5,
        priorityWeight: 3.4,
        lead: '系统级结构衰败雷达已升级到警报区',
        detail: '紧急度 5.0；建议先收缩风险预算。',
      }
    );

    expect(items[0].children.label).toBe('系统自动重排升级：结构衰败/系统雷达');
    expect(items[0].children.changeLabel).toBe('升级');
  });

  it('adds refresh-priority payload only for tasks whose board position changed', () => {
    const items = buildBoardReorderItems(
      [
        { id: 'task_a', status: 'in_progress', board_order: 0 },
        { id: 'task_b', status: 'new', board_order: 0 },
      ],
      [
        { id: 'task_a', status: 'new', board_order: 0 },
        { id: 'task_b', status: 'new', board_order: 1 },
      ],
      {
        task_a: {
          severity: 'high',
          priorityReason: 'structural_decay',
          urgencyScore: 5,
          priorityWeight: 3.4,
          recommendation: '建议优先复核系统级防御构造。',
          structuralDecayRadarDriven: true,
          structuralDecayRadarShift: {
            lead: '系统级结构衰败雷达已升级到警报区',
          },
        },
      }
    );

    expect(items[0]).toMatchObject({
      task_id: 'task_b',
      status: 'new',
      board_order: 0,
    });
    expect(items[0].refresh_priority_event).toBeUndefined();
    expect(items[1].task_id).toBe('task_a');
    expect(items[1].refresh_priority_event).toMatchObject({
      reason_key: 'structural_decay',
      reason_label: '结构衰败/系统雷达',
    });
  });
});
