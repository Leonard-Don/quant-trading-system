import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SectionHeader from '../design/components/SectionHeader';

describe('SectionHeader', () => {
  test('renders eyebrow, title and actions', () => {
    render(<SectionHeader eyebrow="RESEARCH" title="行业扫描与轮动" actions={<a>更多</a>} />);
    expect(screen.getByText('RESEARCH')).toBeTruthy();
    expect(screen.getByText('行业扫描与轮动')).toBeTruthy();
    expect(screen.getByText('更多')).toBeTruthy();
  });
});
