// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The Cargo build script for the Tauri shell.
//
// Cargo runs this ONCE, before compiling the crate. `tauri_build::build()`
// is the helper that reads `tauri.conf.json` and generates the code
// the crate needs to know about the window, the icons and the bundled
// resources (see `generate_context!` in src/main.rs).
//
// The generated file lands in `OUT_DIR` -- a build artifact directory
// outside the source tree -- so this script never writes into the
// repository.
//
// WHAT THIS FILE MUST NOT DO
// --------------------------
// It must stay free of game logic. The Rust shell's only job is to own
// the window and to route commands and events to the Python core
// (see src/main.rs); every game rule lives in `core/tetris_core/`.
fn main() {
    // Ask the Tauri build helper to process the configuration.
    tauri_build::build()
}
