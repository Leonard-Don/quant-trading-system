import { describe, test, expect, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ThemeProvider, useTheme } from '../contexts/ThemeContext';

function Probe() {
  const { isDarkMode, toggleTheme } = useTheme();
  return <button onClick={toggleTheme}>{isDarkMode ? 'dark' : 'light'}</button>;
}

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('style');
  document.documentElement.removeAttribute('data-theme');
});

describe('ThemeContext (token-driven)', () => {
  test('defaults to dark and injects token vars', () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByRole('button').textContent).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('--color-surface').trim()).toBe('#131d31');
  });

  test('toggle flips to light and re-injects vars', () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);
    act(() => { screen.getByRole('button').click(); });
    expect(screen.getByRole('button').textContent).toBe('light');
    expect(document.documentElement.style.getPropertyValue('--color-surface').trim()).toBe('#ffffff');
  });
});
