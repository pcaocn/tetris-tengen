// Vector block drawing helpers (spec 6.3, 6.4). Blocks reproduce the
// authentic Tengen sprite lighting measured from the captures: a mid-tone
// body, light shading on the top and right edges, dark shading on the left
// and bottom edges, and a thin black outline. Edges are smooth gradient
// fades over rounded corners instead of flat pixel-style bands (owner
// decision 2026-10-24: flat bands still read as one big pixel). Drawn at
// logical coordinates; no sprite art is copied from the captures.

import type { BlockTrio } from "../theme";

// Prepares a canvas backing store at the device pixel size and returns a
// context whose transform maps logical units to device pixels (spec 6.4).
export function logicalCanvas(
  canvas: HTMLCanvasElement,
  logicalWidth: number,
  logicalHeight: number,
  scale: number,
): CanvasRenderingContext2D {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = logicalWidth * scale;
  const cssHeight = logicalHeight * scale;
  canvas.width = Math.max(1, Math.round(cssWidth * dpr));
  canvas.height = Math.max(1, Math.round(cssHeight * dpr));
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("no 2d context");
  ctx.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0);
  return ctx;
}

// Traces a rounded rectangle (manual arcTo path; no roundRect dependency).
function roundedPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  const rad = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + rad, y);
  ctx.arcTo(x + w, y, x + w, y + h, rad);
  ctx.arcTo(x + w, y + h, x, y + h, rad);
  ctx.arcTo(x, y + h, x, y, rad);
  ctx.arcTo(x, y, x + w, y, rad);
  ctx.closePath();
}

// "#rrggbb" -> "rgba(r, g, b, alpha)"
function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// One edge-shade pass: fills `rect` with a linear gradient of `color`
// fading from `alpha` at the rim to fully transparent `fade` units inward.
// The gradient line runs perpendicular to the shaded edge.
function edgeFade(
  ctx: CanvasRenderingContext2D,
  color: string,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  rx: number,
  ry: number,
  rw: number,
  rh: number,
): void {
  const g = ctx.createLinearGradient(x0, y0, x1, y1);
  g.addColorStop(0, rgba(color, 0.9));
  g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g;
  ctx.fillRect(rx, ry, rw, rh);
}

// A solid rounded cell in one flat color (no bevels), used by the
// line-clear dissolve (spec 4.5).
export function drawCellColor(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  size: number,
  color: string,
): void {
  const inset = Math.max(1, size * 0.02);
  const radius = Math.max(2, size * 0.12);
  roundedPath(
    ctx,
    x + inset,
    y + inset,
    size - inset * 2,
    size - inset * 2,
    Math.max(1, radius - inset),
  );
  ctx.fillStyle = color;
  ctx.fill();
}

export function drawBlock(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  size: number,
  trio: BlockTrio,
): void {
  const inset = Math.max(1, size * 0.02); // black outline thickness
  const radius = Math.max(2, size * 0.12); // rounded corner
  const fade = Math.max(2, size * 0.13); // edge-shade depth

  roundedPath(ctx, x, y, size, size, radius);
  ctx.fillStyle = "#000000";
  ctx.fill();

  const bx = x + inset;
  const by = y + inset;
  const bs = size - inset * 2;
  roundedPath(ctx, bx, by, bs, bs, Math.max(1, radius - inset));
  ctx.fillStyle = trio.mid;
  ctx.fill();

  // Shade the edges with smooth fades, clipped to the rounded body. Light
  // on the top and right, dark on the left and bottom, as sampled.
  ctx.save();
  roundedPath(ctx, bx, by, bs, bs, Math.max(1, radius - inset));
  ctx.clip();
  edgeFade(ctx, trio.light, 0, by, 0, by + fade, bx, by, bs, fade); // top
  edgeFade(ctx, trio.light, bx + bs, 0, bx + bs - fade, 0, bx + bs - fade, by, fade, bs); // right
  edgeFade(ctx, trio.dark, bx, 0, bx + fade, 0, bx, by, fade, bs); // left
  edgeFade(ctx, trio.dark, 0, by + bs, 0, by + bs - fade, bx, by + bs - fade, bs, fade); // bottom
  ctx.restore();
}
