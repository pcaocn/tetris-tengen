import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

// One state snapshot from the Python core (spec 2.2). The UI renders from
// this state only and never computes game rules (spec 2.4).
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
  music_track: string | null;
  music_phase: "gameplay" | "level_complete" | "milestone" | "game_over";
  color_index: number;
}

export type GameStatus = GameState["status"];

export function useGameState() {
  const [state, setState] = useState<GameState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const subscriptions: Promise<UnlistenFn>[] = [
      listen<GameState>("game-state", (event) => {
        setState(event.payload);
        setNotice(null);
      }),
      listen<Record<string, unknown>>("core-event", (event) => {
        const payload = event.payload ?? {};
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
    return () => {
      subscriptions.forEach((p) => p.then((f) => f()).catch(() => {}));
    };
  }, []);

  const retry = () => {
    setError(null);
    invoke("start_core").catch((e) => setError(String(e)));
  };

  return { state, notice, error, retry };
}
