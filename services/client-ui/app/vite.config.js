import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Ứng dụng được phục vụ dưới /c/ (nginx của client-ui). API: /c/api/v1/* và /c/auth/*.
export default defineConfig({
  base: "/c/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/echarts") || id.includes("node_modules/zrender")) return "charts";
          if (id.includes("lightweight-charts")) return "lwc";
        },
      },
    },
  },
});
