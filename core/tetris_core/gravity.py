"""Gravity timing in 60 Hz frames.

WHAT THIS FILE IMPLEMENTS
=========================
- ``frames_per_row(level)``: the Tengen cartridge's normal-gravity
  interval for levels 0..17, in frames per row.
- ``soft_drop_fpr(normal, held)``: the effective interval while the Down
  key is held, with two guard rails (never slower than normal gravity,
  never faster than one row per frame).

EVIDENCE AND SOURCES
====================
- The normal-gravity table is the Tengen NES table published on
  TetrisWiki ("Tetris (NES, Tengen)", Gravity page):

      level:  0   1   2   3   4   5   6  7  8  9  10   11  12   13   14   15   16  17
      frames:33  28  24  20  17  14  11  9  7  6  5.5  5   4.5  4    3.75 3.5  3.25 3

  The original table has fractional averages for the faster levels; this
  file stores those decimals directly and the game keeps fractional
  progress in quarter-frame units, so 5.5 and 3.75 are exact.
- The soft-drop acceleration curve is still the provisional Tengen-style
  curve (spec 4.3). It starts at 6 frames per row and loses one frame per
  row every four held frames, flooring at one row per frame. Holding
  Down therefore always helps, never hurts, and a short tap does not
  teleport the piece.
"""

from __future__ import annotations

# Normal gravity, in frames per row, for levels 0..17. Indexed by level
# with clamping at both ends so a malformed level can never index past
# the table.
FALL_SPEEDS: tuple[float, ...] = (
    33,
    28,
    24,
    20,
    17,
    14,
    11,
    9,
    7,
    6,
    5.5,
    5,
    4.5,
    4,
    3.75,
    3.5,
    3.25,
    3,
)

# --- soft drop acceleration (VERIFY, spec 4.3) ---------------------------
#
# The curve below is the current PLACEHOLDER: Tengen's exact soft-drop
# acceleration has not been confirmed. It is deliberately a curve rather
# than a fixed multiplier: holding Down starts at SOFT_DROP_START_FPR
# (6 fpr) and loses one frame per row every SOFT_DROP_ACCEL_EVERY frames
# held, down to a floor of SOFT_DROP_MIN_FPR (1 fpr).
#
# Guard rails:
#   - never slower than normal gravity for the level (min(normal, soft));
#   - never faster than one row per frame.
#
# Replace these constants when a source for the real curve is found; the
# tests in test_gravity.py pin every step of this provisional curve.

SOFT_DROP_START_FPR = 6  # frames per row on the first frame Down is held
SOFT_DROP_ACCEL_EVERY = 4  # held frames per one-frame speed-up step
SOFT_DROP_MIN_FPR = 1  # floor: one row per frame


def frames_per_row(level: int) -> float:
    """Falling speed for a level, in frames per row.

    Levels past the end of the table use the last (fastest) entry; a
    negative level uses level 0. The return value is a float because the
    cartridge has fractional intervals at levels 10, 12, 14, 15 and 16.
    """
    if level < 0:
        return FALL_SPEEDS[0]
    if level < len(FALL_SPEEDS):
        return FALL_SPEEDS[level]
    return FALL_SPEEDS[-1]


def soft_drop_fpr(normal_fpr: float, frames_held: int) -> float:
    """Effective frames per row while the Down key has been held.

    Starts at SOFT_DROP_START_FPR, loses one frame per row every
    SOFT_DROP_ACCEL_EVERY held frames, floors at SOFT_DROP_MIN_FPR, and
    is never slower than normal gravity.
    """
    fpr = float(SOFT_DROP_START_FPR)
    steps = frames_held // SOFT_DROP_ACCEL_EVERY
    if steps:
        fpr -= steps
    if fpr < SOFT_DROP_MIN_FPR:
        fpr = float(SOFT_DROP_MIN_FPR)
    return min(float(normal_fpr), fpr)