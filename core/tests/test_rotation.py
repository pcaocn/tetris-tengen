"""Rotation rule tests: top-left anchoring, vertical I exception, wall kick.

Spec 4.2 and section 9. The anchoring rule (every state touches the left and
top edges of the bounding box; vertical I in the second column) is tested as
a property over the whole table, and wall-kick behavior is tested against a
live Game.

WHAT THIS FILE COVERS (two kinds of test)
-----------------------------------------
    1. TABLE PROPERTIES -- test_anchor_rule_touches_top_and_left walks
       all 28 piece-states and asserts the anchoring rule as a
       property, complementing test_pieces.py's verbatim fixture.
    2. LIVE-GAME BEHAVIOUR -- the rest of the file drives a real Game
       with `handle_input("rotate_cw"/"rotate_ccw")`, because the kick
       only exists where the piece meets a wall, the floor, or the
       stack. Pure-table tests cannot see it.

WHY THE KICK TESTS PLACE OBSTACLES BY HAND
------------------------------------------
The tests write blocked cells straight into `game.board` (lock_cells)
and teleport the piece (`game._piece_x = 4 ...`) instead of playing
hundreds of frames to reach the same position. That is deliberate:
each test pins ONE rule (in-place rotation failed -> try the kick ->
kick failed -> reject), and a long natural setup would make the
failure ambiguous. The coordinates in the comments are read off the
Tengen table in pieces.py.

Note: this file used to define its own local FixedRNG (it only needs
piece sequences, never handicap holes). That duplicate was removed in
favour of `helpers.FixedRNG`: the two `next_piece()` implementations were
identical, so keeping both only risked them drifting apart. The shared
stand-in's `hole_column()` is simply never called here.
"""

import pytest

from tetris_core.board import HEIGHT, HIDDEN_ROWS, WIDTH
from tetris_core.game import SPAWN_X, SPAWN_Y, Game
from tetris_core.pieces import ROTATIONS, Piece, shape

from helpers import FixedRNG

PIECE_STATES = [(piece, state) for piece in Piece for state in range(4)]


def make_game(tmp_path, pieces=(Piece.T, Piece.O)):
    """A live Game with a scripted piece stream on an isolated file.

    The T is the workhorse here: its four states are all different
    (unlike I/O/S/Z which repeat states), so rotation tests can tell
    the states apart. The O follows as an inert next piece.
    """
    return Game(
        highscore_path=tmp_path / "highscore.json",
        rng=FixedRNG(pieces),
    )


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_anchor_rule_touches_top_and_left(piece, state):
    """Every state must touch the top and left edges of its box.

    This is the Tengen anchoring rule (spec 4.2) stated as a property
    over the whole table: min_x == 0 and min_y == 0 for all 28
    piece-states -- EXCEPT the vertical I (states 1 and 3), which sits
    in the second column (min_x == 1) while still touching the top.

    Why it matters: top-left anchoring is what makes rotation "pivot
    around the box corner" rather than around the piece centre. It
    rules out Nintendo-style T-spins, and the autopilot's column-range
    arithmetic assumes it. A new state violating the rule would break
    both silently without this test.
    """
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
    """Four turns each way must return the piece to its exact cells.

    Step 1: record the spawn-state cells of the T on an empty board.
    Step 2: press rotate_cw four times -- a full 360 degrees.
    Step 3: the cells must be identical to the start; then the same
       for four CCW presses.

    On an empty board every rotation succeeds (no kicks, no rejects),
    so this pins the state arithmetic ((rot +/- 1) % 4) and the
    anchoring: if any state leaked a shift or a kick, the cycle would
    drift and the piece would end up displaced.
    """
    game = make_game(tmp_path, [Piece.T, Piece.O])
    start = game.piece_cells()
    for _ in range(4):
        game.handle_input("rotate_cw")
    assert game.piece_cells() == start
    for _ in range(4):
        game.handle_input("rotate_ccw")
    assert game.piece_cells() == start


