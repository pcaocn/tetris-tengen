"""Piece generator tests (spec 4.6, section 9).

WHAT THIS FILE TESTS
====================
The RNG is the one component that is deliberately unpredictable in real
play, so these tests pin down the properties that must hold IN SPITE of
that unpredictability:

    1. REPRODUCIBILITY -- the same seed replays the identical piece
       sequence. This is the property the whole project leans on: the
       autopilot benchmarks (`sweep_autopilot.py`) compare strategies on
       shared seeds, which is only a fair comparison if a seed fully
       determines the pieces a game sees.
    2. SEED DIVERGENCE -- different seeds give different sequences, so
       reproducibility does not collapse into "every game is the same".
    3. COVERAGE -- over a long sample all seven pieces appear; no piece
       can silently vanish from the game.
    4. TYPE SAFETY -- every draw is a genuine `Piece` enum value; the
       `randint(1, 7)` -> `Piece` cast inside never leaks a raw int.
    5. REPEATS ALLOWED -- the Tengen PLACEHOLDER randomizer is a uniform
       draw with repeats (no 7-bag, no Nintendo-style reroll of
       consecutive duplicates). Locking that in means a future switch to
       7-bag shows up as a deliberate, reviewed test change rather than
       an accident.

WHY THE SAMPLE SIZES (100 / 50 / 10_000 / 1000 / 200)?
------------------------------------------------------
They are statistical thresholds, not exact requirements. A uniform
7-piece generator misses some piece in 10,000 draws with probability
(6/7)^10000 -- effectively zero -- and produces no adjacent repeat in
199 chances with probability (6/7)^199, about one in ten trillion. So
each test fails only if the generator is genuinely broken, never by
bad luck; the round numbers keep the intent readable.
"""

from tetris_core.pieces import Piece
from tetris_core.rng import PieceRNG


def test_same_seed_same_sequence():
    """The same seed must replay the identical sequence (spec 4.6).

    Two independent generators constructed with seed 42 must produce
    matching 100-piece sequences. This is the property that makes the
    autopilot benchmarks comparable: a strategy variant is judged on
    exactly the same pieces as its rival. If this failed, every sweep
    in the repo would be comparing games that differ by luck.
    """
    a = PieceRNG(seed=42)
    b = PieceRNG(seed=42)
    seq_a = [a.next_piece() for _ in range(100)]
    seq_b = [b.next_piece() for _ in range(100)]
    assert seq_a == seq_b


def test_different_seeds_differ():
    """Different seeds must produce different sequences.

    The mirror image of the previous test: if seeds 1 and 2 gave the
    same pieces, "seeding" would be a no-op and the sweeps would all
    play one fixed game. 50 draws is far more than needed to tell two
    healthy generators apart by chance.
    """
    a = [PieceRNG(seed=1).next_piece() for _ in range(50)]
    b = [PieceRNG(seed=2).next_piece() for _ in range(50)]
    assert a != b


def test_all_pieces_appear_over_long_sample():
    """Every one of the seven pieces must appear in a long sample.

    A uniform generator over Piece eventually produces all seven; if
    the set of 10,000 draws ever misses one, the randint bounds inside
    PieceRNG have drifted out of step with the Piece enum (a piece was
    added, renamed, or renumbered). The player would simply never see
    the missing piece -- a bug that is very hard to notice by playing.
    """
    rng = PieceRNG(seed=7)
    seen = {rng.next_piece() for _ in range(10_000)}
    assert seen == set(Piece)


def test_values_are_valid_pieces():
    """Every draw must be a real Piece, never a raw int or None.

    PieceRNG draws `randint(1, 7)` and casts straight to `Piece`; this
    test walks 1000 draws to make sure that cast is total. A single bad
    value would poison everything downstream -- a grid cell, a stats
    key, a protocol event -- so it is cheap to assert here.
    """
    rng = PieceRNG(seed=3)
    for _ in range(1000):
        assert isinstance(rng.next_piece(), Piece)


def test_repeats_are_allowed():
    # Tengen placeholder: uniform with repeats, no reroll, no bag (spec 4.6).
    """Consecutive repeats must be possible (the placeholder randomizer).

    The current rule is a plain uniform draw: no 7-bag shuffling and no
    reroll of a piece equal to the previous one. The assertion looks
    for AT LEAST ONE adjacent repeat in 200 draws -- with a healthy
    uniform generator that is a near-certainty ((6/7)^199 chance of
    none), so the test only fails if the generator actively suppresses
    repeats. That would be a silent rule change: Tengen play FEELS
    different when the same piece can stack up three times in a row.
    """
    rng = PieceRNG(seed=11)
    seq = [rng.next_piece() for _ in range(200)]
    assert any(seq[i] == seq[i + 1] for i in range(len(seq) - 1))
