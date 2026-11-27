"""Highscore planning from the live piece and the visible preview.

The two plies share the engine's movement and timing. After steering,
holding Down lands at a known row, so the remaining idle ticks can be
projected directly. Each column is an integer whose lowest bit is the
bottom row. This makes simulating hundreds of locks affordable.
"""
from __future__ import annotations

from collections import deque
from copy import copy
from functools import lru_cache, reduce
from operator import and_
from typing import NamedTuple, TYPE_CHECKING

from . import autopilot
from .board import Board, HEIGHT, WIDTH
from .pieces import Piece, ROTATIONS, ROTATION_KICKS
from .scoring import MAX_LEVEL, placement_points, points_for_clear

if TYPE_CHECKING:
    from .game import Game

WALL = (1 << HEIGHT) - 1
# Python 3.9 is supported by the system-Python desktop fallback.
_popcount = getattr(int, "bit_count", lambda n: bin(n).count("1"))
SAFE_CLEAR_WEIGHT = 5.0  # 125 heuristic units for a Tetris on a low board
READY_ROW_WEIGHT = 20.0  # four prepared rows remain worth less than cashing in
ACTIONS = ("left", "right", "cw", "ccw")


class Landing(NamedTuple):
    columns: list[int]
    cleared: int
    height: float
    route: tuple[str, ...]
    placement_award: int


def steer(game: Game, action: str) -> bool:
    if action in ("cw", "ccw"):
        return game._try_rotate(1 if action == "cw" else -1)
    return game._move(-1 if action == "left" else 1)


@lru_cache(None)
def _shape(kind: Piece, rot: int):
    """Column offsets, bottom cell offsets, and column bits above that cell."""
    cells = ROTATIONS[kind][rot]
    columns = []
    for x in sorted({x for x, _ in cells}):
        ys = [y for dx, y in cells if dx == x]
        bottom = max(ys)
        columns.append((x, bottom, sum(1 << (bottom - y) for y in ys)))
    return columns, max(bottom for _, bottom, _ in columns), sum(y for _, y in cells) / 4


@lru_cache(512)
def _open_routes(kind, x, rot):
    """Shortest wall-legal input sequences in unobstructed air."""
    queue = deque([(x, rot, ())])
    routes = []
    seen = {(x, ROTATIONS[kind][rot])}
    while queue:
        x, rot, route = queue.popleft()
        routes.append((x, rot, route))
        for action in ACTIONS:
            nx, nr = x, rot
            rotating = action in ("cw", "ccw")
            if rotating:
                nr = (rot + (1 if action == "cw" else -1)) % 4
            else:
                nx += -1 if action == "left" else 1
            shape = ROTATIONS[kind][nr]
            for kick in (ROTATION_KICKS if rotating else (0,)):
                if all(0 <= nx + kick + dx < WIDTH for dx, _ in shape):
                    key = nx + kick, shape
                    if key not in seen:
                        seen.add(key)
                        queue.append((nx + kick, nr, route + (action,)))
                    break
    return routes


def _routes(game, columns):
    routes = _open_routes(game.piece_kind, game._piece_x, game._rot)
    # Prove every input finishes above the tallest obstacle, including
    # the floor. A shadow uses the same fractional gravity and hold timer.
    shadow = copy(game)
    top = HEIGHT - max(map(int.bit_length, columns))
    for _ in routes[-1][2]:
        shadow._apply_gravity()
    if shadow._piece_y + 4 < top:
        for x, rot, route in routes:
            yield x, rot, game._piece_y, route, True
        return

    # Near obstacles, explore alternate input orders with real kicks and
    # frame timing. Keep the first route to each orientation and column.
    # This bounded search omits delayed tucks that revisit the same pose.
    if game.board is None:
        game = copy(game)
        game.board = _board(columns)
    queue = deque([(game, ())])
    seen = {(game._piece_x, ROTATIONS[game.piece_kind][game._rot])}
    while queue:
        state, route = queue.popleft()
        soft = not state._rest_frames or state._landing_soft_drop
        yield state._piece_x, state._rot, state._piece_y, route, soft
        for action in ACTIONS:
            shadow = copy(state)
            if not steer(shadow, action):
                continue
            key = shadow._piece_x, ROTATIONS[shadow.piece_kind][shadow._rot]
            if key in seen:
                continue
            seen.add(key)
            _, locked = shadow._fall_frame()
            if locked:
                yield (shadow._piece_x, shadow._rot, shadow._piece_y, route + (action,),
                       shadow._landing_soft_drop)
            else:
                queue.append((shadow, route + (action,)))


