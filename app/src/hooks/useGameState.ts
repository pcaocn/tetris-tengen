// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The UI's ONLY connection to the game. Two Tauri channels meet here:
//
//   INBOUND  ("game-state", "core-event" events) -- the Rust shell
//     forwards the Python core's JSON snapshots; each one fully replaces
//     the previous state. There is no accumulation, no merging: the core
//     owns the truth, the UI just holds the latest snapshot.
//   OUTBOUND (gameApi calls) -- typed wrappers around the Rust commands
//     for "get_state", "start_core", and cached startup status.
//
// The snapshot shape lives in `types/game.ts`; this hook only subscribes,
// reconciles startup, and exposes the latest state.
import { useEffect, useState } from "react";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { gameApi } from "../api/game";
import type { CoreStatusSnapshot, GameState } from "../types/game";

/**
 * Subscribes to the core's state stream for the lifetime of the app.
 *
 * @returns state  -- the latest snapshot, or null until the first one
 *                    arrives (the "CONNECTING..." phase).
 *          notice -- a transient info message from the core (shown over
 *                    the playfield, then cleared by the next snapshot).
 *          error  -- a fatal core problem (shown full-screen with Retry).
 *          retry  -- asks the shell to relaunch the Python core.
 */
export function useGameState() {
  const [state, setState] = useState<GameState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Empty deps: subscribe ONCE. The listeners never change identity, and
  // the callbacks only touch the stable setState/setNotice functions.
  useEffect(() => {
    // listen() is async — it resolves to the unsubscribe function — so the
    // promises are collected and every cleanup awaits them. Without this,
    // unmounting before they resolve would leave zombie listeners (which
    // StrictMode's double-mount would immediately expose as doubled state).
    let alive = true;
    let liveVersion = 0;
    let lifecycleVersion = 0;

    const subscriptions: Promise<UnlistenFn>[] = [
      listen<GameState>("game-state", (event) => {
        liveVersion += 1;
        if (!alive) return;
        setState(event.payload);
        // A fresh snapshot means the core is healthy again: drop any
        // stale notice from a restart.
        setNotice(null);
      }),
      listen<Record<string, unknown>>("core-event", (event) => {
        lifecycleVersion += 1;
        if (!alive) return;
        const payload = event.payload ?? {};
        // Lifecycle messages from the shell about the CORE process
        // (distinct from game-state, which is about the GAME).
        switch (payload.type) {
          case "core-restarted":
            setNotice(String(payload.message ?? "Game reset."));
            break;
          case "core-error":
            setError(String(payload.message ?? "Python core failed to start."));
            break;
          case "core-started":
            setError(null);
            break;
        }
      }),
    ];
    // Do not query the cached status until BOTH listeners are attached.
    // Otherwise an early core-error/core-started event can land in the
    // gap and be overwritten by a stale query response.
    Promise.all(subscriptions)
      .then(() => {
        if (!alive) return;
        // Snapshot the lifecycle versions at query time. If a newer live
        // state or lifecycle event arrives before the query resolves, its
        // version will differ and the older result must not overwrite it.
        const stateVersion = liveVersion;
        const lifecycleAtQuery = lifecycleVersion;
        // Ask the shell for its cached startup result. This is what
        // recovers an early spawn failure: the `core-error` event may
        // have fired before this effect subscribed, so listening alone
        // can never see it.
        gameApi
          .getCoreStatus()
          .then((snapshot: CoreStatusSnapshot) => {
            if (!alive) return;
            if (snapshot.state && stateVersion === liveVersion) {
              setState(snapshot.state);
            }
            // Only a fatal status raises here. A stale "running" response
            // must never erase a newer core-error event.
            if (
              snapshot.status === "error" &&
              lifecycleAtQuery === lifecycleVersion
            ) {
              setError(snapshot.error ?? "Python core failed to start.");
            }
          })
          .catch(() => {});
        // Also ask for a fresh state; harmless if the core is not up yet,
        // the first state event will still arrive once it starts.
        gameApi.getState().catch(() => {});
      })
      .catch(() => {
        if (alive) setError("Python core failed to start.");
      });
    // Cleanup: unsubscribe in the same order, swallowing errors — a
    // rejected subscription promise at teardown must not mask anything.
    return () => {
      alive = false;
      // Unsubscribe each listener when its promise resolves. This covers
      // both "resolved before cleanup" and "resolves after cleanup".
      subscriptions.forEach((p) => p.then((f) => f()).catch(() => {}));
    };
  }, []);

  const retry = () => {
    // Clear first so the button can be pressed again even if the start
    // fails anew (the core-error event will re-set it).
    setError(null);
    gameApi.startCore().catch((e) => setError(String(e)));
  };

  return { state, notice, error, retry };
}