// Shared game types. These describe the JSON snapshot emitted by the
// Python core and the small startup-status object cached by the Rust shell.
// Components import from here; useGameState only owns the subscription.

export type GameStatus =
  | "playing"
  | "paused"
  | "level_complete"
  | "game_over";

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
  status: GameStatus;
  lock_count: number;
  clear_count: number;
  top_scores: { score: number; at: string }[];
  top_run: boolean;
  autopilot: AutopilotMode;
  music_track: string | null;
  music_phase: "gameplay" | "level_complete" | "milestone" | "game_over";
  color_index: number;
}

export type AutopilotMode = "quick" | "highscore" | null;

export interface NewGameOptions {
  level?: number;
  music?: string | null;
  handicap?: number;
}

export type StartupStatus = "starting" | "running" | "error";

/** Cached answer from the shell for a UI that subscribed after startup. */
export interface CoreStatusSnapshot {
  status: StartupStatus;
  error: string | null;
  state: GameState | null;
}