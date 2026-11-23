// Rust core (spec 2.3): spawn the Python game process, forward commands to
// it, and forward `state` messages to the UI as `game-state` events. The
// Rust core never interprets game data and contains no game rules.
//
// WHAT THIS LAYER DOES (and what it must never do)
// --------------------------------------------------
//   - Own the window and the Tauri lifecycle.
//   - Start the Python process and keep it alive.
//   - Forward UI commands to Python as JSON lines on stdin.
//   - Forward Python's state events to the UI as Tauri events.
//
// It must NOT contain a single game rule: no gravity, no scoring, no
// rotation, no line-clear logic. Every rule lives in the Python core, and
// this file only moves JSON around. That split is what lets the whole
// game be tested headlessly in Python (see core/sweep_autopilot.py).
//
// THE THREE PROCESSES
// --------------------
//     React UI  --invoke/events-->  Rust (this file)  --JSON lines-->  Python
//     (draw+input)                   (window, routing)                 (all rules)
//
// The UI never talks to Python directly, and Python never knows a window
// exists.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};

/// Startup state of the Python child, mirrored for a UI that subscribes
/// after the shell has already tried to launch it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CoreStartupStatus {
    Starting,
    Running,
    Error,
}

impl CoreStartupStatus {
    fn as_str(self) -> &'static str {
        match self {
            Self::Starting => "starting",
            Self::Running => "running",
            Self::Error => "error",
        }
    }
}

/// The shared handle on the Python process, registered as Tauri state.
///
/// `Arc` because the supervisor thread needs to own a reference while the
/// UI commands borrow one; `Mutex` because the child process handles and
/// the latest state are touched from both the thread and the UI thread.
pub struct PythonCore {
    inner: Mutex<Inner>,
    /// Monotonic counter used to give every command a unique `id`, so a
    /// response can be matched to the request that caused it.
    next_id: AtomicU64,
    /// True while the supervisor thread is running. Prevents starting
    /// two supervisors (which would fight over the child process).
    supervising: AtomicBool,
    /// Set during shutdown, so the supervisor knows not to restart Python.
    shutting_down: AtomicBool,
}

