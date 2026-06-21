import { describe, test, expect } from 'vitest';
import { THEME_VARS, RADII, FONT_SANS, antdTokenInputs, chartPalette } from '../design/tokens';

const REQUIRED_VARS = [
  '--color-app', '--color-surface', '--color-raised', '--color-inset',
  '--color-fg', '--color-muted', '--color-subtle', '--color-accent',
  '--color-up', '--color-down', '--color-warn', '--color-info',
  '--color-success', '--color-danger', '--color-hairline', '--color-on-accent',
];

describe('design tokens', () => {
  test('both themes define every required var', () => {
    for (const theme of ['dark', 'light']) {
      for (const key of REQUIRED_VARS) {
        expect(THEME_VARS[theme]).toHaveProperty(key);
        expect(THEME_VARS[theme][key]).toBeTruthy();
      }
    }
  });

  test('exposes scales and antd/chart inputs', () => {
    expect(RADII.lg).toBe('14px');
    expect(FONT_SANS).toMatch(/Inter/);
    expect(antdTokenInputs.dark.colorPrimary).toBe('#38bdf8');
    expect(antdTokenInputs.light.colorPrimary).toBe('#2563eb');
    expect(chartPalette.dark.up).toBe('#34d399');
  });

  test('antd + chart inputs are derived from THEME_VARS (no drift)', () => {
    for (const theme of ['dark', 'light']) {
      expect(antdTokenInputs[theme].colorPrimary).toBe(THEME_VARS[theme]['--color-accent']);
      expect(antdTokenInputs[theme].colorBorder).toBe(THEME_VARS[theme]['--color-hairline']);
      expect(antdTokenInputs[theme].colorBgContainer).toBe(THEME_VARS[theme]['--color-surface']);
      expect(chartPalette[theme].up).toBe(THEME_VARS[theme]['--color-up']);
      expect(chartPalette[theme].down).toBe(THEME_VARS[theme]['--color-down']);
      expect(chartPalette[theme].accent).toBe(THEME_VARS[theme]['--color-accent']);
      expect(chartPalette[theme].info).toBe(THEME_VARS[theme]['--color-info']);
      expect(chartPalette[theme].warn).toBe(THEME_VARS[theme]['--color-warn']);
    }
  });
});
