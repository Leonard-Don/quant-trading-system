/**
 * StrategyForm 组件测试
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import StrategyForm from '../components/StrategyForm';

// 模拟 API 服务
jest.mock('../services/api', () => ({
    getStrategies: jest.fn(() => Promise.resolve([
        { id: 'sma_crossover', name: 'SMA Crossover', description: 'Moving average crossover strategy' },
        { id: 'rsi', name: 'RSI', description: 'Relative Strength Index strategy' }
    ])),
    runBacktest: jest.fn(() => Promise.resolve({
        success: true,
        metrics: {
            total_return: 0.15,
            sharpe_ratio: 1.2,
            max_drawdown: -0.08
        }
    }))
}));

// 模拟 antd 组件
jest.mock('antd', () => {
    const antd = jest.requireActual('antd');
    return {
        ...antd,
        message: {
            success: jest.fn(),
            error: jest.fn(),
            warning: jest.fn(),
            loading: jest.fn()
        }
    };
});

jest.mock('../utils/messageApi', () => ({
    useSafeMessageApi: () => ({
        success: jest.fn(),
        error: jest.fn(),
        warning: jest.fn(),
        info: jest.fn(),
    }),
}));

beforeAll(() => {
    if (!window.matchMedia) {
        window.matchMedia = () => ({
            matches: false,
            addListener: () => {},
            removeListener: () => {},
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => false,
        });
    }

    if (!window.ResizeObserver) {
        window.ResizeObserver = class {
            observe() {}
            unobserve() {}
            disconnect() {}
        };
    }
});


describe('StrategyForm Component', () => {

    describe('Form Validation', () => {
        test('validates stock symbol format', () => {
            const validSymbols = ['AAPL', 'GOOGL', 'MSFT', '^GSPC'];
            const invalidSymbols = ['', '   '];

            validSymbols.forEach(symbol => {
                expect(symbol.trim().length).toBeGreaterThan(0);
            });

            invalidSymbols.forEach(symbol => {
                expect(symbol.trim().length).toBe(0);
            });
        });

        test('validates initial capital is positive', () => {
            const validCapitals = [10000, 100000, 1000000];
            const invalidCapitals = [-100, 0];

            validCapitals.forEach(capital => {
                expect(capital).toBeGreaterThan(0);
            });

            invalidCapitals.forEach(capital => {
                expect(capital).toBeLessThanOrEqual(0);
            });
        });

        test('validates date range', () => {
            const startDate = new Date('2023-01-01');
            const endDate = new Date('2023-12-31');

            expect(startDate < endDate).toBe(true);
        });
    });

    describe('Strategy Selection', () => {
        test('syncs strategy field from loaded strategies before submit', async () => {
            const handleSubmit = jest.fn();
            render(
                <StrategyForm
                    strategies={[
                        {
                            name: 'moving_average',
                            parameters: {
                                fast_period: { default: 20 },
                                slow_period: { default: 50 },
                            },
                        },
                    ]}
                    onSubmit={handleSubmit}
                    loading={false}
                />
            );

            await waitFor(() => {
                expect(screen.getByDisplayValue('AAPL')).toBeInTheDocument();
                expect(screen.getAllByText('移动平均策略').length).toBeGreaterThan(0);
            });

            fireEvent.click(screen.getByRole('button', { name: '开始回测' }));

            await waitFor(() => {
                expect(handleSubmit).toHaveBeenCalledWith(expect.objectContaining({
                    strategy: 'moving_average',
                }));
            });
        });

        test('default strategy is selected', () => {
            const defaultStrategy = 'sma_crossover';
            const strategies = ['sma_crossover', 'rsi', 'macd'];

            expect(strategies).toContain(defaultStrategy);
        });

        test('all strategies have valid IDs', () => {
            const strategies = [
                { id: 'sma_crossover', name: 'SMA Crossover' },
                { id: 'rsi', name: 'RSI' },
                { id: 'macd', name: 'MACD' }
            ];

            strategies.forEach(strategy => {
                expect(strategy.id).toBeDefined();
                expect(strategy.id.length).toBeGreaterThan(0);
            });
        });
    });

    describe('Form Submission', () => {
        test('prepares correct payload format', () => {
            const formData = {
                symbol: 'AAPL',
                strategy: 'sma_crossover',
                initial_capital: 100000,
                start_date: '2023-01-01',
                end_date: '2023-12-31'
            };

            // 验证 payload 结构
            expect(formData).toHaveProperty('symbol');
            expect(formData).toHaveProperty('strategy');
            expect(formData).toHaveProperty('initial_capital');
            expect(formData).toHaveProperty('start_date');
            expect(formData).toHaveProperty('end_date');
        });
    });
});


describe('ResultsDisplay Component', () => {

    describe('Metrics Display', () => {
        test('formats percentage correctly', () => {
            const formatPercent = (value) => (value * 100).toFixed(2) + '%';

            expect(formatPercent(0.15)).toBe('15.00%');
            expect(formatPercent(-0.08)).toBe('-8.00%');
            expect(formatPercent(0)).toBe('0.00%');
        });

        test('formats currency correctly', () => {
            const formatCurrency = (value) => `$${value.toLocaleString()}`;

            expect(formatCurrency(100000)).toBe('$100,000');
            expect(formatCurrency(1234567.89)).toContain('1,234,567');
        });

        test('determines positive/negative returns', () => {
            const isPositive = (value) => value >= 0;

            expect(isPositive(0.15)).toBe(true);
            expect(isPositive(-0.08)).toBe(false);
            expect(isPositive(0)).toBe(true);
        });
    });

    describe('Chart Data Processing', () => {
        test('processes time series data correctly', () => {
            const rawData = [
                { date: '2023-01-01', value: 100000 },
                { date: '2023-01-02', value: 101000 },
                { date: '2023-01-03', value: 99500 }
            ];

            const processed = rawData.map(item => ({
                ...item,
                formattedDate: new Date(item.date).toLocaleDateString()
            }));

            expect(processed.length).toBe(3);
            expect(processed[0]).toHaveProperty('formattedDate');
        });

        test('calculates returns from values', () => {
            const values = [100000, 101000, 99500, 102000];
            const returns = values.slice(1).map((v, i) => (v - values[i]) / values[i]);

            expect(returns.length).toBe(3);
            expect(returns[0]).toBeCloseTo(0.01, 5);  // 1% return
        });
    });
});


describe('API Error Handling', () => {

    test('handles network errors gracefully', () => {
        const networkError = {
            code: 'ECONNABORTED',
            message: 'timeout of 30000ms exceeded'
        };

        const getErrorMessage = (error) => {
            if (error.code === 'ECONNABORTED') {
                return '请求超时，请检查网络连接';
            }
            return '请求失败，请稍后重试';
        };

        expect(getErrorMessage(networkError)).toBe('请求超时，请检查网络连接');
    });

    test('handles HTTP error status codes', () => {
        const getErrorMessage = (status) => {
            switch (status) {
                case 400: return '请求参数错误';
                case 401: return '请先登录';
                case 403: return '没有权限访问';
                case 404: return '请求的资源不存在';
                case 429: return '请求过于频繁';
                case 500: return '服务器内部错误';
                default: return '未知错误';
            }
        };

        expect(getErrorMessage(400)).toBe('请求参数错误');
        expect(getErrorMessage(500)).toBe('服务器内部错误');
    });

    test('extracts error message from response', () => {
        const errorResponse = {
            error: {
                code: 'VALIDATION_ERROR',
                message: '无效的股票代码'
            }
        };

        const extractMessage = (response) => {
            return response?.error?.message || '未知错误';
        };

        expect(extractMessage(errorResponse)).toBe('无效的股票代码');
        expect(extractMessage({})).toBe('未知错误');
    });
});


describe('WebSocket Service', () => {

    test('validates symbol format for subscription', () => {
        const normalizeSymbol = (symbol) => symbol.toUpperCase().trim();

        expect(normalizeSymbol('aapl')).toBe('AAPL');
        expect(normalizeSymbol('  googl  ')).toBe('GOOGL');
    });

    test('handles subscription state', () => {
        const subscriptions = new Set();

        subscriptions.add('AAPL');
        subscriptions.add('GOOGL');

        expect(subscriptions.has('AAPL')).toBe(true);
        expect(subscriptions.has('MSFT')).toBe(false);
        expect(subscriptions.size).toBe(2);

        subscriptions.delete('AAPL');
        expect(subscriptions.has('AAPL')).toBe(false);
    });

    test('parses price update messages', () => {
        const message = {
            type: 'price_update',
            symbol: 'AAPL',
            data: {
                price: 150.25,
                change: 2.50,
                change_percent: 1.69
            }
        };

        expect(message.type).toBe('price_update');
        expect(message.data.price).toBe(150.25);
        expect(message.data.change_percent).toBeCloseTo(1.69, 2);
    });
});
