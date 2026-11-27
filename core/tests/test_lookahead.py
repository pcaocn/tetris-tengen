from copy import copy

import pytest

from tetris_core import autopilot, highscore, lookahead
from tetris_core.board import HEIGHT
from tetris_core.game import Game, SPAWN_X, SPAWN_Y, Status
from tetris_core.pieces import Piece
from helpers import FixedRNG


def position(kind, preview, heights):
    game = Game(highscore.NO_SAVE, FixedRNG([kind, preview]))
    columns = [(1 << h) - 1 for h in heights]
    game.board = lookahead._board(columns)
    game.set_autopilot("highscore")
    game._soft_drop = True
    return game, columns


@pytest.mark.parametrize("ready_weight,scoring_lock,clear_size", [(20, 2, 3), (28, 4, 4)])
def test_preview_changes_first_move_and_converts_the_well(monkeypatch, ready_weight,
                                                          scoring_lock, clear_size):
    monkeypatch.setitem(autopilot.STRATEGIES["highscore"], "ready_row_weight", ready_weight)
    heights = [3, 3, 2, 3, 4, 4, 3, 4, 4, 0]
    game, _ = position(Piece.T, Piece.I, heights)
    other, _ = position(Piece.T, Piece.O, heights)
    assert lookahead.plan(game, SPAWN_X, SPAWN_Y) != lookahead.plan(other, SPAWN_X, SPAWN_Y)
    assert game._rng._i == 2  # evaluating the preview must never draw another piece
    for _ in range(250):
        before = game.lines
        game.update()
        if game.lines > before:
            break
    assert (game.lock_count, game.lines - before) == (scoring_lock, clear_size)


def test_avoids_blocking_preview_spawn():
    game, _ = position(Piece.I, Piece.I, [0, 0, 0, 0, 16, 16, 16, 0, 0, 0])
    for _ in range(100):
        game.update()
        if game.lock_count:
            break
    assert game.lock_count == 1
    assert game.status is Status.PLAYING and game.piece_kind is Piece.I


@pytest.mark.parametrize("level,height", [(0, 0), (17, 13)])
def test_each_projected_landing_replays_in_live_engine(level, height):
    for kind in Piece:
        game, columns = position(kind, Piece.O, [height] * 5 + [0] * 5)
        game.level = level
        game._piece_y += 2
        game._gravity_counter = 8
        game._soft_held = 9
        for expected, cleared, _, route, award in lookahead._landings(game, columns):
            replay = copy(game)
            replay.board = lookahead._board(columns)
            replay.autopilot = None
            for action in route:
                assert replay.lock_count == 0
                assert lookahead.steer(replay, action)
                replay.update()
            for _ in range(100):
                if replay.lock_count:
                    break
                replay.update()
            assert replay.lock_count == 1
            assert replay.lines == cleared
            assert replay.score == award
            while replay.clearing:
                replay.update()
            assert autopilot._grid(replay.board) == autopilot._grid(lookahead._board(expected))


def test_move_before_rotation_when_spawn_rotation_is_blocked():
    game, columns = position(Piece.T, Piece.O, [0] * 10)
    for x, y in ((5, 3), (4, 3), (4, 4), (4, 5), (5, 5), (6, 5)):
        columns[x] |= 1 << (HEIGHT - 1 - y)
    game.board = lookahead._board(columns)
    assert not game._try_rotate(1) and not game._try_rotate(-1)
    assert any(route[0] == "right" and "cw" in route
               for _, _, _, route, _ in lookahead._landings(game, columns) if route)


def test_handoff_clears_held_repeat_before_autopilot_moves():
    game = Game(highscore.NO_SAVE, FixedRNG([Piece.L]))
    game.handle_input("left")
    for _ in range(13):
        game.update()
    x = game._piece_x
    game.set_autopilot("quick")
    assert game._das_dir == 0
    game.update()
    assert abs(game._piece_x - x) <= 1


def test_compact_features_match_reference_with_buried_holes():
    columns = [3, 0, 5, 70, 12, 56, 2, 31, 9, 1]
    grid = autopilot._grid(lookahead._board(columns))
    weights = autopilot.STRATEGIES["highscore"]
    actual = autopilot._board_evaluator(weights, 0.4)(2, 5, *lookahead._features(columns))
    assert actual == autopilot._score(grid, 2, 5, weights, 0.4)

def test_vertical_i_clears_four_rows_in_live_engine():
    game, _ = position(Piece.I, Piece.O, [4] * 9 + [0])
    for _ in range(100):
        game.update()
        if game.lock_count:
            break
    assert game.lines == 4


def test_held_drop_at_first_contact_is_used_for_placement_points():
    game, columns = position(Piece.O, Piece.O, [0] * 10)
    game._piece_y = HEIGHT - 2
    game._rest_frames = 2
    game._landing_soft_drop = False
    landing = next(lookahead._landings(game, columns))
    assert landing.route == ()
    assert landing.placement_award == 1


def test_well_bonus_fades_with_buried_holes():
    weights = {"ready_row_weight": 28, "ready_row_hole_cost": 2}
    assert [lookahead._ready_row_weight(weights, n) for n in (0, 1, 2, 3, 4, 10)] == [
        28, 26, 24, 22, 20, 20,
    ]
