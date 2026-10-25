"""Per-piece spawn counters shown in the stats panel (spec 4.9)."""

from __future__ import annotations


from .pieces import Piece

# Panel display order measured from the owner's captures: the in-game stats
# panel lists the pieces I, T, O, J, L, S, Z (see png/screenshot_*.png).
KIND_ORDER = ("I", "T", "O", "J", "L", "S", "Z")


class PieceStats:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._counts: dict[Piece, int] = {piece: 0 for piece in Piece}

    def increment(self, piece: Piece) -> None:
        self._counts[piece] += 1

    def as_dict(self) -> dict[str, int]:
        return {name: self._counts[Piece[name]] for name in KIND_ORDER}
