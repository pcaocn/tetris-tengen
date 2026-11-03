"""JSON-line protocol: parse commands, build response and state events.

Spec 2.2: requests arrive as JSON lines on stdin; every command gets a
`response` event with the same id; `state` snapshots carry the full game
state. Python never crashes on bad input (spec 2.2, section 8).

Protocol note (documented spec gap): spec 2.4 says the UI sends `left`/
`right` on keydown and stops on keyup, but the action list in spec 2.2 has
no release actions, and Python-side DAS cannot work without them. This
implementation adds `left_off` and `right_off` actions.

WHAT THIS LAYER IS RESPONSIBLE FOR
----------------------------------
Only three things:
  1. Parse a JSON line into a command.
  2. Validate the command's fields and hand it to `Game`.
  3. Build the state snapshot that the UI renders.

It deliberately contains NO game rules. Every rule lives in `Game`,
`Board`, `Pieces`, `Gravity` or `Scoring`. If you find yourself adding a
Tetris rule here, it belongs in the engine instead.

THE REQUEST/EVENT CONTRACT
---------------------------
Every request carries an `id`, and every request is answered by exactly
one `response` event with the same `id` -- that is how the Rust shell
matches an answer to its question. A successful command is followed by a
fresh `state` event, so the UI always sees the effect of the command
immediately rather than waiting for the next 60 Hz tick.

ROBUSTNESS (spec 2.2 and section 8): a malformed line, a bad field type,
or an unknown command produces an error `response` -- and the process
keeps running. The game loop must never die because of a bad command.
"""

from __future__ import annotations


import json

from .board import HIDDEN_ROWS
from .game import Game, locked_color_index


class Core:
    """Protocol layer around one Game."""

    def __init__(self, highscore_path=None, rng=None) -> None:
        # One Game for the lifetime of the process. `rng` is injectable so
        # the benchmarks can drive the same core with a fixed seed.
        self.game = Game(highscore_path=highscore_path, rng=rng)

    def handle_line(self, line: str) -> list[dict]:
        """Process one stdin line; return the events to emit.

        Returns a LIST because a command can produce several events: at
        minimum a `response`, and normally a `response` plus a `state`.
        """
        # Step 1: parse. A line that is not valid JSON, or is valid JSON
        # but not an object, is a protocol error -- report it and carry on.
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError("command must be a JSON object")
        except (ValueError, TypeError) as exc:
            return [
                {
                    "type": "response",
                    "id": None,
                    "ok": False,
                    "error": f"malformed command: {exc}",
                },
                {"type": "log", "level": "error", "message": f"malformed command: {line!r}"},
            ]
        # Step 2: remember the id so the answer can be matched to it.
        msg_id = msg.get("id")
        # Step 3: run the command. Any exception it raises becomes an
        # error response -- the process must survive bad input.
        try:
            self._dispatch(msg)
        except Exception as exc:  # never crash on bad input (spec 2.2)
            return [{"type": "response", "id": msg_id, "ok": False, "error": str(exc)}]
        # Step 4: success -- acknowledge, then send the new state.
        return [{"type": "response", "id": msg_id, "ok": True}, self.state_event()]

    def _dispatch(self, msg: dict) -> None:
        """Validate one command and apply it to the game.

        Every branch validates its own arguments. Note the explicit
        `isinstance(x, bool)` checks: in Python `True` is an `int`, so
        without that check a boolean would silently pass as a number.
        """
        cmd = msg.get("cmd")
        if cmd == "input":
            action = msg["action"]
            if not isinstance(action, str):
                raise ValueError("action must be a string")
            self.game.handle_input(action)
        elif cmd == "new_game":
            level = msg.get("level", 0)
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("level must be an integer")
            music = msg.get("music")
            if music is not None and not isinstance(music, str):
                raise ValueError("music must be a string")
            handicap = msg.get("handicap", 0)
            if isinstance(handicap, bool) or not isinstance(handicap, int):
                raise ValueError("handicap must be an integer")
            # The options page offers 0, 3, 6, 9 and 12 garbage rows;
            # anything outside 0..12 is rejected here.
            if not 0 <= handicap <= 12:
                raise ValueError("handicap must be 0..12")
            self.game.new_game(level, music, handicap)
        elif cmd == "set_level":
            # Cheat command: jump to a level. Levels are 0..9 (the
            # locked-color table has ten entries, spec 6.2).
            level = msg.get("level")
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("level must be an integer")
            if not 0 <= level <= 9:
                raise ValueError("level must be 0..9")
            if not self.game.set_level(level):
                raise ValueError("cannot change level while not playing")
        elif cmd == "set_music":
            music = msg.get("music")
            if music is not None and not isinstance(music, str):
                raise ValueError("music must be a string")
            if not self.game.set_music(music):
                raise ValueError("cannot change music while not playing")
        elif cmd == "set_autopilot":
            # Cheat command: "quick" (clear lines fast), "highscore"
            # (maximize score), or null to turn the autopilot off.
            if "mode" not in msg:
                raise ValueError("mode is required")
            mode = msg["mode"]
            if mode is not None and mode not in ("quick", "highscore"):
                raise ValueError('mode must be "quick", "highscore", or null')
            self.game.set_autopilot(mode)
        elif cmd == "pause":
            self.game.pause()
        elif cmd == "get_state":
            pass  # the state event below is the answer
        else:
            raise ValueError(f"unknown cmd: {cmd!r}")

    def state_event(self) -> dict:
        """Build the full state snapshot the UI renders.

        This is the ONLY thing the UI ever sees about the game. Every
        value here is a fact, never a rule: the UI draws the board, the
        score, and the piece -- it never computes any of them.
        """
        g = self.game
        if g.piece_kind is None:
            # No active piece (between locks, during a clear animation,
            # or after game over). The UI draws nothing for "current".
            current = None
        else:
            # Cells in visible coordinates; rows above the playfield are
            # negative and the UI clips them. The shift by HIDDEN_ROWS
            # is the whole extended-grid -> visible-grid conversion.
            cells = [[x, y - HIDDEN_ROWS] for x, y in g.piece_cells()]
            current = {"kind": g.piece_kind.name, "cells": cells}
        # Line-clear dissolve (spec 4.5): rows being cleared, in visible
        # coordinates, plus the animation frame; null when not clearing.
        clearing = None
        if g.clearing is not None:
            rows, frame = g.clearing
            clearing = {"rows": [r - HIDDEN_ROWS for r in rows], "frame": frame}
        return {
            "type": "state",
            "frame": g.frame,
            "board": g.board.visible_grid(),
            "current": current,
            "clearing": clearing,
            "next": g.next_piece.name,
            "score": g.score,
            "lines": g.lines,
            "level": g.level,
            "high_score": g.high_score,
            "stats": g.stats.as_dict(),
            "status": g.status.value,
            # Monotonic counters: the UI watches these numbers change to
            # know when to play the lock and clear sounds (spec 5).
            "lock_count": g.lock_count,
            "clear_count": g.clear_count,
            "top_scores": g.top_scores,
            "top_run": g.top_run,
            "autopilot": g.autopilot,
            "music_track": g.music,
            "music_phase": g.music_phase,
            # Which locked-piece color the UI should paint (spec 6.2).
            "color_index": locked_color_index(g.level),
        }
