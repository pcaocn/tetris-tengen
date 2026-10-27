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

const MUSIC_MENU = ["Silent", "Loginska", "Bradinsky", "Kalinka", "Troika"];
const HANDICAP_LEVELS = [0, 3, 6, 9, 12];

// The cathedral scene drawn dimmed as the options page background
// (owner request 2026-10-25).
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
