import { FONT_SMOOTH, LAYOUT, PANEL_BG, TEXT_BRIGHT, TEXT_COLOR } from "../theme";
import type { GameState } from "../hooks/useGameState";

// Score, high score, lines, and level readouts (spec 6.1), styled after the
// captures: white labels on gray bars, pale-blue values.
export function ScorePanel({
  state,
  scale,
}: {
  state: GameState | null;
  scale: number;
}) {
  const { x, y, rowHeight, labelSize, valueSize } = LAYOUT.score;
  const rows: Array<[string, string]> = [
    ["SCORE", String(state?.score ?? 0)],
    ["HIGH SCORE", String(state?.high_score ?? 0)],
    ["LINES", String(state?.lines ?? 0)],
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
