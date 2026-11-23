// Python child process and protocol transport.
//
// This module owns the interpreter/resource resolution, child handles,
// stdin writes, stdout parsing, snapshot caching, readiness, retry/restart,
// and shutdown. It contains no Tauri command surface; `lib.rs` registers
// the commands and calls `ensure_supervision` during setup.

use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter};

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
pub(crate) struct PythonCore {
    inner: Mutex<Inner>,
    /// Monotonic counter used to give every command a unique `id`.
    next_id: AtomicU64,
    /// True while the supervisor thread is running.
    supervising: AtomicBool,
    /// Set during shutdown, so the supervisor knows not to restart Python.
    shutting_down: AtomicBool,
}

/// The mutable state, all behind one lock.
struct Inner {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<ChildStdout>,
    latest_state: Option<Value>,
    startup_status: CoreStartupStatus,
    startup_error: Option<String>,
}

impl PythonCore {
    pub(crate) fn new() -> Self {
        Self {
            inner: Mutex::new(Inner {
                child: None,
                stdin: None,
                stdout: None,
                latest_state: None,
                startup_status: CoreStartupStatus::Starting,
                startup_error: None,
            }),
            next_id: AtomicU64::new(1),
            supervising: AtomicBool::new(false),
            shutting_down: AtomicBool::new(false),
        }
    }

    /// Spawn (or re-spawn) the game engine.
    ///
    /// Resolution order:
    ///   1. `TETRIS_PYTHON` / `TETRIS_CORE_DIR` developer overrides.
    ///   2. Release builds: the `tetris-core` sidecar next to the app
    ///      executable (staged by `tools/build_sidecar.sh` and declared
    ///      in `bundle.externalBin`).
    ///   3. Debug builds: the checkout's `.venv` and `core/` directory.
    fn spawn(&self) -> Result<(), String> {
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        if let Some(mut child) = inner.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        inner.stdin = None;
        inner.stdout = None;
        inner.latest_state = None;
        inner.startup_status = CoreStartupStatus::Starting;
        inner.startup_error = None;
        let mut command = resolve_launch()?;
        let program = command.get_program().to_string_lossy().to_string();
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("failed to start {program}: {e}"))?;
        inner.stdin = Some(child.stdin.take().ok_or("python stdin unavailable")?);
        inner.stdout = Some(child.stdout.take().ok_or("python stdout unavailable")?);
        inner.child = Some(child);
        // OS spawn is not readiness. Stay in Starting until the first
        // valid game-state snapshot is cached (see `cache_state`).
        inner.startup_status = CoreStartupStatus::Starting;
        inner.startup_error = None;
        Ok(())
    }

    /// Take the stdout pipe out of the lock, so the supervisor can read
    /// without holding the lock (reading blocks!).
    fn take_stdout(&self) -> Option<ChildStdout> {
        self.inner.lock().ok()?.stdout.take()
    }

    /// Send one command to Python as a single JSON line.
    pub(crate) fn send_command(&self, mut cmd: Value) -> Result<(), String> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        cmd["id"] = json!(id);
        let mut inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        let stdin = inner.stdin.as_mut().ok_or("python core is not running")?;
        writeln!(stdin, "{cmd}").map_err(|e| format!("write to python failed: {e}"))?;
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
    pub(crate) fn latest_state(&self) -> Option<Value> {
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
    /// and the newest state snapshot.
    pub(crate) fn status_snapshot(&self) -> Result<Value, String> {
        let inner = self.inner.lock().map_err(|_| "core lock poisoned")?;
        Ok(json!({
            "status": inner.startup_status.as_str(),
            "error": inner.startup_error.clone(),
            "state": inner.latest_state.clone(),
        }))
    }

    /// Start the supervision thread (no-op if already supervising).
    pub(crate) fn ensure_supervision(self: &Arc<Self>, app: AppHandle) {
        if self.supervising.swap(true, Ordering::Relaxed) {
            return;
        }
        // A manual Retry lands here after a pre-readiness failure. Clear
        // the old error immediately; the child is not Running until its
        // first state snapshot arrives.
        self.set_startup_status(CoreStartupStatus::Starting, None);
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
            inner.stdin = None;
            if let Some(mut child) = inner.child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

/// Work out how to launch the engine for this build.
fn resolve_launch() -> Result<Command, String> {
    // Developer overrides always win, in both debug and release.
    let python_override = std::env::var("TETRIS_PYTHON").ok().map(PathBuf::from);
    let core_override = std::env::var("TETRIS_CORE_DIR").ok().map(PathBuf::from);
    if python_override.is_some() || core_override.is_some() {
        let repo_core = core_override
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../core"));
        let python = python_override.unwrap_or_else(|| {
            let venv = repo_core.join(".venv/bin/python");
            if venv.exists() {
                venv
            } else {
                PathBuf::from("/usr/bin/python3")
            }
        });
        let mut command = Command::new(python);
        command.arg("-m").arg("tetris_core").current_dir(repo_core);
        return Ok(command);
    }

    // Release builds use the bundled sidecar. It is copied next to the
    // app executable by the Tauri bundler (bundle.externalBin).
    if !cfg!(debug_assertions) {
        let sidecar = std::env::current_exe()
            .ok()
            .and_then(|exe| exe.parent().map(|dir| dir.join("tetris-core")))
            .ok_or_else(|| "cannot locate the tetris-core sidecar".to_string())?;
        if !sidecar.exists() {
            return Err(format!(
                "packaged sidecar not found at {}; run tools/build_sidecar.sh",
                sidecar.display()
            ));
        }
        return Ok(Command::new(sidecar));
    }

    // Debug builds run the checkout's virtual environment.
    let repo_core = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../core");
    let venv = repo_core.join(".venv/bin/python");
    let python = if venv.exists() {
        venv
    } else {
        PathBuf::from("/usr/bin/python3")
    };
    let mut command = Command::new(python);
    command.arg("-m").arg("tetris_core").current_dir(repo_core);
    Ok(command)
}

/// The supervisor thread: keep the Python process alive.
fn supervise(app: AppHandle, core: Arc<PythonCore>) {
    loop {
        core.set_startup_status(CoreStartupStatus::Starting, None);
        if let Err(message) = core.spawn() {
            core.set_startup_status(CoreStartupStatus::Error, Some(message.clone()));
            core.supervising.store(false, Ordering::Relaxed);
            let _ = app.emit(
                "core-event",
                json!({ "type": "core-error", "message": message }),
            );
            return;
        }
        if let Some(stdout) = core.take_stdout() {
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                handle_message(&app, &core, &line);
            }
        }
        if core.shutting_down.load(Ordering::Relaxed) {
            core.reap_child();
            return;
        }
        if !core.is_ready() {
            // The child closed stdout before producing a single valid
            // state. Reap it, publish a readable error, and require a
            // manual Retry instead of looping through respawns.
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
        // Python exited after a healthy run: restart it.
        core.reap_child();
        let _ = app.emit(
            "core-event",
            json!({ "type": "core-restarted", "message": "Game reset." }),
        );
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
fn handle_message(app: &AppHandle, core: &PythonCore, line: &str) -> bool {
    let Ok(msg) = serde_json::from_str::<Value>(line) else {
        return false;
    };
    if is_game_state(&msg) {
        let became_ready = core.cache_state(msg.clone());
        if became_ready {
            let _ = app.emit("core-event", json!({ "type": "core-started" }));
        }
        let _ = app.emit("game-state", msg);
        became_ready
    } else {
        let _ = app.emit("core-event", msg);
        false
    }
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
