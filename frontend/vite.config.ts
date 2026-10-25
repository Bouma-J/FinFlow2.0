import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Dev local : API Django sur :8000.
      // Docker / autre cible : VITE_API_TARGET=http://localhost:8080
      ...Object.fromEntries(
        ["/api", "/media", "/django-admin", "/static"].map((path) => [
          path,
          {
            target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
            changeOrigin: true,
          },
        ]),
      ),
    },
  },
});
