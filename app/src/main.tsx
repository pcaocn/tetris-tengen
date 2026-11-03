// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The front-end entry point. Vite loads this file because index.html
// references it as `<script type="module" src="/src/main.tsx">`; from
// here the whole React tree hangs.
//
// The layering of the app, top to bottom:
//   main.tsx        -- mounts React into the single #root div.
//   App.tsx         -- owns the window, the keyboard, and the audio.
//   useGameState    -- the single channel to the game: Tauri events in,
//                      `invoke` calls out. The UI never computes rules.
//   components/*    -- pure renderers of the state snapshot (plus the
//                      canvas vector art in Board/draw/cathedral).
// Everything below App is dumb on purpose: the Python core is the
// source of truth for board, pieces, gravity, scoring and stats, and
// the Rust shell just ferries JSON between it and this window.
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// React 18 function components only; no global state library in v1
// (spec section 11, 12).
//
// `<React.StrictMode>` matters for how you should read the effects in
// App.tsx: in development StrictMode intentionally mounts, unmounts and
// remounts every component once, so every useEffect runs, cleans up and
// runs again. Any effect whose cleanup is missing (a listener left
// attached, a canvas context leaked) shows up immediately as doubled
// sound or doubled input. That is why the cleanups below are not
// optional tidiness -- they are load-bearing.
//
// `getElementById("root")!` -- the `!` tells TypeScript the div exists;
// it is defined in index.html, which Vite injects this bundle into.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
