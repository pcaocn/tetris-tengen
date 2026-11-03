"""Playfield grid, collision checks, and line clears (spec 4.1).

The board is an extended 10x23 grid: 3 hidden rows above the 20 visible
rows (spec 4.1 spawn: box top at row 22 counted from the bottom of the
extended board, i.e. the top row here). Row 0 is the top; row 22 the bottom.
Cells hold 0 for empty or a Piece index 1..7 (I, O, T, S, Z, J, L).

VERIFY (spec 4.1): the exact extended-board height / spawn row convention
still needs to be checked against the source; HIDDEN_ROWS is the knob.

WHY AN EXTENDED GRID?
----------------------
The visible playfield is only 20 rows, but a piece needs room to exist
*above* the visible area while it falls. Rather than adding special-case
bounds checks everywhere, the board is simply made taller than what the
player can see: rows 0-2 are the hidden rows, rows 3-22 are the visible
playfield. Every collision test then works on one uniform rectangle.

COORDINATE CONVENTION (used by every module in this package):
    x = column, 0 (left) .. 9 (right)
    y = row,    0 (top)  .. 22 (bottom of the extended grid)
`y` increases DOWNWARD, which matches how the UI draws the canvas, so no
flipping is needed anywhere in the rendering path.

The two coordinate spaces in play:
    - EXTENDED coordinates: what the engine uses internally. The hidden
      rows occupy y = 0..2.
    - VISIBLE coordinates: what the protocol sends to the UI. The visible
      rows are the extended rows 3..22, so visible_y = extended_y - 3.
      `visible_grid()` and `protocol.state_event()` perform that shift at
      the boundary, so the UI never has to know the hidden rows exist.

This module deliberately contains NO game rules beyond the grid itself:
no gravity, no scoring, no rotation. It is the "dumb" data structure that
the rest of the engine builds its rules on.
"""

from __future__ import annotations


WIDTH = 10
VISIBLE_HEIGHT = 20
HIDDEN_ROWS = 3
HEIGHT = VISIBLE_HEIGHT + HIDDEN_ROWS


class Board:
    """The 10x23 grid of piece indices, plus the collision/clear helpers.

    The grid is stored as a list of HEIGHT rows, each a list of WIDTH
    ints: `_grid[y][x]`. Note the order -- y first, then x -- because the
    rows must be indexable as whole rows for the line-clear logic.
    """

    def __init__(self) -> None:
        # A fresh board is all zeros (empty). The rows are independent
        # lists (the `[[0] * WIDTH for _ in range(HEIGHT)]` idiom), so
        # mutating one row never leaks into another -- a shared-row bug
        # that would show up as a whole row filling in at once.
        self._grid: list[list[int]] = [[0] * WIDTH for _ in range(HEIGHT)]

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def in_bounds(self, x: int, y: int) -> bool:
        """True when (x, y) is inside the EXTENDED grid.

        Note this includes the hidden rows: a piece is allowed to occupy
        y = 0..2, it just is not drawn.
        """
        return 0 <= x < WIDTH and 0 <= y < HEIGHT

    def get(self, x: int, y: int) -> int:
        """The piece index at (x, y), or raise if out of bounds."""
        if not self.in_bounds(x, y):
            raise IndexError(f"cell out of bounds: ({x}, {y})")
        return self._grid[y][x]

    def cells_free(self, cells) -> bool:
        """True when every (x, y) cell is inside the board and empty.

        This is THE collision test used by the whole engine: to move,
        rotate, or drop a piece, the engine asks whether the piece's
        proposed cells are free. Because it checks bounds AND emptiness
        in one pass, the same call handles "hit the wall", "hit the floor",
        and "hit the stack" without three separate tests.
        """
        return all(self.in_bounds(x, y) and self._grid[y][x] == 0 for x, y in cells)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def lock_cells(self, cells, value: int) -> None:
        """Write `value` into each cell -- this is what "locking" a piece means.

        The value is the piece index (1..7), which the UI maps to a
        falling-piece color; the locked-piece color per level is applied
        by the UI, not stored in the grid (spec 6.2).
        """
        for x, y in cells:
            if not self.in_bounds(x, y):
                raise ValueError(f"cell out of bounds: ({x}, {y})")
            self._grid[y][x] = value

    def full_rows(self) -> list[int]:
        """Indices of completely filled rows, top to bottom.

        "Full" means every one of the WIDTH cells is non-zero. Scanning
        all HEIGHT rows (not just the visible ones) is correct because a
        hidden row can be completed by a piece that then clears upward
        into view.
        """
        return [y for y in range(HEIGHT) if all(v != 0 for v in self._grid[y])]

    def clear_rows(self, rows) -> None:
        """Remove the given rows and shift everything above down.

        The standard Tetris shift: after removing the cleared rows, every
        row ABOVE them moves DOWN by the number of cleared rows below it.
        The implementation does this by filtering the cleared rows out of
        the row list and then prepending that many fresh empty rows at
        the top -- which is exactly "everything above shifts down".
        """
        rows_set = set(rows)
        # Keep every row that is NOT being cleared, preserving order.
        kept = [row for y, row in enumerate(self._grid) if y not in rows_set]
        # How many rows were removed (HEIGHT minus what survived).
        cleared = HEIGHT - len(kept)
        # Prepend `cleared` empty rows: the surviving rows keep their
        # relative order and now sit lower down the grid.
        self._grid = [[0] * WIDTH for _ in range(cleared)] + kept

    def is_row_empty(self, y: int) -> bool:
        """True when row y holds no cells (used by the clear animation)."""
        return all(v == 0 for v in self._grid[y])

    def visible_grid(self) -> list[list[int]]:
        """The 20 visible rows as a copy, row 0 at the top (protocol 2.2).

        Slicing off HIDDEN_ROWS drops the hidden rows, and the explicit
        `list(row)` copy prevents the UI from ever holding a reference
        into the live grid (which would let a renderer mutate the game).
        """
        return [list(row) for row in self._grid[HIDDEN_ROWS:]]
