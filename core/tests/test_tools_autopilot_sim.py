"""Regression tests for the legacy tools/autopilot_sim.py runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from tetris_core import highscore

TOOLS_RUNNER = Path(__file__).resolve().parents[2] / "tools" / "autopilot_sim.py"


def load_tools_runner():
    spec = importlib.util.spec_from_file_location("tetris_tools_autopilot_sim", TOOLS_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tools_runner_does_not_touch_player_highscore(tmp_path, monkeypatch):
    """Exercise a real qualifying top-out independently of planner strength."""
    player_path = tmp_path / "player-highscore.json"
    highscore.add(1, player_path)
    before = player_path.read_bytes()

    monkeypatch.setenv("TETRIS_HIGHSCORE_PATH", str(player_path))
    runner = load_tools_runner()
    class NearTopOut(runner.Game):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.score = 100
            self._piece_y = 17
            self.board.lock_cells([(x, 3) for x in range(1, 10)], 1)
            self.board.lock_cells([(x, 4) for x in range(1, 10)], 1)

    monkeypatch.setattr(runner, "Game", NearTopOut)
    result = runner.run_one(1253421050)

    assert result["died"] is True
    assert result["score"] > 1
    assert player_path.read_bytes() == before