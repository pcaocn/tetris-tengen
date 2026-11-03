import { useEffect, useRef, type ReactNode } from "react";
import {
  DISPLAY_SHAPES,
  FALLING_COLORS,
  FONT_SMOOTH,
  LAYOUT,
  PANEL_BG,
  STATS_BAR_FILL,
  STATS_BAR_MAX,
  STATS_ORDER,
  STATS_TICK_EVERY,
  TEXT_BRIGHT,
} from "../theme";
import type { GameState } from "../hooks/useGameState";
import { drawBlock, logicalCanvas } from "./draw";

const KINDS: readonly string[] = STATS_ORDER;

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// Per-piece spawn counters (spec 4.9), as a histogram: one column per
// piece kind, the piece's mini glyph at the bottom and a vertical bar
// above it that grows with the count. The counts arrive in
// `state.stats` (a {kind: count} record) straight from the Python core —
// this panel only divides by STATS_BAR_MAX to size the fill.
//
// Why a histogram and not seven numbers: it mirrors the original game's
// stats screen and makes the RNG distribution visible at a glance — a
// rigged-feeling drought of I pieces shows as a short bar.

// -- One histogram column's bottom piece ----------------------------------
// Mini piece glyph in its own three-tone color. The canvas is trimmed to
// the piece's bounds so the columns sit compactly.
//
// WHY A SEPARATE COMPONENT PER GLYPH: each glyph is its own small canvas
// (React keys the seven of them by kind), so a count change re-renders the
// bar divs but the glyph canvases only repaint when their kind/cell/scale
// change — the deps below. Trimming: the canvas is sized to the piece's
// bounding box (+8px breathing room, 4px on each side) instead of a fixed
// 4x4 grid, so a 1-wide I doesn't carry three empty columns.
function MiniGlyph({ kind, cell, scale }: { kind: string; cell: number; scale: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const cells = DISPLAY_SHAPES[kind];
    const trio = FALLING_COLORS[kind];
    if (!canvas || !cells || !trio) return;
    const xs = cells.map(([cx]) => cx);
    const ys = cells.map(([, cy]) => cy);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const w = (Math.max(...xs) - minX + 1) * cell + 8;
    const h = (Math.max(...ys) - minY + 1) * cell + 8;
    const ctx = logicalCanvas(canvas, w, h, scale);
    for (const [cx, cy] of cells) {
      drawBlock(ctx, 4 + (cx - minX) * cell, 4 + (cy - minY) * cell, cell, trio);
    }
  }, [kind, cell, scale]);

  return <canvas ref={ref} />;
}

// -- The panel itself ------------------------------------------------------
// Per-piece spawn counters (spec 4.9). Owner decision 2026-10-24, per the
// captures: one column per piece — the glyph at the bottom and a vertical
// bar above it that grows upward with the count, with a horizontal tick
// every 5 pieces (full at 50).
//
// (The tick spacing/full-at value above is the original note; the shipped
// constants are every 10 pieces, full at 120 — see STATS_TICK_EVERY /
// STATS_BAR_MAX in theme.ts, raised 2026-10-25 so the bars fill slowly
// across a whole game rather than maxing out by level 5.)
export function StatsPanel({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const { x, y, titleSize, cell, barWidth, barHeight, gap } = LAYOUT.stats;
  const stats = state?.stats ?? {};
  // The tick marks: built once per render as a list of absolutely
  // positioned hairlines, then included inside EVERY bar's track below
  // (the same array instance is reused — they are stateless divs, so
  // sharing is safe and React reconciles them by key).
  // `bottom: (t / MAX) * 100%` places tick t proportionally up the track,
  // so a tick always means "this many pieces" regardless of bar height.
  const ticks: ReactNode[] = [];
  for (let t = STATS_TICK_EVERY; t <= STATS_BAR_MAX; t += STATS_TICK_EVERY) {
    ticks.push(
      <div
        key={t}
        style={{
          position: "absolute",
          bottom: `${(t / STATS_BAR_MAX) * 100}%`,
          left: 0,
          width: "100%",
          height: 2 * scale,
          background: "rgba(255, 255, 255, 0.35)",
        }}
      />,
    );
  }
  return (
    <>
      <div style={{ position: "absolute", left: x * scale, top: y * scale }}>
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
      <div
        style={{
          position: "absolute",
          left: x * scale,
          top: (y + titleSize * 1.6 + 24) * scale,
          display: "flex",
          alignItems: "flex-start",
          gap: gap * scale,
        }}
      >
        {KINDS.map((kind) => {
          // Unknown kinds (a new piece added core-side) read as 0; a count
          // beyond the max is clamped so the fill never exceeds 100%.
          const count = stats[kind] ?? 0;
          const fill = Math.min(count, STATS_BAR_MAX) / STATS_BAR_MAX;
          // Fixed-height glyph area under every bar so all bars align at
          // the same height regardless of piece shape (owner 2026-10-24),
          // and a fixed column width so the pitch between the bars is
          // even — the pieces have different widths (I is one square
          // wide), so the trimmed glyph canvases alone would not space
          // evenly (owner 2026-10-27).
          const glyphBox = (4 * cell + 8) * scale;
          const colWidth = (3 * cell + 8) * scale;
          return (
            <div
              key={kind}
              style={{
                width: colWidth,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <div
                style={{
                  position: "relative",
                  width: barWidth * scale,
                  height: barHeight * scale,
                  // Black track, no boundary line; all bars share one
                  // yellowish fill between the T and J colors (owner
                  // correction 2026-10-27, closest to the original).
                  background: "#000000",
                  overflow: "hidden",
                }}
              >
                {/* The fill: anchored to `bottom`, so as `height` grows with
                    the count the bar rises upward from the glyph — matching
                    the original's upward-growing columns. */}
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    bottom: 0,
                    width: "100%",
                    height: `${fill * 100}%`,
                    background: STATS_BAR_FILL,
                  }}
                />
                {ticks}
              </div>
              <div style={{ height: glyphBox, display: "flex", alignItems: "flex-end" }}>
                <MiniGlyph kind={kind} cell={cell} scale={scale} />
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