/// The mutable state, all behind one lock.
struct Inner {
    /// The Python process handle.
    child: Option<Child>,
    /// The write end of the child's stdin (commands go here).
    stdin: Option<ChildStdin>,
    /// The read end of the child's stdout (events come from here).
    stdout: Option<ChildStdout>,
    /// The most recent `state` event, cached so `get_state` can answer
    /// immediately without waiting for the next frame.
    latest_state: Option<Value>,
    /// The most recent startup result. A UI that mounts after a failed
    /// spawn can read this instead of waiting forever on "Connecting".
    startup_status: CoreStartupStatus,
    /// The fatal startup error, if `startup_status` is `Error`.
    startup_error: Option<String>,
    /// The resolved interpreter path (cached after the first resolution).
    python: Option<PathBuf>,
    /// The resolved core directory (cached after the first resolution).
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
                startup_status: CoreStartupStatus::Starting,
                startup_error: None,
                python: None,
                core_dir: None,
            }),
            // Command ids start at 1.
            next_id: AtomicU64::new(1),
            supervising: AtomicBool::new(false),
            shutting_down: AtomicBool::new(false),
        }
    }

    /// Spawn (or re-spawn) the Python process. Resolution order (spec
    /// 2.3, section 13): env overrides; the repository checkout this
    /// binary was built from (baked in at compile time — dev and
    /// installed on the build machine); the bundled core source in the
    /// app resources with the system python3 (installed elsewhere).
    fn spawn(&self, app: &AppHandle) -> Result<(), String> {
        // The lock serialises spawn against concurrent commands, so the
        // child handles cannot be swapped out mid-write.
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        // If a previous child is still around, kill it and reap it.
        // This is the re-spawn path after Python crashed.
        if let Some(mut child) = inner.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        // Drop the old pipes; the new child gets fresh ones.
        inner.stdin = None;
        inner.stdout = None;
        inner.latest_state = None;
        inner.startup_status = CoreStartupStatus::Starting;
        inner.startup_error = None;
        // Work out which Python to run and where the core lives.
        let (python, core_dir) = resolve_paths(app, &mut inner);
        // Start `python -m tetris_core` with the core directory as the
        // working directory (so the package is importable), pipes on
        // stdin/stdout, and stderr INHERITED — the core's log lines
        // then appear in the app's console instead of disappearing.
        let mut child = Command::new(&python)
            .arg("-m")
            .arg("tetris_core")
            .current_dir(&core_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("failed to start {}: {e}", python.display()))?;
        // Take the pipes out of the child handle so they can be used
        // independently (the child no longer needs to own them).
        inner.stdin = Some(child.stdin.take().ok_or("python stdin unavailable")?);
        inner.stdout = Some(child.stdout.take().ok_or("python stdout unavailable")?);
        inner.child = Some(child);
        // OS spawn is not readiness. Stay in Starting until the first
        // valid game-state snapshot is cached (see `cache_state`).
        inner.startup_status = CoreStartupStatus::Starting;
        inner.startup_error = None;
        Ok(())
    }

    /// Take the stdout pipe out of the lock, so the supervisor thread can
    /// read from it without holding the lock (reading blocks!).
    fn take_stdout(&self) -> Option<ChildStdout> {
        self.inner.lock().ok()?.stdout.take()
    }

    /// Send one command to Python as a single JSON line.
    fn send_command(&self, mut cmd: Value) -> Result<(), String> {
        // Give the command a unique id. The Python core echoes it back
        // in its `response`, which is how the UI can tell which answer
        // belongs to which request.
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        cmd["id"] = json!(id);
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        let stdin = inner.stdin.as_mut().ok_or("python core is not running")?;
        // One JSON object per line — that is the whole protocol.
        writeln!(stdin, "{cmd}").map_err(|e| format!("write to python failed: {e}"))?;
        // Flush immediately: the core reads line by line and would
        // otherwise wait for the buffer to fill.
        stdin.flush().map_err(|e| format!("flush failed: {e}"))?;
        Ok(())
    }

    /// Cache the newest state event. Returns true only for the first
    /// valid snapshot, which is the moment the child becomes ready.
    fn cache_state(&self, state: Value) -> bool {
        let mut inner = match self.inner.lock() {
            Ok(inner) => inner,
            Err(_) => return false,
        };
        inner.latest_state = Some(state);
        if inner.startup_status == CoreStartupStatus::Starting {
            inner.startup_status = CoreStartupStatus::Running;
            inner.startup_error = None;
            true
        } else {
            false
        }
    }

    /// True once a valid state snapshot has been cached.
    fn is_ready(&self) -> bool {
        self.inner
            .lock()
            .map(|inner| inner.startup_status == CoreStartupStatus::Running)
            .unwrap_or(false)
    }

    /// The cached state, cloned out so the caller can own it.
    fn latest_state(&self) -> Option<Value> {
        self.inner.lock().ok()?.latest_state.clone()
    }

    /// Reap the child and detach its pipes. If stdout closed while the
    /// child was still alive, terminate it so a pre-readiness failure
    /// cannot hang the supervisor.
    fn reap_child(&self) -> Option<std::process::ExitStatus> {
        let mut inner = self.inner.lock().ok()?;
        inner.stdin = None;
        inner.stdout = None;
        let mut child = inner.child.take()?;
        match child.try_wait() {
            Ok(Some(status)) => Some(status),
            Ok(None) => {
                let _ = child.kill();
                child.wait().ok()
            }
            Err(_) => None,
        }
    }

    /// Record the current startup phase and any fatal error.
    fn set_startup_status(&self, status: CoreStartupStatus, error: Option<String>) {
        if let Ok(mut inner) = self.inner.lock() {
            inner.startup_status = status;
            inner.startup_error = error;
        }
    }

    /// A late subscriber's view of the shell: startup phase, fatal error,
    /// and the newest state snapshot. This is what lets React recover an
    /// error event that fired before its listeners were attached.
    fn status_snapshot(&self) -> Result<Value, String> {
        let inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        Ok(json!({
            "status": inner.startup_status.as_str(),
            "error": inner.startup_error.clone(),
            "state": inner.latest_state.clone(),
        }))
    }

    /// Start the supervision thread (no-op if already supervising). The
    /// thread restarts Python if it exits (spec 2.3, section 8).
    fn ensure_supervision(self: &Arc<Self>, app: AppHandle) {
        // `swap` returns the previous value: if it was already true, a
        // supervisor is running and there is nothing to do. Using an
        // atomic swap makes this check-and-set race-free.
        if self.supervising.swap(true, Ordering::Relaxed) {
            return;
        }
        // A manual Retry lands here after a pre-readiness failure. Clear
        // the old error immediately; the child is not Running until its
        // first state snapshot arrives.
        self.set_startup_status(CoreStartupStatus::Starting, None);
        // The supervisor thread needs its own Arc to keep the core alive.
        let core = Arc::clone(self);
        let _ = thread::Builder::new()
            .name("python-supervisor".into())
            .spawn(move || supervise(app, core));
    }
}

