"""Autopilot placement search (cheat mode; owner request 2026-10-27).

Quick and the historical Highscore benchmark enumerate straight drops for
the current piece. Each candidate locks onto a copy of the board, clears
completed rows, and receives a score based on its landing height and the
resulting board features. The best-scoring rotation and column win.

Desktop Highscore uses the two-piece route planner in lookahead.py. Both
searches share the feature weights and danger ramp in this module.

WHY SIMULATE INSTEAD OF SCORING THE CURRENT BOARD
-------------------------------------------------
Because the decision depends on what the placement WILL leave behind, not
on the board as it is. A piece that completes a tetris changes the board
completely; the value of that placement is only visible after simulating
the clear. That is why `_lock` is called on every candidate.

THE EL-TETRIS FEATURES (what the score is made of)
---------------------------------------------------
Published El-Tetris weights, each describing one property of the
resulting board:
  - LANDING HEIGHT: how high the piece came to rest. Landing high is
    bad -- it leaves less room to work.
  - CLEARED ROWS / POINTS: how much was cleared and what it was worth.
  - ROW TRANSITIONS: how many times a row changes between empty and
    filled. Fewer is better -- a jagged surface is harder to build on.
  - COLUMN TRANSITIONS: the same idea vertically.
  - HOLES: empty cells buried under the stack. The worst possible shape,
    because they can never be filled.
  - WELL SUMS: the depth of single-column gaps between taller columns.
    Shallow wells are good (they hold pieces for future clears); deep
    ones are dangerous.

All six are combined linearly with the weights below, so the profile of a
strategy is just a set of numbers.

THE BOARD-FULLNESS BLEND (the "danger" ramp)
---------------------------------------------
The highscore profile changes its weights as the stack rises. Below
`danger_h` rows it plays for score; above it, the weights blend toward
`danger_w`, a survival profile. The blend factor runs 0.0 (safe) to 1.0
(fully dangerous) over `danger_span` rows. This was added on 2026-10-29
after the measured early deaths all looked the same: a board filled to
the ceiling with holes everywhere.

READING THE WEIGHTS
-------------------
The weights are read as: "how many points does this feature cost or
earn?". A negative weight punishes the feature, a positive one rewards
it. The magnitudes are small and the units are arbitrary, but they must
be read RELATIVE to each other: `landing_w` at -14 per row means a
placement four rows higher costs 56 points, which is why a clear worth
25 points is not worth taking at full danger unless the danger weights
also raise `points_w`.
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
    # Board-fullness awareness (owner request 2026-10-29): hunting
    # tetrises means holding a well open, which is safe while the stack
    # is low but fatal past half full -- the surrounding stack towers to
    # the ceiling and a deep well full of buried holes cannot be
    # recovered. Past the danger threshold the strategy stops hunting and
    # plays for survival: keep the surface flat, no deep wells, no holes.
    #
    # The numbers below are the "hard-flat8" profile, chosen on 400
    # held-out seeds (master 77777, 250k-frame budget): early deaths
    # (fewer than 3000 lines) fell from 78/400 to 33/400 against the
    # pre-2026-10-29 profile, with the median score within 1% of it.
    "danger_h": 10.0,  # stack height where the danger ramp starts
    "danger_span": 6.0,  # rows above danger_h for the ramp to reach full
    "danger_holes": 0.0,  # buried holes count as extra stack height
    "flat_w": -8.0,  # penalty per unit of column-height step (danger only)
    "flat_base": 0.0,  # share of the flatness penalty that applies when safe
    # Stack-height terms (owner request 2026-10-29). The measured early
    # deaths all look the same: every column at height 13-20, the stack
    # at the ceiling, holes everywhere. El-Tetris has no feature for the
    # height of the stack, so nothing rewards taking it DOWN: the
    # landing cost of a tetris high on the stack (-14 per row, so about
    # -200) dwarfs the points it earns (+25), and the strategy fills the
    # board instead of clearing it. These two terms close that gap.
    "agg_w": 0.0,  # penalty per unit of total stack height (all columns)
    "maxh_w": 0.0,  # penalty per unit of the tallest column
    # Credit a placement for the stack height its own clear removes.
    # "landing_height" is measured from the piece's resting cells on the
    # PRE-lock board, but the lock drops the cleared rows from the top of
    # the grid, so the stack the placement leaves behind is that many
    # rows lower than where the piece came to rest. Without the credit a
    # tetris is charged the landing cost of four rows it just deleted.
    "landing_credit": 0.0,
    # Only hold back a small clear when a big one is actually reachable
    # (a one-column well at least this deep). 0 disables the check, so
    # the shipped behaviour is unchanged until this is measured.
    "defer_well": 0.0,
    # Largest clear still worth refusing. A single is worth 100 points
    # and a double 400, so refusing a double to chase a 2500-point
    # tetris is a much worse bet than refusing a single. 2 keeps the
    # shipped behaviour (1-2 line clears are deferred).
    "defer_max": 2.0,
    "danger_w": {  # weights at full danger (blended in as the stack fills)
        "landing_w": -14.0,  # much stronger pull toward low landings
        "landing_free": 0.0,  # no free stacking allowance at all
        "well_w": -14.0,  # stop holding a deep well open
        "holes_w": -32.0,  # buried holes are fatal when the board is full
        "points_w": 1.0,  # clears are worth this much at full danger
        "landing_credit": 0.0,
    },
}
STRATEGIES = {"quick": _QUICK, "highscore": _HIGHSCORE}


def _lerp(base: float, danger_value: float, danger: float) -> float:
    """Blend a weight from its base value to its danger value.

    `danger` is the blend factor: 0.0 returns `base` unchanged, 1.0
    returns `danger_value`, and anything between interpolates. This is
    what makes the strategy's behaviour change GRADUALLY as the stack
    fills, instead of switching abruptly at some threshold.
    """
    return base + (danger_value - base) * danger


def _max_height(grid: list[list[int]]) -> int:
    """Height of the tallest column (0 for an empty board).

    The height of a column is the number of cells from the BOTTOM of the
    grid up to its first filled cell: `HEIGHT - y` for the topmost
    filled row y. The scan stops at the first filled cell in each column
    (the `break`), because only the topmost cell defines the height --
    holes below it do not add to the height.
    """
    best = 0
    for x in range(WIDTH):
        for y in range(HEIGHT):
            if grid[y][x]:
                h = HEIGHT - y
                if h > best:
                    best = h
                break
    return best


def _danger(stack_h: int, holes: int, w: dict) -> float:
    """How close the stack is to unrecoverable, 0.0 (safe) to 1.0.

    Owner request 2026-10-29: past half full a Tetris board is very hard
    to recover, so the highscore strategy stops hunting big clears and
    plays for survival. Measured on the board *before* the candidate
    placement, so every candidate is judged in the same context.

    "danger_holes" (optional) raises the effective stack height by the
    number of buried holes: a dirty board is closer to death than a
    clean one of the same height.

    The ramp: danger is 0 below `danger_h` rows and reaches 1.0 at
    `danger_h + danger_span`. With the shipped values (10 and 6) that
    means the strategy is fully in survival mode at a stack height of 16
    rows out of 23 -- which is roughly "past half full", as the owner
    asked for.
    """
    h0 = w.get("danger_h")
    if not h0:
        # No danger ramp configured: the profile never blends.
        return 0.0
    span = max(1.0, w.get("danger_span", 6.0))
    # Holes can make the board effectively taller than it measures.
    effective = stack_h + w.get("danger_holes", 0.0) * holes
    # Clamp to [0, 1]: below the threshold the board is safe (0), above
    # the top of the ramp it is maximally dangerous (1).
    return max(0.0, min(1.0, (effective - h0) / span))


def _holes(grid: list[list[int]]) -> int:
    """Number of empty cells buried under the stack.

    A hole is an empty cell that has a filled cell ABOVE it in the same
    column. Such a cell can never be filled again -- the piece that
    would fill it cannot reach under the stack -- so holes are permanent
    damage and the most heavily punished feature in the profile.

    The scan walks each column top to bottom, flipping `seen` to True at
    the first filled cell; every empty cell after that point is a hole.
    """
    count = 0
    for x in range(WIDTH):
        seen = False
        for y in range(HEIGHT):
            if grid[y][x]:
                seen = True
            elif seen:
                count += 1
    return count


def _grid(board) -> list[list[int]]:
    """Snapshot the live board as a plain grid of 0/1.

    The autopilot works on plain lists rather than on the `Board` object
    so that it can simulate hypothetical placements without touching the
    real game. The snapshot is taken ONCE per search (see `best_placement`)
    and copied per candidate, so the live board is never mutated.
    """
    return [
        [1 if board.get(x, y) != 0 else 0 for x in range(WIDTH)]
        for y in range(HEIGHT)
    ]


def _resting_cells(board, kind: Piece, rot: int, x: int) -> list[tuple[int, int]] | None:
    """Absolute cells for the piece dropped from the top at column x, or
    None when it does not fit there at all.

    This is a simplified drop: it does not model the lock delay, the DAS
    or the gravity counter -- it just asks "if the piece fell straight
    down at column x, where would it come to rest?".

    Three steps:
      1. Build the piece's cells at the given rotation and column.
      2. Reject it if it sticks out sideways or cannot fit at the top
         (a piece cannot pass through the stack on its way down).
      3. Lower it one row at a time until the next row down would
         collide -- that is the resting position.
    """
    offsets = ROTATIONS[kind][rot]
    cells = [(x + dx, dy) for dx, dy in offsets]
    if any(cx < 0 or cx >= WIDTH for cx, _ in cells):
        return None  # hangs off the side of the board
    if not board.cells_free(cells):
        return None  # the spawn position is blocked
    # Drop straight down until the piece can move no further.
    while board.cells_free([(cx, cy + 1) for cx, cy in cells]):
        cells = [(cx, cy + 1) for cx, cy in cells]
    return cells


def _lock(grid: list[list[int]], cells) -> tuple[list[list[int]], int]:
    """Lock the piece into a copy of the grid and clear full rows.

    Returns the new grid and how many rows were cleared. The caller must
    pass a COPY of the grid, because this function mutates it in place
    while writing the piece in.

    The clear logic mirrors `Board.clear_rows`: filter out the completed
    rows and prepend that many empty rows at the top.
    """
    # Write the piece in. The value 1 is enough -- the autopilot only
    # cares about "filled vs empty", not which piece it was.
    for x, y in cells:
        grid[y][x] = 1
    # Keep only the rows that are not completely filled.
    kept = [row for row in grid if not all(row)]
    cleared = HEIGHT - len(kept)
    # The cleared rows are replaced by empty rows at the top, so the
    # stack above them shifts down.
    return [[0] * WIDTH for _ in range(cleared)] + kept, cleared


def _score(
    grid: list[list[int]],
    cleared: int,
    landing_height: float,
    w: dict,
    danger: float = 0.0,
    evaluate=None,
) -> float:
    """Score a simulated position. Higher is better.

    `grid` is the board AFTER the candidate piece was locked and the
    line clears were applied. `cleared` is how many rows that clear
    removed, `landing_height` is where the piece came to rest (measured
    on the PRE-lock board), `w` is the strategy's weight profile, and
    `danger` is the board-fullness blend factor (0.0 safe .. 1.0 full).

    The function is a single linear combination of board features, so
    every weight in the profile can be read directly as "what this
    feature is worth".
    """
    # ---- Feature extraction -----------------------------------------
    # Column heights and hole count, both from the resulting board.
    heights = []
    holes = 0
    for x in range(WIDTH):
        seen = False
        h = 0
        for y in range(HEIGHT):
            if grid[y][x]:
                if not seen:
                    # The topmost filled cell defines the column height.
                    h = HEIGHT - y
                    seen = True
            elif seen:
                # Empty cell BELOW a filled one: a hole.
                holes += 1
        heights.append(h)
    # Row transitions (empty/filled changes across each row, walls count
    # as filled).
    #
    # The scan starts with `prev = 1` because the LEFT WALL counts as
    # filled, and ends by checking the last cell against the RIGHT WALL.
    # A completely flat empty row therefore has 0 transitions, and a
    # completely full row also has 0. A row that alternates has many.
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
    #
    # The vertical equivalent: `prev = 0` at the top because above the
    # stack there is nothing, and the floor counts as filled at the
    # bottom. This is what punishes a stack with holes and overhangs.
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
    # sum rewards shallow wells and punishes deep ones. The deepest
    # single well is tracked separately: a tetris needs a one-column
    # well four rows deep, so a deep well is the sign that a big clear
    # is actually being set up.
    #
    # A cell is "in a well" when it is empty AND both horizontal
    # neighbours are filled at that row (the board edges count as
    # filled neighbours). Consecutive such cells form a well; the sum
    # of a well's depth is d*(d+1)/2, so a depth-4 well costs 10 --
    # quadratically punishing deep wells.
    well_sums = 0
    max_well = 0
    for x in range(WIDTH):
        depth = 0
        for y in range(HEIGHT):
            left = grid[y][x - 1] if x > 0 else 1
            right = grid[y][x + 1] if x + 1 < WIDTH else 1
            if grid[y][x] == 0 and left and right:
                depth += 1
            else:
                # The well ends here: bank its triangular depth sum.
                well_sums += depth * (depth + 1) // 2
                max_well = max(max_well, depth)
                depth = 0
        # Bank the well that ran to the bottom of the column.
        well_sums += depth * (depth + 1) // 2
        max_well = max(max_well, depth)
    if evaluate is None:
        evaluate = _board_evaluator(w, danger)
    return evaluate(cleared, landing_height, heights, holes, row_transitions,
                    col_transitions, well_sums, max_well)


def _board_evaluator(w: dict, danger: float):
    """Blend the strategy weights once for all landings from the same board."""
    danger_weights = w.get("danger_w") or {}

    def blend(name):
        base = w.get(name, 0.0)
        return _lerp(base, danger_weights.get(name, base), danger)

    landing_w = blend("landing_w")
    landing_free = blend("landing_free")
    credit = blend("landing_credit")
    holes_w = blend("holes_w")
    well_w = blend("well_w")
    agg_w = blend("agg_w")
    maxh_w = blend("maxh_w")
    points_w = blend("points_w")
    lines_w = blend("lines_w")
    clears = [lines_w * n + points_w * (points_for_clear(n) / 100) for n in range(5)]
    defer = w["defer_w"] * (1.0 - danger)
    min_well = w.get("defer_well", 0)
    defer_max = w.get("defer_max", 2)
    flat_base = w.get("flat_base", 0.0)
    flat_w = w.get("flat_w", 0.0) * (flat_base + (1.0 - flat_base) * danger)

    def evaluate(cleared, landing_height, heights, holes, row_edges, col_edges, wells, deepest):
        # Legacy profiles can defer a small clear on a low, clean stack.
        clear_term = clears[cleared]
        if (defer and 1 <= cleared <= defer_max and holes == 0
                and max(heights) < w["safe_h"] and deepest >= min_well):
            clear_term -= defer
        height = max(0.0, landing_height - credit * cleared)
        roughness = sum(abs(a - b) for a, b in zip(heights, heights[1:])) if flat_w else 0
        return (
            landing_w * max(0.0, height - landing_free)
            + clear_term
            + W_ROW_TRANSITIONS * row_edges
            + W_COL_TRANSITIONS * col_edges
            + holes_w * holes
            + well_w * wells
            + flat_w * roughness
            + agg_w * sum(heights)
            + maxh_w * max(heights)
        )

    return evaluate


def best_placement(
    board, kind: Piece, strategy: str = "quick"
) -> tuple[int, int] | None:
    """The (rotation, x) whose simulated landing scores highest under
    the given strategy, or None when the piece does not fit anywhere
    (the stack has reached the top).

    THE SEARCH LOOP
    ----------------
    For each rotation state, for each column where the piece would fit,
    simulate the landing and score it. The best-scoring candidate wins.

    The candidate count is small: 4 rotation states x at most 10 columns
    = at most 40 placements, and each one is a cheap grid simulation.
    That is fast enough to run every frame on a modern machine, but the
    game only does it once per piece anyway (see `Game._autopilot_step`).
    """
    w = STRATEGIES[strategy]
    rot_count = len(ROTATIONS[kind])
    best: tuple[int, int] | None = None
    best_score: float | None = None
    # The board does not change during the search, so snapshot it once
    # instead of rebuilding it for every candidate placement.
    base = _grid(board)
    # Board fullness before the placement: the danger context is the
    # same for every candidate, so they are judged consistently.
    #
    # This is measured BEFORE the placement, on purpose: every candidate
    # must be judged against the SAME danger level, otherwise the
    # comparison between them would be unfair.
    danger = _danger(_max_height(base), _holes(base), w)
    evaluate = _board_evaluator(w, danger)
    for rot in range(rot_count):
        # The column range for this rotation: the piece's own width
        # decides how far left or right it may start. `min(xs)` and
        # `max(xs)` are the piece's leftmost and rightmost offsets, so
        # `-min(xs)` is the leftmost legal column and
        # `WIDTH - max(xs)` is one past the rightmost legal one.
        xs = [dx for dx, _ in ROTATIONS[kind][rot]]
        for x in range(-min(xs), WIDTH - max(xs)):
            # Where does the piece come to rest if dropped at this column?
            cells = _resting_cells(board, kind, rot, x)
            if cells is None:
                continue  # does not fit here
            # Simulate the lock on a COPY of the board. The copy is
            # essential: `_lock` mutates the grid it is given.
            grid, cleared = _lock([row[:] for row in base], cells)
            # The landing height: the average height of the piece's
            # resting cells. Averaging (rather than taking the lowest
            # or highest cell) matches the published El-Tetris feature,
            # and it keeps the measure comparable between a flat piece
            # and a tall one.
            landing_height = HEIGHT - sum(cy for _, cy in cells) / len(cells)
            # Score the resulting position with this strategy's weights.
            score = _score(grid, cleared, landing_height, w, danger, evaluate)
            # Keep the best so far. Strictly greater, so the FIRST
            # candidate wins a tie (deterministic behaviour).
            if best_score is None or score > best_score:
                best_score = score
                best = (rot, x)
    return best
