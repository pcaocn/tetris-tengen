// Tauri setup, commands, and registration.
//
// The Python child process and protocol transport live in
// `python_core.rs`; this file only exposes the desktop command surface and
// starts supervision during setup.

mod python_core;

use std::sync::Arc;

use serde_json::{json, Value};
use tauri::{AppHandle, State};

use python_core::PythonCore;

// ----------------------------------------------------------------------
// Tauri commands: the API the React UI calls.
//
// Each one is a thin wrapper that builds a JSON command and hands it to
// `send_command`. None of them interpret the reply — the Python core
// sends the state event separately, and the UI listens for that.
// ----------------------------------------------------------------------

/// Forward a key press: left, right, soft_drop_on/off, rotate_cw/ccw.
#[tauri::command]
fn send_input(core: State<'_, Arc<PythonCore>>, action: String) -> Result<(), String> {
    core.send_command(json!({ "cmd": "input", "action": action }))
}

/// Start a new game. The options page supplies the level, the music
/// track and the handicap (0/3/6/9/12 garbage rows).
#[tauri::command]
fn new_game(
    core: State<'_, Arc<PythonCore>>,
    level: Option<i64>,
    music: Option<String>,
    handicap: Option<i64>,
) -> Result<(), String> {
    core.send_command(json!({
        "cmd": "new_game",
        "level": level.unwrap_or(0),
        "music": music,
        "handicap": handicap.unwrap_or(0)
    }))
}

/// Toggle pause. (On the end-of-stage celebration, this is also what
/// skips ahead to the next level.)
#[tauri::command]
fn pause(core: State<'_, Arc<PythonCore>>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "pause" }))
}

// Cheat: jump to a level mid-game (owner request 2026-10-25).
#[tauri::command]
fn set_level(core: State<'_, Arc<PythonCore>>, level: Option<i64>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_level", "level": level.unwrap_or(0) }))
}

// Cheat: cycle the gameplay music mid-game (owner request 2026-10-25).
#[tauri::command]
fn set_music(core: State<'_, Arc<PythonCore>>, music: Option<String>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_music", "music": music }))
}

// Cheat: control the autopilot (owner request 2026-10-27).
#[tauri::command]
fn set_autopilot(core: State<'_, Arc<PythonCore>>, mode: Option<String>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_autopilot", "mode": mode }))
}

/// Ask for the current state and return the cached copy.
#[tauri::command]
fn get_state(core: State<'_, Arc<PythonCore>>) -> Result<Option<Value>, String> {
    core.send_command(json!({ "cmd": "get_state" }))?;
    Ok(core.latest_state())
}

/// Return the shell's cached startup status and latest snapshot.
#[tauri::command]
fn get_core_status(core: State<'_, Arc<PythonCore>>) -> Result<Value, String> {
    core.status_snapshot()
}

/// Make sure the supervisor is running. The UI calls this on mount, in
/// case the window was created before the setup hook ran.
#[tauri::command]
fn start_core(app: AppHandle, core: State<'_, Arc<PythonCore>>) -> Result<(), String> {
    core.ensure_supervision(app.clone());
    Ok(())
}

/// Desktop entry point used by `main.rs`.
pub fn run() {
    // The core is shared: the Tauri state (for the commands) and the
    // supervisor thread both hold a reference.
    let core = Arc::new(PythonCore::new());
    tauri::Builder::default()
        .manage(core.clone())
        .invoke_handler(tauri::generate_handler![
            send_input,
            new_game,
            set_level,
            set_music,
            set_autopilot,
            pause,
            get_state,
            get_core_status,
            start_core
        ])
        .setup(move |app| {
            // Start the Python process as soon as the app is up, so the
            // UI has a state to draw immediately.
            core.ensure_supervision(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
