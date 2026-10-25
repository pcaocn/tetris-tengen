"""Piece generator (spec 4.6).

VERIFY (spec 4.6): the Tengen randomizer must be looked up; do not assume
the Nintendo reroll rule and do not use 7-bag. The implementation below is
a PLACEHOLDER: a uniform choice among the seven pieces with repeats
allowed, seedable so tests are deterministic (open item).
"""

from __future__ import annotations


import random

from .pieces import Piece


class PieceRNG:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def next_piece(self) -> Piece:
        return Piece(self._rng.randint(1, 7))

    def hole_column(self) -> int:
        """Random column for a handicap row's gap (title-screen handicap)."""
        return self._rng.randint(0, 9)
