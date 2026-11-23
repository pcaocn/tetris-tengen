import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import { gameApi } from "../api/game";
import { KEY_MAP } from "../controls";
import type { GameState } from "../types/game";

// Konami cheat (owner request 2026-10-25): typing this key sequence on
// the title screen unlocks cheat mode; digits 0-9 then jump the level
// during play. `cheatPosRef` is the KMP-style prefix pointer: on a
// mismatch it restarts at 1 when the key is the first entry, so repeated
// Up presses still walk the sequence.
const CHEAT_CODE = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "KeyB",
  "KeyA",
];

export interface GameKeyboardOptions {
  stateRef: { current: GameState | null };
  hasStartedRef: { current: boolean };
  atOptionsRef: { current: boolean };
  musicSelRef: { current: number };
  handicapSelRef: { current: number };
  cheatUnlocked: boolean;
  activeCol: number;
  musicMenuLength: number;
  handicapCount: number;
  musicCycle: string[];
  pressStart: () => void;
  send: (action: string) => void;
  playMenuSfx: (name: string) => void;
  setCheatUnlocked: Dispatch<SetStateAction<boolean>>;
  setActiveCol: Dispatch<SetStateAction<number>>;
  setMusicSel: Dispatch<SetStateAction<number>>;
  setHandicapSel: Dispatch<SetStateAction<number>>;
  setMenuTouched: Dispatch<SetStateAction<boolean>>;
}

/**
 * Owns the window-level keydown/keyup pair. App owns screen and menu
 * state; this hook only translates input into callbacks and command
 * invocations. Listener registration and cleanup live here.
 */
export function useGameKeyboard({
  stateRef,
  hasStartedRef,
  atOptionsRef,
  musicSelRef,
  handicapSelRef,
  cheatUnlocked,
  activeCol,
  musicMenuLength,
  handicapCount,
  musicCycle,
  pressStart,
  send,
  playMenuSfx,
  setCheatUnlocked,
  setActiveCol,
  setMusicSel,
  setHandicapSel,
  setMenuTouched,
}: GameKeyboardOptions) {
  const cheatRef = useRef(cheatUnlocked);
  const cheatPosRef = useRef(0);
  const activeColRef = useRef(activeCol);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Branch 1: pre-game screens. The cheat sequence tracks on every
      // pre-game key, even menu keys.
      if (!hasStartedRef.current && stateRef.current) {
        if (atOptionsRef.current) {
          if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
            const col = activeColRef.current === 0 ? 1 : 0;
            activeColRef.current = col;
            setActiveCol(col);
          } else if (e.code === "ArrowUp" || e.code === "ArrowDown") {
            const dir = e.code === "ArrowUp" ? -1 : 1;
            void playMenuSfx(dir === 1 ? "select1" : "select2");
            if (activeColRef.current === 0) {
              setMusicSel((s) => {
                const next = (s + dir + musicMenuLength) % musicMenuLength;
                musicSelRef.current = next;
                return next;
              });
              setMenuTouched(true);
            } else {
              setHandicapSel((s) => {
                const next = (s + dir + handicapCount) % handicapCount;
                handicapSelRef.current = next;
                return next;
              });
            }
          }
        }
        if (e.code === CHEAT_CODE[cheatPosRef.current]) {
          cheatPosRef.current += 1;
          if (cheatPosRef.current === CHEAT_CODE.length) {
            cheatPosRef.current = 0;
            cheatRef.current = true;
            setCheatUnlocked(true);
          }
        } else {
          cheatPosRef.current = e.code === CHEAT_CODE[0] ? 1 : 0;
        }
      } else if (cheatRef.current && stateRef.current?.status === "playing") {
        // Branch 2: in-game cheats. Each returns after handling, so a
        // cheat key never ALSO reaches the KEY_MAP below.
        const digit = /^(?:Digit|Numpad)([0-9])$/.exec(e.code);
        if (digit) {
          e.preventDefault();
          gameApi.setLevel(Number(digit[1])).catch(() => {});
          return;
        }
        if (e.code === "Backquote") {
          e.preventDefault();
          const current = stateRef.current?.music_track ?? musicCycle[0];
          const idx = musicCycle.indexOf(current);
          const next = musicCycle[(idx + 1) % musicCycle.length];
          gameApi.setMusic(next).catch(() => {});
          return;
        }
        if (e.code === "Home") {
          e.preventDefault();
          const next =
            stateRef.current?.autopilot === "highscore" ? null : "highscore";
          gameApi.setAutopilot(next).catch(() => {});
          return;
        }
        if (e.code === "End") {
          e.preventDefault();
          const next = stateRef.current?.autopilot === "quick" ? null : "quick";
          gameApi.setAutopilot(next).catch(() => {});
          return;
        }
      }
      // Branch 3: normal in-game controls.
      const binding = KEY_MAP[e.code];
      if (!binding) return;
      e.preventDefault();
      if (e.repeat) return; // auto-repeat comes from Python DAS (spec 2.4)
      if (binding.down === "start") {
        pressStart();
        return;
      }
      send(binding.down);
    };

    // keyup has no menu/cheat branches: only the DAS-style release
    // half-pairs (left_off, soft_drop_off, ...) matter.
    const onKeyUp = (e: KeyboardEvent) => {
      const binding = KEY_MAP[e.code];
      if (!binding?.up) return;
      e.preventDefault();
      send(binding.up);
    };

    // Focus loss may swallow the matching keyup. Release every held-key
    // latch so the core cannot keep auto-shifting or soft-dropping.
    const releaseHeld = () => {
      send("left_off");
      send("right_off");
      send("soft_drop_off");
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") releaseHeld();
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", releaseHeld);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", releaseHeld);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [
    stateRef,
    hasStartedRef,
    atOptionsRef,
    musicSelRef,
    handicapSelRef,
    musicMenuLength,
    handicapCount,
    musicCycle,
    pressStart,
    send,
    playMenuSfx,
    setCheatUnlocked,
    setActiveCol,
    setMusicSel,
    setHandicapSel,
    setMenuTouched,
  ]);
}