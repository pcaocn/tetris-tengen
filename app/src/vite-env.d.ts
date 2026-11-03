/// <reference types="vite/client" />

// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// Type declarations for the non-TypeScript imports the app makes.
//
// This file is never executed -- it only tells the TypeScript compiler
// what the `?url` imports look like, so `import theme from
// "./music/foo.ogg?url"` type-checks as the string URL that Vite
// actually produces at build time.
//
// The `/// <reference ...>` line above pulls in Vite's own client
// types (asset modules, CSS modules, `import.meta.env`, and so on).
// The two module declarations below cover the audio files, which come
// from the repo-level music/ folder (spec 5).
//
// WITHOUT THESE DECLARATIONS
// --------------------------
// TypeScript would reject every music import with "Could not find a
// declaration file for module '*.ogg?url'", and `npm run typecheck`
// would fail even though the app runs fine.
//
// Both formats are declared because the owner's music collection holds
// .ogg files, while the browser-reachable copies the app ships may be
// .mp3.

// Music files imported from the repo-level music/ folder (spec 5).
// Vite turns each import into the URL of the built asset, which is
// what the <audio> element's `src` needs.
declare module "*.ogg?url" {
  const src: string;
  export default src;
}

declare module "*.mp3?url" {
  const src: string;
  export default src;
}
