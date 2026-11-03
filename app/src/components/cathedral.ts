// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// Vector scene of Saint Basil's Cathedral for the title screen (spec 5).
// Adapted from the owner's reference render,
// png/Saint_Basil's_Cathedral_render.ts, with fixes and richer detail:
// separate closed arch paths, proper wide-based onion domes, clipped
// spiral stripes and checkers, a fuller tower silhouette, and size
// scaled to the canvas.
//
// HOW THE SCENE IS BUILT
// ----------------------
// One exported entry point, drawSaintBasilsScene(ctx, w, h, cheat), which
// paints the whole composition back-to-front in this order:
//
//   1. drawSky               -- vertical gradient + soft radial sun
//   2. drawPlatform          -- the stone base the cathedral stands on
//   3. drawWalls             -- the terracotta body with white arcade
//   4. five drawTower calls  -- the corner towers, each a thin terracotta
//                               body topped by one onion dome
//   5. drawCentralTentTower  -- the tallest, central tent tower LAST among
//                               the towers so it overlaps them; it also
//                               carries the CHEAT indicator (its tip dome
//                               turns green when the Konami code is armed)
//
// THE COORDINATE CONVENTION
// -------------------------
// Every shape is placed PROPORTIONALLY: positions are fractions of the
// canvas width/height (h * 0.86, w * 0.22, ...) and thicknesses are small
// fractions of w. Nothing is in absolute pixels, so the same code renders
// the 1960x1476 title scene and any other size without re-tuning. The
// fractions themselves were eyeballed against the reference render — each
// carries its meaning in a nearby comment.
//
// WHY ALL THE save()/clip()/restore()
// -----------------------------------
// Stripes and checkers are drawn as RECTANGLES across the whole dome, then
// clipped to the onion-dome path, so the pattern never spills past the
// dome's curve. ctx.save()/restore() bracket each clip so one dome's
// clipping can never leak into the next shape.

type Ctx = CanvasRenderingContext2D;

// Palette for the scene. The building colors are chosen by hand (this is
// a stylized original render, not a reproduction); GOLD_* ramp is reused
// for every gilded dome and cross. GREEN is only used by the cheat dome.
const TERRACOTTA = "#b83b27";
const TERRACOTTA_DARK = "#9e2a1b";
const WINDOW_DARK = "#3d1610";
const WHITE = "#ffffff";
const STONE = "#b1b6bc";
const STONE_JOINT = "#829ab1";
const GOLD_LIGHT = "#ffea79";
const GOLD = "#f1c40f";
const GOLD_DARK = "#b7950b";
const BLUE = "#2980b9";
const GREEN = "#27ae60";
const RED_CHECK = "#c0392b";

// Layer 1: the sky. A pale top-to-bottom gradient (overcast Russian sky)
// plus one "soft sun": a radial gradient centered at 78% across, 14% down,
// fading to fully transparent at 8% of the width — the alpha stops
// (0.95 -> 0.45 -> 0) make the halo, not a drawn circle.
function drawSky(ctx: Ctx, w: number, h: number): void {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "#f0f4f8");
  g.addColorStop(1, "#d9e2ec");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  // Soft sun.
  const sun = ctx.createRadialGradient(w * 0.78, h * 0.14, 0, w * 0.78, h * 0.14, w * 0.08);
  sun.addColorStop(0, "rgba(255, 250, 220, 0.95)");
  sun.addColorStop(0.35, "rgba(255, 245, 200, 0.45)");
  sun.addColorStop(1, "rgba(255, 245, 200, 0)");
  ctx.fillStyle = sun;
  ctx.fillRect(0, 0, w, h);
}

// Layer 2: the stone platform. Sits at 86% of the height (the horizon line
// everything else is built down to), spanning 12%..88% of the width. The
// masonry is one strokeRect per 3%-wide slab — the joint color reads as
// mortar lines. The thin 12%-black strip below the platform is its shadow.
function drawPlatform(ctx: Ctx, w: number, h: number): void {
  const y = h * 0.86;
  const x0 = w * 0.12;
  const x1 = w * 0.88;
  ctx.fillStyle = STONE;
  ctx.fillRect(x0, y, x1 - x0, h * 0.03);
  ctx.strokeStyle = STONE_JOINT;
  // Hairline joints that stay visible at any scene size (the Math.max
  // floor guards tiny canvases).
  ctx.lineWidth = Math.max(1, w * 0.001);
  for (let x = x0; x < x1; x += w * 0.03) {
    ctx.strokeRect(x, y, w * 0.03, h * 0.03);
  }
  ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
  ctx.fillRect(x0, y + h * 0.03, x1 - x0, h * 0.006);
}

