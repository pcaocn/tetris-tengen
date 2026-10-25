import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Tauri frontend. publicDir points at the repo assets folder so the
// open-licensed font in assets/font is served at /font (spec 6.3).
// fs.allow includes the repo root so the title music can be imported
// from ../music in dev mode (spec 5).
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  publicDir: "../assets",
  server: {
    port: 5173,
    strictPort: true,
    fs: {
      allow: [".."],
    },
  },
});
