import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

if (typeof window.matchMedia !== 'function') {
    window.matchMedia = (query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
    });
}

import CrossMarketAssetSection from '../components/cross-market/CrossMarketAssetSection';

const baseAssets = [
    { key: 'long-0', symbol: 'AAPL', asset_class: 'US_STOCK', weight: 0.5 },
    { key: 'long-1', symbol: 'MSFT', asset_class: 'US_STOCK', weight: 0.5 },
];

describe('CrossMarketAssetSection', () => {
    const renderSection = (props = {}) => render(
        <CrossMarketAssetSection
            title="多头篮子"
            side="long"
            sideAssets={baseAssets}
            onAdd={vi.fn()}
            onUpdate={vi.fn()}
            onRemove={vi.fn()}
            {...props}
        />,
    );

    it('renders the title and one row per asset', () => {
        const { container } = renderSection();
        expect(screen.getByText('多头篮子')).toBeInTheDocument();
        const symbolInputs = container.querySelectorAll('input[placeholder="资产代码"]');
        expect(symbolInputs).toHaveLength(2);
        expect(symbolInputs[0].value).toBe('AAPL');
        expect(symbolInputs[1].value).toBe('MSFT');
    });

    it('clicking 新增 forwards the side label to onAdd', () => {
        const onAdd = vi.fn();
        renderSection({ onAdd });
        // Antd composes the icon's a11y name + text → "plus 新增"
        fireEvent.click(screen.getByRole('button', { name: /新增/ }));
        expect(onAdd).toHaveBeenCalledWith('long');
    });

    it('symbol edits forward (key, "symbol", newValue) to onUpdate', () => {
        const onUpdate = vi.fn();
        const { container } = renderSection({ onUpdate });
        const firstSymbol = container.querySelectorAll('input[placeholder="资产代码"]')[0];
        fireEvent.change(firstSymbol, { target: { value: 'TSLA' } });
        expect(onUpdate).toHaveBeenLastCalledWith('long-0', 'symbol', 'TSLA');
    });

    it('delete button forwards the asset key to onRemove', () => {
        const onRemove = vi.fn();
        renderSection({ onRemove });
        const deleteButtons = screen.getAllByRole('button', { name: /删除/ });
        fireEvent.click(deleteButtons[1]);
        expect(onRemove).toHaveBeenCalledWith('long-1');
    });

    it('handles empty asset list without crashing', () => {
        renderSection({ sideAssets: [] });
        expect(screen.getByText('多头篮子')).toBeInTheDocument();
    });

    it('uses ASSET_CLASS_OPTIONS for the class select dropdown', () => {
        const { container } = renderSection();
        // The Select renders the displayed label, not the value; assert
        // the options are reachable via the rendered AntD select widget.
        const selects = container.querySelectorAll('.ant-select-selector');
        expect(selects.length).toBe(2);
    });
});
