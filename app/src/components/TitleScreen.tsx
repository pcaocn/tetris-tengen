import { useEffect, useRef } from "react";
import {
  BACKGROUND,
  FALLING_COLORS,
  FONT_SMOOTH,
  FRAME_DARK,
  FRAME_LIGHT,
  TITLE_GOLD,
  TITLE_GREEN,
  TITLE_PROMPT_SIZE,
} from "../theme";
import { drawSaintBasilsScene } from "./cathedral";
import { logicalCanvas } from "./draw";

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// The title screen (spec 5): gold bands with green diamond studs, the
// full-screen double frame, the cathedral canvas scene, the red italic
// TETRIS wordmark, and the blinking PRESS ENTER prompt. It is a pure
// function of (scale, cheat) — no state, no listeners; the keyboard that
// drives it (Enter -> options, the Konami sequence) lives in
// hooks/useGameKeyboard.ts.
//
// The scene art is one canvas; everything else is styled divs. The bands
// and frame are rectangles, so DOM is simpler than canvas paths there.
const SCENE_W = 1960;
const SCENE_H = 1650;
// Scene canvas size in logical units — slightly SMALLER than the full
// 2048x1920 screen so it slides inside the double frame with a margin;
// TitleScreen positions it at (44, 44) inside the frame area.

// The cathedral scene is drawn in `cathedral.ts`, with the foreground
// monument and foliage in `cathedralForeground.ts`: a clean cover-inspired
// central red tent with a gold cap, surrounding patterned onion domes,
// arcaded galleries, and a shared baseline. When the cheat code has been
// entered, only the central cap turns green — the cheat indicator
// (owner request 2026-10-25).
//
// `cheat` is threaded into the canvas drawing, which is why this is a
// prop and not CSS: the recolor happens inside the renderer, not on a DOM
// node.
function SceneArt({ scale, cheat }: { scale: number; cheat?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = logicalCanvas(canvas, SCENE_W, SCENE_H, scale);
    drawSaintBasilsScene(ctx, SCENE_W, SCENE_H, cheat ?? false);
  }, [scale, cheat]);
  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", left: 44 * scale, top: 44 * scale }}
    />
  );
}

// Big red italic TETRIS wordmark over the sky, as in the reference
// capture (a red italic wordmark sits above the cathedral).
//
// The "red" is a vertical gradient from the I-piece's light tone to its
// dark tone (FALLING_COLORS.I), clipped to the letterforms via the
// background-clip: text + transparent color trick. Original Tengen had a
// solid 3D wordmark; this is the owner's stylized stand-in (no original
// artwork copied, spec 1 non-goals).
function Logo({ scale }: { scale: number }) {
  // 170 logical px tall, x1.3 line box so the italic ascenders/descenders
  // are not clipped by the flex row.
  const size = 170 * scale;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: 90 * scale,
        height: size * 1.3,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: FONT_SMOOTH,
        fontStyle: "italic",
        fontWeight: 800,
        fontSize: size,
        letterSpacing: 20 * scale,
        backgroundImage: `linear-gradient(${FALLING_COLORS.I.light}, ${FALLING_COLORS.I.dark})`,
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        color: "transparent",
      }}
    >
      TETRIS
    </div>
  );
}

// Title screen (owner request 2026-10-25, refined the same day): the
// cathedral scene, the red italic TETRIS wordmark, and a blinking PRESS
// ENTER prompt. The introduction theme (01) plays; all menus moved to
// the options page reached with Enter.
/**
 * Renders the full title screen. `cheat` recolors the cathedral's tip
 * dome green once the Konami code has been entered — the only visible
 * sign the cheats are armed.
 */
export function TitleScreen({ scale, cheat }: { scale: number; cheat?: boolean }) {
  const bandHeight = 48 * scale;
  // The green diamond studs along the top and bottom gold bands: 13 of
  // them, evenly spaced 150 logical px apart starting at x=80, each a
  // 34px green square rotated 45deg (the cheap way to draw a diamond).
  // 13 * 150 = 1950 logical px ≈ the full 2048 width, so the row spans
  // the screen edge to edge.
  const diamonds = [];
  for (let i = 0; i < 13; i++) {
    const size = 34 * scale;
    diamonds.push(
      <div
        key={i}
        style={{
          position: "absolute",
          left: (80 + i * 150) * scale - size / 2,
          top: bandHeight / 2 - size / 2,
          width: size,
          height: size,
          background: TITLE_GREEN,
          transform: "rotate(45deg)",
        }}
      />,
    );
  }
  const band = (
    <div style={{ position: "relative", height: bandHeight, background: TITLE_GOLD }}>
      {diamonds}
    </div>
  );
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
      {band}
      <div style={{ position: "relative", flex: 1 }}>
        {/* The double frame again (24/12/20 insets), same recipe as
            OptionsScreen — dark band, light band, black interior. */}
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
        <SceneArt scale={scale} cheat={cheat} />
        <Logo scale={scale} />
        <div
          className="blink"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 50 * scale,
            textAlign: "center",
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            fontSize: TITLE_PROMPT_SIZE * scale,
            color: TITLE_GOLD,
            letterSpacing: 4 * scale,
            textShadow: `${2 * scale}px ${2 * scale}px 0 rgba(0, 0, 0, 0.25)`,
          }}
        >
          PRESS ENTER
        </div>
      </div>
      {band}
    </div>
  );
}
