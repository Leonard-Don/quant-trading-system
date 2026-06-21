import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Surface from '../design/components/Surface';

describe('Surface', () => {
  test('renders children and applies the raised variant + custom class', () => {
    render(<Surface variant="raised" className="extra">hello</Surface>);
    const el = screen.getByText('hello');
    expect(el.className).toContain('bg-raised');
    expect(el.className).toContain('extra');
  });

  test('defaults to flat variant', () => {
    render(<Surface>flat</Surface>);
    expect(screen.getByText('flat').className).toContain('bg-surface');
  });
});
