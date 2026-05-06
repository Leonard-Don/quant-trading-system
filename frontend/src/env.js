// Centralised env reader.
//
// Vite exposes vars on `import.meta.env` and only exports keys that start
// with `VITE_`. CRA used `process.env` and required `REACT_APP_` prefixes.
// This module reads both so:
//   - production callers should set VITE_API_URL etc.
//   - existing tests that mutate process.env.REACT_APP_X keep working.
//
// Usage:
//   import { getEnv, IS_DEV } from "../env";
//   const apiUrl = getEnv("API_URL", "http://127.0.0.1:8000");

const viteEnv =
  typeof import.meta !== "undefined" && import.meta.env ? import.meta.env : {};
const procEnv =
  typeof process !== "undefined" && process.env ? process.env : {};

export function getEnv(name, fallback) {
  const viteKey = `VITE_${name}`;
  const reactKey = `REACT_APP_${name}`;
  // Order: live Vite var, live process var (test override), legacy keys, fallback.
  if (viteEnv[viteKey] !== undefined && viteEnv[viteKey] !== "") {
    return viteEnv[viteKey];
  }
  if (procEnv[viteKey] !== undefined && procEnv[viteKey] !== "") {
    return procEnv[viteKey];
  }
  if (procEnv[reactKey] !== undefined && procEnv[reactKey] !== "") {
    return procEnv[reactKey];
  }
  if (viteEnv[reactKey] !== undefined && viteEnv[reactKey] !== "") {
    return viteEnv[reactKey];
  }
  return fallback;
}

// Boolean dev mode. Vite sets `import.meta.env.DEV`; CRA used NODE_ENV.
export const IS_DEV =
  viteEnv.DEV !== undefined
    ? Boolean(viteEnv.DEV)
    : procEnv.NODE_ENV !== "production";
