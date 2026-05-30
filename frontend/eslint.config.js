// ESLint 9 flat config for the React + Vite frontend.
//
// First static-analysis layer for this codebase. Posture mirrors the Python
// side's ruff-baseline stance: genuine *bug* classes are hard errors, while
// pre-existing style/debt (unused vars, exhaustive-deps) surfaces as warnings to
// chip away at rather than a wall that blocks every commit on day one.
import js from '@eslint/js';
import globals from 'globals';
import reactPlugin from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  { ignores: ['build/**', 'coverage/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      // `process` is read defensively in src/env.js as an import.meta.env fallback.
      globals: { ...globals.browser, ...globals.es2021, process: 'readonly' },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react: reactPlugin, 'react-hooks': reactHooks },
    settings: { react: { version: 'detect' } },
    rules: {
      // Real bugs — hard errors.
      'react-hooks/rules-of-hooks': 'error',
      // High value but noisy on the current tree → warn (the main thing this
      // codebase lacked any guard for: ~80 useEffects checked only by review).
      'react-hooks/exhaustive-deps': 'warn',
      // Treat JSX-referenced identifiers as used so the React 17+ automatic
      // runtime doesn't trigger false no-unused-vars / no-undef.
      'react/jsx-uses-vars': 'error',
      'react/jsx-uses-react': 'off',
      'react/react-in-jsx-scope': 'off',
      // Pre-existing debt — surfaced as warnings to burn down, not a hard gate
      // (mirrors the Python ruff-baseline stance). Tighten to 'error' once clean.
      'no-unused-vars': 'warn',
      'no-empty': 'warn',
      'no-irregular-whitespace': 'warn',
      'no-unsafe-finally': 'warn',
    },
  },
  {
    // Vitest injects its API as globals (vi/describe/it/expect/...).
    files: ['src/**/*.test.{js,jsx}', 'src/**/__tests__/**/*.{js,jsx}'],
    languageOptions: {
      globals: {
        ...globals.node,
        vi: 'readonly',
        vitest: 'readonly',
        jest: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
  },
];