def _landings(game, columns):
    for x, rot, y, route, soft in _routes(game, columns):
        shape, bottom_offset, mean_offset = _shape(game.piece_kind, rot)
        # Bit zero is the floor row. Ignore obstacles above the piece so
        # this projection is valid for a mid-fall takeover under a ledge.
        floor_y = HEIGHT - 1
        for dx, bottom, _ in shape:
            below = columns[x + dx] & ((1 << (HEIGHT - 1 - y - bottom)) - 1)
            floor_y = min(floor_y, HEIGHT - 1 - bottom - below.bit_length())
        result = list(columns)
        for dx, bottom, bits in shape:
            result[x + dx] |= bits << (HEIGHT - 1 - floor_y - bottom)
        full = reduce(and_, result)
        cleared = _popcount(full)
        while full:
            row = full & -full
            low = row - 1
            result = [(col & low) | ((col >> 1) & ~low) for col in result]
            full = (full ^ row) >> 1
        height = HEIGHT - floor_y - mean_offset
        row_height = HEIGHT - 1 - floor_y - bottom_offset
        award = placement_points(game.level, soft or floor_y > y, row_height)
        yield Landing(result, cleared, height, route, award)


def _features(cols):
    """Same features as autopilot._score, computed on packed columns."""
    heights = [col.bit_length() for col in cols]
    holes = sum(heights) - sum(map(_popcount, cols))
    row_edges = _popcount(WALL ^ cols[0]) + _popcount(WALL ^ cols[-1])
    row_edges += sum(_popcount(a ^ b) for a, b in zip(cols, cols[1:]))
    col_edges = sum(_popcount(col ^ ((col << 1) | 1)) for col in cols)
    wells = deepest = 0
    for left, middle, right in zip([WALL] + cols, cols, cols[1:] + [WALL]):
        mask = left & ~middle & right
        depth = 0
        while mask:
            wells += _popcount(mask)
            mask &= mask >> 1
            depth += 1
        deepest = max(deepest, depth)
    return heights, holes, row_edges, col_edges, wells, deepest


def _ready_rows(cols):
    """Rows a single future vertical I could complete from above."""
    full = one_missing = WALL
    for col in cols:
        one_missing = (one_missing & col) | full
        full &= col
    # There are no full rows after compaction. Each surviving bit
    # therefore marks a row with exactly one missing cell.
    if not one_missing:
        return 0
    best = max(_popcount((one_missing >> col.bit_length()) & 15)
               for col in cols)
    return best


def _board(columns):
    board = Board()
    for x, col in enumerate(columns):
        while col:
            bit = col & -col
            board.lock_cells([(x, HEIGHT - bit.bit_length())], 1)
            col ^= bit
    return board


def plan(game: Game, spawn_x: int, spawn_y: int) -> tuple[str, ...]:
    """Return the current piece's steering sequence, one input per tick."""
    cols = [sum(1 << (HEIGHT - 1 - y) for y in range(HEIGHT) if game.board.get(x, y))
            for x in range(WIDTH)]
    weights = dict(autopilot.STRATEGIES["highscore"], defer_w=0)
    weights["points_w"] = SAFE_CLEAR_WEIGHT
    initial = _features(cols)
    danger = autopilot._danger(max(initial[0]), initial[1], weights)
    # Build a preview shadow without calling spawn, drawing RNG or saving scores.
    preview = copy(game)
    preview._piece_kind = game.next_piece
    preview._piece_x, preview._piece_y, preview._rot = spawn_x, spawn_y, 0
    preview._gravity_counter = preview._gravity_threshold = 0
    preview._soft_held = preview._rest_frames = 0
    preview._soft_drop = True
    spawn = preview.piece_cells()
    preview.board = None  # only populated for obstructed routes
    points_weight = autopilot._lerp(weights["points_w"], weights["danger_w"]["points_w"], danger)
    evaluate = autopilot._board_evaluator(weights, danger)
    setup_weight = READY_ROW_WEIGHT * (1 - danger)
    best = None
    best_route = ()
    for first in _landings(game, cols):
        alive = all(first.columns[x] & (1 << (HEIGHT - 1 - y)) == 0 for x, y in spawn)
        if alive:
            stage_ends = game.lines + first.cleared >= game._next_stage_line
            preview.level = min(MAX_LEVEL, game.level + int(stage_ends))
            score = max(
                evaluate(second.cleared, second.height, *_features(second.columns))
                + setup_weight * _ready_rows(second.columns)
                + points_weight * second.placement_award / 100
                for second in _landings(preview, first.columns)
            )
            award = points_for_clear(first.cleared) + first.placement_award
            score += points_weight * award / 100
        else:
            score = evaluate(first.cleared, first.height, *_features(first.columns))
        rank = alive, score
        if best is None or rank > best:
            best, best_route = rank, first.route
    return best_route
