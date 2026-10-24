"""Tetromino shapes and the Tengen (Atari arcade) rotation table.

Spec section 4.2: rotations are the Atari arcade system, NOT the Nintendo
system. In every rotation state the piece touches the left and top edges of
its 3x3 bounding box; the exception is the vertical I, which sits in the
second column of its box. Rotation is anchored to the top-left corner.

Coordinates are (x, y) offsets from the piece bounding-box top-left corner,
x right, y down. State 0 is the spawn state; 1 = one CW step, 2 = 180,
3 = one CCW step.

VERIFY (spec 4.2): the table below is derived from the anchoring rule stated
in the spec (rotate, then shift so the piece touches the top and left edges).
Every state must be checked against the cited source; see
tests/test_pieces.py which records this table as a fixture.
"""

from enum import IntEnum


class Piece(IntEnum):
    I = 1
    O = 2
    T = 3
    S = 4
    Z = 5
    J = 6
    L = 7


# piece -> 4 rotation states, each a tuple of 4 (x, y) cell offsets.
ROTATIONS: dict[Piece, tuple[tuple[tuple[int, int], ...], ...]] = {
    # I: 4-wide horizontal bar on the top row; vertical I in the SECOND
    # column of its box (spec 4.2 exception). States 2 and 3 repeat 0 and 1.
    Piece.I: (
        ((0, 0), (1, 0), (2, 0), (3, 0)),
        ((1, 0), (1, 1), (1, 2), (1, 3)),
        ((0, 0), (1, 0), (2, 0), (3, 0)),
        ((1, 0), (1, 1), (1, 2), (1, 3)),
    ),
    # O: square, rotation is a no-op.
    Piece.O: (
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
    ),
    # T: spawn nub-up; CW spine left col + nub right; 180 flat top + nub
    # down; CCW spine middle col + nub left.
    Piece.T: (
        ((1, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 1)),
        ((0, 0), (1, 0), (2, 0), (1, 1)),
        ((1, 0), (1, 1), (1, 2), (0, 1)),
    ),
    # S: two distinct states (180-degree symmetry).
    Piece.S: (
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
    ),
    # Z: two distinct states (180-degree symmetry).
    Piece.Z: (
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((0, 1), (0, 2), (1, 0), (1, 1)),
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((0, 1), (0, 2), (1, 0), (1, 1)),
    ),
    # J: spawn flat bottom, nub top-left.
    Piece.J: (
        ((0, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 0)),
        ((0, 0), (1, 0), (2, 0), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (0, 2)),
    ),
    # L: spawn flat bottom, nub top-right.
    Piece.L: (
        ((2, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (0, 1)),
        ((0, 0), (1, 0), (1, 1), (1, 2)),
    ),
}


def shape(kind: Piece, state: int) -> tuple[tuple[int, int], ...]:
    """Cell offsets for a piece in a rotation state (state mod 4)."""
    return ROTATIONS[kind][state % 4]


def box_size(kind: Piece, state: int) -> tuple[int, int]:
    """(width, height) of the piece's bounding box in a rotation state."""
    cells = shape(kind, state)
    return (max(x for x, _ in cells) + 1, max(y for _, y in cells) + 1)
