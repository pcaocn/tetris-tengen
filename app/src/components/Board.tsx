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

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// Draws the playfield on a canvas: the Tengen double frame (dark blue outer,
// light blue inner, as sampled), locked cells in the level's locked color,
// and the falling piece in its own three-tone color (spec 6.2). During a
// line clear the completed rows are wiped from the center outward, one
// column-pair per WIPE_FRAMES_PER_PAIR frames, with the award label shown
// over the field (spec 4.5). Redraws when the state or the scale changes.
//
// WHAT IS STATE AND WHAT IS DERIVED
// ---------------------------------
// Everything drawn here is read straight from the `state` snapshot the
// Python core pushes on every game-state event: the board matrix, the
// falling piece's cells, the clearing rows and their animation frame, and
// the level's color index. Nothing is computed about *rules* here — even
// the wipe progress is just the core's `clearing.frame` re-expressed as
// "how many column pairs are gone". The canvas repaints in full on every
// event; there is no incremental drawing to get out of sync.
//
// The component returns TWO siblings: the canvas and (during a clear) the
// award label as a positioned div. The label is DOM, not canvas, so the
// browser's text stack renders it crisply and the `.blink`-style effects
// stay CSS-driven.
export function Board({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // The whole painting pass. useEffect (not useLayoutEffect) is enough:
  // a missed frame at 60 Hz is invisible, and the core sends ~1 event per
  // frame so the canvas catches up immediately. Depends on [state, scale]:
  // `state` because every snapshot may change cells, `scale` because the
  // backing store must be re-sized (logicalCanvas) when the window resizes.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { cols, rows, cell, frameOuter, frameInner } = LAYOUT.playfield;
    // Canvas extent = the 10x20 field plus the double frame on all sides.
    const fieldW = cols * cell;
    const fieldH = rows * cell;
    const totalW = fieldW + (frameOuter + frameInner) * 2;
    const totalH = fieldH + (frameOuter + frameInner) * 2;
    const ctx = logicalCanvas(canvas, totalW, totalH, scale);

    // Step 1: the frame, painted outside-in — dark band, light band, then
    // the black field. Each rect fully covers the previous one's center,
    // so what remains visible of each is just its rim.
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

    // No snapshot yet (still connecting): the empty framed field is the
    // whole picture.
    if (!state) return;
    const origin = frameOuter + frameInner;
    // Locked-cell color for this level: the core reports `color_index`
    // (level // 10, cycled); the modulo here is a belt-and-braces repeat of
    // the core's own cycling so a future index can't read past the table.
    const locked = LOCKED_COLORS[state.color_index % LOCKED_COLORS.length];
    // Line-clear wipe (spec 4.5, owner decision 2026-10-24): completed
    // rows empty from the center to both sides — pair k ({4-k, 5+k}) is
    // gone once frame >= (k+1) * WIPE_FRAMES_PER_PAIR.
    const clearing = state.clearing;
    // Sets, not arrays: cell lookup is O(1) in the 200-cell loop below,
    // where an array `includes` would be 200x200 in the worst case.
    const clearingRows = clearing ? new Set(clearing.rows) : null;
    const wipedCols = new Set<number>();
    if (clearing) {
      // Animation progress -> how many of the 5 center-out pairs have
      // dissolved. Capped at 5 so an over-run frame count can't walk the
      // pairs out of bounds.
      const pairs = Math.min(5, Math.floor(clearing.frame / WIPE_FRAMES_PER_PAIR));
      for (let k = 0; k < pairs; k++) {
        wipedCols.add(4 - k);
        wipedCols.add(5 + k);
      }
    }
    // Step 2: the locked stack. `value > 0` distinguishes filled cells from
    // the core's 0 markers; cells inside a clearing row whose column has
    // already been wiped are skipped — that skip IS the wipe animation.
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
    // Step 3: the falling piece, in its OWN colors (locked cells use the
    // level color; the falling piece keeps its piece color — that contrast
    // is how Tengen reads, spec 6.2).
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
    // No cleanup returned: the context is re-fetched and the canvas fully
    // repainted next time; nothing accumulates between draws.
  }, [state, scale]);

  // The award label ("SINGLE".."TETRIS") over the clearing band. Computed
  // on every render (outside the effect) because it is positioned DOM, not
  // canvas — and its geometry needs the scale in CSS pixels.
  const { x, y, cols, cell, frameOuter, frameInner } = LAYOUT.playfield;
  const clearingRows = state?.clearing?.rows ?? [];
  // rows.length is the award: 1->SINGLE .. 4->TETRIS. The `?? CLEAR_LABELS[1]`
  // fallback covers the impossible case of a clear with zero rows.
  const label = state?.clearing
    ? CLEAR_LABELS[state.clearing.rows.length] ?? CLEAR_LABELS[1]
    : null;
  // The award label renders inside the row(s) being cleared (owner
  // decision 2026-10-24): centered on the cleared band.
  // Math.min(...rows) = the topmost cleared row; for a single row the band
  // is exactly that row's cell, for a tetris it spans four.
  // NOTE: with an empty `clearingRows` this would be Infinity — but the
  // label is only rendered when `clearingRows.length > 0` (guard below),
  // so the degenerate value never reaches a style.
  const bandTop = (y + frameOuter + frameInner + Math.min(...clearingRows) * cell) * scale;
  const bandHeight = clearingRows.length * cell * scale;
  return (
    <>
      {/* The canvas has no CSS width/height of its own here: logicalCanvas
          sets both (to logical*scale), and the left/top position it over
          the playfield slot in the 2048x1920 layout. */}
      <canvas
        ref={canvasRef}
        style={{ position: "absolute", left: x * scale, top: y * scale }}
      />
      {/* The label only shows while a clear is animating; `length > 0`
          also keeps the Infinity bandTop above out of the DOM. */}
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
            // Capped at 96 logical px so "TETRIS" (the longest award) fits
            // the 840-px-wide band with room to spare; 0.9*cell would
            // otherwise overflow it.
            fontSize: Math.min(96, cell * 0.9) * scale,
            color: TEXT_BRIGHT,
            // Hard offset shadow (no blur) — the chunky drop-shadow look
            // of the era; scales with the window.
            textShadow: `${4 * scale}px ${4 * scale}px 0 rgba(0, 0, 0, 0.5)`,
          }}
        >
          {label}
        </div>
      )}
    </>
  );
}
