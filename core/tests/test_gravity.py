"""Gravity table and soft drop tests (spec 4.3, section 9).

WHAT THIS FILE TESTS
====================
Two layers of the fall-speed rules:

    1. THE TABLE (pure functions from gravity.py): `frames_per_row`
       returns the Tengen interval for a level, including the fractional
       high-level values; `soft_drop_fpr` returns the effective speed
       while Down is held, with its two guard rails.
    2. THE FRAME LOOP (through a live Game): gravity really moves the
       piece on the schedule the table promises, soft drop engages and
       disengages mid-fall, and the gravity accumulator restarts at zero
       with each new piece.

WHY QUARTER FRAMES
------------------
The cartridge has fractional intervals (5.5, 3.75, ...). The game keeps
four accumulator units per frame, so the table values are exact and the
tests can count ticks without floating-point drift.
"""

from __future__ import annotations

import pytest

from tetris_core.game import SPAWN_Y, Game
from tetris_core.gravity import (
    SOFT_DROP_MIN_FPR,
    SOFT_DROP_START_FPR,
    frames_per_row,
    soft_drop_fpr,
)
from tetris_core.pieces import Piece

from helpers import FixedRNG


def test_frames_per_row_tengen_table():
    """The normal-gravity table, sampled at its ends and fractional middle."""
    assert frames_per_row(0) == 33
    assert frames_per_row(5) == 14
    assert frames_per_row(9) == 6
    assert frames_per_row(10) == 5.5
    assert frames_per_row(13) == 4
    assert frames_per_row(14) == 3.75
    assert frames_per_row(16) == 3.25
    assert frames_per_row(17) == 3
    assert frames_per_row(99) == 3  # clamps to the last entry
    assert frames_per_row(-1) == 33  # clamps to level 0


def test_soft_drop_curve_and_guard_rails():
    """The soft-drop curve and its two guard rails."""
    assert soft_drop_fpr(33, 0) == SOFT_DROP_START_FPR
    assert soft_drop_fpr(33, 3) == 6
    assert soft_drop_fpr(33, 4) == 5
    assert soft_drop_fpr(33, 8) == 4
    assert soft_drop_fpr(33, 20) == 1
    assert soft_drop_fpr(33, 100) == SOFT_DROP_MIN_FPR
    assert soft_drop_fpr(5.5, 0) == 5.5  # never slower than normal
    assert soft_drop_fpr(5.5, 100) == 1


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    """A Game on an isolated highscore file with a scripted piece stream."""
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def test_piece_falls_one_row_on_tick_33(tmp_path):
    """Level 0 falls its first row on tick 33, not tick 32."""
    game = make_game(tmp_path)
    for _ in range(32):
        game.update()
    assert game._piece_y == SPAWN_Y
    game.update()
    assert game._piece_y == SPAWN_Y + 1


@pytest.mark.parametrize(
    ("level", "ticks", "rows"),
    [
        (0, 33, 1),
        (10, 11, 2),
        (14, 15, 4),
        (16, 13, 4),
    ],
)
def test_gravity_acceptance_through_frame_update(tmp_path, level, ticks, rows):
    """The brief's acceptance cases, exercised through `update()`."""
    game = make_game(tmp_path)
    game.new_game(level=level)
    for _ in range(ticks):
        game.update()
    assert game._piece_y == SPAWN_Y + rows


def test_soft_drop_starts_gradually(tmp_path):
    """Holding Down starts at 6 fpr: one row in the first 6 frames."""
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    for _ in range(6):
        game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_soft_drop_is_faster_than_normal(tmp_path):
    """A soft-dropping piece must outrun an identical normal one."""
    soft = make_game(tmp_path)
    normal = make_game(tmp_path)
    soft.handle_input("soft_drop_on")
    for _ in range(30):
        soft.update()
        normal.update()
    assert soft._piece_y >= normal._piece_y + 5


def test_soft_drop_off_restores_normal_speed(tmp_path):
    """Releasing Down hands the piece back to normal gravity."""
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    for _ in range(10):
        game.update()
    game.handle_input("soft_drop_off")
    y_after_soft = game._piece_y
    for _ in range(30):
        game.update()
    assert game._piece_y == y_after_soft


def test_switching_to_soft_drop_does_not_build_backlog(tmp_path):
    """Fast speed must discard stale accumulator progress, not bank it.

    After 32 normal frames the accumulator holds 128 quarter-frames.
    Pressing Down makes the threshold 24. The next tick should drop one
    row (capped to one tick of progress), and the following tick should
    not immediately drop again from the old backlog.
    """
    game = make_game(tmp_path)
    for _ in range(32):
        game.update()
    assert game._gravity_counter == 128
    assert game._piece_y == SPAWN_Y

    game.handle_input("soft_drop_on")
    game.update()
    assert game._piece_y == SPAWN_Y + 1
    game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_gravity_accumulator_resets_on_spawn(tmp_path):
    """A fresh piece starts its fall schedule from zero."""
    game = make_game(tmp_path)
    for _ in range(20):
        game.update()
    assert game._gravity_counter == 20 * 4  # quarter-frame units
    game._spawn_next()
    assert game._gravity_counter == 0
    assert game._piece_y == SPAWN_Y