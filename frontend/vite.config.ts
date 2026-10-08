import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development, /api requests are proxied to the FastAPI backend.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: env.VITE_PROXY_TARGET || "http://localhost:8000", changeOrigin: true },
      },
    },
  };
});
