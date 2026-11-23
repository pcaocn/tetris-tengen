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
// this panel only chooses a shared ceiling and sizes each fill against it.
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
// across a whole game rather than maxing out by level 5. When a count
// passes 120 the whole panel switches to that leader as the ceiling.)
export function StatsPanel({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const { x, y, titleSize, cell, barWidth, barHeight, gap } = LAYOUT.stats;
  const stats = state?.stats ?? {};
  // One shared ceiling per snapshot: the original 120-piece scale, or the
  // current leader when it grows past 120. This keeps every bar on the
  // same denominator and makes the leader's bar full without rescaling
  // the others to half height.
  const counts = KINDS.map((kind) => stats[kind] ?? 0);
  const ceiling = Math.max(STATS_BAR_MAX, ...counts);
  // The tick marks: 12 evenly spaced subdivisions of the current range.
  // They are stateless divs shared by every bar track.
  const tickCount = STATS_BAR_MAX / STATS_TICK_EVERY;
  const ticks: ReactNode[] = [];
  for (let i = 1; i <= tickCount; i += 1) {
    ticks.push(
      <div
        key={`tick-${i}`}
        style={{
          position: "absolute",
          bottom: `${(i / tickCount) * 100}%`,
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
        {KINDS.map((kind, index) => {
          // Unknown kinds (a new piece added core-side) read as 0. The
          // shared ceiling is never below 120 and never below the leader.
          const count = counts[index];
          const fillPercent = (100 * count) / ceiling;
          const formatted = count.toLocaleString("en-US");
          // The label is rotated, so its horizontal thickness is the font
          // size and its vertical extent is the text width. Fit both
          // inside the 28 x 560 logical track; the height bound only
          // matters for absurdly long counts.
          const labelFontSize = Math.min(
            barWidth * 0.78,
            (barHeight * 0.9) / Math.max(1, formatted.length * 0.62),
          );
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
                    height: `${fillPercent}%`,
                    background: STATS_BAR_FILL,
                  }}
                />
                {ticks}
                {/* Exact count, above the fill and grid in paint order. The
                    SVG text runs from the bottom anchor upward: rotate -90
                    around the anchor and start the text there, so the first
                    digit is nearest the bottom. White with a dark stroke
                    stays readable over both the black track and the bright
                    fill. */}
                <svg
                  width={barWidth * scale}
                  height={barHeight * scale}
                  viewBox={`0 0 ${barWidth} ${barHeight}`}
                  style={{
                    position: "absolute",
                    inset: 0,
                    pointerEvents: "none",
                    overflow: "visible",
                  }}
                  aria-hidden="true"
                >
                  <text
                    x={barWidth / 2 + labelFontSize * 0.35}
                    y={barHeight - 4}
                    transform={`rotate(-90 ${barWidth / 2 + labelFontSize * 0.35} ${barHeight - 4})`}
                    textAnchor="start"
                    fontFamily={FONT_SMOOTH}
                    fontWeight={700}
                    fontSize={labelFontSize}
                    fill="#ffffff"
                    stroke="rgba(0, 0, 0, 0.85)"
                    strokeWidth={0.8}
                    paintOrder="stroke fill"
                  >
                    {formatted}
                  </text>
                </svg>
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
