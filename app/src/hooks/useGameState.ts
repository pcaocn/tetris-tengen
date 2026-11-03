// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The UI's ONLY connection to the game. Two Tauri channels meet here:
//
//   INBOUND  ("game-state", "core-event" events) -- the Rust shell
//     forwards the Python core's JSON snapshots; each one fully replaces
//     the previous state. There is no accumulation, no merging: the core
//     owns the truth, the UI just holds the latest snapshot.
//   OUTBOUND (`invoke` calls) -- UI commands ("get_state", "start_core")
//     sent to the Rust shell, which translates them to JSON lines on the
//     core's stdin. (Game inputs go through App.tsx's send_input instead.)
//
// This is also where the GameState type lives — the shape of everything
// the UI is allowed to know. If a field is not on it, the UI cannot use
// it, which is what keeps rule computation out of the front end.
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

// One state snapshot from the Python core (spec 2.2). The UI renders from
// this state only and never computes game rules (spec 2.4).
//
// Field notes for the non-obvious ones:
//   frame        -- the core's 60 Hz tick counter (monotonic; useful to
//                   spot stale snapshots when debugging).
//   board        -- 20 rows x 10 cols of ints, 0 = empty, > 0 = filled.
//                   No hidden rows are sent: the core pre-clips them.
//   current      -- the falling piece's kind letter and its 4 cells, or
//                   null between lock and next spawn.
//   clearing     -- the line-clear animation: which rows and how far the
//                   core's 24-frame dissolve has progressed.
//   lock_count / clear_count -- monotonic event counters. The UI diffs
//                   them to fire sound effects (App.tsx); counters rather
//                   than events because state snapshots can be coalesced
//                   in transit and a one-shot event channel would drop.
//   top_run      -- this game-over made the top-5 (drives the fireworks).
//   color_index  -- which locked-color row of the theme table to use.
export interface GameState {
  type: "state";
  frame: number;
  board: number[][];
  current: { kind: string; cells: [number, number][] } | null;
  clearing: { rows: number[]; frame: number } | null;
  next: string;
  score: number;
  lines: number;
  level: number;
  high_score: number;
  stats: Record<string, number>;
  status: "playing" | "paused" | "level_complete" | "game_over";
  lock_count: number;
  clear_count: number;
  top_scores: { score: number; at: string }[];
  top_run: boolean;
  autopilot: "quick" | "highscore" | null;
  music_track: string | null;
  music_phase: "gameplay" | "level_complete" | "milestone" | "game_over";
  color_index: number;
}

export type GameStatus = GameState["status"];

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
    const subscriptions: Promise<UnlistenFn>[] = [
      listen<GameState>("game-state", (event) => {
        setState(event.payload);
        // A fresh snapshot means the core is healthy again: drop any
        // stale notice from a restart.
        setNotice(null);
      }),
      listen<Record<string, unknown>>("core-event", (event) => {
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
    // Ask for the current state; harmless if the core is not up yet, the
    // first state event will still arrive once it starts.
    invoke("get_state").catch(() => {});
    // Cleanup: unsubscribe in the same order, swallowing errors — a
    // rejected subscription promise at teardown must not mask anything.
    return () => {
      subscriptions.forEach((p) => p.then((f) => f()).catch(() => {}));
    };
  }, []);

  const retry = () => {
    // Clear first so the button can be pressed again even if the start
    // fails anew (the core-error event will re-set it).
    setError(null);
    invoke("start_core").catch((e) => setError(String(e)));
  };

  return { state, notice, error, retry };
}
