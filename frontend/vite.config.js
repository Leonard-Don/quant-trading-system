import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite config for the quant-trading-system frontend.
// Replaces react-scripts (CRA, deprecated). Build output stays at
// `build/` so existing CI / start_system.sh references keep working.
export default defineConfig({
  // CRA-era code lives in .js files but contains JSX. Tell plugin-react
  // (and esbuild downstream) to apply the JSX transform to .js too.
  plugins: [react({ include: /\.(js|jsx|ts|tsx|mdx)$/ })],
  esbuild: {
    loader: "jsx",
    include: /src\/.*\.(js|jsx|ts|tsx)$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: { ".js": "jsx" },
    },
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
