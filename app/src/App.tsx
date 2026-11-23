// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The root component: screen state, layout, and wiring. The audio
// lifecycle lives in useGameAudio; keyboard routing lives in
// useGameKeyboard. App owns visible screen/menu state and passes current
// values/callbacks to those hooks.
//
// THE DATA FLOW, END TO END
// --------------------------
//   Python core --(JSON on stdout)--> Rust shell --(Tauri "game-state")
//     --> useGameState --> `state` HERE --> <Board/>, <ScorePanel/>, ...
//   Keyboard hook --(gameApi "send_input" / "new_game" / ...)-->
//     Rust shell --(JSON on stdin)--> Python core.
// The UI's only outputs are those gameApi commands and these draw
// decisions. No rule of Tetris is computed in this file.
import { useCallback, useEffect, useRef, useState } from "react";
import { gameApi } from "./api/game";
import {
  BACKGROUND,
  FONT_SMOOTH,
  LOGICAL_HEIGHT,
  LOGICAL_WIDTH,
  LAYOUT,
  PANEL_BG,
  TEXT_BRIGHT,
} from "./theme";
import { useGameState } from "./hooks/useGameState";
import {
  MUSIC_CYCLE,
  MUSIC_IDS,
  useGameAudio,
} from "./hooks/useGameAudio";
import { useGameKeyboard } from "./hooks/useGameKeyboard";
import type { OverlayPhase } from "./components/Overlay";
// (The component imports below pull in the renderers; each is commented
// in its own file.)
import { Board } from "./components/Board";
import { NextPreview } from "./components/NextPreview";
import { ScorePanel } from "./components/ScorePanel";
import { StatsPanel } from "./components/StatsPanel";
import { Overlay } from "./components/Overlay";

// The options-page music menu. Index i pairs with MUSIC_IDS[i]: "Silent"
// -> null (no music), "Loginska" -> "02", and so on. The protocol values
// live in useGameAudio; this is the display list.
const MUSIC_MENU = ["Silent", "Loginska", "Bradinsky", "Kalinka", "Troika"];
// Handicap rows (owner request 2026-10-25): unfinished garbage rows.
// Indexed in lockstep with OptionsScreen's display list; the VALUE here
// is what reaches new_game (rows dealt at spawn).
const HANDICAP_LEVELS = [0, 3, 6, 9, 12];

// Scales the logical space to fit the window with uniform scaling and
// letterboxing; optional integer-scale mode snaps to whole numbers
// (spec 6.4). The UI is laid out in logical units only.
function fitScale(width: number, height: number, integerScale: boolean): number {
  const raw = Math.min(width / LOGICAL_WIDTH, height / LOGICAL_HEIGHT);
  if (integerScale) return Math.max(1, Math.floor(raw));
  return raw;
}

/**
 * The root component. Reading order inside the body:
 *   1. state + screen/menu state
 *   2. callbacks: send, pressStart
 *   3. hooks: audio, keyboard
 *   4. derived layout numbers and the JSX tree
 */
