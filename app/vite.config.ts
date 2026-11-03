import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The Vite build configuration for the React front end. Vite bundles
// the TypeScript/TSX sources into the static assets that Tauri then
// embeds in the app bundle; in dev mode it serves them to the Tauri
// window on a local port.
//
// This file contains no game logic. It only tells the bundler where
// things live and which port the dev server listens on.
//
// The Tauri frontend. publicDir points at the repo assets folder so the
// open-licensed font in assets/font is served at /font (spec 6.3).
// fs.allow includes the repo root so the title music can be imported
// from ../music in dev mode (spec 5).
export default defineConfig({
  // The React plugin: compiles the TSX and enables the Fast Refresh
  // that makes `npm run tauri dev` reload the window on save.
  plugins: [react()],
  // Keep the terminal output: the dev server's logs are the main way
  // to see a build or import error in the front end.
  clearScreen: false,
  // The repo's `assets/` folder is served as the site root, so
  // `assets/font/<face>.woff2` is reachable as `/font/<face>.woff2`.
  publicDir: "../assets",
  server: {
    // The port Tauri expects in development. `strictPort` makes Vite
    // FAIL rather than silently pick 5174 if the port is busy -- a
    // silent fallback would leave the window pointing at nothing.
    port: 5173,
    strictPort: true,
    fs: {
      // Allow the dev server to read files above `app/`, which is how
      // the title-screen music in `../music` can be imported.
      allow: [".."],
    },
  },
});
