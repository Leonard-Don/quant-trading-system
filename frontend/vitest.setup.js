// Setup for Vitest unit tests. Mirrors what react-scripts auto-loaded
// from setupTests.js, plus a `jest` → `vi` shim so the existing tests
// (which use jest.fn / jest.spyOn / jest.useFakeTimers / etc.) work
// unchanged under Vitest.

import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

const installMatchMedia = () => {
  const matchMedia = vi.fn().mockImplementation((query) => {
    const mediaQueryList = {
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    };
    return mediaQueryList;
  });

  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: matchMedia,
  });
  Object.defineProperty(globalThis, "matchMedia", {
    writable: true,
    configurable: true,
    value: matchMedia,
  });
};

const installGetComputedStyleShim = () => {
  const originalGetComputedStyle = window.getComputedStyle.bind(window);
  Object.defineProperty(window, "getComputedStyle", {
    writable: true,
    configurable: true,
    value: (element) => originalGetComputedStyle(element),
  });
};

installMatchMedia();
installGetComputedStyleShim();

// Ensure each Vitest case starts with a clean Testing Library DOM and stable
// browser shims. CRA/Jest setups performed cleanup automatically; without it,
// long CI shards can retain portals/forms or polluted matchMedia mocks from
// prior tests and queries start seeing duplicate elements or AntD breakpoint
// listeners receive malformed events.
afterEach(() => {
  cleanup();
  window.localStorage?.clear();
  window.sessionStorage?.clear();
  vi.useRealTimers();
  installMatchMedia();
  installGetComputedStyleShim();
});

// Shim: expose `jest` globally as an alias for vitest's `vi`. Tests that
// reference `jest.fn()`, `jest.mock()`, `jest.useFakeTimers()`, etc. then
// keep working without per-file rewrites.
//
// Limitation: `jest.mock()` is hoisted by jest's transformer; vitest
// hoists `vi.mock()`. Vitest also hoists calls assigned to `globalThis.jest`
// when you use `vi.mock` directly, but not always for the alias. If a
// test fails because the mock wasn't hoisted, replace that specific
// `jest.mock(...)` with `vi.mock(...)` in the file itself.
globalThis.jest = vi;
