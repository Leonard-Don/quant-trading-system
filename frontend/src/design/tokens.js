// Single source of truth for design values. Consumed by:
//   - applyTokens.js  -> runtime CSS custom properties
//   - tailwind.css    -> utility names map to these var names
//   - antdTheme.js    -> Ant Design ConfigProvider theme
// THEME_VARS is the canonical color source; antdTokenInputs and chartPalette are
// DERIVED from it so a color edit can never drift across consumers. Do NOT hardcode
// design colors anywhere else (stylelint guards CSS).

export const THEME_VARS = {
  dark: {
    '--color-app': '#0b1220',
    '--color-surface': '#131d31',
    '--color-raised': '#1b2740',
    '--color-inset': '#0f1828',
    '--color-fg': '#f1f5f9',
    '--color-muted': '#94a3b8',
    '--color-subtle': '#64748b',
    '--color-accent': '#38bdf8',
    '--color-up': '#34d399',
    '--color-down': '#f87171',
    '--color-warn': '#fbbf24',
    '--color-info': '#818cf8',
    '--color-success': '#34d399',
    '--color-danger': '#f87171',
    '--color-hairline': 'rgba(148, 163, 184, 0.14)',
    '--color-on-accent': '#04121f',
  },
  light: {
    '--color-app': '#f1f5f9',
    '--color-surface': '#ffffff',
    '--color-raised': '#f8fafc',
    '--color-inset': '#eef2f7',
    '--color-fg': '#1e293b',
    '--color-muted': '#475569',
    '--color-subtle': '#64748b',
    '--color-accent': '#2563eb',
    '--color-up': '#059669',
    '--color-down': '#dc2626',
    '--color-warn': '#d97706',
    '--color-info': '#4f46e5',
    '--color-success': '#059669',
    '--color-danger': '#dc2626',
    '--color-hairline': 'rgba(100, 116, 139, 0.18)',
    '--color-on-accent': '#ffffff',
  },
};

export const RADII = { sm: '6px', md: '10px', lg: '14px', pill: '999px' };

export const FONT_SANS =
  "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

const deriveAntd = (theme) => {
  const v = THEME_VARS[theme];
  return {
    colorPrimary: v['--color-accent'],
    colorBgLayout: v['--color-app'],
    colorBgContainer: v['--color-surface'],
    colorBgElevated: v['--color-raised'],
    colorText: v['--color-fg'],
    colorTextSecondary: v['--color-muted'],
    colorBorder: v['--color-hairline'],
  };
};

export const antdTokenInputs = { dark: deriveAntd('dark'), light: deriveAntd('light') };

const deriveChart = (theme) => {
  const v = THEME_VARS[theme];
  return {
    up: v['--color-up'],
    down: v['--color-down'],
    accent: v['--color-accent'],
    info: v['--color-info'],
    warn: v['--color-warn'],
    grid: v['--color-hairline'],
    axis: v['--color-muted'],
  };
};

export const chartPalette = { dark: deriveChart('dark'), light: deriveChart('light') };
