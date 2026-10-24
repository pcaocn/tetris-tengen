"""Fixture tests for the Tengen rotation table.

The EXPECTED table below records the rotation table as a fixture (spec 4.2,
section 9: one test per piece per state). It is derived from the spec's
anchoring rule; every state must still be checked against the cited source
(VERIFY, open item).
"""

import pytest

from tetris_core.pieces import ROTATIONS, Piece, box_size, shape

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
    assert ROTATIONS[piece] == EXPECTED[piece]


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_state_has_exactly_four_distinct_cells(piece, state):
    cells = shape(piece, state)
    assert len(cells) == 4
    assert len(set(cells)) == 4


@pytest.mark.parametrize("piece,state", PIECE_STATES)
def test_state_cells_are_connected(piece, state):
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
    cells = shape(piece, state)
    w, h = box_size(piece, state)
    assert w == max(x for x, _ in cells) + 1
    assert h == max(y for _, y in cells) + 1


def test_i_horizontal_is_four_wide_top_row():
    assert box_size(Piece.I, 0) == (4, 1)
    assert shape(Piece.I, 0) == ((0, 0), (1, 0), (2, 0), (3, 0))


def test_i_vertical_sits_in_second_column():
    assert box_size(Piece.I, 1) == (2, 4)
    assert all(x == 1 for x, _ in shape(Piece.I, 1))
    assert [y for _, y in shape(Piece.I, 1)] == [0, 1, 2, 3]


def test_o_never_changes():
    states = ROTATIONS[Piece.O]
    assert all(state == states[0] for state in states)


def test_non_i_pieces_stay_within_3x3_box():
    for piece in Piece:
        if piece is Piece.I:
            continue
        for state in range(4):
            w, h = box_size(piece, state)
            assert w <= 3 and h <= 3


def test_o_box_is_2x2():
    assert box_size(Piece.O, 0) == (2, 2)


def test_state_wraps_modulo_four():
    assert shape(Piece.T, 5) == shape(Piece.T, 1)
    assert shape(Piece.T, -1) == shape(Piece.T, 3)
