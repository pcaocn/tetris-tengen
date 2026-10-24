import { useEffect, useRef } from "react";
import {
  DISPLAY_SHAPES,
  FALLING_COLORS,
  FONT_SMOOTH,
  LAYOUT,
  PANEL_BG,
  STATS_ORDER,
  TEXT_BRIGHT,
  TEXT_COLOR,
} from "../theme";
import type { GameState } from "../hooks/useGameState";
import { drawBlock, logicalCanvas } from "./draw";

const KINDS: readonly string[] = STATS_ORDER;

// Per-piece spawn counters (spec 4.9), reproducing the authentic stats
// panel from the captures: a mini piece glyph in its own color beside each
// count, in the panel's order (I, T, O, J, L, S, Z).
function MiniGlyph({ kind, cell, scale }: { kind: string; cell: number; scale: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const cells = DISPLAY_SHAPES[kind];
    const trio = FALLING_COLORS[kind];
    if (!canvas || !cells || !trio) return;
    const w = 4 * cell + 8;
    const h = 4 * cell + 8;
    const ctx = logicalCanvas(canvas, w, h, scale);
    const xs = cells.map(([cx]) => cx);
    const ys = cells.map(([, cy]) => cy);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const originX = (w - (Math.max(...xs) - minX + 1) * cell) / 2;
    const originY = (h - (Math.max(...ys) - minY + 1) * cell) / 2;
    for (const [cx, cy] of cells) {
      drawBlock(ctx, originX + (cx - minX) * cell, originY + (cy - minY) * cell, cell, trio);
    }
  }, [kind, cell, scale]);

  return <canvas ref={ref} />;
}

export function StatsPanel({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const { x, y, rowHeight, titleSize, labelSize, cell } = LAYOUT.stats;
  const stats = state?.stats ?? {};
  const title = {
    position: "absolute" as const,
    left: x * scale,
    top: y * scale,
  };
  return (
    <>
      <div style={title}>
        <div
          style={{
            background: PANEL_BG,
            color: TEXT_BRIGHT,
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            fontSize: titleSize * scale,
            lineHeight: `${titleSize * 1.6 * scale}px`,
            padding: `0 ${12 * scale}px`,
            display: "inline-block",
          }}
        >
          STATS
        </div>
      </div>
      {KINDS.map((kind, i) => (
        <div
          key={kind}
          style={{
            position: "absolute",
            left: x * scale,
            top: (y + (i + 1) * rowHeight) * scale,
            display: "flex",
            alignItems: "center",
            gap: 16 * scale,
          }}
        >
          <MiniGlyph kind={kind} cell={cell} scale={scale} />
          <div
            style={{
              color: TEXT_COLOR,
              fontFamily: FONT_SMOOTH,
              fontSize: labelSize * scale,
            }}
          >
            {String(stats[kind] ?? 0).padStart(3, "0")}
          </div>
        </div>
      ))}
    </>
  );
}
