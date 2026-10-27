import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Ontwikkeling: log in via http://localhost:8000/auth/dev (of Entra); de sessiecookie geldt ook voor poort 5173.
// De proxy stuurt /api en /auth naar Python, zodat de browser maar één oorsprong ziet (geen CORS).
// Productie: `npm run build` bouwt naar ../app/web; FastAPI serveert die map (zie app/main.py).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../app/web", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000", "/auth": "http://localhost:8000" },
  },
});
