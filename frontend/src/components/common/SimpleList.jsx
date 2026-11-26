import React from 'react';

const resolveColumns = (grid) => grid.column || grid.md || grid.sm || grid.xs || 1;

const SimpleList = ({ dataSource = [], renderItem, grid, size, locale, style, className }) => {
    if (!dataSource.length) {
        return (
            <div className={className} style={{ padding: '16px 0', textAlign: 'center', color: 'var(--text-secondary)', ...style }}>
                {locale?.emptyText ?? '暂无数据'}
            </div>
        );
    }

    if (grid) {
        const responsive = !grid.column && (grid.xs || grid.sm || grid.md);
        return (
            <div
                className={className}
                style={{
                    display: 'grid',
                    gap: grid.gutter ?? 0,
                    gridTemplateColumns: responsive
                        ? 'repeat(auto-fit, minmax(220px, 1fr))'
                        : `repeat(${resolveColumns(grid)}, minmax(0, 1fr))`,
                    ...style,
                }}
            >
                {dataSource.map((item, index) => (
                    <React.Fragment key={item?.key ?? index}>{renderItem(item, index)}</React.Fragment>
                ))}
            </div>
        );
    }

    return (
        <div className={className} style={style} data-size={size}>
            {dataSource.map((item, index) => (
                <div
                    key={item?.key ?? index}
                    className="simple-list-item"
                    style={{
                        padding: size === 'small' ? '8px 0' : '12px 0',
                        borderBottom: index < dataSource.length - 1 ? '1px solid var(--border-color)' : 'none',
                    }}
                >
                    {renderItem(item, index)}
                </div>
            ))}
        </div>
    );
};

const Item = ({ children, style }) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', ...style }}>
        {children}
    </div>
);

const Meta = ({ avatar, title, description }) => (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flex: 1, minWidth: 0 }}>
        {avatar ? <div style={{ flex: 'none' }}>{avatar}</div> : null}
        <div style={{ flex: 1, minWidth: 0 }}>
            {title ? <div style={{ fontWeight: 600, marginBottom: description ? 4 : 0, color: 'var(--text-primary)' }}>{title}</div> : null}
            {description ? <div style={{ color: 'var(--text-secondary)' }}>{description}</div> : null}
        </div>
    </div>
);

Item.Meta = Meta;
SimpleList.Item = Item;

export default SimpleList;
