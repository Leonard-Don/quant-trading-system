import { describe, test, expect, afterEach } from 'vitest';
import { applyTokens } from '../design/applyTokens';

afterEach(() => {
  document.documentElement.removeAttribute('style');
});

describe('applyTokens', () => {
  test('writes the dark theme vars onto :root', () => {
    applyTokens('dark');
    expect(document.documentElement.style.getPropertyValue('--color-surface').trim()).toBe('#131d31');
  });

  test('switching to light overrides the same var names', () => {
    applyTokens('dark');
    applyTokens('light');
    expect(document.documentElement.style.getPropertyValue('--color-surface').trim()).toBe('#ffffff');
  });
});
