import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';

import PolicyRadarPanel from '../components/industry/PolicyRadarPanel';

const mockGetSignal = jest.fn();
const mockGetRecords = jest.fn();

jest.mock('../services/api', () => ({
    getPolicyRadarSignal: (...args) => mockGetSignal(...args),
    getPolicyRadarRecords: (...args) => mockGetRecords(...args),
}));

const SIGNAL_DATA = {
    industry_signals: {
        '新能源': { avg_impact: 0.42, mentions: 5, signal: 'bullish' },
        '半导体': { avg_impact: -0.31, mentions: 3, signal: 'bearish' },
    },
    policy_count: 8,
    source_health: {
        ndrc: { level: 'healthy', record_count: 4, full_text_ratio: 0.85 },
    },
    last_refresh: '2026-05-03T08:00:00',
    available: true,
};

const RECORDS_DATA = {
    records: [
        {
            record_id: 'r1',
            timestamp: '2026-05-02T09:30:00',
            source: 'policy_radar:ndrc',
            raw_value: {
                title: '新能源汽车下乡通知',
                summary: '财政部发文鼓励新能源汽车下乡',
            },
            normalized_score: 0.42,
            metadata: { detail_url: 'https://example.com/p/1' },
            tags: ['新能源'],
        },
    ],
    timeframe: '7d',
    industry: null,
    limit: 10,
    available: true,
};

describe('PolicyRadarPanel', () => {
    beforeEach(() => {
        mockGetSignal.mockReset();
        mockGetRecords.mockReset();
    });

    it('renders industry signals and recent records on success', async () => {
        mockGetSignal.mockResolvedValue({ success: true, data: SIGNAL_DATA });
        mockGetRecords.mockResolvedValue({ success: true, data: RECORDS_DATA });

        render(<PolicyRadarPanel />);

        await waitFor(() => {
            expect(screen.getByText('共 8 条政策记录')).toBeInTheDocument();
        });
        // Industry signals
        expect(screen.getByText(/新能源 · 偏多/)).toBeInTheDocument();
        expect(screen.getByText(/半导体 · 偏空/)).toBeInTheDocument();
        // Source health badge
        expect(screen.getByText(/ndrc · 健康/)).toBeInTheDocument();
        // Record renders title and link
        expect(screen.getByText('新能源汽车下乡通知')).toBeInTheDocument();
        expect(screen.getByText(/原文/)).toBeInTheDocument();
    });

    it('shows the empty placeholder when both endpoints return unavailable payloads', async () => {
        mockGetSignal.mockResolvedValue({ success: true, data: { ...SIGNAL_DATA, available: false, industry_signals: {}, policy_count: 0 } });
        mockGetRecords.mockResolvedValue({ success: true, data: { ...RECORDS_DATA, available: false, records: [] } });

        render(<PolicyRadarPanel />);

        await waitFor(() => {
            expect(screen.getByText(/政策数据未就绪/)).toBeInTheDocument();
        });
        expect(screen.queryByText(/共 .* 条政策记录/)).not.toBeInTheDocument();
    });

    it('survives API errors by falling back to the empty state', async () => {
        mockGetSignal.mockRejectedValue(new Error('boom'));
        mockGetRecords.mockRejectedValue(new Error('boom'));

        render(<PolicyRadarPanel />);

        await waitFor(() => {
            expect(screen.getByText(/政策数据未就绪/)).toBeInTheDocument();
        });
    });

    it('forwards the industry filter to the records endpoint', async () => {
        mockGetSignal.mockResolvedValue({ success: true, data: SIGNAL_DATA });
        mockGetRecords.mockResolvedValue({ success: true, data: { ...RECORDS_DATA, industry: '新能源' } });

        render(<PolicyRadarPanel industry="新能源" timeframe="30d" limit={5} />);

        await waitFor(() => {
            expect(mockGetRecords).toHaveBeenCalledWith({
                industry: '新能源',
                timeframe: '30d',
                limit: 5,
            });
        });
    });

    it('refresh button triggers another fetch round', async () => {
        mockGetSignal.mockResolvedValue({ success: true, data: SIGNAL_DATA });
        mockGetRecords.mockResolvedValue({ success: true, data: RECORDS_DATA });

        render(<PolicyRadarPanel />);
        // Wait for the data-loaded state so the antd Button is not in loading
        // mode (loading buttons swallow clicks).
        await waitFor(() => {
            expect(screen.getByText('共 8 条政策记录')).toBeInTheDocument();
        });
        expect(mockGetSignal).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByLabelText('刷新政策雷达'));

        await waitFor(() => expect(mockGetSignal).toHaveBeenCalledTimes(2));
    });
});
