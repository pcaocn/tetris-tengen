import { invoke } from "@tauri-apps/api/core";
import type {
  AutopilotMode,
  CoreStatusSnapshot,
  GameState,
  NewGameOptions,
} from "../types/game";

// Typed wrappers around the Rust commands. Keeping the invoke calls here
// means components and hooks depend on game vocabulary, not Tauri's IPC.
// The Rust command names and payload shapes are the same ones registered in
// `src-tauri/src/lib.rs`.
export const gameApi = {
  sendInput: (action: string) => invoke<void>("send_input", { action }),

  newGame: (options: NewGameOptions = {}) =>
    invoke<void>("new_game", {
      level: options.level ?? 0,
      music: options.music ?? null,
      handicap: options.handicap ?? 0,
    }),

  pause: () => invoke<void>("pause"),

  setLevel: (level: number) => invoke<void>("set_level", { level }),

  setMusic: (music: string) => invoke<void>("set_music", { music }),

  setAutopilot: (mode: AutopilotMode) =>
    invoke<void>("set_autopilot", { mode }),

  getState: () => invoke<GameState | null>("get_state"),

  getCoreStatus: () => invoke<CoreStatusSnapshot>("get_core_status"),

  startCore: () => invoke<void>("start_core"),
} as const;