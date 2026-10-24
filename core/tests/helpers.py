"""Shared test helpers."""

from tetris_core.pieces import Piece


class FixedRNG:
    """Deterministic stand-in for PieceRNG (spec 4.6: seedable generator)."""

    def __init__(self, pieces):
        self._pieces = list(pieces)
        self._i = 0

    def next_piece(self) -> Piece:
        piece = self._pieces[self._i % len(self._pieces)]
        self._i += 1
        return piece
