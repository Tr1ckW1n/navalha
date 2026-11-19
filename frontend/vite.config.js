import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // em dev, /api vai para o FastAPI; em produção a própria API serve o site (mesma URL)
    proxy: { "/api": { target: "http://localhost:8000" } },
  },
});
