# Frontend Design-System Foundation (Plan 0a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-source design-token layer + Tailwind v4 + a set of reusable "Midnight Fintech" base components, motion primitives, and chart theming — a foundation later workspaces consume, with zero impact on the existing 56 Vitest specs.

**Architecture:** One JS module (`src/design/tokens.js`) is the single source of truth for design values. It feeds three consumers: (1) runtime CSS custom properties via `applyTokens.js`, (2) Tailwind v4 utilities (utility names map to those CSS vars in `src/design/tailwind.css`), (3) the Ant Design `ConfigProvider` theme via `antdTheme.js`. Base components are thin, token-driven wrappers (Tailwind classes) that coexist with antd; antd still renders heavy widgets (tables/forms/datepickers).

**Tech Stack:** React 18, Vite 5, Ant Design 5 (kept), Tailwind CSS v4 (`@tailwindcss/vite`, preflight off), framer-motion, @fontsource/inter, Vitest + React Testing Library, stylelint.

**Conventions for every commit in this plan:**
- Run from the `frontend/` directory unless stated otherwise.
- Every `git commit` must end with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (shown in each commit command below).
- Work happens on the existing branch `feat/frontend-design-system-foundation`.

---

## File Structure

Created in this plan (all under `frontend/`):

| Path | Responsibility |
|---|---|
| `src/design/tokens.js` | Single source: per-theme CSS-var maps, radii/spacing/font scales, antd token inputs, chart palette |
| `src/design/cn.js` | Tiny className joiner (no new dep) |
| `src/design/applyTokens.js` | Inject a theme's CSS vars onto `document.documentElement` |
| `src/design/antdTheme.js` | Build the antd `ConfigProvider` theme object from tokens |
| `src/design/tailwind.css` | Tailwind v4 entry (no preflight) + `@theme` mapping utilities → token vars |
| `src/design/chartTheme.js` | Chart palette/axis/grid derived from tokens (for recharts / lightweight-charts) |
| `src/design/components/Surface.jsx` | Base elevated surface (flat/raised/inset) |
| `src/design/components/Panel.jsx` | Surface + optional header (title/icon/actions) + body |
| `src/design/components/SectionHeader.jsx` | eyebrow + title + actions row |
| `src/design/components/StatusPill.jsx` | dot + label + tone |
| `src/design/components/StatCard.jsx` | micro label + tabular value + optional delta |
| `src/design/components/MetricGrid.jsx` | responsive KPI grid wrapper |
| `src/design/components/PageHero.jsx` | eyebrow + title + subtitle + KPI slot |
| `src/design/components/Toolbar.jsx` | filter/segmented control row container |
| `src/design/components/index.js` | barrel export |
| `src/design/motion/FadeIn.jsx` | framer-motion fade/slide-in wrapper (reduced-motion aware) |
| `src/design/motion/Stagger.jsx` | framer-motion staggered children container |
| `src/design/motion/AnimatedNumber.jsx` | rAF count-up (reduced-motion aware), no lib |
| `src/design/motion/index.js` | barrel export |
| `src/design/gallery/DesignGallery.jsx` | dev-only page rendering every primitive (manual visual check) |
| `.stylelintrc.json` | stylelint config: ban `!important` + enforce tokens in `src/design/**` |

Modified:

| Path | Change |
|---|---|
| `package.json` | add deps + `lint:css` script |
| `vite.config.js` | add `@tailwindcss/vite` plugin |
| `src/index.jsx` | import `@fontsource/inter` weights + `./design/tailwind.css` |
| `src/contexts/ThemeContext.jsx` | drive antd theme from `antdTheme.js` + call `applyTokens` |
| `src/App.jsx` | add hidden `__gallery` dev view route (dev-only) |

Out of scope for 0a (later plans): today rebuild + treemap fix (Plan 0b); deleting `realtimePanelStyles.js` (realtime workspace plan); screenshot visual-regression harness (separate follow-up — current e2e at `tests/e2e/` uses raw Playwright scripts, not `@playwright/test`).

---

## Task 1: Install dependencies and add the CSS lint script

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install runtime + dev dependencies**

Run (from `frontend/`):

```bash
npm install framer-motion @fontsource/inter
npm install -D tailwindcss @tailwindcss/vite stylelint stylelint-config-standard
```

- [ ] **Step 2: Add the `lint:css` script**

In `frontend/package.json`, inside `"scripts"`, add:

```json
"lint:css": "stylelint \"src/design/**/*.css\""
```

- [ ] **Step 3: Verify the dev server still boots**

