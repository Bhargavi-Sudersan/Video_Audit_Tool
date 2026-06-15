import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the frontend runs on :5173 and proxies /api to the
// FastAPI backend on :8000. In production both can sit behind one reverse
// proxy (see docker-compose.yml / nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