// One round-topped arch, the scene's workhorse shape (arcade openings,
// windows). Path recipe: up the left side, a half-circle cap over the top
// (the arc from PI to 2*PI is the upper semicircle), down the right side,
// close along the bottom. `w` is the full arch width, `h` its total height.
function arch(ctx: Ctx, cx: number, baseY: number, w: number, h: number, fill: string): void {
  const r = w / 2;
  ctx.beginPath();
  ctx.moveTo(cx - r, baseY);
  ctx.lineTo(cx - r, baseY - h + r);
  ctx.arc(cx, baseY - h + r, r, Math.PI, Math.PI * 2);
  ctx.lineTo(cx + r, baseY);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
}

// Layer 3: the main wall block, 30%..70% of the width, from 66% height
// down to the platform. The white cornice band caps it; below, five
// arcade bays are each drawn TWICE — a bigger white arch (the decorative
// surround) and a slightly smaller dark arch on top (the recessed
// opening). Drawing dark over white is what gives the opening depth.
function drawWalls(ctx: Ctx, w: number, h: number): void {
  const x = w * 0.3;
  const width = w * 0.4;
  const y = h * 0.66;
  ctx.fillStyle = TERRACOTTA;
  ctx.fillRect(x, y, width, h * 0.86 - y);
  // White cornice and arcade.
  ctx.fillStyle = WHITE;
  ctx.fillRect(x, y, width, h * 0.018);
  for (let i = 0; i < 5; i++) {
    const cx = x + width * (0.14 + i * 0.18);
    arch(ctx, cx, h * 0.82, w * 0.045, h * 0.09, WHITE);
    arch(ctx, cx, h * 0.82, w * 0.03, h * 0.07, WINDOW_DARK);
  }
}

// The onion-dome silhouette, as a path around ORIGIN (0, 0) = the dome's
// base center; callers translate to where the dome should sit. Two
// mirrored cubic beziers: each flares OUT to 1.55x the base half-width
// (the onion's bulge) before curving in to the point at -1.55 * size
// height. `size` is the dome's scale unit — total height ~1.55 * size.
// The exact bulge/point factors are what make it read "onion" instead of
// "bullet"; they were tuned against the reference render.
function onionDomePath(ctx: Ctx, size: number): void {
  const bw = size * 0.62;
  ctx.beginPath();
  ctx.moveTo(-bw, 0);
  ctx.bezierCurveTo(-bw * 1.55, -size * 0.35, -bw * 0.9, -size * 1.05, 0, -size * 1.55);
  ctx.bezierCurveTo(bw * 0.9, -size * 1.05, bw * 1.55, -size * 0.35, bw, 0);
  ctx.closePath();
}

// Spiral stripes for the blue/green domes: five parallel bars painted over
// the dome, then clipped to the dome path. The translate+rotate (-0.35
// radians ≈ 20°) BEFORE drawing the bars is what makes them read as a
// spiral wrapping the onion — straight vertical bars would look flat.
// save/restore guarantee the clip and rotation die here.
function clipStripes(ctx: Ctx, size: number, color: string): void {
  ctx.save();
  onionDomePath(ctx, size);
  ctx.clip();
  ctx.translate(0, -size * 0.8);
  ctx.rotate(-0.35);
  ctx.fillStyle = color;
  for (let i = -2; i <= 2; i++) {
    ctx.fillRect(i * size * 0.5 - size * 0.06, -size, size * 0.14, size * 2.2);
  }
  ctx.restore();
}