impl Drop for PythonCore {
    /// Clean up when the app shuts down: stop the supervisor from
    /// restarting Python, then kill the child process.
    fn drop(&mut self) {
        self.shutting_down.store(true, Ordering::Relaxed);
        if let Ok(mut inner) = self.inner.lock() {
            // Close stdin first: that is how the core learns to exit
            // (its reader thread sees EOF and the loop returns).
            inner.stdin = None;
            if let Some(mut child) = inner.child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

/// Work out which Python interpreter to run and which directory to run
/// it in. Returns (interpreter path, core directory).
///
/// THE RESOLUTION ORDER (spec 2.3) — this is the part that is easy to
/// get wrong, so it is spelled out:
///
///   1. `TETRIS_CORE_DIR` / `TETRIS_PYTHON` environment overrides —
///      used for debugging.
///   2. The repository checkout the binary was BUILT from. The path is
///      baked in at COMPILE time with `env!("CARGO_MANIFEST_DIR")`.
///      This matters: the packaged app previously read it at RUNTIME,
///      which is empty in an installed app, and the app spun on
///      "connecting" forever. `env!` is resolved by the compiler, so the
///      path is a constant in the binary.
///   3. The core source bundled into the app resources, run with the
///      system `/usr/bin/python3` — for machines without the checkout.
///      The core uses `from __future__ import annotations`, so Python
///      3.9+ is enough.
fn resolve_paths(app: &AppHandle, inner: &mut Inner) -> (PathBuf, PathBuf) {
    // Cache the result: the paths never change during a run.
    if let (Some(p), Some(d)) = (inner.python.clone(), inner.core_dir.clone()) {
        return (p, d);
    }
    // The repository checkout this binary was built from: baked in at
    // compile time (env! — a runtime env read is empty in an installed
    // app, which left the packaged build spinning on "connecting").
    let repo_core = std::env::var("TETRIS_CORE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../core"));
    // The core source bundled into the app resources (installs on
    // machines without the repository).
    let bundled = app
        .path()
        .resource_dir()
        .ok()
        .filter(|r| r.join("tetris_core").exists());
    // The venv interpreter of the checkout, preferred when present.
    let venv_python = repo_core.join(".venv/bin/python");
    // Where to run Python from: the checkout if it has the package,
    // otherwise the bundled resources, otherwise the checkout anyway
    // (so the error message names a sensible path).
    let core_dir = if repo_core.join("tetris_core").exists() {
        repo_core
    } else if let Some(b) = bundled {
        // Resources/tetris_core is the package; run from its parent.
        b
    } else {
        repo_core
    };
    // The interpreter: an explicit override wins, then the checkout's
    // venv, then the system python3 (which ships with the Xcode
    // Command Line Tools on macOS).
    let python = match std::env::var("TETRIS_PYTHON") {
        Ok(p) => PathBuf::from(p),
        Err(_) => {
            if venv_python.exists() {
                venv_python
            } else {
                PathBuf::from("/usr/bin/python3")
            }
        }
    };
    // Cache for the next call.
    inner.python = Some(python.clone());
    inner.core_dir = Some(core_dir.clone());
    (python, core_dir)
}

/// The supervisor thread: keep the Python process alive.
///
/// The loop is "spawn, then read its output until it exits". When the
/// read loop ends (Python died), the process is re-spawned. The only
/// way out is the `shutting_down` flag set during app shutdown.
fn supervise(app: AppHandle, core: Arc<PythonCore>) {
    loop {
        // Start (or restart) Python. The status is mirrored in Rust so a
        // UI that subscribes later can see either the successful launch or
        // the fatal error instead of remaining on "Connecting".
        core.set_startup_status(CoreStartupStatus::Starting, None);
        if let Err(message) = core.spawn(&app) {
            // Spawning failed outright: report it to the UI and stop
            // supervising (retrying would just fail again).
            core.set_startup_status(CoreStartupStatus::Error, Some(message.clone()));
            core.supervising.store(false, Ordering::Relaxed);
            let _ = app.emit(
                "core-event",
                json!({ "type": "core-error", "message": message }),
            );
            return;
        }
        // Read the core's stdout line by line until it closes. The first
        // valid state line flips Starting -> Running and emits
        // `core-started`; log lines and command responses do not.
        if let Some(stdout) = core.take_stdout() {
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                handle_message(&app, &core, &line);
            }
        }
        // If the app is shutting down, do not restart.
        if core.shutting_down.load(Ordering::Relaxed) {
            core.reap_child();
            return;
        }
        if !core.is_ready() {
            // The child closed stdout before producing a single valid
            // state. This is a startup failure, not a mid-game crash:
            // reap it, publish a readable error, and require a manual
            // Retry instead of looping through 250 ms respawns.
            let status = core.reap_child();
            let message = match status {
                Some(status) => {
                    format!("python exited before sending state ({status})")
                }
                None => "python exited before sending state".to_string(),
            };
            core.set_startup_status(CoreStartupStatus::Error, Some(message.clone()));
            core.supervising.store(false, Ordering::Relaxed);
            let _ = app.emit(
                "core-event",
                json!({ "type": "core-error", "message": message }),
            );
            return;
        }
        // Python exited after a healthy run: restart it. The in-progress
        // game is lost and the UI shows "Game reset." (spec section 8).
        core.reap_child();
        let _ = app.emit(
            "core-event",
            json!({ "type": "core-restarted", "message": "Game reset." }),
        );
        // A short pause before restarting, so a core that fails
        // immediately on startup does not spin the CPU at 100%.
        thread::sleep(Duration::from_millis(250));
    }
}

/// A valid game-state snapshot: the Python core's state object with a
/// status string and a board array. A log or response is not readiness.
fn is_game_state(msg: &Value) -> bool {
    msg.get("type").and_then(Value::as_str) == Some("state")
        && msg.get("status").and_then(Value::as_str).is_some()
        && msg.get("board").map(Value::is_array).unwrap_or(false)
}

/// Route one line of the core's stdout to the right place.
///
/// `state` events go to the UI as `game-state` (the channel the React
/// app listens on); everything else (`response`, `log`) goes to
/// `core-event` for diagnostics. Returns true only when this line was
/// the first valid state and therefore made the child ready.
fn handle_message(app: &AppHandle, core: &PythonCore, line: &str) -> bool {
    // A line that is not valid JSON is ignored: the core is supposed to
    // only write JSON, but a stray print must not kill the supervisor.
    let Ok(msg) = serde_json::from_str::<Value>(line) else {
        return false;
    };
    if is_game_state(&msg) {
        let became_ready = core.cache_state(msg.clone());
        if became_ready {
            // Readiness is a state snapshot, not an OS spawn or a log.
            let _ = app.emit("core-event", json!({ "type": "core-started" }));
        }
        let _ = app.emit("game-state", msg);
        became_ready
    } else {
        // responses and log events, forwarded for diagnostics (spec 2.3)
        let _ = app.emit("core-event", msg);
        false
    }
}

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

// Cheat: control the autopilot (owner request 2026-10-27; the UI gates
// this behind the Konami code — Home = highscore, End = quick, off via
// either key).
#[tauri::command]
fn set_autopilot(core: State<'_, Arc<PythonCore>>, mode: Option<String>) -> Result<(), String> {
    core.send_command(json!({ "cmd": "set_autopilot", "mode": mode }))
}

/// Ask for the current state and return the cached copy.
///
/// The command is sent so the core refreshes its snapshot, but the
/// answer returned here is the one already cached — the fresh state
/// arrives separately as a `game-state` event.
#[tauri::command]
fn get_state(core: State<'_, Arc<PythonCore>>) -> Result<Option<Value>, String> {
    core.send_command(json!({ "cmd": "get_state" }))?;
    Ok(core.latest_state())
}

/// Return the shell's cached startup status and latest snapshot.
///
/// React calls this after subscribing. It is deliberately separate from
/// `get_state`: that command needs a live Python child, while this one can
/// still answer when the child failed to spawn.
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

fn main() {
    // The core is shared: the Tauri state (for the commands) and the
    // supervisor thread both hold a reference.
    let core = Arc::new(PythonCore::new());
    tauri::Builder::default()
        // Register it so the commands can reach it via `State<'_, Arc<...>>`.
        .manage(core.clone())
        // The commands the UI may invoke.
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_snapshot_starts_in_starting_phase() {
        let core = PythonCore::new();
        let snapshot = core.status_snapshot().expect("status snapshot");
        assert_eq!(snapshot["status"], "starting");
        assert!(snapshot["error"].is_null());
        assert!(snapshot["state"].is_null());
    }

    #[test]
    fn status_snapshot_retains_fatal_error_for_late_ui() {
        let core = PythonCore::new();
        core.set_startup_status(CoreStartupStatus::Error, Some("spawn failed".into()));
        let snapshot = core.status_snapshot().expect("status snapshot");
        assert_eq!(snapshot["status"], "error");
        assert_eq!(snapshot["error"], "spawn failed");
    }

    #[test]
    fn first_valid_state_marks_child_ready_and_clears_error() {
        let core = PythonCore::new();
        core.set_startup_status(CoreStartupStatus::Starting, Some("old error".into()));
        assert!(!core.is_ready());

        let state = json!({"type": "state", "status": "playing", "board": []});
        assert!(core.cache_state(state.clone()));
        assert!(core.is_ready());
        let snapshot = core.status_snapshot().expect("status snapshot");
        assert_eq!(snapshot["status"], "running");
        assert!(snapshot["error"].is_null());
        assert_eq!(snapshot["state"], state);

        // A second state is ordinary play, not another readiness edge.
        assert!(!core.cache_state(json!({"type": "state", "status": "playing", "board": []})));
    }

    #[test]
    fn only_a_game_state_counts_as_readiness() {
        assert!(is_game_state(
            &json!({"type": "state", "status": "playing", "board": []})
        ));
        assert!(!is_game_state(
            &json!({"type": "log", "message": "starting"})
        ));
        assert!(!is_game_state(
            &json!({"type": "state", "status": "playing"})
        ));
    }
}
