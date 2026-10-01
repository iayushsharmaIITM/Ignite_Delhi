import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// The backend serves the built files from /static/app and keeps the API at
// the same origin, so dev proxies everything API-shaped to 127.0.0.1:8000.
const API = process.env.KESTREL_API || "http://localhost:8000"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": API,
      "/health": API,
    },
  },
  build: {
    outDir: "dist",
  },
})