// Checkerboard for the red domes: white squares on a 0.24*size grid,
// clipped to the dome. The parity test — skip when (row + col) is even —
// is what leaves alternating gaps, producing the checker pattern; the
// loop ranges cover slightly beyond the dome on purpose, since the clip
// discards the overflow.
function clipCheckers(ctx: Ctx, size: number): void {
  ctx.save();
  onionDomePath(ctx, size);
  ctx.clip();
  ctx.fillStyle = WHITE;
  const step = size * 0.24;
  for (let gy = -1.6; gy < 0.2; gy += 1) {
    for (let gx = -2; gx < 2; gx++) {
      if ((Math.round(gy) + Math.round(gx)) % 2 === 0) continue;
      ctx.fillRect(gx * step, gy * step, step, step);
    }
  }
  ctx.restore();
}

// Russian orthodox cross: the vertical bar plus THREE horizontal bars of
// increasing width toward the bottom (the lowest one slanted), the
// traditional three-bar shape. Stroke-based, so `s` is the half-height.
function orthodoxCross(ctx: Ctx, x: number, y: number, s: number): void {
  ctx.strokeStyle = GOLD;
  ctx.lineWidth = Math.max(2, s * 0.07);
  ctx.beginPath();
  ctx.moveTo(x, y - s);
  ctx.lineTo(x, y);
  ctx.moveTo(x - s * 0.24, y - s * 0.72);
  ctx.lineTo(x + s * 0.24, y - s * 0.72);
  ctx.moveTo(x - s * 0.48, y - s * 0.4);
  ctx.lineTo(x + s * 0.48, y - s * 0.4);
  ctx.moveTo(x - s * 0.32, y - s * 0.08);
  ctx.lineTo(x + s * 0.32, y - s * 0.24);
  ctx.stroke();
}

// One complete dome: fill per `style`, then the gold neck band at its
// base, then the cross on top. Styles:
//   "gold"      — radial gradient (highlight offset up-left) for shine
//   "blue"      — flat blue + white spiral stripes
//   "green"     — flat green + gold spiral stripes
//   "checkered" — red + white checkerboard (the cheat turns this variant
//                 unused; green style serves the cheat tip dome instead)
// The dome is drawn at (cx, baseY) via translate, so onionDomePath's
// origin convention (base center at 0,0, growing upward) applies as-is.
function drawDome(ctx: Ctx, cx: number, baseY: number, size: number, style: string): void {
  ctx.save();
  ctx.translate(cx, baseY);
  onionDomePath(ctx, size);
  if (style === "gold") {
    const g = ctx.createRadialGradient(-size * 0.2, -size * 1.1, size * 0.1, 0, -size * 0.8, size);
    g.addColorStop(0, GOLD_LIGHT);
    g.addColorStop(0.5, GOLD);
    g.addColorStop(1, GOLD_DARK);
    ctx.fillStyle = g;
    ctx.fill();
  } else if (style === "blue") {
    ctx.fillStyle = BLUE;
    ctx.fill();
    clipStripes(ctx, size, WHITE);
  } else if (style === "green") {
    ctx.fillStyle = GREEN;
    ctx.fill();
    clipStripes(ctx, size, GOLD);
  } else {
    ctx.fillStyle = RED_CHECK;
    ctx.fill();
    clipCheckers(ctx, size);
  }
  // Gold neck band at the dome base.
  ctx.fillStyle = GOLD;
  ctx.fillRect(-size * 0.5, 0, size, Math.max(3, size * 0.09));
  ctx.restore();
  orthodoxCross(ctx, cx, baseY - size * 1.55, size * 0.9);
}

// The thin terracotta column under a corner dome: from its top (where the
// dome's base sits) down to the platform, with white trim bands and two
// small arched windows. Width is a fixed 5.5% of scene width — all four
// corner towers share it, only dome size/style differ.
function towerBody(ctx: Ctx, cx: number, topY: number, w: number, h: number): void {
  const bw = w * 0.055;
  ctx.fillStyle = TERRACOTTA;
  ctx.fillRect(cx - bw / 2, topY, bw, h * 0.86 - topY);
  // White trim bands.
  ctx.fillStyle = WHITE;
  ctx.fillRect(cx - bw / 2, topY, bw, h * 0.012);
  const mid = topY + (h * 0.86 - topY) * 0.55;
  ctx.fillRect(cx - bw / 2, mid, bw, h * 0.01);
  // Small windows.
  arch(ctx, cx, mid - h * 0.012, w * 0.02, h * 0.045, WINDOW_DARK);
  arch(ctx, cx, h * 0.84, w * 0.022, h * 0.05, WINDOW_DARK);
}

