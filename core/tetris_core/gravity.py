"""Fall speed table and soft drop acceleration (spec 4.3).

VERIFY (spec 4.3): the Tengen speed table must be looked up in a cited
source; Nintendo values must not be used. The table below is a PLACEHOLDER
so the game is playable while the source is tracked down (open item).

VERIFY (spec 4.3): Tengen soft drop speeds up gradually while held rather
than jumping to a fixed speed. The exact curve is TBD; the constants below
are a PLACEHOLDER pending a documented source.

HOW GRAVITY IS MODELLED
-----------------------
Tetris gravity is measured in FRAMES PER ROW (fpr), not in rows per
second: the piece falls one row every `fpr` frames. At 60 Hz, an fpr of
6 means 10 rows per second.

Working in frames (rather than seconds) is deliberate: the game loop is
fixed at 60 Hz (spec 2.1), so an integer frame count makes the fall
exactly reproducible for a given seed -- which is what lets the autopilot
benchmarks be deterministic and comparable.

The two functions here are the ONLY place a fall speed is decided:
  - `frames_per_row(level)`   -> normal gravity for a level
  - `soft_drop_fpr(normal, held)` -> gravity while the Down key is held
"""

from __future__ import annotations


# Frames per row by level. Index = level. Beyond the table, the last value.
# Smaller number = faster fall. Level 0 is the slowest (50 frames = about
# 1.2 rows/second); by level 13 the piece falls a row every 2 frames.
FALL_SPEEDS = (50, 42, 35, 29, 24, 19, 15, 12, 9, 6, 5, 4, 3, 2)

# Soft drop model: effective frames-per-row starts at SOFT_DROP_START_FPR and
# drops by 1 for every SOFT_DROP_ACCEL_EVERY frames the key is held, floored
# at SOFT_DROP_MIN_FPR, and never slower than normal gravity.
#
# This is the "speeds up GRADUALLY while held" behaviour the spec
# describes for Tengen (spec 4.3) -- as opposed to Nintendo's fixed
# 2x-speed soft drop. Holding Down is therefore a two-stage action: a
# brief slow phase, then a faster one.
SOFT_DROP_START_FPR = 6  # frames per row in the first moments of holding
SOFT_DROP_ACCEL_EVERY = 4  # held frames per 1-frame-per-row acceleration step
SOFT_DROP_MIN_FPR = 1  # fastest the fall can get (one row per frame)


def frames_per_row(level: int) -> int:
    """Normal gravity for a level, in frames per row.

    Two clamping rules:
      - Levels below 0 are treated as level 0.
      - Levels past the end of the table keep the last (fastest) value,
        so the game stays playable if the level ever exceeds 13.
    """
    if level < 0:
        level = 0
    if level < len(FALL_SPEEDS):
        return FALL_SPEEDS[level]
    return FALL_SPEEDS[-1]


def soft_drop_fpr(normal_fpr: int, frames_held: int) -> int:
    """Effective frames-per-row while soft drop is held.

    `frames_held` is how many frames the Down key has been down so far.
    The integer division by SOFT_DROP_ACCEL_EVERY is what makes the
    acceleration stepwise (one step per 4 held frames) rather than a
    smooth ramp.

    Two floors/ceilings are applied:
      - Never faster than SOFT_DROP_MIN_FPR (the acceleration stops there).
      - Never SLOWER than normal gravity: if the level is already faster
        than the soft-drop start value (a high level), holding Down must
        not actually slow the piece down.
    """
    fpr = SOFT_DROP_START_FPR - frames_held // SOFT_DROP_ACCEL_EVERY
    if fpr < SOFT_DROP_MIN_FPR:
        fpr = SOFT_DROP_MIN_FPR
    if fpr > normal_fpr:
        fpr = normal_fpr
    return fpr
