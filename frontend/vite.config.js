import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite config for the quant-trading-system frontend.
// Replaces react-scripts (CRA, deprecated). Build output stays at
// `build/` so existing CI / start_system.sh references keep working.
export default defineConfig({
  // plugin-react: app code lives in .jsx; tests under src/__tests__ keep
  // a .js extension by team convention but contain JSX (e.g. vi.mock
  // factories returning <div>…</div>). Include those in the JSX transform.
  plugins: [react({ include: /\.(jsx|tsx|mdx)$|\/__tests__\/.*\.js$/ })],
  esbuild: {
    // Match plugin-react's include so esbuild's transform applies the JSX
    // loader to the same set. App-level .js files no longer need this.
    loader: "jsx",
    include: /\.(jsx|tsx)$|\/__tests__\/.*\.js$/,
    exclude: [],
  },
  // Local dev port matches what start_system.sh / e2e expect.
  server: {
    port: 3000,
    strictPort: true,
    // CRA's `proxy` field in package.json is replaced by explicit proxy here.
    // Both /api/* HTTP and /ws/* WebSocket upgrade through the same backend.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  build: {
    // Keep CRA's default output dir so deployment / Nginx configs need no change.
    outDir: "build",
    sourcemap: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    extensions: [".mjs", ".js", ".jsx", ".ts", ".tsx", ".json"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.js"],
    include: ["src/__tests__/**/*.test.{js,jsx}"],
    css: false,
  },
});
