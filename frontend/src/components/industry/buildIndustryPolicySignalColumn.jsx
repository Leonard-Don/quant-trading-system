import { Tag } from 'antd';

/**
 * Builds the antd Table column descriptor for the "政策信号" column on the
 * Industry Heat ranking table. Extracted from `IndustryDashboard.jsx` so the
 * column logic — empty fallback, signal-tag coloring, |impact| sorter — can
 * be unit-tested without spinning up the full dashboard.
 *
 * The shape returned matches what's spread into `hotIndustryColumns`. Render
 * output stays in sync with the inline implementation in IndustryDashboard.
 *
 * @param {object} opts
 * @param {string} opts.mutedColor  Token color for the "无数据" "-" fallback.
 * @returns {object} antd Table column descriptor with sorter, render, etc.
 */
export const buildIndustryPolicySignalColumn = ({ mutedColor = 'var(--text-muted)' } = {}) => ({
    title: '政策信号',
    dataIndex: 'policy_signal',
    key: 'policy_signal',
    width: 132,
    // 按 |avg_impact| 排序：让用户能一眼把政策影响最强的行业顶到表头/表尾。
    // 缺数据的行按 0 处理，永远落底。
    sorter: (a, b) => Math.abs(Number(a?.policy_signal?.avg_impact) || 0)
        - Math.abs(Number(b?.policy_signal?.avg_impact) || 0),
    onHeaderCell: () => ({ 'data-testid': 'industry-policy-signal-column' }),
    onCell: () => ({ 'data-testid': 'industry-policy-signal-cell' }),
    render: (policySignal) => {
        if (!policySignal) {
            // 无政策数据：与其他空字段保持一致的 "-" 而不是空白，避免错位。
            return <span style={{ color: mutedColor, fontSize: 12 }}>-</span>;
        }
        const { signal, avg_impact: avgImpact, mentions } = policySignal;
        const impactValue = Number(avgImpact);
        const hasImpact = Number.isFinite(impactValue);
        let tagColor = 'default';
        let tagText = '中性';
        if (signal === 'bullish') {
            tagColor = 'red';
            tagText = '偏多';
        } else if (signal === 'bearish') {
            tagColor = 'green';
            tagText = '偏空';
        }
        const impactColor = hasImpact && impactValue >= 0 ? '#cf1322' : '#3f8600';
        return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'flex-start' }}>
                <Tag
                    color={tagColor}
                    data-testid={`industry-policy-signal-tag-${signal || 'neutral'}`}
                    style={{ margin: 0, borderRadius: 999, fontSize: 10, paddingInline: 8, lineHeight: '16px' }}
                >
                    {tagText}
                </Tag>
                <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                    <span style={{ color: mutedColor, fontSize: 10 }}>提及 {Number(mentions) || 0}</span>
                    {hasImpact && (
                        <span style={{ color: impactColor, fontSize: 11, fontWeight: 600 }}>
                            {impactValue >= 0 ? '+' : ''}{impactValue.toFixed(2)}
                        </span>
                    )}
                </div>
            </div>
        );
    },
});

export default buildIndustryPolicySignalColumn;
