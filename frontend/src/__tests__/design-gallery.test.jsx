import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DesignGallery from '../design/gallery/DesignGallery';

describe('DesignGallery', () => {
  test('renders representative primitives', () => {
    render(<DesignGallery />);
    expect(screen.getByRole('heading', { name: '策略回测工作台' })).toBeTruthy();
    expect(screen.getByText('已连接')).toBeTruthy();
    expect(screen.getByText('待处理')).toBeTruthy();
  });
});
