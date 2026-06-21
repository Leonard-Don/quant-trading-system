import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusPill from '../design/components/StatusPill';

describe('StatusPill', () => {
  test('renders label and applies the success tone color', () => {
    render(<StatusPill tone="success">已连接</StatusPill>);
    const el = screen.getByText('已连接').closest('span');
    expect(el.className).toContain('text-success');
  });

  test('falls back to neutral tone', () => {
    render(<StatusPill>未知</StatusPill>);
    const el = screen.getByText('未知').closest('span');
    expect(el.className).toContain('text-muted');
  });
});