def test_clockwise_and_counterclockwise_use_same_table(tmp_path):
    """CW and CCW must be two directions through ONE table.

    Step 1: one CW press from state 0 -- the piece must now be exactly
       table state 1, at its current (unchanged) position.
    Step 2: two CCW presses -- 1 -> 0 -> 3, wrapping modulo 4.

    The expected cells are rebuilt from ROTATIONS[Piece.J] with the
    game's live (x, y), so the test proves the game renders the SAME
    table both ways, not a second CCW-specific table. The J is chosen
    because its four states are all distinct, making any mix-up
    visible.
    """
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
    """When neither the in-place rotation NOR the kick fits, nothing moves.

    Step 1: teleport the T to (4, 10) in its spawn state -- cells
       (5,10), (4,11), (5,11), (6,11).
    Step 2: the CCW target (state 3) needs cells (5,10), (5,11),
       (5,12), (4,11); the kick candidate (one square left) needs
       (4,10), (4,11), (4,12), (3,11). Lock blocks into BOTH sets.
    Step 3: the rotation must be silently ignored -- no exception, the
       piece stays at state 0, column 4.

    This is the game's error handling for an impossible rotation: a
    failed rotation must never crash or half-apply. (The `is None`
    assertion documents that handle_input returns nothing here -- the
    rejection is communicated by the unchanged state, not an error.)
    """
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
    """A blocked rotation must kick exactly ONE square to the LEFT.

    Step 1: T at (4, 10), spawn state.
    Step 2: block ONLY the in-place CCW cell (5, 12). The kicked
       landing cells -- (4,10), (4,11), (4,12), (3,11) -- stay free.
    Step 3: rotate CCW.

    The piece must end in state 3 at column 3 (4 - 1): rotated AND
    shifted, with all its cells genuinely free. This is Tengen's single
    wall kick (spec 4.2) -- the entire forgiveness the rotation system
    offers, and the difference between rotating against a wall
    succeeding or not for the player.
    """
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
    """The kick is left-only by design: a fitting right-kick must be refused.

    Step 1: T at (4, 10).
    Step 2: block the in-place CCW cell (5, 12) AND the left-kick cell
       (4, 12), but leave (6, 12) free -- so a hypothetical kick to the
       RIGHT would fit.
    Step 3: rotate CCW; the rotation must still be rejected (state 0,
       column 4).

    This pins the direction of the kick, not just its existence: Tengen
    kicks one square LEFT only (spec 4.2), so the engine must not
    "helpfully" kick the other way. A symmetric kick would be a silent
    rule change the owner has not asked for.
    """
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
    """A horizontal I one row above the floor must refuse to rotate.

    Step 1: place the horizontal I with its box at (4, 21) -- cells at
       row 21, columns 4..7 (one row above the floor at row 22).
    Step 2: rotate CW. The vertical I needs rows 21..24 in its box's
       second column -- rows 23 and 24 are past the bottom (row 22) --
       and the left-kick at column 3 needs rows 21..24 too.
    Step 3: both candidates fail, so the I stays horizontal and in
       place.

    There is no floor kick in the Tengen table (spec 4.2, still a
    VERIFY item): rotating an I on the flat floor must do nothing. A
    version that "helped" here would change how the endgame is played.
    """
    game = make_game(tmp_path, [Piece.I, Piece.O])
    # Horizontal I one row above the floor: cells at row 21, columns 4..7.
    game._piece_x = 4
    game._piece_y = 21
    game.handle_input("rotate_cw")
    assert game._rot == 0  # vertical would need rows 21..24; board ends at 22
    assert game.piece_cells() == [(4, 21), (5, 21), (6, 21), (7, 21)]


def test_i_rotates_fully_near_right_wall(tmp_path):
    """The I rotates against the RIGHT wall with no kick needed.

    Step 1: horizontal I hugging the right wall -- box at (6, 5), cells
       at columns 6..9.
    Step 2: rotate CW. The vertical I sits in the box's SECOND column
       (6 + 1 = 7): cells (7,5)..(7,8) -- clear of the wall.
    Step 3: the rotation succeeds outright (state 1, no shift); a CCW
       turn returns the horizontal I exactly where it was.

    This documents a pleasant consequence of the top-left anchoring:
    the vertical I's second-column quirk means right-wall overlaps
    cannot occur during rotation, so kicks only ever trigger on stack
    or floor contact (spec 4.2 VERIFY note).
    """
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
    """A fresh game must spawn the piece exactly where spec 4.1 says.

    Step 1: build the game (the first FixedRNG piece is the T).
    Step 2: check the box anchor: x == SPAWN_X (5), y == SPAWN_Y (3 =
       HIDDEN_ROWS).
    Step 3: check the cells: the leftmost cell is at the spawn column,
       the topmost at the spawn row, nothing runs off the right edge,
       and every row is < 20 -- the piece occupies the top band of the
       board, per the owner decision of 2026-10-24 that spawn happens
       at the TOP of the visible playfield (row 3 is the first visible
       row) so the piece is immediately on screen.

    This is the contract every other module assumes: the game-over rule
    (a blocked spawn ends the game) and the protocol's visible-cell
    arithmetic both start from this exact position.
    """
    game = make_game(tmp_path, [Piece.T, Piece.O])
    assert game._piece_x == SPAWN_X
    assert game._piece_y == SPAWN_Y
    cells = game.piece_cells()
    # spec 4.1: the box is anchored at column 5 and row 3. The extended
    # board is 23 rows tall, indexed 0 (top) to 22 (bottom), and rows
    # 0-2 are the HIDDEN rows -- so row 3 is the FIRST VISIBLE row. The
    # piece therefore appears at the very top of the playfield (owner
    # decision 2026-10-24: spawn at the top of the VISIBLE area, so the
    # next piece shows on screen at once), NOT hidden above it.
    #
    # For the T piece that means cells at (6,3) (5,4) (6,4) (7,4):
    # one cell on the first visible row, three on the second.
    assert min(x for x, _ in cells) == SPAWN_X
    assert min(y for _, y in cells) == SPAWN_Y
    assert max(y for _, y in cells) < HEIGHT
    # The rule this pins: NO part of the spawned piece may sit in the
    # hidden rows. That is the owner decision of 2026-10-24 stated as an
    # assertion -- spawn at the top of the VISIBLE area, so the piece is
    # on screen at once rather than dropping in from above. (This line
    # used to read `all(y < 20)`, a bound so loose it would also have
    # passed with the piece spawned at row 15.)
    assert all(y >= HIDDEN_ROWS for _, y in cells)
    assert max(x for x, _ in cells) < WIDTH
