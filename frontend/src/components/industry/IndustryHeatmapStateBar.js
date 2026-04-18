import React from 'react';
import { Button, Tag } from 'antd';
import { activateOnEnterOrSpace } from './industryShared';

const IndustryHeatmapStateBar = ({
    visible,
    activeHeatmapStateTags,
    onFocusHeatmapControl,
    onClearHeatmapStateTag,
    onResetHeatmapViewState,
    panelSurface,
    panelBorder,
    panelShadow,
    panelMuted,
}) => {
    if (!visible) {
        return null;
    }

    return (
        <div
            style={{
                marginBottom: 12,
                padding: '10px 14px',
                borderRadius: 10,
                background: panelSurface,
                border: panelBorder,
                boxShadow: panelShadow,
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, color: panelMuted, fontWeight: 700, letterSpacing: '0.04em' }}>当前视图</span>
                    {activeHeatmapStateTags.map((item) => (
                        <Tag
                            key={item.key}
                            color="processing"
                            closable
                            className={`heatmap-state-tag-${item.key} industry-state-tag`}
                            onClick={() => onFocusHeatmapControl(item.key)}
                            onClose={(event) => {
                                event.preventDefault();
                                onClearHeatmapStateTag(item.key);
                            }}
                            role="button"
                            tabIndex={0}
                            aria-label={`当前热力图筛选 ${item.label} ${item.value}`}
                            onKeyDown={(event) => {
                                if (event.key === 'Backspace' || event.key === 'Delete') {
                                    event.preventDefault();
                                    onClearHeatmapStateTag(item.key);
                                    return;
                                }
                                activateOnEnterOrSpace(event, () => onFocusHeatmapControl(item.key));
                            }}
                            style={{ margin: 0, fontSize: 12, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                        >
                            {item.label}: {item.value}
                        </Tag>
                    ))}
                </div>
                <Button className="industry-reset-button" size="small" type="text" onClick={onResetHeatmapViewState}>
                    清除全部
                </Button>
            </div>
        </div>
    );
};

export default IndustryHeatmapStateBar;
