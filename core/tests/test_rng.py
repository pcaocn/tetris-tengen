"""Piece generator tests (spec 4.6, section 9)."""

from tetris_core.pieces import Piece
from tetris_core.rng import PieceRNG


def test_same_seed_same_sequence():
    a = PieceRNG(seed=42)
    b = PieceRNG(seed=42)
    seq_a = [a.next_piece() for _ in range(100)]
    seq_b = [b.next_piece() for _ in range(100)]
    assert seq_a == seq_b


def test_different_seeds_differ():
    a = [PieceRNG(seed=1).next_piece() for _ in range(50)]
    b = [PieceRNG(seed=2).next_piece() for _ in range(50)]
    assert a != b


def test_all_pieces_appear_over_long_sample():
    rng = PieceRNG(seed=7)
    seen = {rng.next_piece() for _ in range(10_000)}
    assert seen == set(Piece)


def test_values_are_valid_pieces():
    rng = PieceRNG(seed=3)
    for _ in range(1000):
        assert isinstance(rng.next_piece(), Piece)


def test_repeats_are_allowed():
    # Tengen placeholder: uniform with repeats, no reroll, no bag (spec 4.6).
    rng = PieceRNG(seed=11)
    seq = [rng.next_piece() for _ in range(200)]
    assert any(seq[i] == seq[i + 1] for i in range(len(seq) - 1))
