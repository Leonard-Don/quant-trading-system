import { buildHunterModel } from '../components/GodEyeDashboard/viewModels';

describe('buildHunterModel narrative shifts', () => {
  it('adds a cross-market alert when dominant driver and theme core change across research snapshots', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {},
      status: {},
      researchTasks: [
        {
          id: 'task_1',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Energy vs AI thesis',
          template: 'energy_vs_ai_apps',
          updated_at: '2026-03-20T10:00:00',
          snapshot: {
            payload: {
              template_meta: {
                template_id: 'energy_vs_ai_apps',
                dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.31 }],
                theme_core: 'XLE+8.5pp',
                theme_support: 'SOXX',
              },
            },
          },
          snapshot_history: [
            {
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.31 }],
                  theme_core: 'XLE+8.5pp',
                  theme_support: 'SOXX',
                },
              },
            },
            {
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  dominant_drivers: [{ key: 'baseload_support', label: '基建/基荷支撑', value: 0.19 }],
                  theme_core: 'HG=F+4.0pp',
                  theme_support: 'IGV',
                },
              },
            },
          ],
        },
      ],
    });

    expect(alerts.some((item) => item.title.includes('主导叙事切换'))).toBe(true);
    const shiftAlert = alerts.find((item) => item.key === 'narrative-shift-energy_vs_ai_apps');
    expect(shiftAlert.severity).toBe('high');
    expect(shiftAlert.description).toContain('主导驱动从 基建/基荷支撑 切换到 成长端估值压力');
    expect(shiftAlert.action.target).toBe('cross-market');
    expect(shiftAlert.action.template).toBe('energy_vs_ai_apps');
  });
});
