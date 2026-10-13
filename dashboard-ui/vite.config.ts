import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: { outDir: "../hub/static/dashboard", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:5001" } },
});
