import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';

describe('buildSnapshotComparison for pricing snapshots', () => {
  it('includes governance, policy execution, and source-mode deltas', () => {
    const comparison = buildSnapshotComparison(
      'pricing',
      {
        payload: {
          period: '1y',
          gap_analysis: { fair_value_mid: 180, gap_pct: -8.4 },
          fair_value: { low: 160, mid: 180, high: 198 },
          implications: {
            primary_view: '低估',
            confidence: 'medium',
            confidence_score: 0.58,
            factor_alignment: { label: 'aligned' },
          },
          primary_driver: { factor: 'alpha' },
          factor_model: { period: '1y', data_points: 252, ff5_alpha_pct: 4.2 },
          people_layer: {
            summary: '技术治理仍有支撑。',
            insider_flow: { label: '内部人持平' },
            hiring_signal: { alert_message: '技术岗补充仍在继续。' },
            executive_profile: { leadership_balance: '技术/产品主导' },
          },
          people_governance_overlay: {
            label: '执行支撑',
            governance_discount_pct: 2.4,
            confidence: 0.41,
            summary: '执行仍偏稳健，治理折价有限。',
            executive_evidence: { leadership_balance: '技术/产品主导' },
            insider_evidence: { label: '内部人持平' },
            hiring_evidence: { alert_message: '技术岗补充仍在继续。' },
            policy_execution_context: {
              label: 'watch',
              summary: '政策执行仍处观察区。',
              top_department: '发改委',
            },
            source_mode_summary: {
              label: 'official-led',
              coverage: 4,
              summary: '官方/披露源占主导。',
            },
          },
          research_input: {
            macro: {
              people_layer: { summary: '技术治理仍有支撑。' },
              policy_execution: {
                label: 'watch',
                summary: '政策执行仍处观察区。',
                top_departments: [{ department_label: '发改委' }],
              },
              source_mode_summary: {
                label: 'official-led',
                coverage: 4,
                summary: '官方/披露源占主导。',
              },
            },
          },
          view_context: {
            summary: '快速视图：自动排序升档 · 类型：Pricing',
            scoped_task_label: '当前定位：rw_task_1',
          },
        },
      },
      {
        payload: {
          period: '6mo',
          gap_analysis: { fair_value_mid: 166, gap_pct: 3.1 },
          fair_value: { low: 148, mid: 166, high: 183 },
          implications: {
            primary_view: '高估',
            confidence: 'low',
            confidence_score: 0.44,
            factor_alignment: { label: 'conflict' },
          },
          primary_driver: { factor: 'governance_discount' },
          factor_model: { period: '6mo', data_points: 126, ff5_alpha_pct: -1.8 },
          people_layer: {
            summary: '治理脆弱正在抬升。',
            insider_flow: { label: '内部人减持偏谨慎' },
            hiring_signal: { alert_message: '技术组织继续被商业 KPI 稀释。' },
            executive_profile: { leadership_balance: '商业/财务主导' },
          },
          people_governance_overlay: {
            label: '治理折价',
            governance_discount_pct: 8.6,
            confidence: 0.72,
            summary: '执行/治理折价主导当前定价。',
            executive_evidence: { leadership_balance: '商业/财务主导' },
            insider_evidence: { label: '内部人减持偏谨慎' },
            hiring_evidence: { alert_message: '技术组织继续被商业 KPI 稀释。' },
            policy_execution_context: {
              label: 'chaotic',
              summary: '部门执行混乱继续升温。',
              top_department: '发改委',
            },
            source_mode_summary: {
              label: 'fallback-heavy',
              coverage: 8,
              summary: '回退源占比抬升，需要压缩风险预算。',
            },
          },
          research_input: {
            macro: {
              people_layer: { summary: '治理脆弱正在抬升。' },
              policy_execution: {
                label: 'chaotic',
                summary: '部门执行混乱继续升温。',
                top_departments: [{ department_label: '发改委' }],
              },
              source_mode_summary: {
                label: 'fallback-heavy',
                coverage: 8,
                summary: '回退源占比抬升，需要压缩风险预算。',
              },
            },
          },
          view_context: {
            summary: '快速视图：自动排序升档 · 类型：Pricing',
            scoped_task_label: '当前定位：rw_task_1',
          },
        },
      },
    );

    const labels = (comparison?.rows || []).map((row) => row.label);
    expect(labels).toContain('Evidence Alignment');
    expect(labels).toContain('Governance Overlay');
    expect(labels).toContain('Policy Execution');
    expect(labels).toContain('Source Mode');
    expect(labels).toContain('People Layer');
    expect(labels).toContain('Executive Evidence');

    const governanceRow = comparison.rows.find((row) => row.label === 'Governance Discount');
    expect(governanceRow.left).toBe('2.40%');
    expect(governanceRow.right).toBe('8.60%');

    const policyRow = comparison.rows.find((row) => row.label === 'Policy Execution');
    expect(policyRow.left).toBe('watch');
    expect(policyRow.right).toBe('chaotic');

    const sourceModeRow = comparison.rows.find((row) => row.label === 'Source Mode');
    expect(sourceModeRow.left).toBe('官方/披露主导');
    expect(sourceModeRow.right).toBe('回退源偏多');
  });
});
