import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendPort = parseInt(process.env.BACKEND_PORT || "9000");
const frontendPort = parseInt(process.env.FRONTEND_PORT || "5173");

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    fs: {
      allow: [".."],
    },
    allowedHosts: true,
    proxy: {
      "/api": { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true, ws: true },
      "/health": { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
    },
  },
});
