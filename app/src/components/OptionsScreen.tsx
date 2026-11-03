import { useEffect, useRef } from "react";
import {
  BACKGROUND,
  FONT_SMOOTH,
  FRAME_DARK,
  FRAME_LIGHT,
  TITLE_GOLD,
} from "../theme";
import { drawSaintBasilsScene } from "./cathedral";
import { logicalCanvas } from "./draw";

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// The options page, shown between the title and the game (owner request
// 2026-10-25): the cathedral scene dimmed behind two menu columns — MUSIC
// on the left, HANDICAP on the right — and a blinking start prompt.
//
// WHO OWNS THE STATE: none of it. The selection indices live in App.tsx
// (musicSel, handicapSel, activeCol) because App also routes the keys and
// starts the game with the chosen values; this component is a pure
// renderer of (selection, focus). Keyboard handling and the Enter->start
// transition are in App.tsx's keydown effect.
//
// LOCAL COPIES OF THE APP'S CONSTANTS: MUSIC_MENU and HANDICAP_LEVELS are
// duplicated here (App.tsx has the same arrays) so the display labels stay
// with the display. They must stay in sync with App's MUSIC_IDS /
// HANDICAP_LEVELS, which carry the protocol values — the menu index here
// and the value sent in `new_game` are parallel arrays of the same length.
const MUSIC_MENU = ["Silent", "Loginska", "Bradinsky", "Kalinka", "Troika"];
// Handicap = number of garbage rows dealt at spawn (owner request
// 2026-10-25). 0 rows = no handicap; 12 is the hardest.
const HANDICAP_LEVELS = [0, 3, 6, 9, 12];

// The cathedral scene drawn dimmed as the options page background
// (owner request 2026-10-25).
//
// It is the same drawSaintBasilsScene() as the title screen, at the same
// 1960x1476 scene size, just wrapped in a div with opacity 0.3 — visual
// continuity between the two screens without a second piece of art. The
// 44/300 offset pushes it down so the columns have clear sky behind them.
function SceneBackdrop({ scale }: { scale: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = logicalCanvas(canvas, 1960, 1476, scale);
    drawSaintBasilsScene(ctx, 1960, 1476);
  }, [scale]);
  return (
    <div style={{ position: "absolute", inset: 0, opacity: 0.3 }}>
      <canvas
        ref={canvasRef}
        style={{ position: "absolute", left: 44 * scale, top: 300 * scale }}
      />
    </div>
  );
}

// Options page (owner request 2026-10-25): reached from the title with
// Enter. Left column selects the gameplay music (previewed on landing);
// right column selects the handicap rows. Up/Down move within the
// focused column, Left/Right switch focus, Enter starts the game. All
// options are listed as full menus.
//
// One reusable column, told which row is selected and whether it has
// keyboard focus — the highlight styling is all derived from those two
// facts, so the component needs no state of its own.
function Column({
  title,
  items,
  selected,
  active,
  x,
  scale,
}: {
  title: string;
  items: (string | number)[];
  selected: number;
  active: boolean;
  x: number;
  scale: number;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: x * scale,
        top: 420 * scale,
        display: "flex",
        flexDirection: "column",
        gap: 14 * scale,
        opacity: active ? 1 : 0.55,
      }}
    >
      <div
        style={{
          fontFamily: FONT_SMOOTH,
          fontWeight: 700,
          fontSize: 48 * scale,
          color: active ? TITLE_GOLD : "#ffffff",
          letterSpacing: 4 * scale,
          textShadow: `${2 * scale}px ${2 * scale}px 0 rgba(0, 0, 0, 0.4)`,
        }}
      >
        {title}
      </div>
      {items.map((item, i) => {
        const sel = i === selected;
        // Row styling: the selected row is a gold bar with black text; the
        // focused column ALSO draws a white outline on its selected row, so
        // on a two-column page you can always tell (a) which row is chosen
        // and (b) which column the keys will move. The unfocused column is
        // additionally dimmed to 0.55 opacity by the container above.
        return (
          <div
            key={item}
            style={{
              fontFamily: FONT_SMOOTH,
              fontWeight: sel ? 700 : 400,
              fontSize: 40 * scale,
              lineHeight: `${72 * scale}px`,
              padding: `0 ${24 * scale}px`,
              width: 420 * scale,
              background: sel ? TITLE_GOLD : "rgba(128, 128, 128, 0.85)",
              color: sel ? "#000000" : "#ffffff",
              border: sel && active ? `${4 * scale}px solid #ffffff` : "none",
              boxSizing: "border-box",
            }}
          >
            {item}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Renders the whole options page.
 *
 * @param musicSel  index into MUSIC_MENU (and App's parallel MUSIC_IDS).
 * @param handicap  the selected handicap VALUE (rows), not an index — hence
 *                  the indexOf() lookup in the HANDICAP column below.
 * @param activeCol 0 = music column focused, 1 = handicap column focused.
 */
export function OptionsScreen({
  scale,
  musicSel,
  handicap,
  activeCol,
}: {
  scale: number;
  musicSel: number;
  handicap: number;
  activeCol: number;
}) {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: BACKGROUND,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ position: "relative", flex: 1 }}>
        {/* The same three-layer frame as the title screen (24/12/20 px
            insets): dark band, light band, then the black interior —
            painted with plain inset divs instead of canvas because they
            are pure rectangles. */}
        <div
          style={{ position: "absolute", inset: `${24 * scale}px`, background: FRAME_DARK }}
        />
        <div
          style={{
            position: "absolute",
            inset: `${(24 + 12) * scale}px`,
            background: FRAME_LIGHT,
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: `${(24 + 20) * scale}px`,
            background: BACKGROUND,
          }}
        />
        <SceneBackdrop scale={scale} />
        <Column
          title="MUSIC"
          items={MUSIC_MENU}
          selected={musicSel}
          active={activeCol === 0}
          x={240}
          scale={scale}
        />
        {/* indexOf because the prop is the value (rows), not the index. */}
        <Column
          title="HANDICAP"
          items={HANDICAP_LEVELS}
          selected={HANDICAP_LEVELS.indexOf(handicap)}
          active={activeCol === 1}
          x={1300}
          scale={scale}
        />
        <div
          className="blink"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 90 * scale,
            textAlign: "center",
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            fontSize: 44 * scale,
            color: TITLE_GOLD,
            letterSpacing: 4 * scale,
          }}
        >
          PRESS ENTER TO START
        </div>
      </div>
    </div>
  );
}
