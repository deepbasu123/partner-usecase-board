import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxies the admin API to the local FastAPI. In prod the SPA is served by
// FastAPI itself, so relative /api calls work.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://localhost:8001", changeOrigin: true },
      "/healthz": { target: "http://localhost:8001", changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
