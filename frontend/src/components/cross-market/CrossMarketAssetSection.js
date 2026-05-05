/**
 * Side-of-book (long / short) asset basket editor for the cross-market
 * backtest panel (layer 2 split).
 *
 * Pure presentational: renders the asset rows and lifts every mutation
 * back through three callbacks (onAdd / onUpdate / onRemove). The host
 * panel owns the assets state and the asset_class option list.
 */

import React from 'react';
import { Button, Card, Col, Input, InputNumber, Row, Select, Space } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';

import { ASSET_CLASS_OPTIONS } from '../../utils/crossMarketDefaults';

const CrossMarketAssetSection = ({
    title,
    side,
    sideAssets = [],
    onAdd,
    onUpdate,
    onRemove,
}) => (
    <Card
        title={title}
        extra={(
            <Button size="small" icon={<PlusOutlined />} onClick={() => onAdd?.(side)}>
                新增
            </Button>
        )}
        variant="borderless"
        className="workspace-panel cross-market-asset-card"
    >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
            {sideAssets.map((asset) => (
                <Row gutter={12} key={asset.key}>
                    <Col xs={24} md={8}>
                        <Input
                            value={asset.symbol}
                            placeholder="资产代码"
                            onChange={(event) => onUpdate?.(asset.key, 'symbol', event.target.value)}
                        />
                    </Col>
                    <Col xs={24} md={8}>
                        <Select
                            value={asset.asset_class}
                            options={ASSET_CLASS_OPTIONS}
                            style={{ width: '100%' }}
                            onChange={(value) => onUpdate?.(asset.key, 'asset_class', value)}
                        />
                    </Col>
                    <Col xs={18} md={6}>
                        <InputNumber
                            value={asset.weight}
                            min={0.01}
                            step={0.05}
                            placeholder="权重"
                            style={{ width: '100%' }}
                            onChange={(value) => onUpdate?.(asset.key, 'weight', value)}
                        />
                    </Col>
                    <Col xs={6} md={2}>
                        <Button
                            icon={<DeleteOutlined />}
                            danger
                            aria-label={`删除 ${asset.symbol || '空白资产'}`}
                            onClick={() => onRemove?.(asset.key)}
                        />
                    </Col>
                </Row>
            ))}
        </Space>
    </Card>
);

export default CrossMarketAssetSection;