export default function App() {
  // The single game-state subscription (see useGameState.ts).
  const { state, notice, error, retry } = useGameState();
  // Window size, tracked to recompute the scale on every resize.
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [integerScale, setIntegerScale] = useState(false); // default off (spec 6.4)
  // "Has a game ever been started" — the title/options -> game gate.
  // The ref mirror exists for the keyboard hook and pressStart.
  const hasStartedRef = useRef(false);
  const [started, setStarted] = useState(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [cheatUnlocked, setCheatUnlocked] = useState(false);
  // Title -> options -> game flow (owner request 2026-10-25): the title
  // shows only the cathedral; Enter opens the options page.
  const [atOptions, setAtOptions] = useState(false);
  const atOptionsRef = useRef(false);
  // Title music menu (owner request 2026-10-25).
  const [musicSel, setMusicSel] = useState(0);
  const musicSelRef = useRef(0);
  // "The user moved the music menu at least once" — gates the preview.
  const [menuTouched, setMenuTouched] = useState(false);
  // Title handicap menu (owner request 2026-10-25).
  const [handicapSel, setHandicapSel] = useState(0);
  const handicapSelRef = useRef(0);
  // Options page: which column has focus (0 = music, 1 = handicap).
  const [activeCol, setActiveCol] = useState(0);

  // Window size tracking: feeds fitScale. Cleanup removes the listener —
  // under StrictMode's double-mount a leaked listener would double-fire
  // setSize and re-render the layout twice per resize.
  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /**
   * Forwards one protocol action to the core via the Rust shell.
   * Fire-and-forget: the core's reply arrives as the next game-state
   * event, not as a return value, so a failed invoke just means the
   * input is lost (no toast, no retry — the next input supersedes it).
   */
  const send = useCallback((action: string) => {
    gameApi.sendInput(action).catch(() => {});
  }, []);

  /**
   * The Enter button's meaning, by where you are:
   *   title screen  -> open the options page (no core call yet)
   *   options page  -> start the game: new_game(level 0, chosen music,
   *                    chosen handicap) — this is the ONLY call that
   *                    creates a game
   *   game over     -> another new_game (restart)
   *   otherwise     -> toggle pause
   */
  const pressStart = useCallback(() => {
    if (error) return;
    const current = stateRef.current;
    if (!hasStartedRef.current) {
      if (!atOptionsRef.current) {
        atOptionsRef.current = true;
        setAtOptions(true);
        return;
      }
      hasStartedRef.current = true;
      setStarted(true);
      gameApi
        .newGame({
          level: 0,
          music: MUSIC_IDS[musicSelRef.current],
          handicap: HANDICAP_LEVELS[handicapSelRef.current],
        })
        .catch(() => {});
      return;
    }
    if (!current || current.status === "game_over") {
      // Restart path — same parameters as the first start, so the chosen
      // music and handicap survive across games.
      gameApi
        .newGame({
          level: 0,
          music: MUSIC_IDS[musicSelRef.current],
          handicap: HANDICAP_LEVELS[handicapSelRef.current],
        })
        .catch(() => {});
    } else {
      gameApi.pause().catch(() => {});
    }
  }, [error]);

  // Audio resources and playback lifecycle. The hook owns the two theme
  // elements, the cue element, the WebAudio context, and the gesture
  // unlock; it consumes the pure planners in audioPlan.ts / sfxPlan.ts.
  const { audioARef, audioBRef, cueRef, onMusicEnded, playSfx } =
    useGameAudio({
      state,
      started,
      atOptions,
      musicSel,
      menuTouched,
    });

  // Keyboard routing. App owns screen/menu state; the hook owns the
  // window listeners, repeat filtering, Konami tracking, and focus-loss
  // releases.
  useGameKeyboard({
    stateRef,
    hasStartedRef,
    atOptionsRef,
    musicSelRef,
    handicapSelRef,
    cheatUnlocked,
    activeCol,
    musicMenuLength: MUSIC_MENU.length,
    handicapCount: HANDICAP_LEVELS.length,
    musicCycle: MUSIC_CYCLE,
    pressStart,
    send,
    playMenuSfx: playSfx,
    setCheatUnlocked,
    setActiveCol,
    setMusicSel,
    setHandicapSel,
    setMenuTouched,
  });

  // Derived layout: the scale for this exact window size, and the on-screen
  // box of the logical rectangle. Math.round because CSS px are integral
  // (fractional sizes would blur the letterbox edge).
  const scale = fitScale(size.width, size.height, integerScale);
  const areaWidth = Math.round(LOGICAL_WIDTH * scale);
  const areaHeight = Math.round(LOGICAL_HEIGHT * scale);

  // Which overlay to show. Priority: a real error page wins over
  // everything; then the pre-game screens; then the core's status. The
  // hasStartedRef (not `started`) keeps the title up through the render
  // where the state flips, avoiding a one-frame flash of "playing".
  let phase: OverlayPhase = "connecting";
  if (state) {
    phase = hasStartedRef.current
      ? (state.status as OverlayPhase)
      : atOptions
        ? "options"
        : "start";
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

  // The letterboxed game area: exactly the scaled logical rectangle,
  // centered by styles.css. Every child positions absolutely inside it,
  // so the whole UI scales as one unit.
  return (
    <div
      className="game-area"
      style={{ width: areaWidth, height: areaHeight, background: BACKGROUND }}
    >
      <Board state={state} scale={scale} />
      {/* Autopilot indicator (owner request 2026-10-27/28). */}
      {state?.autopilot && state?.status !== "game_over" && (
        <div
          style={{
            position: "absolute",
            left: LAYOUT.playfield.x * scale,
            top: (LAYOUT.playfield.y - 56) * scale,
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            color: TEXT_BRIGHT,
            background: PANEL_BG,
            padding: `0 ${12 * scale}px`,
            fontSize: 36 * scale,
            lineHeight: `${36 * 1.6 * scale}px`,
          }}
        >
          {state.autopilot === "highscore"
            ? "AUTO - HIGH SCORE"
            : "AUTO - QUICK CLEAR LINES"}
        </div>
      )}
      {/* Theme music: two elements, so the playlist can hand over to a
          preloaded track without a gap, and the one-shot cues on a third,
          over the paused theme. */}
      <audio ref={audioARef} onEnded={onMusicEnded} preload="auto" />
      <audio ref={audioBRef} onEnded={onMusicEnded} preload="auto" />
      <audio ref={cueRef} preload="auto" />
      {/* "NEXT" label above the preview box. */}
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
        musicSel={musicSel}
        handicap={HANDICAP_LEVELS[handicapSel]}
        activeCol={activeCol}
        topScores={state?.top_scores}
        topRun={state?.top_run}
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