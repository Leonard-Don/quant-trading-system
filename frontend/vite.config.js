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
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing vendor libs out of the app entry
        // chunk into long-cacheable bundles. App code churns on every deploy;
        // react/antd/recharts do not — so a returning user re-downloads only
        // the small app chunk, and these load in parallel. Also clears the
        // single >500 kB entry chunk the default config produced.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          // Only carve out two clean, non-cyclic groups; everything else (recharts,
          // d3, lightweight-charts, misc) is left to Rollup's default algorithm so
          // its lazy route/shared chunks — and the isolated CandlestickChart chunk —
          // are preserved and no first-load regression is introduced.
          //
          // React ecosystem is a pure leaf (imports nothing app-side), so isolating
          // it can't create a cycle. The whole React runtime stays together because
          // antd/recharts import react-is at module-init; a foreign-chunk react-is
          // is what previously dead-locked the mount.
          if (/[\\/](react|react-dom|react-is|scheduler|prop-types|use-sync-external-store|object-assign)[\\/]/.test(id))
            return "react-vendor";
          // Keep ALL of antd's family (antd + @ant-design/* + rc-*) in one chunk so
          // antd<->icons / antd<->rc never split across chunks (that was a cycle).
          if (id.includes("antd") || id.includes("@ant-design") || /[\\/]rc-[a-z-]+[\\/]/.test(id))
            return "antd-vendor";
          return undefined;
        },
      },
    },
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
