"""Autopilot placement search (cheat mode; owner request 2026-10-27).

Enumerates every landing for the current piece, simulates the lock and
line clears, and scores the result with published El-Tetris feature
weights. Pure functions over the board: no game rules live here, and
nothing is mutated. Named "autopilot", not "AI": it is pure calculation.

Two strategies (owner request 2026-10-28):
- "quick": clear lines as quickly as possible — the classic linear
  El-Tetris scoring; a single is as good as part of a tetris.
- "highscore": maximize score — defer 1-2 line clears while the stack is
  safe (they block would-be tetrises and triples), reward clears by
  their point value (a tetris is worth 25x a single), relax the well
  penalty (the strategy needs a well column), and let the stack build
  freely up to a knee before the landing-height cost rises.
"""

from __future__ import annotations

from .board import HEIGHT, WIDTH
from .pieces import ROTATIONS, Piece
from .scoring import points_for_clear

# Published El-Tetris weights (the score is maximized).
W_LANDING = -4.500158825082766
W_LINES = 3.4181268101392694
W_ROW_TRANSITIONS = -3.2178882868487753
W_COL_TRANSITIONS = -9.348695305445199
W_HOLES = -7.899265427351652
W_WELL_SUMS = -3.3855972247263626

# Strategy weight profiles. "quick" is the classic linear scoring;
# "highscore" trades clear speed for bigger clears.
_QUICK = {
    "landing_w": W_LANDING,
    "landing_free": 0.0,  # every row of height costs
    "lines_w": W_LINES,  # linear per cleared row
    "points_w": 0.0,
    "defer_w": 0.0,  # never defer
    "safe_h": 0,
    "well_w": W_WELL_SUMS,
    "holes_w": W_HOLES,
}
_HIGHSCORE = {
    "landing_w": W_LANDING,
    "landing_free": 4.0,  # stacking below this height is free
    "lines_w": 0.0,
    "points_w": 1.0,  # clears score by points: 1/4/9/25 per 100 pts
    "defer_w": 25.0,  # cost of burning a 1-2 line clear while safe
    "safe_h": 10,  # above this height, survival beats deferral
    "well_w": -2.0,  # relaxed, but roofing a well must never pay
    "holes_w": -12.0,  # buried wells are catastrophic: extra caution
}
STRATEGIES = {"quick": _QUICK, "highscore": _HIGHSCORE}


def _grid(board) -> list[list[int]]:
    return [
        [1 if board.get(x, y) != 0 else 0 for x in range(WIDTH)]
        for y in range(HEIGHT)
    ]


def _resting_cells(board, kind: Piece, rot: int, x: int) -> list[tuple[int, int]] | None:
    """Absolute cells for the piece dropped from the top at column x, or
    None when it does not fit there at all."""
    offsets = ROTATIONS[kind][rot]
    cells = [(x + dx, dy) for dx, dy in offsets]
    if any(cx < 0 or cx >= WIDTH for cx, _ in cells):
        return None
    if not board.cells_free(cells):
        return None
    while board.cells_free([(cx, cy + 1) for cx, cy in cells]):
        cells = [(cx, cy + 1) for cx, cy in cells]
    return cells


def _lock(grid: list[list[int]], cells) -> tuple[list[list[int]], int]:
    """Lock the piece into a copy of the grid and clear full rows."""
    for x, y in cells:
        grid[y][x] = 1
    kept = [row for row in grid if not all(row)]
    cleared = HEIGHT - len(kept)
    return [[0] * WIDTH for _ in range(cleared)] + kept, cleared


def _score(grid: list[list[int]], cleared: int, landing_height: float, w: dict) -> float:
    heights = []
    holes = 0
    for x in range(WIDTH):
        seen = False
        h = 0
        for y in range(HEIGHT):
            if grid[y][x]:
                if not seen:
                    h = HEIGHT - y
                    seen = True
            elif seen:
                holes += 1
        heights.append(h)
    # Row transitions (empty/filled changes across each row, walls count
    # as filled).
    row_transitions = 0
    for row in grid:
        prev = 1
        for cell in row:
            if cell != prev:
                row_transitions += 1
            prev = cell
        if prev != 1:
            row_transitions += 1
    # Column transitions (the floor counts as filled).
    col_transitions = 0
    for x in range(WIDTH):
        prev = 0
        for y in range(HEIGHT):
            if grid[y][x] != prev:
                col_transitions += 1
            prev = grid[y][x]
        if prev != 1:
            col_transitions += 1
    # Wells: deep single-column gaps flanked by filled cells. The depth
    # sum rewards shallow wells and punishes deep ones.
    well_sums = 0
    for x in range(WIDTH):
        depth = 0
        for y in range(HEIGHT):
            left = grid[y][x - 1] if x > 0 else 1
            right = grid[y][x + 1] if x + 1 < WIDTH else 1
            if grid[y][x] == 0 and left and right:
                depth += 1
            else:
                well_sums += depth * (depth + 1) // 2
                depth = 0
        well_sums += depth * (depth + 1) // 2
    # Clear term: linear lines (quick) or point-valued clears with a
    # deferral cost for burning 1-2 line clears while the stack is safe
    # and clean (highscore); holes or a tall stack waive the deferral —
    # survival first.
    clear_term = w["lines_w"] * cleared + w["points_w"] * (
        points_for_clear(cleared) / 100
    )
    if w["defer_w"] and 1 <= cleared <= 2 and max(heights) < w["safe_h"] and holes == 0:
        clear_term -= w["defer_w"]
    return (
        w["landing_w"] * max(0.0, landing_height - w["landing_free"])
        + clear_term
        + W_ROW_TRANSITIONS * row_transitions
        + W_COL_TRANSITIONS * col_transitions
        + w["holes_w"] * holes
        + w["well_w"] * well_sums
    )


def best_placement(
    board, kind: Piece, strategy: str = "quick"
) -> tuple[int, int] | None:
    """The (rotation, x) whose simulated landing scores highest under
    the given strategy, or None when the piece does not fit anywhere
    (the stack has reached the top)."""
    w = STRATEGIES[strategy]
    rot_count = len(ROTATIONS[kind])
    best: tuple[int, int] | None = None
    best_score: float | None = None
    for rot in range(rot_count):
        xs = [dx for dx, _ in ROTATIONS[kind][rot]]
        for x in range(-min(xs), WIDTH - max(xs)):
            cells = _resting_cells(board, kind, rot, x)
            if cells is None:
                continue
            grid, cleared = _lock(_grid(board), cells)
            landing_height = HEIGHT - sum(cy for _, cy in cells) / len(cells)
            score = _score(grid, cleared, landing_height, w)
            if best_score is None or score > best_score:
                best_score = score
                best = (rot, x)
    return best
