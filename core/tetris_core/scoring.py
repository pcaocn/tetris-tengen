"""Tengen scoring and level rules.

Only the rules used by the implementation live here. The old flat
30-line block bonus is removed; clear awards are accumulated into a
pending stage award and paid at stage completion.

WHAT THIS FILE IMPLEMENTS
=========================
- The four clear-value awards, credited to a pending stage award and paid
  once when the stage ends (owner decision 2026-10-29, refined by the
  Tengen cartridge brief).
- The placement formula for a locked piece:
  `min(d * r * (r + h), 999)`.
- The Tengen level curve: 30-line stages through level 5, then 50-line
  stages, with the displayed level capped at 17. Stage boundaries are
  tracked separately by the game so the cap still pays and celebrates.

EVIDENCE AND SOURCES
====================
- Clear values: the Tengen NES manual, printed p. 9 -- 100 / 400 / 900 /
  2,500 points for 1 / 2 / 3 / 4 rows at once.
- Level curve: the same manual's 30-line steps through 150, then 50-line
  steps; TetrisWiki's Tengen level table confirms the 17-level display cap.
- Placement formula: TetrisWiki, "Tetris (NES, Tengen)" -- one or two
  points per cell of the piece's height, times the level number, with a
  999-point cap. The row-height mapping used here is the height of the
  piece's LOWEST occupied cell, with 0 on the bottom visible row. That is
  the mapping in the disassembly's bitmap scan (`main.asm` L8658-L8692,
  which keeps the last occupied cell before L9A47 adds it to the level
  term).

The autopilot's evaluator imports ``points_for_clear`` and normalises by
100; it must stay importable even as the payout timing changes.
"""

from __future__ import annotations

# Tengen stage lengths, in lines. Stages 0-4 are 30 lines; from level 5
# onward every stage is 50 lines.
INITIAL_STAGE_LINES = 30
LATE_STAGE_LINES = 50

# The displayed level stops at 17, but stage boundaries keep arriving
# every 50 lines (800, 850, ...) and still pay.
MAX_LEVEL = 17
LEVEL_COUNT = MAX_LEVEL + 1

# The placement formula's cap (TetrisWiki).
PLACEMENT_POINTS_CAP = 999

# The clear-value helper is the single source of truth for the award
# table. It is used by the game (pending stage award) and by the
# autopilot's evaluator, so a tuning change here automatically changes
# both the score and the AI's valuation of a clear.
AWARD_VALUES = {1: 100, 2: 400, 3: 900, 4: 2500}


def points_for_clear(cleared: int) -> int:
    """Tengen's award for a clear of `cleared` rows (0..4).

    The rule is value-based: four rows at once is worth 25 single rows,
    not four. That super-linear table is what makes the "highscore"
    autopilot strategy want to hunt tetrises. The clear value is
    accumulated into a pending stage award and credited once the stage
    ends; it is no longer paid immediately on every clear.
    """
    if cleared <= 0:
        return 0
    return AWARD_VALUES[min(4, cleared)]


def placement_points(level: int, soft_drop: bool, row_height: int) -> int:
    """Points for one locked piece, excluding line-clear awards.

    ``level`` is the level at landing, BEFORE any stage advance caused by
    this lock. ``soft_drop`` is the drop state at landing (Down held).
    ``row_height`` is the height of the piece's lowest occupied cell,
    counted from zero on the bottom visible row.

    Formula: ``min(d * r * (r + h), 999)`` with ``r = level + 1`` and
    ``d = 2`` for a soft-drop landing, otherwise 1.
    """
    r = max(0, level) + 1
    d = 2 if soft_drop else 1
    h = max(0, row_height)
    return min(d * r * (r + h), PLACEMENT_POINTS_CAP)


def stage_lines_for_level(level: int) -> int:
    """How many lines make a stage at `level`.

    Levels 0-4 use the cartridge's opening 30-line stages; level 5 and
    above use 50-line stages. The cap level 17 still uses 50, so 800 and
    850 are real stage boundaries.
    """
    return INITIAL_STAGE_LINES if level < 5 else LATE_STAGE_LINES


def level_for_lines(start_level: int, lines: int, base_lines: int = 0) -> int:
    """The displayed level after clearing `lines` total lines.

    `start_level` is the level at the last anchor (a new game or a level
    jump), not necessarily the level the game began at. `base_lines` is
    the line count at that anchor, so progression after a mid-game jump
    measures only the lines cleared since the jump. The default of zero
    preserves the whole-run rule for a game that never jumped.

    The curve is not a single 30-line rule: stages 0-4 are 30 lines and
    stages 5+ are 50 lines. The loop walks those stage lengths so a
    nonzero start or a custom jump cannot accidentally re-count the whole
    run's line total.
    """
    level = max(0, min(start_level, MAX_LEVEL))
    remaining = max(0, lines - base_lines)
    while level < MAX_LEVEL:
        need = stage_lines_for_level(level)
        if remaining < need:
            break
        remaining -= need
        level += 1
    return min(level, MAX_LEVEL)