import React from 'react';
import { Segmented } from 'antd';

/**
 * 通用时间范围选择器
 * @param {string} value - 当前选中的值
 * @param {function} onChange - 变更回调
 * @param {boolean} disabled - 是否禁用
 * @param {string} size - 尺寸 'large' | 'middle' | 'small'
 */
const TimeRangeSelector = ({ value, onChange, disabled = false, size = 'middle' }) => {
    const options = [
        { label: '5天', value: '5d' },
        { label: '1月', value: '1mo' },
        { label: '3月', value: '3mo' },
        { label: '6月', value: '6mo' },
        { label: '1年', value: '1y' },
        { label: '全部', value: 'max' }
    ];

    return (
        <Segmented
            options={options}
            value={value}
            onChange={onChange}
            disabled={disabled}
            size={size}
        />
    );
};

export default TimeRangeSelector;
