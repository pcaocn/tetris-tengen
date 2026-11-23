import { useEffect, useRef } from "react";
import {
  DISPLAY_SHAPES,
  FALLING_COLORS,
  FRAME_DARK,
  FRAME_LIGHT,
  LAYOUT,
  type BlockTrio,
} from "../theme";
import type { GameState } from "../types/game";
import { drawBlock, logicalCanvas } from "./draw";

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// One-piece next preview (spec 4.1), drawn on a small canvas with the
// piece's authentic three-tone colors. Tengen shows only ONE upcoming
// piece (unlike modern guides), so the core's `state.next` is a single
// kind letter, not a queue.
//
// The piece is drawn from the DISPLAY_SHAPES snapshot table, not from the
// live core rotation state — a preview never needs a rotation, just the
// piece's iconic spawn orientation. Redraws only when the state or scale
// changes; the box art is cheap enough to repaint whole each time.
export function NextPreview({
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
    const { boxW, boxH, cell } = LAYOUT.next;
    const ctx = logicalCanvas(canvas, boxW, boxH, scale);
    // Step 1: black backdrop, then the same double frame as the playfield
    // (dark thick stroke, then thin light one) so the box reads as part of
    // the chrome family. strokeRect strokes are centered on the path, hence
    // the 2px / 7px insets keeping both strokes fully inside the canvas.
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, boxW, boxH);
    ctx.strokeStyle = FRAME_DARK;
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, boxW - 4, boxH - 4);
    ctx.strokeStyle = FRAME_LIGHT;
    ctx.lineWidth = 2;
    ctx.strokeRect(7, 7, boxW - 14, boxH - 14);
    // Step 2: look up the piece. An empty `next` (between games) or an
    // unknown letter leaves the empty box — never a crash.
    const kind = state?.next;
    if (!kind) return;
    const cells = DISPLAY_SHAPES[kind];
    const trio: BlockTrio | undefined = FALLING_COLORS[kind];
    if (!cells || !trio) return;
    // Step 3: center the piece's bounding box in the preview box. The
    // table's cell offsets start wherever was convenient for the shape
    // (an I sits in row 1, an O fills a 2x2), so the min/max bounds are
    // measured first and subtracted, making the centering independent of
    // the table's arbitrary origin.
    const minX = Math.min(...cells.map(([cx]) => cx));
    const maxX = Math.max(...cells.map(([cx]) => cx));
    const minY = Math.min(...cells.map(([, cy]) => cy));
    const maxY = Math.max(...cells.map(([, cy]) => cy));
    const shapeW = (maxX - minX + 1) * cell;
    const shapeH = (maxY - minY + 1) * cell;
    const originX = (boxW - shapeW) / 2;
    const originY = (boxH - shapeH) / 2;
    for (const [cx, cy] of cells) {
      drawBlock(
        ctx,
        originX + (cx - minX) * cell,
        originY + (cy - minY) * cell,
        cell,
        trio,
      );
    }
  }, [state, scale]);

  const { x, y, boxW, boxH } = LAYOUT.next;
  // The CSS width/height repeat what logicalCanvas already set; keeping
  // them in the style too is harmless belt-and-braces (same values).
  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", left: x * scale, top: y * scale, width: boxW * scale, height: boxH * scale }}
    />
  );
}
