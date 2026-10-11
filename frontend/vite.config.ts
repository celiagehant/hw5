import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard calls the FastAPI backend directly (see src/api/client.ts);
// the backend's CORS settings allow this origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
