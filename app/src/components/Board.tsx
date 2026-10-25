import { useEffect, useRef } from "react";
import {
  CLEAR_LABELS,
  FALLING_COLORS,
  FONT_SMOOTH,
  FRAME_DARK,
  FIELD_BG,
  FRAME_LIGHT,
  LAYOUT,
  LOCKED_COLORS,
  TEXT_BRIGHT,
  WIPE_FRAMES_PER_PAIR,
  type BlockTrio,
} from "../theme";
import type { GameState } from "../hooks/useGameState";
import { drawBlock, logicalCanvas } from "./draw";

// Draws the playfield on a canvas: the Tengen double frame (dark blue outer,
// light blue inner, as sampled), locked cells in the level's locked color,
// and the falling piece in its own three-tone color (spec 6.2). During a
// line clear the completed rows are wiped from the center outward, one
// column-pair per WIPE_FRAMES_PER_PAIR frames, with the award label shown
// over the field (spec 4.5). Redraws when the state or the scale changes.
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
    // Line-clear wipe (spec 4.5, owner decision 2026-10-24): completed
    // rows empty from the center to both sides — pair k ({4-k, 5+k}) is
    // gone once frame >= (k+1) * WIPE_FRAMES_PER_PAIR.
    const clearing = state.clearing;
    const clearingRows = clearing ? new Set(clearing.rows) : null;
    const wipedCols = new Set<number>();
    if (clearing) {
      const pairs = Math.min(5, Math.floor(clearing.frame / WIPE_FRAMES_PER_PAIR));
      for (let k = 0; k < pairs; k++) {
        wipedCols.add(4 - k);
        wipedCols.add(5 + k);
      }
    }
    state.board.forEach((row, rowIdx) => {
      row.forEach((value, colIdx) => {
        if (value > 0) {
          if (clearingRows?.has(rowIdx) && wipedCols.has(colIdx)) return;
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

  const { x, y, cols, cell, frameOuter, frameInner } = LAYOUT.playfield;
  const clearingRows = state?.clearing?.rows ?? [];
  const label = state?.clearing
    ? CLEAR_LABELS[state.clearing.rows.length] ?? CLEAR_LABELS[1]
    : null;
  // The award label renders inside the row(s) being cleared (owner
  // decision 2026-10-24): centered on the cleared band.
  const bandTop = (y + frameOuter + frameInner + Math.min(...clearingRows) * cell) * scale;
  const bandHeight = clearingRows.length * cell * scale;
  return (
    <>
      <canvas
        ref={canvasRef}
        style={{ position: "absolute", left: x * scale, top: y * scale }}
      />
      {label && clearingRows.length > 0 && (
        <div
          style={{
            position: "absolute",
            left: (x + frameOuter + frameInner) * scale,
            top: bandTop,
            width: cols * cell * scale,
            height: bandHeight,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            fontSize: Math.min(96, cell * 0.9) * scale,
            color: TEXT_BRIGHT,
            textShadow: `${4 * scale}px ${4 * scale}px 0 rgba(0, 0, 0, 0.5)`,
          }}
        >
          {label}
        </div>
      )}
    </>
  );
}
