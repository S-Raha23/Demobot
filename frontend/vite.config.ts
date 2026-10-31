import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend API: :8000 for `make dev`; set DEMOBOT_API to point elsewhere.
const API = process.env.DEMOBOT_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.PORT ?? 5173),
    proxy: {
      "/api": { target: API, changeOrigin: true },
      "/assets/franka_panda": { target: API, changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      "/api": { target: API, changeOrigin: true },
      "/assets/franka_panda": { target: API, changeOrigin: true },
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: { three: ["three", "urdf-loader"] },
      },
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
