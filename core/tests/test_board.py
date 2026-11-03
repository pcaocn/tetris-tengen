"""Board grid tests: bounds, locking, full rows, clears, visible grid.

WHAT THIS FILE TESTS
====================
`Board` (see tetris_core/board.py) is the engine's "dumb" data
structure, but every rule in the game is built on its exact behaviour,
so this file pins down the five load-bearing facts:

    1. BOUNDS -- the grid is 10 wide x 23 tall (3 hidden rows on top of
       the 20 visible ones). A cell outside it is never "free", which
       is how wall and floor collisions are detected with no special
       cases anywhere else in the engine.
    2. LOCKING -- `lock_cells` writes piece indices into cells and
       REFUSES to write outside the grid. A silent out-of-bounds write
       would corrupt a neighbouring row or crash far from the cause.
    3. FULL ROWS -- a row is full only when all 10 columns are filled;
       `full_rows()` reports them top-to-bottom. Scanning all 23 rows
       (not just the visible ones) matters because a piece can complete
       a row up in the hidden area.
    4. CLEARS -- `clear_rows` removes rows and shifts everything above
       down by exactly the number of cleared rows below it. Every
       score, level, and board state in the game flows through this
       one operation.
    5. VISIBLE GRID -- `visible_grid()` slices off the hidden rows and
       hands the UI a copy, so the protocol board is always 20 rows and
       the renderer can never mutate the live game.

ROW NUMBERS USED BELOW
----------------------
Row 0 is the TOP of the extended grid; row 22 is the floor the player
sees. Tests fill rows from the bottom (21, 22) because that is where
real stacks form; the "multiple rows" test spreads rows out (10, 11,
20) to check the ordering of the returned list.
"""

import pytest

from tetris_core.board import HEIGHT, HIDDEN_ROWS, VISIBLE_HEIGHT, WIDTH, Board


def test_empty_board_all_in_bounds_cells_free():
    """A fresh board must be entirely empty AND entirely in bounds.

    The 10x23 = 230 cells are enumerated and all must be free. This is
    the baseline collision fact the whole game rests on: if any cell of
    a fresh board failed `cells_free`, pieces could not spawn or fall
    at all. The row-major comprehension also implicitly checks that the
    grid has exactly HEIGHT usable rows and WIDTH usable columns --
    an out-of-range access would raise instead of returning False.
    """
    b = Board()
    cells = [(x, y) for x in range(WIDTH) for y in range(HEIGHT)]
    assert b.cells_free(cells)


def test_out_of_bounds_cells_not_free():
    """All four edges of the grid must reject cells.

    One probe per wall: left (-1), right (WIDTH), bottom (HEIGHT, the
    row below the floor), top (-1, above the hidden rows). Because
    `cells_free` checks bounds and emptiness in one pass, these four
    assertions ARE the entire wall/floor collision model of the game --
    there is no separate "hit the wall" code path to test.
    """
    b = Board()
    assert not b.cells_free([(-1, 0)])
    assert not b.cells_free([(WIDTH, 0)])
    assert not b.cells_free([(0, HEIGHT)])
    assert not b.cells_free([(0, -1)])


def test_lock_and_get():
    """Locking writes piece indices that `get` reads back exactly.

    Two adjacent cells get piece index 2 (an O), and the cell next door
    must stay 0 -- proving the write is per-cell, not per-row. The grid
    values are the piece indices 1..7, which is what the UI maps to
    colors and what the protocol sends, so a wrong value here would
    show up as the wrong color on screen.
    """
    b = Board()
    b.lock_cells([(3, 5), (4, 5)], 2)
    assert b.get(3, 5) == 2
    assert b.get(4, 5) == 2
    assert b.get(5, 5) == 0


def test_lock_out_of_bounds_raises():
    """Locking outside the grid must raise, never write silently.

    The bottom (row HEIGHT, one below the floor) and the left (column
    -1) are probed. An exception is the correct failure mode: a silent
    out-of-bounds write would either corrupt a neighbouring row's data
    or (with negative indices) wrap around in Python and hit the wrong
    row entirely -- a bug that would surface as garbage on screen far
    from the actual cause.
    """
    b = Board()
    with pytest.raises(ValueError):
        b.lock_cells([(0, HEIGHT)], 1)
    with pytest.raises(ValueError):
        b.lock_cells([(-1, 0)], 1)


def test_full_rows_detects_only_complete_rows():
    """Nine filled cells must NOT make a row full; the tenth must.

    Step 1: fill columns 0..8 of the bottom row (row 22), leaving col 9
       empty -- `full_rows()` must report nothing (no false clear).
    Step 2: fill the last cell -- now, and only now, row 22 is complete
       and is reported.

    This is the exact boundary the scoring code relies on: a clear is
    triggered by a COMPLETE row, never by a nearly-complete one. The
    existing inline comment ("col 9 left empty") marks the deliberate
    gap.
    """
    b = Board()
    for x in range(WIDTH - 1):  # col 9 left empty: no false clear
        b.lock_cells([(x, 22)], 1)
    assert b.full_rows() == []
    b.lock_cells([(9, 22)], 1)
    assert b.full_rows() == [22]


