import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

if (typeof globalThis.jest === 'undefined') {
  globalThis.jest = vi;
}
