"""Piece generator (spec 4.6).

VERIFY (spec 4.6): the Tengen randomizer must be looked up; do not assume
the Nintendo reroll rule and do not use 7-bag. The implementation below is
a PLACEHOLDER: a uniform choice among the seven pieces with repeats
allowed, seedable so tests are deterministic (open item).

WHY SEEDABILITY IS THE IMPORTANT PART HERE
------------------------------------------
Every piece is drawn from `random.Random(seed)`, an instance-local
generator, NOT the module-level `random` global. That single decision
makes the whole project testable and measurable:

  - A test can construct `PieceRNG(1234)` and assert an exact piece
    sequence (tests/test_rng.py).
  - The autopilot benchmarks can replay the SAME game on every machine:
    `Game(rng=PieceRNG(seed))` with a fixed seed gives the same pieces,
    the same board, and therefore the same score.
  - The sweep in `sweep_autopilot.py` runs dozens of strategy variants on
    one shared list of seeds, so the variants differ ONLY by their
    weights -- never by luck (spec 4.11).

`hole_column` exists for the same reason: the title-screen handicap
places one random gap per garbage row, and that gap must also be
reproducible from the seed.
"""

from __future__ import annotations


import random

from .pieces import Piece


class PieceRNG:
    """A seedable source of pieces and handicap holes."""

    def __init__(self, seed: int | None = None) -> None:
        # A private Random instance: seeding it does not disturb the
        # global random state used elsewhere in the process. Passing
        # None gives a non-deterministic generator (used by the real game,
        # where each launch should feel different).
        self._rng = random.Random(seed)

    def next_piece(self) -> Piece:
        """The next piece.

        `randint(1, 7)` is inclusive on both ends, and the values 1..7
        are exactly the `Piece` enum values -- so the int is cast
        straight to `Piece`. This is a uniform draw with repeats
        allowed (no 7-bag), which is the documented PLACEHOLDER
        behaviour; the real Tengen randomizer is still VERIFY (spec 4.6).
        """
        return Piece(self._rng.randint(1, 7))

    def hole_column(self) -> int:
        """Random column for a handicap row's gap (title-screen handicap).

        Columns are 0..9 (10 columns wide). The handicap fills every
        bottom row except one cell, so this picks the column that is
        left EMPTY in that row.
        """
        return self._rng.randint(0, 9)
