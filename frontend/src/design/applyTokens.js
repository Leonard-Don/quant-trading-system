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
