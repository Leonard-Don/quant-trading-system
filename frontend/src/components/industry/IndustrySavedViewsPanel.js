import React, { useMemo, useState } from 'react';
import { Card, Button, Empty, Input, Space, Tag } from 'antd';
import { SaveOutlined, DeleteOutlined, EyeOutlined, DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { buildSavedIndustryViewLabel } from './industryShared';

const IndustrySavedViewsPanel = ({
    draftName,
    onDraftNameChange,
    onSave,
    savedViews,
    onApply,
    onOverwrite,
    onRemove,
    onExport,
    onImportClick,
}) => {
    const [expanded, setExpanded] = useState(false);
    const latestSavedView = useMemo(() => savedViews[0] || null, [savedViews]);

    return (
    <Card
        size="small"
        data-testid="industry-saved-views-panel"
        style={{ marginBottom: 12 }}
        title="保存视图"
        extra={(
            <Space size={8}>
                <Input
                    data-testid="industry-saved-view-name-input"
                    value={draftName}
                    onChange={(event) => onDraftNameChange(event.target.value)}
                    placeholder="给当前视图起个名字…"
                    size="small"
                    style={{ width: 180 }}
                    aria-label="输入保存视图名称"
                    name="industry-saved-view-name"
                />
                <Button size="small" type="primary" icon={<SaveOutlined />} onClick={onSave} data-testid="industry-saved-view-save-button">
                    保存
                </Button>
                <Button size="small" icon={<DownloadOutlined />} onClick={onExport}>
                    导出
                </Button>
                <Button size="small" icon={<UploadOutlined />} onClick={onImportClick}>
                    导入
                </Button>
                {savedViews.length > 0 && (
                    <Button size="small" type="text" onClick={() => setExpanded((current) => !current)}>
                        {expanded ? '收起列表' : '展开列表'}
                    </Button>
                )}
            </Space>
        )}
    >
        {savedViews.length === 0 ? (
            <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="还没有保存过视图，可以把当前热力图、排行和提醒订阅配置存起来。"
            />
        ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 12,
                        flexWrap: 'wrap',
                        border: '1px solid color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
                        borderRadius: 10,
                        padding: '10px 12px',
                        background: 'rgba(255,255,255,0.42)',
                    }}
                >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                            已保存 {savedViews.length} 个视图
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-secondary)' }}>
                            {latestSavedView && (
                                <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>
                                    最新 {buildSavedIndustryViewLabel(latestSavedView)}
                                </Tag>
                            )}
                            <span>适合存下常看的热力图、排行和提醒组合</span>
                        </div>
                    </div>
                    {latestSavedView && !expanded && (
                        <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => onApply(latestSavedView.id)}>
                            应用最新
                        </Button>
                    )}
                </div>

                {expanded && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {savedViews.map((view) => (
                            <div
                                key={view.id}
                                data-testid="industry-saved-view-item"
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: 12,
                                    flexWrap: 'wrap',
                                    border: '1px solid color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
                                    borderRadius: 10,
                                    padding: '10px 12px',
                                    background: 'rgba(255,255,255,0.42)',
                                }}
                            >
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{buildSavedIndustryViewLabel(view)}</div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-secondary)' }}>
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                                            {view.state?.marketCapFilter === 'all' ? '全部市值来源' : `来源 ${view.state?.marketCapFilter}`}
                                        </Tag>
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                                            排序 {view.state?.sortBy || 'total_score'}
                                        </Tag>
                                        <span>更新于 {new Date(view.updatedAt || view.createdAt || Date.now()).toLocaleString('zh-CN', { hour12: false })}</span>
                                    </div>
                                </div>
                                <Space size={8} wrap>
                                    <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => onApply(view.id)}>
                                        应用
                                    </Button>
                                    <Button size="small" onClick={() => onOverwrite(view.id)}>
                                        覆盖
                                    </Button>
                                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onRemove(view.id)}>
                                        删除
                                    </Button>
                                </Space>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        )}
    </Card>
    );
};

export default IndustrySavedViewsPanel;
