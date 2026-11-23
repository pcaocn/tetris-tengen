// Desktop executable entry point.
//
// The Tauri builder, commands, and Python child live in `lib.rs` and
// `python_core.rs`; this file only keeps the platform-specific executable
// attribute and delegates to the library's `run()`.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tengen_tetris::run();
}
