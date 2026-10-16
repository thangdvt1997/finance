import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsMeta from "./vite-plugin-ts-meta.js";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

// Dev: `npm run dev` proxy /api -> mock/real gateway (xem ../dev/mock_server.py)
const target = process.env.API_TARGET || "http://127.0.0.1:8590";
export default defineConfig({
  plugins: [react(), tailwindcss(), tsMeta()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version), __BUILD_TIME__: JSON.stringify(new Date().toISOString()) },
  server: { port: 5173, proxy: { "/api": { target, ws: true, changeOrigin: true } } },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) return 'charts';
          if (id.includes('lightweight-charts')) return 'lwc';
        },
      },
    },
  },
});
