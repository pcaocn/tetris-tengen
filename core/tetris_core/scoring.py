"""Line clears, scoring bonuses, and level progression (spec 4.5).

Per-clear award values verified by the owner 2026-10-24 from the award
table in png/screenshot_28.png. The 30-line bonus-block structure and the
level rule remain VERIFY/TBD placeholders (open items) so the game is
playable; they live here in one place for the owner to replace with
verified values.

THE SCORING MODEL IN THREE PARTS
--------------------------------
1. CLEAR AWARD: every line-clear event immediately awards points based on
   HOW MANY rows were cleared at once -- 1 row = 100, 2 = 400, 3 = 900,
   4 = 2500. The values are super-linear on purpose: a tetris (4 rows)
   pays 25x a single. This is what makes the "highscore" autopilot hunt
   tetrises (spec 4.11) -- it is the only way to score fast.
2. BLOCK BONUS: a bonus is paid for each completed 30-line block. The
   `block_bonuses` helper counts how many blocks a single clear crossed,
   so one tetris that completes two blocks at once pays two bonuses.
3. LEVEL: the level advances by one for each completed 30-line block.

The 30-line block structure is also what drives the end-of-stage
celebration: `game.py` compares the level before and after a clear and
freezes for the celebration track when the level changed (spec 5).
"""

from __future__ import annotations


# Immediate points per single clear event, by lines cleared at once
# (owner-verified from the award table: single 100, double 400,
# triple 900, tetris 2500).
#
# The ratio between them is the whole point: a tetris is worth 25x a
# single, 6.25x a double, and 2.8x a triple. The "highscore" autopilot
# reads these numbers directly (`points_for_clear(cleared) / 100` is its
# points weight), so changing a value here changes how the AI plays.
POINTS_FOR_CLEAR = {1: 100, 2: 400, 3: 900, 4: 2500}

# A bonus block completes every 30 cleared lines (spec 4.5 structure).
BONUS_BLOCK_LINES = 30
BLOCK_BONUS_POINTS = 300

# Level progression placeholder: one level per completed 30-line block.
# Do not assume the Nintendo every-10-lines rule (spec 4.5).
LEVEL_LINES = 30


def points_for_clear(cleared: int) -> int:
    """Points awarded for one clear event of `cleared` rows.

    Returns 0 for anything that is not a real clear size (0 rows, or an
    impossible 5+), which keeps the caller simple: it can pass the row
    count straight through without checking it first.
    """
    return POINTS_FOR_CLEAR.get(cleared, 0)


def block_bonuses(lines_before: int, lines_after: int) -> int:
    """How many BONUS_BLOCK_LINES blocks were completed by this clear.

    Integer division counts how many whole blocks the TOTAL line count
    spans. Taking the difference between the count before and after the
    clear gives the number of blocks this one clear crossed -- which can
    be more than one (a tetris that lands exactly on a block boundary
    completes two blocks at once).

    Note that this counts BLOCKS, not lines: the leftover lines inside an
    unfinished block carry no bonus (spec 4.5 VERIFY -- the spec still
    asks what happens to lines cleared outside a bonus block).
    """
    return lines_after // BONUS_BLOCK_LINES - lines_before // BONUS_BLOCK_LINES


def level_for_lines(start_level: int, lines: int, base_lines: int = 0) -> int:
    """The level reached after clearing `lines` lines.

    `start_level` is the level at the last anchor (a new game or a level
    jump), not necessarily the level the game began at. `base_lines` is
    the line count at that anchor, so progression after a mid-game jump
    measures only the lines cleared since the jump. The default of zero
    preserves the original whole-run rule for a game that never jumped.
    """
    progress = max(0, lines - base_lines)
    return start_level + progress // LEVEL_LINES
