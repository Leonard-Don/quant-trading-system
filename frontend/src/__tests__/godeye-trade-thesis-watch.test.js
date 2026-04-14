import { buildTradeThesisWatchModel } from '../components/GodEyeDashboard/viewModels';

describe('GodEye trade thesis watch model', () => {
  it('extracts drifting trade thesis tasks into a ranked watchlist', () => {
    const items = buildTradeThesisWatchModel(
      [
        {
          id: 'thesis_1',
          type: 'trade_thesis',
          status: 'in_progress',
          symbol: 'BABA',
          title: '[Thesis] China internet relative short',
          snapshot: {
            payload: {
              trade_thesis: {
                thesis: {
                  stance: '结构性做空',
                  expected_horizon: '3-6m',
                  summary: '应用层叙事开始空心化，主表达腿需要重新确认。',
                  primary_leg: { symbol: 'KWEB', side: 'short' },
                  trade_legs: [
                    { symbol: 'KWEB', side: 'short', role: 'core_expression' },
                    { symbol: 'BABA', side: 'short', role: 'relative_expression' },
                    { symbol: 'GLD', side: 'long', role: 'stress_hedge' },
                  ],
                },
                structural_decay: {
                  score: 0.74,
                },
                results_summary: {
                  summary: '当前 Thesis 需要重新确认主表达腿和风险对冲。',
                },
              },
            },
          },
        },
        {
          id: 'thesis_2',
          type: 'trade_thesis',
          status: 'in_progress',
          symbol: 'NVDA',
          title: '[Thesis] AI infra hedge',
          snapshot: {
            payload: {
              trade_thesis: {
                thesis: {
                  stance: '观察',
                  expected_horizon: '1-3m',
                  primary_leg: { symbol: 'NVDA', side: 'long' },
                  trade_legs: [{ symbol: 'NVDA', side: 'long', role: 'core_expression' }],
                },
                structural_decay: {
                  score: 0.33,
                },
              },
            },
          },
        },
      ],
      [
        {
          taskId: 'thesis_1',
          refreshLabel: '建议更新',
          severity: 'high',
          priorityReason: 'trade_thesis',
          tradeThesisDriven: true,
          tradeThesisShift: {
            lead: '主表达腿从 BABA 切到 KWEB，更像板块级表达。',
            evidenceSummary: '主腿 BABA→KWEB',
            actionHint: '建议优先确认主表达腿和组合方向是否仍然成立。',
          },
        },
      ]
    );

    expect(items).toHaveLength(2);
    expect(items[0].taskId).toBe('thesis_1');
    expect(items[0].symbol).toBe('KWEB');
    expect(items[0].refreshSeverity).toBe('high');
    expect(items[0].driftLead).toContain('主表达腿从 BABA 切到 KWEB');
    expect(items[0].driftEvidence).toBe('主腿 BABA→KWEB');
    expect(items[0].action.target).toBe('workbench');
    expect(items[0].action.type).toBe('trade_thesis');
    expect(items[1].taskId).toBe('thesis_2');
    expect(items[1].refreshLabel).toBe('保持观察');
  });
});
