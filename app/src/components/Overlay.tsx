import { FONT_SMOOTH, LAYOUT, OVERLAY_DIM, TEXT_COLOR } from "../theme";
import type { GameStatus } from "../types/game";
import { TitleScreen } from "./TitleScreen";
import { OptionsScreen } from "./OptionsScreen";

// The overlay's phase = the game's status, plus two UI-only phases that
// exist before the core knows about us: "connecting" (no state snapshot
// yet) and the pre-game screens. Declared here so App and the screens can
// share the exact union.
export type OverlayPhase = "connecting" | "start" | "options" | GameStatus;

// ============================================================
// WHAT THIS COMPONENT DOES
// ============================================================
// Status overlays drawn over the playfield (spec section 5). The "start"
// phase renders the full title screen (TitleScreen). Other exact text,
// positions, and timing are TBD from the owner's captures (open item);
// these are functional placeholders.
//
// PHASE ROUTING: "start" and "options" return whole screens (they cover
// everything); every other phase renders a dimmed box sized exactly to the
// playfield's inner area, so the stack and panels stay visible around it.
// "playing" renders nothing at all — except a transient notice (e.g.
// "Game reset.") pushed by a core-event, which floats in the same box.
export function Overlay({
  phase,
  score,
  notice,
  scale,
  cheat,
  musicSel,
  handicap,
  activeCol,
  topScores,
  topRun,
}: {
  phase: OverlayPhase;
  score: number;
  notice: string | null;
  scale: number;
  cheat?: boolean;
  musicSel?: number;
  handicap?: number;
  activeCol?: number;
  topScores?: { score: number; at: string }[];
  topRun?: boolean;
}) {
  if (phase === "start") {
    return <TitleScreen scale={scale} cheat={cheat} />;
  }
  if (phase === "options") {
    return (
      <OptionsScreen
        scale={scale}
        musicSel={musicSel ?? 0}
        handicap={handicap ?? 0}
        activeCol={activeCol ?? 0}
      />
    );
  }
  // The dimmed box matches the playfield's INNER area exactly: origin plus
  // both frame thicknesses on each side, then cols*cell x rows*cell. That
  // is why the frame values appear here — the overlay covers blocks, not
  // chrome.
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

  // Each phase picks its content; falling through with null means "render
  // nothing this frame" (the playing case without a notice).
  let content: React.ReactNode = null;
  switch (phase) {
    case "connecting":
      content = <div style={text(48)}>CONNECTING...</div>;
      break;
    case "paused":
      content = <div style={text(56)}>PAUSE</div>;
      break;
    case "level_complete":
      // End-of-stage celebration (owner request 2026-10-29): the
      // celebration track plays once and the next level starts by
      // itself; Enter skips ahead for the impatient.
      content = (
        <div style={text(48)}>
          STAGE CLEAR
          <br />
          <span className="blink">NEXT LEVEL...</span>
        </div>
      );
      break;
    case "game_over":
      // Top-5 runs (owner request 2026-10-25): the table of record
      // date/time/score with the firework rockets playing, until Enter.
      if (topRun) {
        content = (
          <div style={text(40)}>
            GAME OVER — TOP 5
            {(topScores ?? []).map((entry, i) => (
              <div
                key={i}
                style={{ fontFamily: FONT_SMOOTH, fontSize: 32 * scale, lineHeight: 1.8 }}
              >
                {/* Date formatting on the fly: the core stores ISO timestamps
                ("2026-10-31T21:04:07"); replace("T", " ") + slice(0, 16)
                turn that into "2026-10-31 21:04" — minute precision, no
                date library needed for a five-row table. "--" covers a
                record saved without a timestamp. */}
            {`${i + 1}.  ${entry.at ? entry.at.replace("T", " ").slice(0, 16) : "--"}  ${entry.score.toLocaleString("en-US")}`}
              </div>
            ))}
            <span className="blink">PRESS ENTER</span>
          </div>
        );
      } else {
        content = (
          <div style={text(48)}>
            GAME OVER
            <br />
            SCORE {score.toLocaleString("en-US")}
            <br />
            PRESS ENTER
          </div>
        );
      }
      break;
    case "playing":
      content = notice ? <div style={text(36)}>{notice}</div> : null;
      break;
  }
  if (content === null) return null;
  return <div style={box}>{content}</div>;
}
