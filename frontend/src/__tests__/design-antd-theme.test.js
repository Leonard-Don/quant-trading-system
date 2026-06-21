import { describe, test, expect } from 'vitest';
import { theme as antdTheme } from 'antd';
import { buildAntdTheme } from '../design/antdTheme';

describe('buildAntdTheme', () => {
  test('dark config uses dark algorithm + token primary', () => {
    const cfg = buildAntdTheme(true);
    expect(cfg.algorithm).toBe(antdTheme.darkAlgorithm);
    expect(cfg.token.colorPrimary).toBe('#38bdf8');
    expect(cfg.token.borderRadius).toBe(10);
  });

  test('light config uses default algorithm + token primary', () => {
    const cfg = buildAntdTheme(false);
    expect(cfg.algorithm).toBe(antdTheme.defaultAlgorithm);
    expect(cfg.token.colorPrimary).toBe('#2563eb');
  });
});
