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
    """The tools runner must use NO_SAVE even when a player table exists.

    Seed 1253421050 is a deterministic qualifying run under the current
    rules: it tops out with a positive score. The test does not hardcode
    the historic 91,300-point write; it only requires a real game over
    whose score would beat the seeded low score, then proves the player
    table stayed byte-for-byte identical.
    """
    player_path = tmp_path / "player-highscore.json"
    highscore.add(1, player_path)
    before = player_path.read_bytes()

    monkeypatch.setenv("TETRIS_HIGHSCORE_PATH", str(player_path))
    runner = load_tools_runner()
    result = runner.run_one(1253421050)

    assert result["died"] is True
    assert result["score"] > 1
    assert player_path.read_bytes() == before