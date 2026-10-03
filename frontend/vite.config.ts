import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// In production app.py serves the built bundle from frontend/dist at "/" (see
// KESTREL_UI in app.py) — NOT from /static/app, which was never true. The dev
// server proxies everything API-shaped (and the legacy pages the product still
// links to) to the backend, so both live on one origin either way.
const API = process.env.KESTREL_API || "http://localhost:8000"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // 5174 is the port the local stack and the docs use (--strictPort there);
    // 5173 is Vite's default. detect_frontend.py probes both.
    port: 5174,
    proxy: {
      "/api": API,
      "/health": API,
      // legacy HTML shell pages mounted inside the React app (same-origin via
      // the proxy in dev; same-origin natively in production)
      "/brains": API,
      "/upload": API,
      "/graph": API,
      "/static": API,
    },
  },
  build: {
    outDir: "dist",
  },
})
