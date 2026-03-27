import {
  buildViewUrlForCurrentState,
  buildWorkbenchLink,
  readResearchContext,
} from '../utils/researchContext';

describe('researchContext workbench deep links', () => {
  it('builds and reads workbench filter params', () => {
    const url = buildWorkbenchLink(
      {
        refresh: 'high',
        type: 'cross_market',
        sourceFilter: 'godeye',
        reason: 'resonance',
        taskId: 'task_123',
      },
      '?view=godsEye'
    );

    expect(url).toContain('view=workbench');
    expect(url).toContain('workbench_refresh=high');
    expect(url).toContain('workbench_type=cross_market');
    expect(url).toContain('workbench_source=godeye');
    expect(url).toContain('workbench_reason=resonance');
    expect(url).toContain('task=task_123');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('workbench');
    expect(parsed.workbenchRefresh).toBe('high');
    expect(parsed.workbenchType).toBe('cross_market');
    expect(parsed.workbenchSource).toBe('godeye');
    expect(parsed.workbenchReason).toBe('resonance');
    expect(parsed.task).toBe('task_123');
  });

  it('preserves workbench filters when syncing the current workbench view url', () => {
    const url = buildViewUrlForCurrentState(
      'workbench',
      '?view=workbench&workbench_refresh=high&workbench_type=pricing&workbench_source=pricing_playbook&workbench_reason=policy_source&task=rw_123'
    );

    expect(url).toContain('view=workbench');
    expect(url).toContain('workbench_refresh=high');
    expect(url).toContain('workbench_type=pricing');
    expect(url).toContain('workbench_source=pricing_playbook');
    expect(url).toContain('workbench_reason=policy_source');
    expect(url).toContain('task=rw_123');

    const parsed = readResearchContext(url.split('?')[1] ? `?${url.split('?')[1]}` : '');
    expect(parsed.view).toBe('workbench');
    expect(parsed.workbenchRefresh).toBe('high');
    expect(parsed.workbenchType).toBe('pricing');
    expect(parsed.workbenchSource).toBe('pricing_playbook');
    expect(parsed.workbenchReason).toBe('policy_source');
    expect(parsed.task).toBe('rw_123');
  });
});
