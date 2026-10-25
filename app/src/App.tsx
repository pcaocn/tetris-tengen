import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  BACKGROUND,
  FONT_SMOOTH,
  LOGICAL_HEIGHT,
  LOGICAL_WIDTH,
  LAYOUT,
  PANEL_BG,
  TEXT_BRIGHT,
} from "./theme";
import { KEY_MAP } from "./controls";
import { useGameState } from "./hooks/useGameState";
import type { OverlayPhase } from "./components/Overlay";
import { Board } from "./components/Board";
import { NextPreview } from "./components/NextPreview";
import { ScorePanel } from "./components/ScorePanel";
import { StatsPanel } from "./components/StatsPanel";
import { Overlay } from "./components/Overlay";

// Scales the logical space to fit the window with uniform scaling and
// letterboxing; optional integer-scale mode snaps to whole numbers
// (spec 6.4). The UI is laid out in logical units only.
function fitScale(width: number, height: number, integerScale: boolean): number {
  const raw = Math.min(width / LOGICAL_WIDTH, height / LOGICAL_HEIGHT);
  if (integerScale) return Math.max(1, Math.floor(raw));
  return raw;
}

// Konami cheat (owner request 2026-10-25): typing this key sequence on
// the title screen unlocks cheat mode; digits 0-9 then jump the level
// during play.
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

export default function App() {
  const { state, notice, error, retry } = useGameState();
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [integerScale, setIntegerScale] = useState(false); // default off (spec 6.4)
  const hasStartedRef = useRef(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [cheatUnlocked, setCheatUnlocked] = useState(false);
  const cheatRef = useRef(false);
  const cheatPosRef = useRef(0);

  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const send = useCallback((action: string) => {
    invoke("send_input", { action }).catch(() => {});
  }, []);

  const pressStart = useCallback(() => {
    if (error) return;
    const current = stateRef.current;
    if (!hasStartedRef.current || !current || current.status === "game_over") {
      hasStartedRef.current = true;
      invoke("new_game", { level: 0 }).catch(() => {});
    } else {
      invoke("pause").catch(() => {});
    }
  }, [error]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Cheat mode (owner request 2026-10-25): the classic sequence typed
      // on the title screen unlocks it; digits 0-9 jump the level in play.
      if (!hasStartedRef.current && stateRef.current) {
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
        const digit = /^(?:Digit|Numpad)([0-9])$/.exec(e.code);
        if (digit) {
          e.preventDefault();
          invoke("set_level", { level: Number(digit[1]) }).catch(() => {});
          return;
        }
      }
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
    const onKeyUp = (e: KeyboardEvent) => {
      const binding = KEY_MAP[e.code];
      if (!binding?.up) return;
      e.preventDefault();
      send(binding.up);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [pressStart, send]);

  const scale = fitScale(size.width, size.height, integerScale);
  const areaWidth = Math.round(LOGICAL_WIDTH * scale);
  const areaHeight = Math.round(LOGICAL_HEIGHT * scale);

  let phase: OverlayPhase = "connecting";
  if (state) {
    phase = hasStartedRef.current ? state.status : "start";
  }
  if (error) {
    return (
      <div
        style={{
          fontFamily: FONT_SMOOTH,
          color: TEXT_BRIGHT,
          textAlign: "center",
          lineHeight: 2,
        }}
      >
        <p>Cannot reach the Python core.</p>
        <p style={{ fontSize: 24, color: PANEL_BG, maxWidth: 960 }}>{error}</p>
        <button onClick={retry} style={{ padding: "20px 48px", fontSize: 32 }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div
      className="game-area"
      style={{ width: areaWidth, height: areaHeight, background: BACKGROUND }}
    >
      <Board state={state} scale={scale} />
      {/* "NEXT" label above the preview box, as in the captures (spec 6.1). */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.next.x * scale,
          top: (LAYOUT.next.y - LAYOUT.next.labelSize * 1.8) * scale,
          fontFamily: FONT_SMOOTH,
          fontWeight: 700,
          color: TEXT_BRIGHT,
          background: PANEL_BG,
          padding: `0 ${12 * scale}px`,
          fontSize: LAYOUT.next.labelSize * scale,
          lineHeight: `${LAYOUT.next.labelSize * 1.6 * scale}px`,
        }}
      >
        NEXT
      </div>
      <NextPreview state={state} scale={scale} />
      <ScorePanel state={state} scale={scale} />
      <StatsPanel state={state} scale={scale} />
      <Overlay
        phase={phase}
        score={state?.score ?? 0}
        notice={notice}
        scale={scale}
        cheat={cheatUnlocked}
      />
      {/* Integer-scale toggle (spec 6.4, optional, default off). */}
      <label
        style={{
          position: "absolute",
          right: 16 * scale,
          bottom: 8 * scale,
          fontFamily: FONT_SMOOTH,
          color: PANEL_BG,
          fontSize: 24 * scale,
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}
      >
        <input
          type="checkbox"
          checked={integerScale}
          onChange={(e) => setIntegerScale(e.target.checked)}
        />
        INT SCALE
      </label>
    </div>
  );
}
