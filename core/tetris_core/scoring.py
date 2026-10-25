"""Line clears, scoring bonuses, and level progression (spec 4.5).

Per-clear award values verified by the owner 2026-10-24 from the award
table in png/screenshot_28.png. The 30-line bonus-block structure and the
level rule remain VERIFY/TBD placeholders (open items) so the game is
playable; they live here in one place for the owner to replace with
verified values.
"""

from __future__ import annotations


# Immediate points per single clear event, by lines cleared at once
# (owner-verified from the award table: single 100, double 400,
# triple 900, tetris 2500).
POINTS_FOR_CLEAR = {1: 100, 2: 400, 3: 900, 4: 2500}

# A bonus block completes every 30 cleared lines (spec 4.5 structure).
BONUS_BLOCK_LINES = 30
BLOCK_BONUS_POINTS = 300

# Level progression placeholder: one level per completed 30-line block.
# Do not assume the Nintendo every-10-lines rule (spec 4.5).
LEVEL_LINES = 30


def points_for_clear(cleared: int) -> int:
    return POINTS_FOR_CLEAR.get(cleared, 0)


def block_bonuses(lines_before: int, lines_after: int) -> int:
    """How many BONUS_BLOCK_LINES blocks were completed by this clear."""
    return lines_after // BONUS_BLOCK_LINES - lines_before // BONUS_BLOCK_LINES


def level_for_lines(start_level: int, lines: int) -> int:
    return start_level + lines // LEVEL_LINES
