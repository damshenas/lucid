import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds to src/ui/dist, which FastAPI serves at "/". During dev, API calls are
// proxied to the backend on port 8686.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://localhost:8686",
      "/health": "http://localhost:8686",
    },
  },
});
