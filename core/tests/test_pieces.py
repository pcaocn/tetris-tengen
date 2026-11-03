"""Fixture tests for the Tengen rotation table.

The EXPECTED table below records the rotation table as a fixture (spec 4.2,
section 9: one test per piece per state). It is derived from the spec's
anchoring rule; every state must still be checked against the cited source
(VERIFY, open item).
"""

import pytest

from tetris_core.pieces import ROTATIONS, Piece, box_size, shape

# The fixture below is the whole file's centre of gravity: an independent
# transcription of the rotation table. The tests compare `pieces.py`
# against THIS copy, not against a re-derivation of the anchoring rule,
# so an accidental edit to pieces.py cannot "correct" both sides at once.
# Coordinates are (x, y) offsets inside the piece's bounding box, x
# right and y down; the four entries per piece are states 0 (spawn),
# 1 (CW), 2 (180), 3 (CCW).
EXPECTED = {
    Piece.I: (
        ((0, 0), (1, 0), (2, 0), (3, 0)),
        ((1, 0), (1, 1), (1, 2), (1, 3)),
        ((0, 0), (1, 0), (2, 0), (3, 0)),
        ((1, 0), (1, 1), (1, 2), (1, 3)),
    ),
    Piece.O: (
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
    ),
    Piece.T: (
        ((1, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 1)),
        ((0, 0), (1, 0), (2, 0), (1, 1)),
        ((1, 0), (1, 1), (1, 2), (0, 1)),
    ),
    Piece.S: (
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
    ),
    Piece.Z: (
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((0, 1), (0, 2), (1, 0), (1, 1)),
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((0, 1), (0, 2), (1, 0), (1, 1)),
    ),
    Piece.J: (
        ((0, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 0)),
        ((0, 0), (1, 0), (2, 0), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (0, 2)),
    ),
    Piece.L: (
        ((2, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (0, 1)),
        ((0, 0), (1, 0), (1, 1), (1, 2)),
    ),
}

PIECE_STATES = [(piece, state) for piece in Piece for state in range(4)]


@pytest.mark.parametrize("piece", list(Piece))
def test_table_matches_recorded_fixture(piece):
    """Every piece's table must match the recorded fixture, verbatim.

    Spec 4.2 / section 9 asks for one test per piece; the parametrize
    turns this into exactly that. Comparing whole tuples (rather than
    cell by cell) means ANY change to the rotation table -- a swapped
    state, a moved cell, an extra entry -- fails this test loudly. That
    matters because the rotation table is a VERIFY item (spec 4.2): the
    day the owner confirms the real Tengen table, the fix lands here in
    EXPECTED and in pieces.py together.
    """
    assert ROTATIONS[piece] == EXPECTED[piece]


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_state_has_exactly_four_distinct_cells(piece, state):
    """A tetromino state is always four DISTINCT cells.

    Duplicates in a state would mean the piece occupies fewer than four
    board cells when locked -- a deformed piece that clears rows too
    easily and renders wrong. `set(cells)` checks uniqueness because
    `len(cells)` alone would pass a table that repeated a coordinate.
    """
    cells = shape(piece, state)
    assert len(cells) == 4
    assert len(set(cells)) == 4


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_state_cells_are_connected(piece, state):
    """The four cells of a state must form one connected piece.

    A flood fill from any cell must reach all four. A disconnected
    "piece" (two separate clusters) could never arise from a real
    tetromino -- it would lock into the board as two islands, fall
    through gaps a real piece could not, and make the game feel haunted.
    The frontier loop is a textbook BFS over the 4-connected grid
    neighbours of the starting cell.
    """
    cells = set(shape(piece, state))
    seen = {next(iter(cells))}
    frontier = list(seen)
    while frontier:
        x, y = frontier.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in cells and (nx, ny) not in seen:
                seen.add((nx, ny))
                frontier.append((nx, ny))
    assert seen == cells


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_box_size_matches_cells(piece, state):
    """`box_size` must equal the tight bounds of the state's cells.

    The box size is the piece's collision footprint for spawn and for
    the autopilot's column range, so it must be exactly
    (max_x + 1, max_y + 1) -- one wider/taller than the largest offset.
    A box smaller than the cells would clip cells off at the walls; a
    bigger one would block legal moves near the edge.
    """
    cells = shape(piece, state)
    w, h = box_size(piece, state)
    assert w == max(x for x, _ in cells) + 1
    assert h == max(y for _, y in cells) + 1


def test_i_horizontal_is_four_wide_top_row():
    """The spawn-state I: four cells across the TOP row of its box.

    The horizontal I spans (0,0)..(3,0): box 4x1, hugging the top edge
    per the anchoring rule. game.py relies on this when placing the I
    at spawn and when the autopilot computes which columns a drop fits.
    """
    assert box_size(Piece.I, 0) == (4, 1)
    assert shape(Piece.I, 0) == ((0, 0), (1, 0), (2, 0), (3, 0))


def test_i_vertical_sits_in_second_column():
    """The vertical I lives in the SECOND column of its 2x4 box.

    This is THE Tengen quirk (spec 4.2): every x offset is 1, never 0,
    and the y offsets run 0..3. Combined with the top-left anchoring it
    explains why the I can always rotate next to the right wall without
    a kick (see test_rotation.py::test_i_rotates_fully_near_right_wall),
    and it is the one documented exception to "touch the left edge".
    """
    assert box_size(Piece.I, 1) == (2, 4)
    assert all(x == 1 for x, _ in shape(Piece.I, 1))
    assert [y for _, y in shape(Piece.I, 1)] == [0, 1, 2, 3]


def test_o_never_changes():
    """The O is the same 2x2 square in all four states.

    Rotating an O must not wobble it -- a real O-spin that shifted the
    square would let it squeeze through one-column gaps by repeated
    rotation, a classic Tetris bug. Because all four states are
    identical, the game needs no special case for the O.
    """
    states = ROTATIONS[Piece.O]
    assert all(state == states[0] for state in states)


def test_non_i_pieces_stay_within_3x3_box():
    """Six pieces fit a 3x3 box in every state; only the I is bigger.

    The 3x3 bound is what makes the anchoring rule well-defined for
    them (there is always a top and left edge to touch) and bounds the
    autopilot's search space. The I is skipped deliberately: its
    horizontal state is 4 wide.
    """
    for piece in Piece:
        if piece is Piece.I:
            continue
        for state in range(4):
            w, h = box_size(piece, state)
            assert w <= 3 and h <= 3


def test_o_box_is_2x2():
    """The O's box is exactly 2x2 -- no padding.

    Padding would offset the O from where the player sees it land,
    since the box's top-left is the anchor used for spawn (SPAWN_X).
    """
    assert box_size(Piece.O, 0) == (2, 2)


def test_state_wraps_modulo_four():
    """Out-of-range state indices wrap modulo 4, in both directions.

    State 5 must equal state 1 (5 % 4) and state -1 must equal state 3
    (Python's modulo). game.py rotates with `(state +/- 1) % 4`, so
    this wrap is what makes a CCW turn from state 0 land on state 3
    rather than crash or produce a negative index.
    """
    assert shape(Piece.T, 5) == shape(Piece.T, 1)
    assert shape(Piece.T, -1) == shape(Piece.T, 3)
