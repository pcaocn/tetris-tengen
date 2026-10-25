import { FONT_SMOOTH, LAYOUT, OVERLAY_DIM, TEXT_COLOR } from "../theme";
import type { GameStatus } from "../hooks/useGameState";
import { TitleScreen } from "./TitleScreen";

export type OverlayPhase = "connecting" | "start" | GameStatus;

// Status overlays drawn over the playfield (spec section 5). The "start"
// phase renders the full title screen (TitleScreen). Other exact text,
// positions, and timing are TBD from the owner's captures (open item);
// these are functional placeholders.
export function Overlay({
  phase,
  score,
  notice,
  scale,
  cheat,
}: {
  phase: OverlayPhase;
  score: number;
  notice: string | null;
  scale: number;
  cheat?: boolean;
}) {
  if (phase === "start") {
    return <TitleScreen scale={scale} cheat={cheat} />;
  }
  const { x, y, cols, rows, cell, frameOuter, frameInner } = LAYOUT.playfield;
  const box = {
    position: "absolute" as const,
    left: (x + frameOuter + frameInner) * scale,
    top: (y + frameOuter + frameInner) * scale,
    width: cols * cell * scale,
    height: rows * cell * scale,
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    gap: 48 * scale,
    background: OVERLAY_DIM,
  };
  const text = (size: number): React.CSSProperties => ({
    fontFamily: FONT_SMOOTH,
    fontWeight: 700,
    color: TEXT_COLOR,
    fontSize: size * scale,
    textAlign: "center" as const,
    lineHeight: 1.6,
  });

  let content: React.ReactNode = null;
  switch (phase) {
    case "connecting":
      content = <div style={text(48)}>CONNECTING...</div>;
      break;
    case "paused":
      content = <div style={text(56)}>PAUSE</div>;
      break;
    case "game_over":
      content = (
        <div style={text(48)}>
          GAME OVER
          <br />
          SCORE {score}
          <br />
          PRESS ENTER
        </div>
      );
      break;
    case "playing":
      content = notice ? <div style={text(36)}>{notice}</div> : null;
      break;
  }
  if (content === null) return null;
  return <div style={box}>{content}</div>;
}
