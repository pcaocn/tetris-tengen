// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The Cargo build script for the Tauri shell.
//
// Cargo runs this ONCE, before compiling the crate. `tauri_build::build()`
// is the helper that reads `tauri.conf.json` and generates the code
// the crate needs to know about the window, the icons and the bundled
// resources (see `generate_context!` in src/lib.rs).
//
// The generated file lands in `OUT_DIR` -- a build artifact directory
// outside the source tree. The only source-tree write is the ignored
// debug sidecar placeholder created below for Tauri's externalBin check.
//
// WHAT THIS FILE MUST NOT DO
// --------------------------
// It must stay free of game logic. The Rust shell's only job is to own
// the window and to route commands and events to the Python core
// (see src/lib.rs and src/python_core.rs); every game rule lives in
// `core/tetris_core/`.
fn main() {
    ensure_debug_sidecar_placeholder();
    // Ask the Tauri build helper to process the configuration.
    tauri_build::build()
}

/// `bundle.externalBin` makes Tauri's build script require a staged
/// sidecar. Debug builds do not use it (they run the checkout's venv), but
/// `cargo check` / `tauri dev` still need the file to exist. Create a tiny
/// placeholder for debug only; release packaging requires the real binary
/// from `tools/build_sidecar.sh`.
fn ensure_debug_sidecar_placeholder() {
    if std::env::var("PROFILE").as_deref() != Ok("debug") {
        return;
    }
    let manifest = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let dir = manifest.join("binaries");
    let _ = std::fs::create_dir_all(&dir);
    let target = std::env::var("TARGET").unwrap_or_default();
    let ext = if target.contains("windows") {
        ".exe"
    } else {
        ""
    };
    let path = dir.join(format!("tetris-core-{target}{ext}"));
    if path.exists() {
        return;
    }
    let script = if ext.is_empty() {
        "#!/bin/sh\nexec /usr/bin/python3 -m tetris_core \"$@\"\n"
    } else {
        "@echo off\r\npython -m tetris_core %*\r\n"
    };
    if std::fs::write(&path, script).is_ok() {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755));
        }
    }
}
