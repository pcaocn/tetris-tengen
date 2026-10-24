"""Gravity table and soft drop tests (spec 4.3, section 9)."""

from tetris_core.game import SPAWN_Y, Game
from tetris_core.gravity import (
    SOFT_DROP_MIN_FPR,
    SOFT_DROP_START_FPR,
    frames_per_row,
    soft_drop_fpr,
)
from tetris_core.pieces import Piece

from helpers import FixedRNG


def test_frames_per_row_placeholder_table():
    # These assertions record the PLACEHOLDER table (open item, spec 4.3).
    assert frames_per_row(0) == 50
    assert frames_per_row(5) == 19
    assert frames_per_row(9) == 6
    assert frames_per_row(13) == 2
    assert frames_per_row(99) == 2  # clamps to the last entry
    assert frames_per_row(-1) == 50  # clamps to level 0


def test_soft_drop_curve_placeholder():
    # Records the PLACEHOLDER acceleration curve (open item, spec 4.3):
    # starts at SOFT_DROP_START_FPR, loses one frame per row every
    # SOFT_DROP_ACCEL_EVERY held frames, floors at SOFT_DROP_MIN_FPR, and is
    # never slower than normal gravity.
    assert soft_drop_fpr(50, 0) == SOFT_DROP_START_FPR
    assert soft_drop_fpr(50, 3) == 6
    assert soft_drop_fpr(50, 4) == 5
    assert soft_drop_fpr(50, 8) == 4
    assert soft_drop_fpr(50, 20) == 1
    assert soft_drop_fpr(50, 100) == SOFT_DROP_MIN_FPR
    assert soft_drop_fpr(2, 0) == 2  # never slower than normal gravity
    assert soft_drop_fpr(2, 100) == 1  # still accelerates past level speed


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def test_piece_falls_one_row_per_interval(tmp_path):
    game = make_game(tmp_path)
    # Placeholder level 0 speed: 50 frames per row.
    for _ in range(49):
        game.update()
    assert game._piece_y == SPAWN_Y
    game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_soft_drop_starts_gradually(tmp_path):
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    # Placeholder start speed 6 fpr: exactly one row in the first 6 frames,
    # i.e. soft drop does NOT jump to instant speed on press (spec 4.3).
    for _ in range(6):
        game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_soft_drop_is_faster_than_normal(tmp_path):
    soft = make_game(tmp_path)
    normal = make_game(tmp_path)
    soft.handle_input("soft_drop_on")
    for _ in range(30):
        soft.update()
        normal.update()
    assert soft._piece_y >= normal._piece_y + 5


def test_soft_drop_off_restores_normal_speed(tmp_path):
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    for _ in range(10):
        game.update()
    game.handle_input("soft_drop_off")
    y_after_soft = game._piece_y
    for _ in range(30):
        game.update()
    # 30 frames at the placeholder level 0 speed (50 fpr) = no further rows.
    assert game._piece_y == y_after_soft


def test_gravity_counter_resets_on_spawn(tmp_path):
    game = make_game(tmp_path)
    for _ in range(20):
        game.update()
    assert game._gravity_counter == 20 % 50
    game._spawn_next()
    assert game._gravity_counter == 0
    assert game._piece_y == SPAWN_Y