Run: `npm run build`
Expected: build succeeds (Tailwind not wired yet; this only confirms the installs didn't break the build).

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "build(frontend): add tailwind v4, framer-motion, inter, stylelint" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Define the design tokens (single source of truth)

**Files:**
- Create: `frontend/src/design/tokens.js`
- Test: `frontend/src/__tests__/design-tokens.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-tokens.test.js`:

```js
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
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-tokens.test.js`
Expected: FAIL — cannot resolve `../design/tokens`.

- [ ] **Step 3: Create the tokens module**

Create `frontend/src/design/tokens.js`:

```js
// Single source of truth for design values. Consumed by:
//   - applyTokens.js  -> runtime CSS custom properties
//   - tailwind.css    -> utility names map to these var names
//   - antdTheme.js    -> Ant Design ConfigProvider theme
// Do NOT hardcode design colors anywhere else (stylelint guards this).

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

// Literal inputs for Ant Design ConfigProvider (antd needs concrete hex, not var()).
export const antdTokenInputs = {
  dark: {
    colorPrimary: '#38bdf8',
    colorBgLayout: '#0b1220',
    colorBgContainer: '#131d31',
    colorBgElevated: '#1b2740',
    colorText: '#f1f5f9',
    colorTextSecondary: '#94a3b8',
    colorBorder: 'rgba(148, 163, 184, 0.14)',
  },
  light: {
    colorPrimary: '#2563eb',
    colorBgLayout: '#f1f5f9',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#f8fafc',
    colorText: '#1e293b',
    colorTextSecondary: '#475569',
    colorBorder: 'rgba(100, 116, 139, 0.18)',
  },
};

export const chartPalette = {
  dark: { up: '#34d399', down: '#f87171', accent: '#38bdf8', grid: 'rgba(148,163,184,0.14)', axis: '#94a3b8' },
  light: { up: '#059669', down: '#dc2626', accent: '#2563eb', grid: 'rgba(100,116,139,0.18)', axis: '#475569' },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-tokens.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/tokens.js src/__tests__/design-tokens.test.js
git commit -m "feat(design): add single-source design tokens" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Wire Tailwind v4 into Vite (preflight off) and map utilities to tokens

**Files:**
- Modify: `frontend/vite.config.js:1-12`
- Create: `frontend/src/design/tailwind.css`
- Modify: `frontend/src/index.jsx:1-6`

- [ ] **Step 1: Add the Tailwind Vite plugin**

In `frontend/vite.config.js`, change the imports and `plugins` array. Current head:

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
```

becomes:

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
```

and the `plugins` line:

```js
  plugins: [react({ include: /\.(jsx|tsx|mdx)$|\/__tests__\/.*\.js$/ })],
```

becomes:

```js
  plugins: [react({ include: /\.(jsx|tsx|mdx)$|\/__tests__\/.*\.js$/ }), tailwindcss()],
```

- [ ] **Step 2: Create the Tailwind entry CSS (no preflight)**

Create `frontend/src/design/tailwind.css`:

```css
@layer theme, base, antd, utilities;

@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/utilities.css" layer(utilities);

@theme {
  --color-app: #0b1220;
  --color-surface: #131d31;
  --color-raised: #1b2740;
  --color-inset: #0f1828;
  --color-fg: #f1f5f9;
  --color-muted: #94a3b8;
  --color-subtle: #64748b;
  --color-accent: #38bdf8;
  --color-on-accent: #04121f;
  --color-up: #34d399;
  --color-down: #f87171;
  --color-warn: #fbbf24;
  --color-info: #818cf8;
  --color-success: #34d399;
  --color-danger: #f87171;
  --color-hairline: rgba(148, 163, 184, 0.14);
  --radius-md: 10px;
  --radius-lg: 14px;
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
}
```

Note: preflight is intentionally omitted (we import only `theme.css` + `utilities.css`, not `tailwindcss` whole), so Tailwind does not reset antd's base styles. The dark values here are static defaults that exist before JS runs; `applyTokens` (Task 5) overrides the same `--color-*` names per active theme.

- [ ] **Step 3: Import the entry CSS in the app**

In `frontend/src/index.jsx`, the current head is:

```js
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntdApp } from 'antd';
import './index.css';
import App from './App';
import { ThemeProvider } from './contexts/ThemeContext';
```

Add the Tailwind import immediately after `import './index.css';`:

```js
import './index.css';
import './design/tailwind.css';
```

- [ ] **Step 4: Verify Tailwind utilities compile**

Run: `npm run build`
Expected: build succeeds. Then run: `grep -rl "bg-surface\|text-fg" build/assets/*.css 2>/dev/null || echo "utilities tree-shaken (expected until used)"`
Expected: either a match or the tree-shaken message (Tailwind JIT only emits used classes; this just confirms no build error).

- [ ] **Step 5: Commit**

```bash
git add vite.config.js src/design/tailwind.css src/index.jsx
git commit -m "build(design): wire tailwind v4 (no preflight) mapped to tokens" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Self-host the Inter font

**Files:**
- Modify: `frontend/src/index.jsx:1-6`

- [ ] **Step 1: Import Inter weights**

In `frontend/src/index.jsx`, add these imports at the very top (before the React import), so the font is bundled and self-hosted:

```js
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
```

- [ ] **Step 2: Verify the font is bundled**

Run: `npm run build`
Expected: build succeeds and woff2 files for Inter appear under `build/assets/` (run `ls build/assets | grep -i inter` to confirm at least one `.woff2`).

- [ ] **Step 3: Commit**

```bash
git add src/index.jsx
git commit -m "build(design): self-host Inter via @fontsource" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: applyTokens — inject a theme's CSS vars at runtime

**Files:**
- Create: `frontend/src/design/applyTokens.js`
- Test: `frontend/src/__tests__/design-apply-tokens.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-apply-tokens.test.js`:

```js
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-apply-tokens.test.js`
Expected: FAIL — cannot resolve `../design/applyTokens`.

- [ ] **Step 3: Implement applyTokens**

Create `frontend/src/design/applyTokens.js`:

```js
import { THEME_VARS } from './tokens';

// Override the Tailwind @theme defaults at runtime for the active theme.
// Setting properties on documentElement.style wins over stylesheet :root,
// so every `var(--color-*)` (and thus every Tailwind utility) reflects the theme.
export function applyTokens(theme) {
  const vars = THEME_VARS[theme] || THEME_VARS.dark;
  const root = document.documentElement;
  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(name, value);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-apply-tokens.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/applyTokens.js src/__tests__/design-apply-tokens.test.js
git commit -m "feat(design): runtime CSS-var injection via applyTokens" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: antdTheme — build the ConfigProvider theme from tokens

**Files:**
- Create: `frontend/src/design/antdTheme.js`
- Test: `frontend/src/__tests__/design-antd-theme.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-antd-theme.test.js`:

```js
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-antd-theme.test.js`
Expected: FAIL — cannot resolve `../design/antdTheme`.

- [ ] **Step 3: Implement antdTheme**

Create `frontend/src/design/antdTheme.js`:

```js
import { theme as antdTheme } from 'antd';
import { antdTokenInputs, RADII } from './tokens';

export function buildAntdTheme(isDark) {
  const t = isDark ? antdTokenInputs.dark : antdTokenInputs.light;
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: t.colorPrimary,
      borderRadius: parseInt(RADII.md, 10),
      colorBgContainer: t.colorBgContainer,
      colorBgElevated: t.colorBgElevated,
      colorBgLayout: t.colorBgLayout,
      colorBorder: t.colorBorder,
      colorText: t.colorText,
      colorTextSecondary: t.colorTextSecondary,
    },
    components: {
      Layout: { headerBg: t.colorBgLayout, siderBg: t.colorBgLayout, bodyBg: t.colorBgLayout },
      Card: { colorBgContainer: t.colorBgContainer },
      Table: { colorBgContainer: 'transparent', headerBg: t.colorBgElevated },
      Input: { colorBgContainer: t.colorBgContainer },
      Select: { colorBgContainer: t.colorBgContainer },
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-antd-theme.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/antdTheme.js src/__tests__/design-antd-theme.test.js
git commit -m "feat(design): build antd ConfigProvider theme from tokens" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Refactor ThemeContext to drive from tokens (keep public API)

**Files:**
- Modify: `frontend/src/contexts/ThemeContext.jsx` (replace the two inline config objects + provider body)
- Test: `frontend/src/__tests__/design-theme-context.test.jsx`

The public API (`useTheme()` returning `{ isDarkMode, toggleTheme }`, localStorage key `theme-mode`, `data-theme` attribute, default dark) MUST NOT change — existing specs depend on it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-theme-context.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-theme-context.test.jsx`
Expected: FAIL — `--color-surface` is empty (current ThemeContext doesn't inject token vars).

- [ ] **Step 3: Refactor ThemeContext**

Replace the entire body of `frontend/src/contexts/ThemeContext.jsx` (delete the inline `darkThemeConfig`/`lightThemeConfig` objects) with:

```jsx
import { createContext, useContext, useState, useEffect } from 'react';
import { App as AntdApp, ConfigProvider } from 'antd';
import { buildAntdTheme } from '../design/antdTheme';
import { applyTokens } from '../design/applyTokens';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme-mode');
    return saved !== null ? saved === 'dark' : true;
  });

  useEffect(() => {
    const mode = isDarkMode ? 'dark' : 'light';
    localStorage.setItem('theme-mode', mode);
    document.documentElement.setAttribute('data-theme', mode);
    applyTokens(mode);
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
      <ConfigProvider theme={buildAntdTheme(isDarkMode)}>
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

export default ThemeProvider;
```

- [ ] **Step 4: Run new + full suite to verify nothing regressed**

Run: `npx vitest run src/__tests__/design-theme-context.test.jsx`
Expected: PASS.
Then run the full suite: `npm test`
Expected: all specs PASS (the public API is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/contexts/ThemeContext.jsx src/__tests__/design-theme-context.test.jsx
git commit -m "refactor(design): drive ThemeContext from tokens (API unchanged)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: cn helper + Surface component

**Files:**
- Create: `frontend/src/design/cn.js`
- Create: `frontend/src/design/components/Surface.jsx`
- Test: `frontend/src/__tests__/design-surface.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-surface.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-surface.test.jsx`
Expected: FAIL — cannot resolve modules.

- [ ] **Step 3: Implement cn + Surface**

Create `frontend/src/design/cn.js`:

```js
export function cn(...parts) {
  return parts.filter(Boolean).join(' ');
}
```

Create `frontend/src/design/components/Surface.jsx`:

```jsx
import { cn } from '../cn';

const VARIANTS = {
  flat: 'bg-surface',
  raised: 'bg-raised',
  inset: 'bg-inset',
};

export default function Surface({ variant = 'flat', className, children, ...rest }) {
  return (
    <div
      className={cn('rounded-[14px] border border-hairline', VARIANTS[variant] || VARIANTS.flat, className)}
      {...rest}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-surface.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/cn.js src/design/components/Surface.jsx src/__tests__/design-surface.test.jsx
git commit -m "feat(design): add cn helper + Surface primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Panel component

**Files:**
- Create: `frontend/src/design/components/Panel.jsx`
- Test: `frontend/src/__tests__/design-panel.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-panel.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Panel from '../design/components/Panel';

describe('Panel', () => {
  test('renders title, actions and body', () => {
    render(<Panel title="数据源健康" actions={<button>刷新</button>}>body content</Panel>);
    expect(screen.getByText('数据源健康')).toBeTruthy();
    expect(screen.getByRole('button', { name: '刷新' })).toBeTruthy();
    expect(screen.getByText('body content')).toBeTruthy();
  });

  test('omits the header when no title/actions', () => {
    render(<Panel>only body</Panel>);
    expect(screen.queryByTestId('panel-header')).toBeNull();
    expect(screen.getByText('only body')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-panel.test.jsx`
Expected: FAIL — cannot resolve `Panel`.

- [ ] **Step 3: Implement Panel**

Create `frontend/src/design/components/Panel.jsx`:

```jsx
import Surface from './Surface';
import { cn } from '../cn';

export default function Panel({ title, icon, actions, variant = 'flat', className, children }) {
  const hasHeader = title || actions;
  return (
    <Surface variant={variant} className={cn('p-4', className)}>
      {hasHeader && (
        <div data-testid="panel-header" className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon && <span className="text-accent" aria-hidden="true">{icon}</span>}
            {title && <span className="text-[14px] font-medium text-fg">{title}</span>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </Surface>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-panel.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/Panel.jsx src/__tests__/design-panel.test.jsx
git commit -m "feat(design): add Panel primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: SectionHeader component

**Files:**
- Create: `frontend/src/design/components/SectionHeader.jsx`
- Test: `frontend/src/__tests__/design-section-header.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-section-header.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-section-header.test.jsx`
Expected: FAIL — cannot resolve `SectionHeader`.

- [ ] **Step 3: Implement SectionHeader**

Create `frontend/src/design/components/SectionHeader.jsx`:

```jsx
import { cn } from '../cn';

export default function SectionHeader({ eyebrow, title, actions, className }) {
  return (
    <div className={cn('flex items-end justify-between gap-3', className)}>
      <div>
        {eyebrow && (
          <div className="text-[11px] uppercase tracking-[0.1em] text-subtle">{eyebrow}</div>
        )}
        {title && <div className="mt-1 text-[15px] font-medium text-fg">{title}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-section-header.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/SectionHeader.jsx src/__tests__/design-section-header.test.jsx
git commit -m "feat(design): add SectionHeader primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: StatusPill component

**Files:**
- Create: `frontend/src/design/components/StatusPill.jsx`
- Test: `frontend/src/__tests__/design-status-pill.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-status-pill.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-status-pill.test.jsx`
Expected: FAIL — cannot resolve `StatusPill`.

- [ ] **Step 3: Implement StatusPill**

Create `frontend/src/design/components/StatusPill.jsx`:

```jsx
import { cn } from '../cn';

const TONES = {
  success: 'text-success',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
  neutral: 'text-muted',
};

const DOT = {
  success: 'bg-success',
  warn: 'bg-warn',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-muted',
};

export default function StatusPill({ tone = 'neutral', className, children }) {
  const toneClass = TONES[tone] || TONES.neutral;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-[12px]',
        toneClass,
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', DOT[tone] || DOT.neutral)} aria-hidden="true" />
      {children}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-status-pill.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/StatusPill.jsx src/__tests__/design-status-pill.test.jsx
git commit -m "feat(design): add StatusPill primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 12: StatCard component

**Files:**
- Create: `frontend/src/design/components/StatCard.jsx`
- Test: `frontend/src/__tests__/design-stat-card.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-stat-card.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatCard from '../design/components/StatCard';

describe('StatCard', () => {
  test('renders label and value with tabular numerals', () => {
    render(<StatCard label="待处理" value="10" />);
    expect(screen.getByText('待处理')).toBeTruthy();
    const value = screen.getByText('10');
    expect(value.className).toContain('tabular-nums');
  });

  test('applies accent class when accent is set', () => {
    render(<StatCard label="回测快照" value="24" accent />);
    expect(screen.getByText('24').className).toContain('text-accent');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-stat-card.test.jsx`
Expected: FAIL — cannot resolve `StatCard`.

- [ ] **Step 3: Implement StatCard**

Create `frontend/src/design/components/StatCard.jsx`:

```jsx
import { cn } from '../cn';

export default function StatCard({ label, value, delta, accent = false, className }) {
  return (
    <div className={cn('rounded-[10px] border border-hairline bg-surface px-3 py-2.5', className)}>
      <div className="text-[11px] uppercase tracking-[0.1em] text-subtle">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className={cn('text-[22px] font-medium tabular-nums', accent ? 'text-accent' : 'text-fg')}>
          {value}
        </span>
        {delta != null && <span className="text-[12px] tabular-nums text-muted">{delta}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-stat-card.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/StatCard.jsx src/__tests__/design-stat-card.test.jsx
git commit -m "feat(design): add StatCard primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 13: MetricGrid component

**Files:**
- Create: `frontend/src/design/components/MetricGrid.jsx`
- Test: `frontend/src/__tests__/design-metric-grid.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-metric-grid.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MetricGrid from '../design/components/MetricGrid';

describe('MetricGrid', () => {
  test('renders children inside a grid container', () => {
    render(<MetricGrid><div>a</div><div>b</div></MetricGrid>);
    const grid = screen.getByTestId('metric-grid');
    expect(grid.className).toContain('grid');
    expect(grid.childElementCount).toBe(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-metric-grid.test.jsx`
Expected: FAIL — cannot resolve `MetricGrid`.

- [ ] **Step 3: Implement MetricGrid**

Create `frontend/src/design/components/MetricGrid.jsx`:

```jsx
import { cn } from '../cn';

export default function MetricGrid({ className, children }) {
  return (
    <div
      data-testid="metric-grid"
      className={cn('grid grid-cols-2 gap-2.5 sm:grid-cols-4', className)}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-metric-grid.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/MetricGrid.jsx src/__tests__/design-metric-grid.test.jsx
git commit -m "feat(design): add MetricGrid primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 14: PageHero component

**Files:**
- Create: `frontend/src/design/components/PageHero.jsx`
- Test: `frontend/src/__tests__/design-page-hero.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-page-hero.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PageHero from '../design/components/PageHero';

describe('PageHero', () => {
  test('renders eyebrow, title, subtitle and the metrics slot', () => {
    render(
      <PageHero
        eyebrow="RESEARCH · 研究工作台"
        title="策略回测工作台"
        subtitle="一体化回测流"
        metrics={<div data-testid="kpis">kpis</div>}
      />,
    );
    expect(screen.getByText('RESEARCH · 研究工作台')).toBeTruthy();
    expect(screen.getByRole('heading', { name: '策略回测工作台' })).toBeTruthy();
    expect(screen.getByText('一体化回测流')).toBeTruthy();
    expect(screen.getByTestId('kpis')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-page-hero.test.jsx`
Expected: FAIL — cannot resolve `PageHero`.

- [ ] **Step 3: Implement PageHero**

Create `frontend/src/design/components/PageHero.jsx`:

```jsx
import Surface from './Surface';
import { cn } from '../cn';

export default function PageHero({ eyebrow, title, subtitle, metrics, className }) {
  return (
    <Surface variant="raised" className={cn('p-5', className)}>
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 flex-1 basis-[280px]">
          {eyebrow && (
            <div className="mb-2 text-[11px] uppercase tracking-[0.1em] text-accent">{eyebrow}</div>
          )}
          {title && <h2 className="text-[23px] font-medium leading-tight text-fg">{title}</h2>}
          {subtitle && <p className="mt-2 max-w-[420px] text-[13px] leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {metrics && <div className="shrink-0">{metrics}</div>}
      </div>
    </Surface>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-page-hero.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/PageHero.jsx src/__tests__/design-page-hero.test.jsx
git commit -m "feat(design): add PageHero primitive" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 15: Toolbar component + barrel export

**Files:**
- Create: `frontend/src/design/components/Toolbar.jsx`
- Create: `frontend/src/design/components/index.js`
- Test: `frontend/src/__tests__/design-toolbar.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-toolbar.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Toolbar, Surface, Panel, PageHero, StatCard, MetricGrid, SectionHeader, StatusPill } from '../design/components';

describe('Toolbar + barrel', () => {
  test('Toolbar renders children in a flex row', () => {
    render(<Toolbar><button>前 30</button><button>全部</button></Toolbar>);
    const bar = screen.getByTestId('toolbar');
    expect(bar.className).toContain('flex');
    expect(bar.childElementCount).toBe(2);
  });

  test('barrel exports every primitive', () => {
    expect(Surface).toBeTruthy();
    expect(Panel).toBeTruthy();
    expect(PageHero).toBeTruthy();
    expect(StatCard).toBeTruthy();
    expect(MetricGrid).toBeTruthy();
    expect(SectionHeader).toBeTruthy();
    expect(StatusPill).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-toolbar.test.jsx`
Expected: FAIL — cannot resolve `Toolbar` / barrel.

- [ ] **Step 3: Implement Toolbar + barrel**

Create `frontend/src/design/components/Toolbar.jsx`:

```jsx
import { cn } from '../cn';

export default function Toolbar({ className, children }) {
  return (
    <div data-testid="toolbar" className={cn('flex flex-wrap items-center gap-2', className)}>
      {children}
    </div>
  );
}
```

Create `frontend/src/design/components/index.js`:

```js
export { default as Surface } from './Surface';
export { default as Panel } from './Panel';
export { default as SectionHeader } from './SectionHeader';
export { default as StatusPill } from './StatusPill';
export { default as StatCard } from './StatCard';
export { default as MetricGrid } from './MetricGrid';
export { default as PageHero } from './PageHero';
export { default as Toolbar } from './Toolbar';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-toolbar.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/components/Toolbar.jsx src/design/components/index.js src/__tests__/design-toolbar.test.jsx
git commit -m "feat(design): add Toolbar primitive + components barrel" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 16: Motion primitives — FadeIn + Stagger

**Files:**
- Create: `frontend/src/design/motion/FadeIn.jsx`
- Create: `frontend/src/design/motion/Stagger.jsx`
- Test: `frontend/src/__tests__/design-motion.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-motion.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FadeIn from '../design/motion/FadeIn';
import Stagger from '../design/motion/Stagger';

describe('motion primitives', () => {
  test('FadeIn renders its children', () => {
    render(<FadeIn><span>visible</span></FadeIn>);
    expect(screen.getByText('visible')).toBeTruthy();
  });

  test('Stagger renders all children', () => {
    render(<Stagger><div>a</div><div>b</div><div>c</div></Stagger>);
    expect(screen.getByText('a')).toBeTruthy();
    expect(screen.getByText('c')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-motion.test.jsx`
Expected: FAIL — cannot resolve motion modules.

- [ ] **Step 3: Implement FadeIn + Stagger**

Create `frontend/src/design/motion/FadeIn.jsx`:

```jsx
import { motion, useReducedMotion } from 'framer-motion';

export default function FadeIn({ y = 8, delay = 0, className, children }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut', delay }}
    >
      {children}
    </motion.div>
  );
}
```

Create `frontend/src/design/motion/Stagger.jsx`:

```jsx
import { motion, useReducedMotion } from 'framer-motion';
import { Children } from 'react';

export default function Stagger({ step = 0.06, className, children }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: step } } }}
    >
      {Children.map(children, (child, i) => (
        <motion.div
          key={i}
          variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
        >
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-motion.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/motion/FadeIn.jsx src/design/motion/Stagger.jsx src/__tests__/design-motion.test.jsx
git commit -m "feat(design): add FadeIn + Stagger motion primitives" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 17: AnimatedNumber primitive + motion barrel

**Files:**
- Create: `frontend/src/design/motion/AnimatedNumber.jsx`
- Create: `frontend/src/design/motion/index.js`
- Test: `frontend/src/__tests__/design-animated-number.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-animated-number.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-animated-number.test.jsx`
Expected: FAIL — cannot resolve `AnimatedNumber`.

- [ ] **Step 3: Implement AnimatedNumber + barrel**

Create `frontend/src/design/motion/AnimatedNumber.jsx`:

```jsx
import { useEffect, useRef, useState } from 'react';

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function AnimatedNumber({ value, duration = 600, format = (n) => String(Math.round(n)), className }) {
  const [display, setDisplay] = useState(() => (prefersReduced() ? value : 0));
  const rafRef = useRef(0);

  useEffect(() => {
    if (prefersReduced()) {
      setDisplay(value);
      return undefined;
    }
    const from = 0;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, duration]);

  return <span className={className}>{format(display)}</span>;
}
```

Create `frontend/src/design/motion/index.js`:

```js
export { default as FadeIn } from './FadeIn';
export { default as Stagger } from './Stagger';
export { default as AnimatedNumber } from './AnimatedNumber';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-animated-number.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/motion/AnimatedNumber.jsx src/design/motion/index.js src/__tests__/design-animated-number.test.jsx
git commit -m "feat(design): add AnimatedNumber + motion barrel" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 18: chartTheme — palette derived from tokens

**Files:**
- Create: `frontend/src/design/chartTheme.js`
- Test: `frontend/src/__tests__/design-chart-theme.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-chart-theme.test.js`:

```js
import { describe, test, expect } from 'vitest';
import { getChartTheme } from '../design/chartTheme';

describe('getChartTheme', () => {
  test('dark theme exposes up/down/accent/grid/axis + a series array', () => {
    const t = getChartTheme(true);
    expect(t.up).toBe('#34d399');
    expect(t.down).toBe('#f87171');
    expect(t.accent).toBe('#38bdf8');
    expect(Array.isArray(t.series)).toBe(true);
    expect(t.series.length).toBeGreaterThanOrEqual(3);
  });

  test('light theme swaps to the light palette', () => {
    expect(getChartTheme(false).up).toBe('#059669');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-chart-theme.test.js`
Expected: FAIL — cannot resolve `chartTheme`.

- [ ] **Step 3: Implement chartTheme**

Create `frontend/src/design/chartTheme.js`:

```js
import { chartPalette } from './tokens';

// Single place charts read their colors from, so recharts / lightweight-charts
// stop hardcoding #00b578 / #ff3030 and follow the active theme instead.
export function getChartTheme(isDark) {
  const p = isDark ? chartPalette.dark : chartPalette.light;
  return {
    up: p.up,
    down: p.down,
    accent: p.accent,
    grid: p.grid,
    axis: p.axis,
    series: [p.accent, '#818cf8', p.up, '#fbbf24', p.down],
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-chart-theme.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/design/chartTheme.js src/__tests__/design-chart-theme.test.js
git commit -m "feat(design): add token-driven chartTheme" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 19: DesignGallery + hidden dev route

**Files:**
- Create: `frontend/src/design/gallery/DesignGallery.jsx`
- Modify: `frontend/src/App.jsx` (add a hidden `__gallery` view, dev-only)
- Test: `frontend/src/__tests__/design-gallery.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/design-gallery.test.jsx`:

```jsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/design-gallery.test.jsx`
Expected: FAIL — cannot resolve `DesignGallery`.

- [ ] **Step 3: Implement DesignGallery**

Create `frontend/src/design/gallery/DesignGallery.jsx`:

```jsx
import { PageHero, MetricGrid, StatCard, Panel, StatusPill, SectionHeader, Toolbar } from '../components';
import { FadeIn, AnimatedNumber } from '../motion';

export default function DesignGallery() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHero
        eyebrow="RESEARCH · 研究工作台"
        title="策略回测工作台"
        subtitle="从策略配置、执行到结果研判的一体化回测流。"
        metrics={
          <MetricGrid className="w-[280px]">
            <StatCard label="待处理" value={<AnimatedNumber value={10} />} />
            <StatCard label="回测快照" value={<AnimatedNumber value={24} />} accent />
            <StatCard label="实时记录" value="8" />
            <StatCard label="行业观察" value="10" />
          </MetricGrid>
        }
      />

      <Panel title="数据源健康" actions={<StatusPill tone="info">ths_primary</StatusPill>}>
        <Toolbar>
          <StatusPill tone="success">同花顺 THS · 已连接</StatusPill>
          <StatusPill tone="success">新浪财经 SINA · 已连接</StatusPill>
          <StatusPill tone="warn">AKShare · 被拦截</StatusPill>
        </Toolbar>
      </Panel>

      <FadeIn>
        <Panel>
          <SectionHeader eyebrow="SECTION" title="行业扫描与轮动" actions={<StatusPill tone="neutral">市值加权</StatusPill>} />
        </Panel>
      </FadeIn>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/design-gallery.test.jsx`
Expected: PASS.

- [ ] **Step 5: Add the hidden dev route in App.jsx**

In `frontend/src/App.jsx`, add the lazy import alongside the other `lazyWithRetry` view imports (after line 48, `const LowVolatilityView = ...`):

```js
const DesignGallery = lazyWithRetry(() => import('./design/gallery/DesignGallery'));
```

Then in `renderContent()`'s `switch (currentView)` (around line 294), add this case before `case 'backtest':`:

```jsx
      case '__gallery':
        return import.meta.env.DEV
          ? <Suspense fallback={<LazyLoadFallback />}><DesignGallery /></Suspense>
          : null;
```

This is reachable only in dev via `http://localhost:3000/?view=__gallery` and renders `null` in production. It is intentionally not added to `menuItems` or `PUBLIC_VIEWS`.

- [ ] **Step 6: Verify the route renders + full suite still green**

Run: `npm run build` (confirms the lazy import + App change compile).
Run: `npm test` (confirms the full suite, including `app-routing.test.js`, still passes — the new case does not alter `normalizePublicView` or the public view set).
Expected: build succeeds; all specs PASS.

- [ ] **Step 7: Commit**

```bash
git add src/design/gallery/DesignGallery.jsx src/App.jsx src/__tests__/design-gallery.test.jsx
git commit -m "feat(design): add DesignGallery + hidden dev route" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 20: stylelint guard (ban !important, enforce tokens in the design layer)

**Files:**
- Create: `frontend/.stylelintrc.json`

- [ ] **Step 1: Create the stylelint config**

Create `frontend/.stylelintrc.json`:

```json
{
  "extends": "stylelint-config-standard",
  "rules": {
    "declaration-no-important": true,
    "custom-property-pattern": null,
    "at-rule-no-unknown": [true, { "ignoreAtRules": ["theme", "layer", "tailwind", "apply", "variants", "responsive", "screen"] }]
  },
  "ignoreFiles": ["build/**", "node_modules/**"]
}
```

- [ ] **Step 2: Run the linter on the design CSS**

Run: `npm run lint:css`
Expected: PASS (0 problems) — `src/design/tailwind.css` uses no `!important` and the Tailwind at-rules are whitelisted.

- [ ] **Step 3: Verify it actually catches `!important` (sanity check, then revert)**

Run:
```bash
printf '.x{color:red !important;}\n' >> src/design/tailwind.css
npm run lint:css || echo "STYLELINT CORRECTLY FAILED"
git checkout -- src/design/tailwind.css
```
Expected: prints `STYLELINT CORRECTLY FAILED` and the file is restored.

- [ ] **Step 4: Commit**

```bash
git add .stylelintrc.json
git commit -m "build(design): add stylelint guard banning !important in design CSS" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 21: Final verification of the whole foundation

**Files:** none (verification only)

- [ ] **Step 1: Run the full Vitest suite**

Run: `npm test`
Expected: all specs PASS (the original 56 + the new design-layer specs).

- [ ] **Step 2: Run lint + build**

Run: `npm run lint && npm run lint:css && npm run build`
Expected: ESLint clean, stylelint clean, production build succeeds.

- [ ] **Step 3: Manual visual check of the gallery (dev)**

Run: `npm run dev`, open `http://localhost:3000/?view=__gallery`, toggle the theme via the header sun/moon button.
Expected: the gallery renders the hero, KPI cards, status pills, and section header in the Midnight Fintech style; toggling theme flips dark/light correctly with no flash of unstyled colors.

- [ ] **Step 4: No commit needed** (verification only). If any step failed, fix it under the relevant task before proceeding to Plan 0b.

---

## Self-Review (completed by plan author)

- **Spec coverage:** tokens single-source (Tasks 2,5,6,7) ✓; Tailwind v4 no-preflight (Task 3) ✓; Inter self-host (Task 4) ✓; base components Surface/Panel/PageHero/MetricGrid/StatCard/SectionHeader/StatusPill/Toolbar (Tasks 8–15) ✓; motion primitives (Tasks 16–17) ✓; chart theme (Task 18) ✓; quality gates = per-primitive tests + stylelint + gallery (Tasks 8–20) ✓; "keep 56 tests green" enforced in Tasks 7 & 19 & 21 ✓. Treemap fix + today rebuild are explicitly deferred to Plan 0b (spec phasing). Screenshot visual-regression deferred (noted; e2e harness is script-based).
- **Placeholder scan:** none — every code/step block is concrete.
- **Type/name consistency:** token var names (`--color-app/surface/raised/inset/fg/muted/subtle/accent/up/down/warn/info/success/danger/hairline/on-accent`) are identical across `tokens.js`, `tailwind.css`, `applyTokens.js`, and the Tailwind utilities used in components (`bg-surface`, `text-fg`, `border-hairline`, `text-accent`, `bg-success`, etc.). `buildAntdTheme(isDark)`, `applyTokens(theme)`, `getChartTheme(isDark)`, `cn(...)` signatures are used consistently. Barrels export exactly the component/motion names imported by `DesignGallery`.
