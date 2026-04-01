import React, { memo, useMemo } from 'react';

const DEFAULT_WIDTH = 88;
const DEFAULT_HEIGHT = 28;
const DEFAULT_PADDING = 2;

const buildSparklinePath = (points, width, height, padding) => {
    if (!Array.isArray(points) || points.length < 2) {
        return null;
    }

    const numericPoints = points
        .map((point) => Number(point))
        .filter((point) => Number.isFinite(point));

    if (numericPoints.length < 2) {
        return null;
    }

    const min = Math.min(...numericPoints);
    const max = Math.max(...numericPoints);
    const range = Math.max(max - min, 1e-6);
    const innerWidth = Math.max(width - padding * 2, 1);
    const innerHeight = Math.max(height - padding * 2, 1);

    return numericPoints.map((point, index) => {
        const x = padding + (index / (numericPoints.length - 1)) * innerWidth;
        const y = padding + (1 - ((point - min) / range)) * innerHeight;
        return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    }).join(' ');
};

const getLastPointY = (points, height, padding) => {
    const numericPoints = points
        .map((point) => Number(point))
        .filter((point) => Number.isFinite(point));
    if (numericPoints.length < 2) return height / 2;
    const min = Math.min(...numericPoints);
    const max = Math.max(...numericPoints);
    const range = Math.max(max - min, 1e-6);
    const innerHeight = Math.max(height - padding * 2, 1);
    const lastValue = numericPoints[numericPoints.length - 1];
    return padding + (1 - ((lastValue - min) / range)) * innerHeight;
};

const MiniSparkline = ({
    points = [],
    width = DEFAULT_WIDTH,
    height = DEFAULT_HEIGHT,
    className,
    ariaLabel = '近期走势',
}) => {
    const numericPoints = useMemo(
        () => (Array.isArray(points) ? points.map((point) => Number(point)).filter((point) => Number.isFinite(point)) : []),
        [points]
    );

    const path = useMemo(
        () => buildSparklinePath(numericPoints, width, height, DEFAULT_PADDING),
        [numericPoints, width, height]
    );
    const lastPointY = useMemo(
        () => getLastPointY(numericPoints, height, DEFAULT_PADDING),
        [numericPoints, height]
    );

    if (!path) {
        return (
            <div
                className={className}
                data-testid="mini-sparkline-empty"
                style={{
                    width,
                    height,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--text-muted)',
                    fontSize: 11,
                }}
            >
                -
            </div>
        );
    }

    const isPositive = numericPoints[numericPoints.length - 1] >= numericPoints[0];
    const stroke = isPositive ? '#cf1322' : '#3f8600';
    const fill = isPositive
        ? 'rgba(207, 19, 34, 0.10)'
        : 'rgba(63, 134, 0, 0.10)';

    return (
        <svg
            className={className}
            data-testid="mini-sparkline"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={ariaLabel}
            style={{ display: 'block', overflow: 'visible' }}
        >
            <path
                d={path}
                fill="none"
                stroke={stroke}
                strokeWidth="1.8"
                strokeLinejoin="round"
                strokeLinecap="round"
            />
            <circle
                cx={width - DEFAULT_PADDING}
                cy={lastPointY}
                r="2.3"
                fill={stroke}
            />
            <rect
                x="0"
                y={height - 3}
                width={width}
                height="3"
                rx="1.5"
                fill={fill}
                opacity="0.4"
            />
        </svg>
    );
};

export default memo(MiniSparkline);
