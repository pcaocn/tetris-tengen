// Rust core (spec 2.3): spawn the Python game process, forward commands to
// it, and forward `state` messages to the UI as `game-state` events. The
// Rust core never interprets game data and contains no game rules.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, State};

pub struct PythonCore {
    inner: Mutex<Inner>,
    next_id: AtomicU64,
    supervising: AtomicBool,
    shutting_down: AtomicBool,
}

struct Inner {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<ChildStdout>,
    latest_state: Option<Value>,
    python: Option<PathBuf>,
    core_dir: Option<PathBuf>,
}

impl PythonCore {
    fn new() -> Self {
        Self {
            inner: Mutex::new(Inner {
                child: None,
                stdin: None,
                stdout: None,
                latest_state: None,
                python: None,
                core_dir: None,
            }),
            next_id: AtomicU64::new(1),
            supervising: AtomicBool::new(false),
            shutting_down: AtomicBool::new(false),
        }
    }

    /// Spawn (or re-spawn) the Python process. Dev builds use the repository
    /// virtualenv; release packaging is an open item (spec section 13).
    fn spawn(&self) -> Result<(), String> {
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        if let Some(mut child) = inner.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        inner.stdin = None;
        inner.stdout = None;
        inner.latest_state = None;
        let (python, core_dir) = resolve_paths(&mut inner);
        let mut child = Command::new(&python)
            .arg("-m")
            .arg("tetris_core")
            .current_dir(&core_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("failed to start {}: {e}", python.display()))?;
        inner.stdin = Some(child.stdin.take().ok_or("python stdin unavailable")?);
        inner.stdout = Some(child.stdout.take().ok_or("python stdout unavailable")?);
        inner.child = Some(child);
        Ok(())
    }

    fn take_stdout(&self) -> Option<ChildStdout> {
        self.inner.lock().ok()?.stdout.take()
    }

    fn send_command(&self, mut cmd: Value) -> Result<(), String> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        cmd["id"] = json!(id);
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        let stdin = inner
            .stdin
            .as_mut()
            .ok_or("python core is not running")?;
        writeln!(stdin, "{cmd}").map_err(|e| format!("write to python failed: {e}"))?;
        stdin.flush().map_err(|e| format!("flush failed: {e}"))?;
        Ok(())
    }

    fn store_latest(&self, state: Value) {
        if let Ok(mut inner) = self.inner.lock() {
            inner.latest_state = Some(state);
        }
    }

    fn latest_state(&self) -> Option<Value> {
        self.inner.lock().ok()?.latest_state.clone()
    }

    /// Start the supervision thread (no-op if already supervising). The
    /// thread restarts Python if it exits (spec 2.3, section 8).
    fn ensure_supervision(self: &Arc<Self>, app: AppHandle) {
        if self.supervising.swap(true, Ordering::Relaxed) {
            return;
        }
        let core = Arc::clone(self);
        let _ = thread::Builder::new()
            .name("python-supervisor".into())
            .spawn(move || supervise(app, core));
    }
}

impl Drop for PythonCore {
    fn drop(&mut self) {
        self.shutting_down.store(true, Ordering::Relaxed);
        if let Ok(mut inner) = self.inner.lock() {
            inner.stdin = None;
            if let Some(mut child) = inner.child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn resolve_paths(inner: &mut Inner) -> (PathBuf, PathBuf) {
    if let (Some(p), Some(d)) = (inner.python.clone(), inner.core_dir.clone()) {
        return (p, d);
    }
    let core_dir = std::env::var("TETRIS_CORE_DIR")
        .map(PathBuf::from)
        .or_else(|_| {
            std::env::var("CARGO_MANIFEST_DIR")
                .map(|m| PathBuf::from(m).join("../../core"))
        })
        .unwrap_or_else(|_| PathBuf::from("../core"));
    let python = match std::env::var("TETRIS_PYTHON") {
        Ok(p) => PathBuf::from(p),
        Err(_) => {
            let venv = core_dir.join(".venv/bin/python");
            if venv.exists() {
                venv
            } else {
                PathBuf::from("python3")
            }
        }
    };
    inner.python = Some(python.clone());
    inner.core_dir = Some(core_dir.clone());
    (python, core_dir)
}

fn supervise(app: AppHandle, core: Arc<PythonCore>) {
    loop {
        if let Err(message) = core.spawn() {
            core.supervising.store(false, Ordering::Relaxed);
            let _ = app.emit(
                "core-event",
                json!({ "type": "core-error", "message": message }),
            );
            return;
        }
        let _ = app.emit("core-event", json!({ "type": "core-started" }));
        if let Some(stdout) = core.take_stdout() {
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                handle_message(&app, &core, &line);
            }
        }
        if core.shutting_down.load(Ordering::Relaxed) {
            return;
        }
        // Python exited during play: restart it. The in-progress game is
        // lost and the UI shows "Game reset." (spec section 8).
        let _ = app.emit(
            "core-event",
            json!({ "type": "core-restarted", "message": "Game reset." }),
        );
        thread::sleep(Duration::from_millis(250));
    }
}

fn handle_message(app: &AppHandle, core: &PythonCore, line: &str) {
    let Ok(msg) = serde_json::from_str::<Value>(line) else {
        return;
    };
    if msg.get("type").and_then(Value::as_str) == Some("state") {
        core.store_latest(msg.clone());
        let _ = app.emit("game-state", msg);
    } else {
        // responses and log events, forwarded for diagnostics (spec 2.3)
        let _ = app.emit("core-event", msg);
    }
}

#[tauri::command]
fn send_input(core: State<'_, Arc<PythonCore>>, action: String) -> Result<(), String> {
    core.send_command(json!({ "cmd": "input", "action": action }))
}

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

#[tauri::command]
fn pause(core: State<'_, Arc<PythonCore>>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "pause" }))
}

// Cheat: jump to a level mid-game (owner request 2026-10-25; unlocked in
// the UI by the classic code on the title screen).
#[tauri::command]
fn set_level(core: State<'_, Arc<PythonCore>>, level: Option<i64>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_level", "level": level.unwrap_or(0) }))
}

// Cheat: cycle the gameplay music mid-game (owner request 2026-10-25).
#[tauri::command]
fn set_music(core: State<'_, Arc<PythonCore>>, music: Option<String>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_music", "music": music }))
}

#[tauri::command]
fn get_state(core: State<'_, Arc<PythonCore>>) -> Result<Option<Value>, String> {
    core.send_command(json!({ "cmd": "get_state" }))?;
    Ok(core.latest_state())
}

#[tauri::command]
fn start_core(app: AppHandle, core: State<'_, Arc<PythonCore>>) -> Result<(), String> {
    core.ensure_supervision(app.clone());
    Ok(())
}

fn main() {
    let core = Arc::new(PythonCore::new());
    tauri::Builder::default()
        .manage(core.clone())
        .invoke_handler(tauri::generate_handler![
            send_input,
            new_game,
            set_level,
            set_music,
            pause,
            get_state,
            start_core
        ])
        .setup(move |app| {
            core.ensure_supervision(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