def test_full_rows_multiple_top_down_order():
    """`full_rows()` must return every full row, ordered top to bottom.

    Three rows spread across the board (10, 11 near the middle, 20 near
    the bottom) are filled; the result must be the ascending list
    [10, 11, 20]. The order is not cosmetic: the clear animation and
    the protocol's `clearing.rows` report rely on a stable, readable
    top-down list, and a dict- or set-backed implementation would
    scramble it.
    """
    b = Board()
    for y in (10, 11, 20):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 3)
    assert b.full_rows() == [10, 11, 20]


def test_clear_one_row_shifts_above_down():
    """Clearing one row moves everything above it down by exactly one.

    Step 1: fill the bottom row (22) -- the row that will be cleared.
    Step 2: drop a single cell of piece 7 into row 21 (the "survivor").
    Step 3: clear row 22.

    After the clear the survivor must sit at row 22 (it moved DOWN one
    into the cleared space), the cell beside it must be 0, and its old
    row 21 must be empty. This is the "gravity of the stack" rule: in
    the real game it is what pulls the rest of the tower down after
    every clear, so an off-by-one here would leave floating stacks.
    """
    b = Board()
    for x in range(WIDTH):
        b.lock_cells([(x, 22)], 1)
    b.lock_cells([(0, 21)], 7)
    b.clear_rows([22])
    assert b.get(0, 22) == 7  # old row 21 moved to row 22
    assert b.get(1, 22) == 0
    assert b.is_row_empty(21)


def test_clear_two_rows():
    """Clearing two rows shifts the stack above down by TWO.

    Step 1: fill rows 21 and 22 (a double clear).
    Step 2: park a cell at row 20.
    Step 3: clear both rows.

    The survivor must land at row 22 -- two rows down, not one -- and
    row 20 must be empty. The implementation prepends as many empty
    rows as were removed, so this checks that count is per-row, not a
    fixed 1.
    """
    b = Board()
    for y in (21, 22):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 4)
    b.lock_cells([(2, 20)], 6)
    b.clear_rows([21, 22])
    assert b.get(2, 22) == 6
    assert b.is_row_empty(20)


def test_clear_four_rows():
    """The tetris case: four rows removed, everything above drops four.

    Step 1: fill the bottom four rows (19..22) with piece 5.
    Step 2: fill row 18 with piece 6 -- the stack sitting on top of the
       clear.
    Step 3: clear all four rows.

    The entire row 18 must become the new bottom row (22), and every
    row above the old stack (0..17) must be empty. This is the board
    transformation behind the 2500-point tetris: the scoring code never
    touches the grid, it just counts what this operation removed.
    """
    b = Board()
    for y in (19, 20, 21, 22):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 5)
    for x in range(WIDTH):
        b.lock_cells([(x, 18)], 6)
    b.clear_rows([19, 20, 21, 22])
    for x in range(WIDTH):
        assert b.get(x, 22) == 6
    for y in range(18):
        assert b.is_row_empty(y)


def test_clear_no_rows_is_noop():
    """Clearing an empty list must not disturb the board.

    Guard against an off-by-one in the "how many rows were removed"
    arithmetic: `HEIGHT - len(kept)` must come out as 0, prepending
    nothing. If it ever computed 1, every no-clear lock in the game
    would silently delete a row from the top of the stack.
    """
    b = Board()
    b.lock_cells([(0, 22)], 1)
    b.clear_rows([])
    assert b.get(0, 22) == 1


def test_clear_rows_scatter_order():
    """Unsorted, scattered clear input must produce the exact shift.

    Step 1: fill rows 5, 22 and 10 (given to clear_rows as [22, 5, 10]
       -- deliberately NOT sorted), plus one survivor cell at (1, 21).
    Step 2: clear all three.

    Each surviving row shifts down by the number of cleared rows BELOW
    it: the (1, 21) cell has only row 22 below it, so it lands at
    (1, 22); rows 4, 9 and 21 end up empty, which is only true if the
    bands above rows 5 and 10 each shifted by exactly the right count.
    The implementation filters with a set, so input order must not
    matter -- this test would catch a version that walked the list in
    order and shifted rows inconsistently.
    """
    b = Board()
    for y in (5, 22, 10):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 2)
    b.lock_cells([(1, 21)], 9)
    b.clear_rows([22, 5, 10])  # unsorted input must still work
    assert b.get(1, 22) == 9
    assert b.is_row_empty(4) and b.is_row_empty(9) and b.is_row_empty(21)


def test_visible_grid_shape_and_content():
    """The protocol board is 20 visible rows, never a hidden-row leak.

    Step 1: put a cell in the FIRST visible row (extended row
       HIDDEN_ROWS = 3) and a cell in the LAST hidden row (row 2).
    Step 2: read `visible_grid()`.

    The grid must be exactly 20 rows x 10 wide; the visible cell must
    appear at visible row 0, column 0 (the shift `extended - HIDDEN_ROWS`
    is the whole coordinate conversion); and the hidden-row cell must
    appear NOWHERE in column 1. The rows are copies, so the caller
    holding this grid cannot mutate the live board either.
    """
    b = Board()
    b.lock_cells([(0, HIDDEN_ROWS)], 1)  # first visible row
    b.lock_cells([(1, HIDDEN_ROWS - 1)], 1)  # last hidden row: excluded
    grid = b.visible_grid()
    assert len(grid) == VISIBLE_HEIGHT == 20
    assert all(len(row) == WIDTH for row in grid)
    assert grid[0][0] == 1
    assert grid[0][1] == 0
    # hidden rows never leak into the protocol board
    assert all(grid[y][1] == 0 for y in range(VISIBLE_HEIGHT))
