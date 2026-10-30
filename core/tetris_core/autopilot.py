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
    """Blend a weight from its base value to its danger value."""
    return base + (danger_value - base) * danger


def _max_height(grid: list[list[int]]) -> int:
    """Height of the tallest column (0 for an empty board)."""
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
    """
    h0 = w.get("danger_h")
    if not h0:
        return 0.0
    span = max(1.0, w.get("danger_span", 6.0))
    effective = stack_h + w.get("danger_holes", 0.0) * holes
    return max(0.0, min(1.0, (effective - h0) / span))


def _holes(grid: list[list[int]]) -> int:
    """Number of empty cells buried under the stack."""
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


def _score(
    grid: list[list[int]],
    cleared: int,
    landing_height: float,
    w: dict,
    danger: float = 0.0,
) -> float:
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
    # sum rewards shallow wells and punishes deep ones. The deepest
    # single well is tracked separately: a tetris needs a one-column
    # well four rows deep, so a deep well is the sign that a big clear
    # is actually being set up.
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
                well_sums += depth * (depth + 1) // 2
                max_well = max(max_well, depth)
                depth = 0
        well_sums += depth * (depth + 1) // 2
        max_well = max(max_well, depth)
    # Board fullness (owner request 2026-10-29): blend the weights toward
    # their danger values as the stack fills, so past half full the
    # strategy stops hunting tetrises and plays to survive.
    dw = w.get("danger_w") or {}
    landing_w = _lerp(w["landing_w"], dw.get("landing_w", w["landing_w"]), danger)
    landing_free = _lerp(w["landing_free"], dw.get("landing_free", w["landing_free"]), danger)
    well_w = _lerp(w["well_w"], dw.get("well_w", w["well_w"]), danger)
    holes_w = _lerp(w["holes_w"], dw.get("holes_w", w["holes_w"]), danger)
    # Aggregate height (owner request 2026-10-29): the total number of
    # filled cells in the stack. El-Tetris has no feature for it, and
    # that is exactly why the strategy can fill the board without ever
    # clearing it: every term it knows about is either about the shape
    # of one landing or about the points of the clear, and the landing
    # cost of a tetris high on the stack dwarfs the points it earns.
    # The measured early deaths all look the same -- every column at
    # height 13-20, the stack at the ceiling -- so the missing reward
    # is for taking the stack DOWN. A tetris removes four rows from
    # every column it crosses, which this term sees and the landing
    # height does not.
    agg_w = _lerp(w.get("agg_w", 0.0), dw.get("agg_w", w.get("agg_w", 0.0)), danger)
    maxh_w = _lerp(w.get("maxh_w", 0.0), dw.get("maxh_w", w.get("maxh_w", 0.0)), danger)
    # Clearing lines gets more valuable as the stack fills (owner request
    # 2026-10-29). Past half full, a board that is never cleared IS a
    # board that dies: with only the landing penalty in play the
    # strategy stops clearing entirely and the stack fills up instead.
    points_w = _lerp(w["points_w"], dw.get("points_w", w["points_w"]), danger)
    # A flat reward per cleared row, blended the same way. The highscore
    # profile leaves "lines_w" at 0 and pays for clears by their point
    # value instead, which is the right trade while the stack is safe
    # (a tetris is worth 25x a single) but the wrong one once the
    # stack is tall: a single clear is worth 1 point there, against a
    # landing cost of 14 per row, so no clear is ever worth taking and
    # the board fills up instead. Measured on the death boards: every
    # column between 13 and 20 rows high, holes everywhere, and not one
    # tetris in sight. "lines_w" in the danger weights pays per ROW, so
    # even a single becomes worth taking when the stack is high.
    lines_w = _lerp(w["lines_w"], dw.get("lines_w", w["lines_w"]), danger)
    # Credit a placement for the stack height its own clear removes.
    # "landing_height" is measured from the piece's resting cells on the
    # PRE-lock board, but _lock drops the cleared rows from the top of
    # the grid, so the stack the placement leaves behind is that many
    # rows lower than where the piece came to rest. Without this credit
    # a tetris is charged the landing cost of four rows it just deleted:
    # at full danger that is 4 * -14 = -56 against a clear worth +25
    # points, so the strategy refuses to cash in a tetris even when the
    # clear is exactly what it needs. The credit is the missing
    # "reward taking the stack DOWN" term, expressed in the units the
    # landing height already uses.
    credit = _lerp(
        w.get("landing_credit", 0.0),
        dw.get("landing_credit", w.get("landing_credit", 0.0)),
        danger,
    )
    landing_height = max(0.0, landing_height - credit * cleared)
    # Clear term: linear lines (quick) or point-valued clears with a
    # deferral cost for burning 1-2 line clears while the stack is safe
    # and clean (highscore); holes or a tall stack waive the deferral —
    # survival first.
    clear_term = lines_w * cleared + points_w * (
        points_for_clear(cleared) / 100
    )
    # The deferral cost fades out as the stack fills, replacing the hard
    # cutoff at safe_h with a smooth ramp.
    defer_w = w["defer_w"] * (1.0 - danger)
    # "defer_well": only hold back a small clear when a big one is
    # actually reachable. A tetris needs a one-column well four rows
    # deep; deferring a clear on a board with no deep well is not
    # "saving rows for a tetris", it is just refusing points. Measured
    # on live games, a deferred piece is followed by a tetris within
    # 12 pieces about as often as a non-deferred one, so the deferral
    # is not buying the clears it hopes for.
    if w.get("defer_well", 0.0) > 0.0 and max_well < w["defer_well"]:
        defer_w = 0.0
    if (
        defer_w
        and 1 <= cleared <= w.get("defer_max", 2.0)
        and max(heights) < w["safe_h"]
        and holes == 0
    ):
        clear_term -= defer_w
    # Flatness (owner request 2026-10-29): the sum of the height steps
    # between neighbouring columns. A flat board is easy to recover; a
    # board with a deep canyon next to a tall tower is not, and the
    # canyon does not register as a "well" (the well metric needs both
    # neighbours filled at that row). The penalty ramps up with danger;
    # "flat_base" is the share that applies even to a safe board, so a
    # canyon is not dug while the stack is still low (it would be fatal
    # by the time it matters).
    flat_w = w.get("flat_w", 0.0)
    flat_base = w.get("flat_base", 0.0)
    flatness = sum(
        abs(heights[x] - heights[x + 1]) for x in range(WIDTH - 1)
    )
    return (
        landing_w * max(0.0, landing_height - landing_free)
        + clear_term
        + W_ROW_TRANSITIONS * row_transitions
        + W_COL_TRANSITIONS * col_transitions
        + holes_w * holes
        + well_w * well_sums
        + flat_w * (flat_base + (1.0 - flat_base) * danger) * flatness
        + agg_w * sum(heights)
        + maxh_w * max(heights)
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
    # The board does not change during the search, so snapshot it once
    # instead of rebuilding it for every candidate placement.
    base = _grid(board)
    # Board fullness before the placement: the danger context is the
    # same for every candidate, so they are judged consistently.
    danger = _danger(_max_height(base), _holes(base), w)
    for rot in range(rot_count):
        xs = [dx for dx, _ in ROTATIONS[kind][rot]]
        for x in range(-min(xs), WIDTH - max(xs)):
            cells = _resting_cells(board, kind, rot, x)
            if cells is None:
                continue
            grid, cleared = _lock([row[:] for row in base], cells)
            landing_height = HEIGHT - sum(cy for _, cy in cells) / len(cells)
            score = _score(grid, cleared, landing_height, w, danger)
            if best_score is None or score > best_score:
                best_score = score
                best = (rot, x)
    return best
