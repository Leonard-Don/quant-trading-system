// Setup for Vitest unit tests. Mirrors what react-scripts auto-loaded
// from setupTests.js, plus a `jest` → `vi` shim so the existing tests
// (which use jest.fn / jest.spyOn / jest.useFakeTimers / etc.) work
// unchanged under Vitest.

import "@testing-library/jest-dom";
import { vi } from "vitest";

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
