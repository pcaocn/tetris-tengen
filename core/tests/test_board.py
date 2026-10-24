import pytest

from tetris_core.board import HEIGHT, HIDDEN_ROWS, VISIBLE_HEIGHT, WIDTH, Board


def test_empty_board_all_in_bounds_cells_free():
    b = Board()
    cells = [(x, y) for x in range(WIDTH) for y in range(HEIGHT)]
    assert b.cells_free(cells)


def test_out_of_bounds_cells_not_free():
    b = Board()
    assert not b.cells_free([(-1, 0)])
    assert not b.cells_free([(WIDTH, 0)])
    assert not b.cells_free([(0, HEIGHT)])
    assert not b.cells_free([(0, -1)])


def test_lock_and_get():
    b = Board()
    b.lock_cells([(3, 5), (4, 5)], 2)
    assert b.get(3, 5) == 2
    assert b.get(4, 5) == 2
    assert b.get(5, 5) == 0


def test_lock_out_of_bounds_raises():
    b = Board()
    with pytest.raises(ValueError):
        b.lock_cells([(0, HEIGHT)], 1)
    with pytest.raises(ValueError):
        b.lock_cells([(-1, 0)], 1)


def test_full_rows_detects_only_complete_rows():
    b = Board()
    for x in range(WIDTH - 1):  # col 9 left empty: no false clear
        b.lock_cells([(x, 22)], 1)
    assert b.full_rows() == []
    b.lock_cells([(9, 22)], 1)
    assert b.full_rows() == [22]


def test_full_rows_multiple_top_down_order():
    b = Board()
    for y in (10, 11, 20):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 3)
    assert b.full_rows() == [10, 11, 20]


def test_clear_one_row_shifts_above_down():
    b = Board()
    for x in range(WIDTH):
        b.lock_cells([(x, 22)], 1)
    b.lock_cells([(0, 21)], 7)
    b.clear_rows([22])
    assert b.get(0, 22) == 7  # old row 21 moved to row 22
    assert b.get(1, 22) == 0
    assert b.is_row_empty(21)


def test_clear_two_rows():
    b = Board()
    for y in (21, 22):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 4)
    b.lock_cells([(2, 20)], 6)
    b.clear_rows([21, 22])
    assert b.get(2, 22) == 6
    assert b.is_row_empty(20)


def test_clear_four_rows():
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
    b = Board()
    b.lock_cells([(0, 22)], 1)
    b.clear_rows([])
    assert b.get(0, 22) == 1


def test_clear_rows_scatter_order():
    b = Board()
    for y in (5, 22, 10):
        for x in range(WIDTH):
            b.lock_cells([(x, y)], 2)
    b.lock_cells([(1, 21)], 9)
    b.clear_rows([22, 5, 10])  # unsorted input must still work
    assert b.get(1, 22) == 9
    assert b.is_row_empty(4) and b.is_row_empty(9) and b.is_row_empty(21)


def test_visible_grid_shape_and_content():
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
