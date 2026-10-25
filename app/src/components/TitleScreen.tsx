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
  TITLE_TEXT_SIZE,
} from "../theme";
import { drawSaintBasilsScene } from "./cathedral";
import { logicalCanvas } from "./draw";

const SCENE_W = 1960;
const SCENE_H = 1476;

// The cathedral scene fills the inner frame area of the title screen,
// adapted from the owner's reference render (png/Saint_Basil's_
// Cathedral_render.ts), scaled to the canvas. When the cheat code has
// been entered, the scene redraws with the central tent tower's tip dome
// in green — the cheat indicator (owner request 2026-10-25).
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
function Logo({ scale }: { scale: number }) {
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

// Title screen (spec 5, owner request 2026-10-24): the composition follows
// png/screenshot_00.png — gold border bands with green diamond studs, a
// full-screen light-blue double frame, the red italic TETRIS wordmark, the
// Saint Basil's Cathedral scene (from the owner's reference render), and
// two gold text lines (the second blinks as the start prompt).
export function TitleScreen({ scale, cheat }: { scale: number; cheat?: boolean }) {
  const bandHeight = 48 * scale;
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
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 120 * scale,
            textAlign: "center",
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            fontSize: TITLE_TEXT_SIZE * scale,
            color: TITLE_GOLD,
            letterSpacing: 6 * scale,
            textShadow: `${2 * scale}px ${2 * scale}px 0 rgba(0, 0, 0, 0.25)`,
          }}
        >
          TENGEN-STYLE TRIBUTE
        </div>
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
