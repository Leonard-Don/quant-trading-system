/**
 * Industry Heat ranking — policy_radar overlay column.
 *
 * Verifies the new "政策信号" column descriptor produced by
 * `buildIndustryPolicySignalColumn` (split out from IndustryDashboard so the
 * render + sorter logic can be tested in isolation):
 *  1. signal present → tag + mentions + impact rendered
 *  2. signal absent → "-" placeholder
 *  3. table can be sorted by |avg_impact| via the column's sorter()
 *
 * These three cases mirror the backend `include_policy_signal=true` /
 * degraded / opt-out paths covered in
 * `tests/unit/test_industry_rotation_endpoint_exceptions.py`.
 */

import { render, screen, within } from '@testing-library/react';
import { Table } from 'antd';
import '@testing-library/jest-dom';

import buildIndustryPolicySignalColumn from '../components/industry/buildIndustryPolicySignalColumn';

const renderTable = (rows, extraColumns = []) => {
    const columns = [
        {
            title: '行业',
            dataIndex: 'industry_name',
            key: 'industry_name',
        },
        buildIndustryPolicySignalColumn({ mutedColor: '#999' }),
        ...extraColumns,
    ];
    return render(
        <Table
            data-testid="industry-ranking-table"
            dataSource={rows}
            columns={columns}
            rowKey="industry_name"
            pagination={false}
        />,
    );
};

describe('Industry ranking — policy_radar overlay column', () => {
    test('renders signal tag, mention count and impact value when policy data exists', () => {
        const rows = [
            {
                industry_name: '新能源汽车',
                policy_signal: {
                    avg_impact: -0.32,
                    mentions: 119,
                    signal: 'bearish',
                    last_refresh_at: '2026-05-17T07:29:47.810070',
                },
            },
        ];
        renderTable(rows);

        // Column header is identifiable for downstream selectors (sort, filter).
        expect(screen.getByTestId('industry-policy-signal-column')).toBeInTheDocument();

        // Tag matches the signal classification with Chinese label.
        const tag = screen.getByTestId('industry-policy-signal-tag-bearish');
        expect(tag).toHaveTextContent('偏空');

        // Mentions surface with "提及 N" prefix and impact prints with sign.
        expect(screen.getByText(/提及 119/)).toBeInTheDocument();
        expect(screen.getByText(/-0\.32/)).toBeInTheDocument();
    });

    test('renders a "-" placeholder when policy_signal is null', () => {
        const rows = [
            {
                industry_name: '钢铁',
                policy_signal: null,
            },
        ];
        renderTable(rows);

        // The cell exists but only contains "-" — no tag, no mention badge.
        const cells = screen.getAllByTestId('industry-policy-signal-cell');
        expect(cells).toHaveLength(1);
        expect(within(cells[0]).getByText('-')).toBeInTheDocument();
        expect(screen.queryByTestId(/^industry-policy-signal-tag-/)).not.toBeInTheDocument();
        expect(screen.queryByText(/提及/)).not.toBeInTheDocument();
    });

    test('column sorter orders by |avg_impact| (no-data rows fall to bottom)', () => {
        const column = buildIndustryPolicySignalColumn();
        const sorter = column.sorter;

        // Three rows: bullish big impact, bearish smaller impact, no-data row.
        const heavyImpact = { policy_signal: { avg_impact: 0.65, mentions: 8, signal: 'bullish' } };
        const lightImpact = { policy_signal: { avg_impact: -0.32, mentions: 119, signal: 'bearish' } };
        const noPolicy = { policy_signal: null };

        // Sort ascending — |0| < |0.32| < |0.65|. Validate with pairwise sorter calls.
        // (antd Table calls the sorter the same way Array.sort does.)
        const sortedAsc = [heavyImpact, lightImpact, noPolicy].sort(sorter);
        const ascImpacts = sortedAsc.map((row) => Math.abs(Number(row.policy_signal?.avg_impact) || 0));
        expect(ascImpacts).toEqual([0, 0.32, 0.65]);

        // Descending uses the same sorter with reversed arguments (or .reverse()),
        // matching how antd's `Table` toggles sort direction.
        const sortedDesc = [...sortedAsc].reverse();
        const descImpacts = sortedDesc.map((row) => Math.abs(Number(row.policy_signal?.avg_impact) || 0));
        expect(descImpacts).toEqual([0.65, 0.32, 0]);
    });
});
