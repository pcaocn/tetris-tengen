// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// Vector block drawing helpers (spec 6.3, 6.4) — the two primitives every
// canvas painter in the app builds on:
//
//   logicalCanvas()  -- sizes a <canvas> backing store to DEVICE pixels and
//                       returns a 2d context whose transform maps LOGICAL
//                       units (the 2048x1920 space) onto them. Call it once
//                       per draw pass, then draw as if the screen really
//                       were 2048x1920.
//   drawBlock()      -- one Tengen block sprite at logical (x, y), `size`
//                       pixels square, in a piece's three-tone colors.
//
// Blocks reproduce the authentic Tengen sprite lighting measured from the
// captures: a mid-tone body, light shading on the top and right edges, dark
// shading on the left and bottom edges, and a thin black outline. Edges are
// smooth gradient fades over rounded corners instead of flat pixel-style
// bands (owner decision 2026-10-24: flat bands still read as one big pixel).
// Drawn at logical coordinates; no sprite art is copied from the captures.
//
// WHY CANVAS AND NOT DOM ELEMENTS
// -------------------------------
// A full board is 200 cells plus frame art; as DOM nodes that is hundreds of
// styled divs re-rendered at 60 Hz. Canvas redraws the whole field in one
// imperative pass per state event, and the vector art (gradients, arcs) is
// only practical there. The cost is manual: the painters re-run inside
// useEffect and must handle `scale` changes themselves.

import type { BlockTrio } from "../theme";

/**
 * Prepares a canvas backing store at the device pixel size and returns a
 * context whose transform maps logical units to device pixels (spec 6.4).
 *
 * This is the answer to "why does everything look blurry if you skip it":
 * a canvas has two sizes. Its CSS size (how big it appears) and its
 * backing-store size (how many pixels it actually has). Setting only the
 * CSS size stretches a low-res bitmap; setting only the backing store
 * draws at the wrong scale. This function sets BOTH — backing store to
 * `cssSize * devicePixelRatio`, CSS size to `logical * scale` — and then
 * bakes the whole scale chain (`scale * dpr`) into the context transform,
 * so callers draw in plain logical units and stay crisp on Retina.
 *
 * @param canvas   the element to size; its width/height/style are written.
 * @param logicalWidth/Height  the drawing area in logical units.
 * @param scale    window scale from App.tsx's fitScale().
 * @returns a context with the transform applied; draws are in logical units.
 */
export function logicalCanvas(
  canvas: HTMLCanvasElement,
  logicalWidth: number,
  logicalHeight: number,
  scale: number,
): CanvasRenderingContext2D {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = logicalWidth * scale;
  const cssHeight = logicalHeight * scale;
  // Backing store in real device pixels; `Math.max(1, ...)` guards against
  // a degenerate 0x0 canvas (which would make getContext throw or draw
  // nothing) when the window is collapsed to nothing.
  canvas.width = Math.max(1, Math.round(cssWidth * dpr));
  canvas.height = Math.max(1, Math.round(cssHeight * dpr));
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("no 2d context");
  // One transform for everything: device px = logical px * scale * dpr.
  // Every painter after this call just draws in logical units. setTransform
  // (not transform) is used so repeated calls in a redraw don't compound.
  ctx.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0);
  return ctx;
}

// Traces a rounded rectangle (manual arcTo path; no roundRect dependency).
//
// WHY HAND-ROLLED: ctx.roundRect() is recent and missing in older WebKit
// builds; arcTo works everywhere and produces the identical path — four
// corners visited clockwise, each replaced by an arc of radius `r`.
function roundedPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  // Clamp the radius so a too-large `r` can't exceed the rectangle's halves
  // (an over-large arcTo radius silently distorts the path).
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
//
// Canvas gradients take CSS color strings, and a hex string can't carry
// alpha — so each trio color is unpacked once into an rgba() string here.
// The bit shifts decode the hex: `n >> 16` is the red byte, `n >> 8 & 255`
// the green, `n & 255` the blue.
function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// One edge-shade pass: fills `rect` with a linear gradient of `color`
// fading from `alpha` at the rim to fully transparent `fade` units inward.
// The gradient line runs perpendicular to the shaded edge.
//
// The two coordinate groups look redundant but are not: (x0..y1) define the
// gradient's axis and (rx..rh) the filled rectangle. A linear gradient
// extends infinitely sideways along its axis, so its perpendicular
// coordinate is irrelevant — that is why the vertical fades pass x=0 for
// the gradient points while the fill rect still uses the real bx/bs body
// coordinates. The direction of the axis picks which edge brightens:
// rim-to-inner ordering puts the 0.9-alpha stop at the rim.
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

/**
 * Draws one Tengen block: a black-outlined rounded square with the piece's
 * mid-tone body and light/dark gradient bevels. This is the single sprite
 * painter used by the playfield, the NEXT preview and the stats glyphs —
 * every block on screen comes through here.
 *
 * @param x, y   top-left corner in logical units (already translated by the
 *               caller; Board adds the frame origin, previews center first).
 * @param size   the square's side in logical units (the layout's `cell`).
 * @param trio   the piece's sampled light/mid/dark colors.
 */
export function drawBlock(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  size: number,
  trio: BlockTrio,
): void {
  // All three proportions scale with `size` so the sprite looks identical
  // at any cell size, with floors (`Math.max`) so blocks never lose their
  // outline/corners when drawn tiny (the 16-px stats glyphs).
  const inset = Math.max(1, size * 0.02); // black outline thickness
  const radius = Math.max(2, size * 0.12); // rounded corner
  const fade = Math.max(2, size * 0.13); // edge-shade depth

  // Step 1: the black outline. Filled first, slightly larger than the
  // body, so the body is drawn on top and only the `inset` rim shows.
  roundedPath(ctx, x, y, size, size, radius);
  ctx.fillStyle = "#000000";
  ctx.fill();

  // Step 2: the mid-tone body, shrunk by the outline thickness on all
  // sides and drawn with a radius reduced to match.
  const bx = x + inset;
  const by = y + inset;
  const bs = size - inset * 2;
  roundedPath(ctx, bx, by, bs, bs, Math.max(1, radius - inset));
  ctx.fillStyle = trio.mid;
  ctx.fill();

  // Step 3: the bevel — four gradient bands clipped to the rounded body.
  // Light on the top and right, dark on the left and bottom, as sampled.
  // The clip matters: without it the square fade rectangles would spill
  // past the rounded corners.
  ctx.save();
  roundedPath(ctx, bx, by, bs, bs, Math.max(1, radius - inset));
  ctx.clip();
  edgeFade(ctx, trio.light, 0, by, 0, by + fade, bx, by, bs, fade); // top
  edgeFade(ctx, trio.light, bx + bs, 0, bx + bs - fade, 0, bx + bs - fade, by, fade, bs); // right
  edgeFade(ctx, trio.dark, bx, 0, bx + fade, 0, bx, by, fade, bs); // left
  edgeFade(ctx, trio.dark, 0, by + bs, 0, by + bs - fade, bx, by + bs - fade, bs, fade); // bottom
  ctx.restore();
}
