"""JSON-line protocol: parse commands, build response and state events.

Spec 2.2: requests arrive as JSON lines on stdin; every command gets a
`response` event with the same id; `state` snapshots carry the full game
state. Python never crashes on bad input (spec 2.2, section 8).

Protocol note (documented spec gap): spec 2.4 says the UI sends `left`/
`right` on keydown and stops on keyup, but the action list in spec 2.2 has
no release actions, and Python-side DAS cannot work without them. This
implementation adds `left_off` and `right_off` actions.
"""

from __future__ import annotations


import json

from .board import HIDDEN_ROWS
from .game import Game, locked_color_index


class Core:
    """Protocol layer around one Game."""

    def __init__(self, highscore_path=None, rng=None) -> None:
        self.game = Game(highscore_path=highscore_path, rng=rng)

    def handle_line(self, line: str) -> list[dict]:
        """Process one stdin line; return the events to emit."""
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
        msg_id = msg.get("id")
        try:
            self._dispatch(msg)
        except Exception as exc:  # never crash on bad input (spec 2.2)
            return [{"type": "response", "id": msg_id, "ok": False, "error": str(exc)}]
        return [{"type": "response", "id": msg_id, "ok": True}, self.state_event()]

    def _dispatch(self, msg: dict) -> None:
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
            if not 0 <= handicap <= 12:
                raise ValueError("handicap must be 0..12")
            self.game.new_game(level, music, handicap)
        elif cmd == "set_level":
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
        g = self.game
        if g.piece_kind is None:
            current = None
        else:
            # Cells in visible coordinates; rows above the playfield are
            # negative and the UI clips them.
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
            "lock_count": g.lock_count,
            "clear_count": g.clear_count,
            "top_scores": g.top_scores,
            "top_run": g.top_run,
            "autopilot": g.autopilot,
            "music_track": g.music,
            "music_phase": g.music_phase,
            "color_index": locked_color_index(g.level),
        }