// One corner tower = body + dome. (fx, fy) are the tower's position as
// FRACTIONS of the scene; domeScale sizes its onion relative to the
// scene width. The five call sites at the bottom of the file are the
// whole skyline layout.
function drawTower(
  ctx: Ctx,
  w: number,
  h: number,
  fx: number,
  fy: number,
  style: string,
  domeScale: number,
): void {
  const cx = w * fx;
  const topY = h * fy;
  towerBody(ctx, cx, topY, w, h);
  drawDome(ctx, cx, topY, w * domeScale, style);
}

// The central tower — the cathedral's tallest silhouette and the CHEAT
// INDICATOR. Unlike the corner towers it is capped by a concave TENT
// roof (curved inward sides, drawn with two quadratic curves meeting at
// the apex) rather than an onion dome, with gold lattice lines fanning
// from apex to base. On top of the tent sits one tiny dome: gold
// normally, GREEN once the Konami code has been entered (`cheat`), the
// owner's chosen unlock signal.
function drawCentralTentTower(ctx: Ctx, w: number, h: number, cheat: boolean): void {
  const cx = w * 0.5;
  const apexY = h * 0.12;
  const baseY = h * 0.38;
  const bw = w * 0.052;
  // Body and drum below the tent.
  ctx.fillStyle = TERRACOTTA;
  ctx.fillRect(cx - bw, baseY, bw * 2, h * 0.86 - baseY);
  ctx.fillStyle = WHITE;
  ctx.fillRect(cx - bw, baseY, bw * 2, h * 0.016);
  for (let i = -2; i <= 2; i++) {
    arch(ctx, cx + i * bw * 0.45, h * 0.6, w * 0.014, h * 0.05, WINDOW_DARK);
  }
  // Concave tent with gold lattice lines and trim.
  const mid = baseY - (baseY - apexY) * 0.55;
  ctx.beginPath();
  ctx.moveTo(cx, apexY);
  ctx.quadraticCurveTo(cx - bw * 0.9, mid, cx - bw * 1.6, baseY);
  ctx.lineTo(cx + bw * 1.6, baseY);
  ctx.quadraticCurveTo(cx + bw * 0.9, mid, cx, apexY);
  ctx.closePath();
  ctx.fillStyle = TERRACOTTA_DARK;
  ctx.fill();
  ctx.strokeStyle = GOLD;
  ctx.lineWidth = Math.max(1.5, w * 0.0012);
  ctx.beginPath();
  for (const k of [-1.2, -0.6, 0.6, 1.2]) {
    ctx.moveTo(cx, apexY);
    ctx.lineTo(cx + k * bw, baseY);
  }
  ctx.stroke();
  ctx.fillStyle = GOLD;
  ctx.fillRect(cx - bw * 1.6, baseY - h * 0.006, bw * 3.2, h * 0.012);
  // Dome on top of the tent — the cathedral's tip. It turns green as the
  // cheat-unlocked indicator (owner request 2026-10-25).
  drawDome(ctx, cx, apexY, w * 0.018, cheat ? "green" : "gold");
}

/**
 * Paints the complete title-screen scene. The call order IS the painter's
 * algorithm: far things first (sky, platform), near things last — the
 * central tent tower after the corner towers so it overlaps them, the
 * low checkered front tower absolutely last. `cheat` recolors the tip
 * dome green (the cheat-unlocked indicator).
 */
export function drawSaintBasilsScene(ctx: Ctx, w: number, h: number, cheat = false): void {
  drawSky(ctx, w, h);
  drawPlatform(ctx, w, h);
  drawWalls(ctx, w, h);
  drawTower(ctx, w, h, 0.22, 0.52, "gold", 0.016);
  drawTower(ctx, w, h, 0.35, 0.42, "blue", 0.022);
  drawCentralTentTower(ctx, w, h, cheat);
  drawTower(ctx, w, h, 0.65, 0.42, "green", 0.022);
  drawTower(ctx, w, h, 0.78, 0.52, "gold", 0.016);
  drawTower(ctx, w, h, 0.5, 0.66, "checkered", 0.02);
}
