import { FONT_SMOOTH, LAYOUT, PANEL_BG, TEXT_BRIGHT, TEXT_COLOR } from "../theme";
import type { GameState } from "../types/game";

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// Score, high score, lines, and level readouts (spec 6.1), styled after the
// captures: white labels on gray bars, pale-blue values.
//
// The four rows are one `.map` over a [label, value] table rather than four
// copy-pasted blocks: same structure, same spacing (rowHeight apart), only
// the text differs. Every value arrives ready-computed in the state
// snapshot — the panel has no idea how scoring works, and must not (the
// core owns points, line counts and the level curve).
export function ScorePanel({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const { x, y, rowHeight, labelSize, valueSize } = LAYOUT.score;
  // `?? 0` covers the connecting phase (state is null): the panel shows
  // zeros in its slots instead of vanishing — the readout chrome is part
  // of the screen layout and should always be there.
  const rows: Array<[string, string]> = [
    ["SCORE", (state?.score ?? 0).toLocaleString("en-US")],
    ["HIGH SCORE", (state?.high_score ?? 0).toLocaleString("en-US")],
    ["LINES", (state?.lines ?? 0).toLocaleString("en-US")],
    ["LEVEL", String(state?.level ?? 0)],
  ];
  return (
    <>
      {rows.map(([name, val], i) => (
        <div key={name} style={{ position: "absolute", left: x * scale, top: (y + i * rowHeight) * scale }}>
          <div
            style={{
              background: PANEL_BG,
              color: TEXT_BRIGHT,
              fontFamily: FONT_SMOOTH,
              fontWeight: 700,
              fontSize: labelSize * scale,
              lineHeight: `${labelSize * 1.6 * scale}px`,
              padding: `0 ${12 * scale}px`,
              display: "inline-block",
            }}
          >
            {name}
          </div>
          <div
            style={{
              color: TEXT_COLOR,
              fontFamily: FONT_SMOOTH,
              fontSize: valueSize * scale,
              lineHeight: 1.4,
              marginTop: 8 * scale,
            }}
          >
            {val}
          </div>
        </div>
      ))}
    </>
  );
}
