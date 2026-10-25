"""Fall speed table and soft drop acceleration (spec 4.3).

VERIFY (spec 4.3): the Tengen speed table must be looked up in a cited
source; Nintendo values must not be used. The table below is a PLACEHOLDER
so the game is playable while the source is tracked down (open item).

VERIFY (spec 4.3): Tengen soft drop speeds up gradually while held rather
than jumping to a fixed speed. The exact curve is TBD; the constants below
are a PLACEHOLDER pending a documented source.
"""

from __future__ import annotations


# Frames per row by level. Index = level. Beyond the table, the last value.
FALL_SPEEDS = (50, 42, 35, 29, 24, 19, 15, 12, 9, 6, 5, 4, 3, 2)

# Soft drop model: effective frames-per-row starts at SOFT_DROP_START_FPR and
# drops by 1 for every SOFT_DROP_ACCEL_EVERY frames the key is held, floored
# at SOFT_DROP_MIN_FPR, and never slower than normal gravity.
SOFT_DROP_START_FPR = 6
SOFT_DROP_ACCEL_EVERY = 4
SOFT_DROP_MIN_FPR = 1


def frames_per_row(level: int) -> int:
    if level < 0:
        level = 0
    if level < len(FALL_SPEEDS):
        return FALL_SPEEDS[level]
    return FALL_SPEEDS[-1]


def soft_drop_fpr(normal_fpr: int, frames_held: int) -> int:
    """Effective frames-per-row while soft drop is held."""
    fpr = SOFT_DROP_START_FPR - frames_held // SOFT_DROP_ACCEL_EVERY
    if fpr < SOFT_DROP_MIN_FPR:
        fpr = SOFT_DROP_MIN_FPR
    if fpr > normal_fpr:
        fpr = normal_fpr
    return fpr
