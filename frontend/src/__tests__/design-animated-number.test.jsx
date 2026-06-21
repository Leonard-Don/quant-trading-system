import { describe, test, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AnimatedNumber from '../design/motion/AnimatedNumber';

beforeEach(() => {
  // Force reduced motion so the final value renders synchronously.
  window.matchMedia = (q) => ({
    matches: q.includes('reduce'),
    media: q, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null, dispatchEvent() { return false; },
  });
});

describe('AnimatedNumber', () => {
  test('renders the formatted final value immediately under reduced motion', () => {
    render(<AnimatedNumber value={1234} format={(n) => n.toLocaleString('en-US')} />);
    expect(screen.getByText('1,234')).toBeTruthy();
  });
});
