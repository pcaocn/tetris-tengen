import { useEffect, useRef } from "react";
import {
  DISPLAY_SHAPES,
  FALLING_COLORS,
  FRAME_DARK,
  FRAME_LIGHT,
  LAYOUT,
  type BlockTrio,
} from "../theme";
import type { GameState } from "../hooks/useGameState";
import { drawBlock, logicalCanvas } from "./draw";

// One-piece next preview (spec 4.1), drawn on a small canvas with the
// piece's authentic three-tone colors.
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
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, boxW, boxH);
    ctx.strokeStyle = FRAME_DARK;
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, boxW - 4, boxH - 4);
    ctx.strokeStyle = FRAME_LIGHT;
    ctx.lineWidth = 2;
    ctx.strokeRect(7, 7, boxW - 14, boxH - 14);
    const kind = state?.next;
    if (!kind) return;
    const cells = DISPLAY_SHAPES[kind];
    const trio: BlockTrio | undefined = FALLING_COLORS[kind];
    if (!cells || !trio) return;
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
  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", left: x * scale, top: y * scale, width: boxW * scale, height: boxH * scale }}
    />
  );
}
