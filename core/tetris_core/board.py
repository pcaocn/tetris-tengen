"""Playfield grid, collision checks, and line clears (spec 4.1).

The board is an extended 10x23 grid: 3 hidden rows above the 20 visible
rows (spec 4.1 spawn: box top at row 22 counted from the bottom of the
extended board, i.e. the top row here). Row 0 is the top; row 22 the bottom.
Cells hold 0 for empty or a Piece index 1..7 (I, O, T, S, Z, J, L).

VERIFY (spec 4.1): the exact extended-board height / spawn row convention
still needs to be checked against the source; HIDDEN_ROWS is the knob.
"""

WIDTH = 10
VISIBLE_HEIGHT = 20
HIDDEN_ROWS = 3
HEIGHT = VISIBLE_HEIGHT + HIDDEN_ROWS


class Board:
    def __init__(self) -> None:
        self._grid: list[list[int]] = [[0] * WIDTH for _ in range(HEIGHT)]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < WIDTH and 0 <= y < HEIGHT

    def get(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            raise IndexError(f"cell out of bounds: ({x}, {y})")
        return self._grid[y][x]

    def cells_free(self, cells) -> bool:
        """True when every (x, y) cell is inside the board and empty."""
        return all(self.in_bounds(x, y) and self._grid[y][x] == 0 for x, y in cells)

    def lock_cells(self, cells, value: int) -> None:
        for x, y in cells:
            if not self.in_bounds(x, y):
                raise ValueError(f"cell out of bounds: ({x}, {y})")
            self._grid[y][x] = value

    def full_rows(self) -> list[int]:
        """Indices of completely filled rows, top to bottom."""
        return [y for y in range(HEIGHT) if all(v != 0 for v in self._grid[y])]

    def clear_rows(self, rows) -> None:
        """Remove the given rows and shift everything above down."""
        rows_set = set(rows)
        kept = [row for y, row in enumerate(self._grid) if y not in rows_set]
        cleared = HEIGHT - len(kept)
        self._grid = [[0] * WIDTH for _ in range(cleared)] + kept

    def is_row_empty(self, y: int) -> bool:
        return all(v == 0 for v in self._grid[y])

    def visible_grid(self) -> list[list[int]]:
        """The 20 visible rows as a copy, row 0 at the top (protocol 2.2)."""
        return [list(row) for row in self._grid[HIDDEN_ROWS:]]
