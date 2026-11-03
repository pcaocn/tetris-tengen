"""Shared test helpers.

WHAT THIS FILE HOLDS
====================
One class: `FixedRNG`, the deterministic stand-in for `PieceRNG` that
every game-level test injects. It is the reason tests like "the I lands
at columns 5..8" are even writable: a test that needs a specific piece
next does not hunt for a lucky seed -- it spells the sequence out, e.g.
`FixedRNG([Piece.I, Piece.O])` means "an I, then an O, repeating
forever".

WHY NOT USE THE REAL PieceRNG WITH A SEED?
------------------------------------------
A seeded PieceRNG is deterministic, but the sequence it produces is
opaque: to know the third piece you would have to run it. A FixedRNG
makes the script the test is playing READABLE -- the piece list in the
constructor *is* the scenario. The real PieceRNG's own properties
(seed reproducibility, coverage, no 7-bag) are pinned separately in
test_rng.py.

THE CONTRACT
------------
`Game` never type-checks its rng; it only calls `next_piece()` (on every
spawn) and `hole_column()` (for title-screen handicap rows). Any object
with those two methods slots in -- this one cycles its lists forever, so
a test that places more pieces than it listed still sees a predictable
piece instead of an IndexError.
"""

from tetris_core.pieces import Piece


class FixedRNG:
    """Deterministic stand-in for PieceRNG (spec 4.6: seedable generator).

    Two cycling queues, one class:

    - `pieces`: the piece sequence, repeated from the start once
      exhausted. Tests that need exactly one piece of a kind list each
      kind once; tests that loop until "the next piece spawned" list
      just one kind so every spawn is the same piece.
    - `holes`: the gap column for each handicap row (default 0, 3, 6 --
      spread across the 10-wide row so the gaps are easy to tell apart
      in assertions, e.g. `board[-1].index(0) in (0, 3, 6)`).

    Both cycle independently of each other.
    """

    def __init__(self, pieces, holes=(0, 3, 6)) -> None:
        # Copy the caller's lists so the stand-in owns its state: a test
        # passing a list it also reads must not see it consumed.
        self._pieces = list(pieces)
        self._i = 0
        self._holes = list(holes)
        self._h = 0

    def next_piece(self) -> Piece:
        # `% len(...)` is the cycle: after the last listed piece the
        # first comes round again. Deterministic by construction -- no
        # randomness anywhere -- so the same list always gives the same
        # game, on every machine and every run.
        piece = self._pieces[self._i % len(self._pieces)]
        self._i += 1
        return piece

    def hole_column(self) -> int:
        # Same cycling pattern as next_piece, for the handicap rows:
        # each call hands out the next gap column and wraps around.
        col = self._holes[self._h % len(self._holes)]
        self._h += 1
        return col
