"""Rotation rule tests: top-left anchoring, vertical I exception, wall kick.

Spec 4.2 and section 9. The anchoring rule (every state touches the left and
top edges of the bounding box; vertical I in the second column) is tested as
a property over the whole table, and wall-kick behavior is tested against a
live Game.
"""

import pytest

from tetris_core.board import HEIGHT, WIDTH
from tetris_core.game import SPAWN_X, SPAWN_Y, Game
from tetris_core.pieces import ROTATIONS, Piece, shape

PIECE_STATES = [(piece, state) for piece in Piece for state in range(4)]


class FixedRNG:
    """Deterministic stand-in for PieceRNG (spec 4.6)."""

    def __init__(self, pieces):
        self._pieces = list(pieces)
        self._i = 0

    def next_piece(self):
        piece = self._pieces[self._i % len(self._pieces)]
        self._i += 1
        return piece


def make_game(tmp_path, pieces=(Piece.T, Piece.O)):
    return Game(
        highscore_path=tmp_path / "highscore.json",
        rng=FixedRNG(pieces),
    )


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_anchor_rule_touches_top_and_left(piece, state):
    cells = shape(piece, state)
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    if piece is Piece.I and state in (1, 3):
        # vertical I exception: second column, still touching the top edge
        assert min_x == 1
        assert min_y == 0
    else:
        assert min_x == 0
        assert min_y == 0


def test_full_rotation_cycle_returns_to_spawn(tmp_path):
    game = make_game(tmp_path, [Piece.T, Piece.O])
    start = game.piece_cells()
    for _ in range(4):
        game.handle_input("rotate_cw")
    assert game.piece_cells() == start
    for _ in range(4):
        game.handle_input("rotate_ccw")
    assert game.piece_cells() == start


def test_clockwise_and_counterclockwise_use_same_table(tmp_path):
    game = make_game(tmp_path, [Piece.J, Piece.O])
    game.handle_input("rotate_cw")
    assert game.piece_cells() == [
        (x + game._piece_x, y + game._piece_y) for x, y in ROTATIONS[Piece.J][1]
    ]
    game.handle_input("rotate_ccw")
    game.handle_input("rotate_ccw")
    cells = game.piece_cells()
    assert cells == [
        (x + game._piece_x, y + game._piece_y) for x, y in ROTATIONS[Piece.J][3]
    ]


def test_rotation_rejected_when_blocked_and_kick_blocked(tmp_path):
    game = make_game(tmp_path, [Piece.T, Piece.O])
    # T spawn state at (4, 10): cells (5,10), (4,11), (5,11), (6,11).
    game._piece_x = 4
    game._piece_y = 10
    # CCW target cells: (5,10), (5,11), (5,12), (4,11). Block the kick's
    # landing cells too so neither in-place nor kicked rotation fits.
    game.board.lock_cells([(5, 12), (4, 10), (4, 11), (4, 12)], 6)
    assert game.handle_input("rotate_ccw") is None  # input never raises here
    assert game._rot == 0
    assert game._piece_x == 4


def test_wall_kick_shifts_one_square_left(tmp_path):
    game = make_game(tmp_path, [Piece.T, Piece.O])
    game._piece_x = 4
    game._piece_y = 10
    # Block only the in-place CCW target cell (5, 12); the kicked cells
    # (4,10), (4,11), (4,12), (3,11) stay free.
    game.board.lock_cells([(5, 12)], 6)
    game.handle_input("rotate_ccw")
    assert game._rot == 3
    assert game._piece_x == 3
    assert game.board.cells_free(game.piece_cells())


def test_kick_cannot_move_right_only_left(tmp_path):
    game = make_game(tmp_path, [Piece.T, Piece.O])
    game._piece_x = 4
    game._piece_y = 10
    # Block in-place CCW cell (5,12) and the kicked (4,12) but leave (6,12)
    # free: a hypothetical right-kick would fit; Tengen only kicks left.
    game.board.lock_cells([(5, 12), (4, 12)], 6)
    game.handle_input("rotate_ccw")
    assert game._rot == 0
    assert game._piece_x == 4


def test_floor_rotation_of_i_is_rejected(tmp_path):
    game = make_game(tmp_path, [Piece.I, Piece.O])
    # Horizontal I one row above the floor: cells at row 21, columns 4..7.
    game._piece_x = 4
    game._piece_y = 21
    game.handle_input("rotate_cw")
    assert game._rot == 0  # vertical would need rows 21..24; board ends at 22
    assert game.piece_cells() == [(4, 21), (5, 21), (6, 21), (7, 21)]


def test_i_rotates_fully_near_right_wall(tmp_path):
    game = make_game(tmp_path, [Piece.I, Piece.O])
    # Horizontal I hugging the right wall: columns 6..9, box left at 6.
    game._piece_x = 6
    game._piece_y = 5
    game.handle_input("rotate_cw")
    # Vertical I lands in the second column of the box: column 7. No overlap
    # with the right wall, so no kick is needed. VERIFY note (spec 4.2):
    # with top-left anchored tables, right-wall overlaps cannot occur during
    # rotation; kicks only trigger on stack or floor contact.
    assert game._rot == 1
    assert game.piece_cells() == [(7, 5), (7, 6), (7, 7), (7, 8)]
    game.handle_input("rotate_ccw")
    assert game.piece_cells() == [(6, 5), (7, 5), (8, 5), (9, 5)]


def test_spawn_position_matches_spec(tmp_path):
    game = make_game(tmp_path, [Piece.T, Piece.O])
    assert game._piece_x == SPAWN_X
    assert game._piece_y == SPAWN_Y
    cells = game.piece_cells()
    # spec 4.1: box left at column 5, box top at row 22 from the bottom of
    # the extended board (row 0 here), entirely in the hidden rows.
    assert min(x for x, _ in cells) == SPAWN_X
    assert min(y for _, y in cells) == SPAWN_Y
    assert max(y for _, y in cells) < HEIGHT
    assert all(y < 20 for _, y in cells)  # above the visible playfield
    assert max(x for x, _ in cells) < WIDTH
