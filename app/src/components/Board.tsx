import { useEffect, useRef } from "react";
import {
  FALLING_COLORS,
  FRAME_DARK,
  FIELD_BG,
  FRAME_LIGHT,
  LAYOUT,
  LOCKED_COLORS,
  type BlockTrio,
} from "../theme";
import type { GameState } from "../hooks/useGameState";
import { drawBlock, drawCellColor, logicalCanvas } from "./draw";

// Draws the playfield on a canvas: the Tengen double frame (dark blue outer,
// light blue inner, as sampled), locked cells in the level's locked color,
// and the falling piece in its own three-tone color (spec 6.2). Redraws only
// when the state or the scale changes (spec 6.4).
export function Board({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { cols, rows, cell, frameOuter, frameInner } = LAYOUT.playfield;
    const fieldW = cols * cell;
    const fieldH = rows * cell;
    const totalW = fieldW + (frameOuter + frameInner) * 2;
    const totalH = fieldH + (frameOuter + frameInner) * 2;
    const ctx = logicalCanvas(canvas, totalW, totalH, scale);

    ctx.fillStyle = FRAME_DARK;
    ctx.fillRect(0, 0, totalW, totalH);
    ctx.fillStyle = FRAME_LIGHT;
    ctx.fillRect(
      frameOuter,
      frameOuter,
      totalW - frameOuter * 2,
      totalH - frameOuter * 2,
    );
    ctx.fillStyle = FIELD_BG;
    ctx.fillRect(
      frameOuter + frameInner,
      frameOuter + frameInner,
      fieldW,
      fieldH,
    );

    if (!state) return;
    const origin = frameOuter + frameInner;
    const locked = LOCKED_COLORS[state.color_index % LOCKED_COLORS.length];
    // Rows dissolving in the line-clear animation (spec 4.5) flicker
    // through the locked color's light/mid/dark shades with per-column
    // gaps, like the reference capture; everything else draws normally.
    const clearing = state.clearing;
    const clearingRows = clearing ? new Set(clearing.rows) : null;
    const phase = clearing ? Math.floor(clearing.frame / 2) : 0;
    const shades = [locked.light, locked.mid, locked.dark];
    state.board.forEach((row, rowIdx) => {
      row.forEach((value, colIdx) => {
        if (value > 0) {
          if (clearingRows?.has(rowIdx)) {
            const t = (phase + colIdx) % 4;
            if (t < 3) {
              drawCellColor(
                ctx,
                origin + colIdx * cell,
                origin + rowIdx * cell,
                cell,
                shades[t],
              );
            }
            return;
          }
          drawBlock(
            ctx,
            origin + colIdx * cell,
            origin + rowIdx * cell,
            cell,
            locked,
          );
        }
      });
    });
    if (state.current) {
      const falling: BlockTrio | undefined = FALLING_COLORS[state.current.kind];
      if (falling) {
        for (const [cx, cy] of state.current.cells) {
          // Defensive clip: pieces spawn at the visible top, so cells are
          // normally within the 20-row protocol board (spec 2.2).
          if (cy < 0 || cy >= rows || cx < 0 || cx >= cols) continue;
          drawBlock(ctx, origin + cx * cell, origin + cy * cell, cell, falling);
        }
      }
    }
  }, [state, scale]);

  const { x, y } = LAYOUT.playfield;
  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", left: x * scale, top: y * scale }}
    />
  );
}
