"""Per-piece spawn counters shown in the stats panel (spec 4.9).

A tiny module: it counts how many times each piece has spawned during the
current game. The UI renders those counts as vertical bars (spec 4.9),
but the scaling, the bar height and the tick marks all live in the UI --
this module only produces the raw numbers.
"""

from __future__ import annotations


from .pieces import Piece

# Panel display order measured from the owner's captures: the in-game stats
# panel lists the pieces I, T, O, J, L, S, Z (see png/screenshot_*.png).
#
# This is a DISPLAY order, not the enum order (Piece is I, O, T, S, Z, J,
# L). Keeping the two separate means the enum values can stay stable for
# the board grid and the protocol while the panel still shows the pieces
# in the order the original game used.
KIND_ORDER = ("I", "T", "O", "J", "L", "S", "Z")


class PieceStats:
    """Spawn counters for the seven pieces, reset for each new game."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Zero every counter (called on each new game)."""
        self._counts: dict[Piece, int] = {piece: 0 for piece in Piece}

    def increment(self, piece: Piece) -> None:
        """Count one spawn of `piece`."""
        self._counts[piece] += 1

    def as_dict(self) -> dict[str, int]:
        """The counts keyed by piece NAME, in the panel's display order.

        The protocol sends this straight to the UI, so the keys are the
        names ("I", "T", ...) rather than the enum values, and the order
        matches KIND_ORDER -- the UI can iterate the dict directly.
        """
        return {name: self._counts[Piece[name]] for name in KIND_ORDER}
