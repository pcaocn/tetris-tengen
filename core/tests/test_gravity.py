"""Gravity table and soft drop tests (spec 4.3, section 9).

WHAT THIS FILE TESTS
====================
Two layers of the fall-speed rules:

    1. THE TABLE (pure functions from gravity.py): `frames_per_row`
       returns the PLACEHOLDER fall speed for a level and clamps past
       both ends of the table; `soft_drop_fpr` returns the effective
       speed while Down is held, with its two guard rails (never faster
       than one row per frame, never slower than normal gravity).
    2. THE FRAME LOOP (through a live Game): gravity really moves the
       piece on the schedule the table promises, soft drop engages and
       disengages mid-fall, and the gravity counter restarts at zero
       with each new piece so every piece gets a full interval before
       its first row of fall.

WHY EVERYTHING IS COUNTED IN FRAMES
-----------------------------------
The game loop is fixed at 60 Hz (spec 2.1), so "50 frames per row" IS
a fall speed: about 1.2 rows per second at level 0. Working in frames
-- integers, no timers -- makes these tests exact rather than
statistical: each one calls `update()` a precise number of times and
then reads the piece's row back. Any timing flake would mean the loop
itself changed, which is exactly what these tests should catch.

A NOTE ON READING PRIVATE ATTRIBUTES
------------------------------------
The tests reach into `game._piece_y` and `game._gravity_counter`
deliberately: gravity has no observable effect other than the piece's
position, and the counter is invisible in the protocol. They are
white-box tests on purpose.
"""

from tetris_core.game import SPAWN_Y, Game
from tetris_core.gravity import (
    SOFT_DROP_MIN_FPR,
    SOFT_DROP_START_FPR,
    frames_per_row,
    soft_drop_fpr,
)
from tetris_core.pieces import Piece

from helpers import FixedRNG


def test_frames_per_row_placeholder_table():
    """The fall-speed table, sampled at its ends and its steep middle.

    These assertions record the PLACEHOLDER table (open item, spec 4.3):
    level 0 falls a row every 50 frames (about 1.2 rows/s), level 5
    every 19, level 9 every 6 (10 rows/s), level 13 every 2. The last
    two lines are the clamps: level 99 stays at the fastest entry (2)
    and level -1 is treated as level 0 (50), so an out-of-range level
    from a cheat or a bug can never index past the table and crash.
    """
    # These assertions record the PLACEHOLDER table (open item, spec 4.3).
    assert frames_per_row(0) == 50
    assert frames_per_row(5) == 19
    assert frames_per_row(9) == 6
    assert frames_per_row(13) == 2
    assert frames_per_row(99) == 2  # clamps to the last entry
    assert frames_per_row(-1) == 50  # clamps to level 0


def test_soft_drop_curve_placeholder():
    """The soft-drop acceleration curve and its two guard rails.

    Records the PLACEHOLDER acceleration curve (open item, spec 4.3):
    starts at SOFT_DROP_START_FPR, loses one frame per row every
    SOFT_DROP_ACCEL_EVERY held frames, floors at SOFT_DROP_MIN_FPR, and
    is never slower than normal gravity.

    Reading the assertions as a timeline of one long Down press at
    level 0:
      - 0..3 held frames -> 6 fpr: nothing happens at first (the
        "gradual" part; a Nintendo-style 2x soft drop would jump).
      - 4 held frames -> 5, 8 -> 4: one step of acceleration per 4
        held frames, i.e. the curve is STAIRCASED, not smooth.
      - 20+ held frames -> 1 fpr: the floor, one row per frame.
    The last two lines pin the guard rails: at level 2 (normal fpr 2)
    pressing Down with 0 held frames must NOT slow the piece (6 would
    be slower than the level's 2, so normal gravity wins), yet a long
    press still accelerates to 1 -- faster than the level. Holding
    Down at high level therefore always helps, never hurts.
    """
    # Records the PLACEHOLDER acceleration curve (open item, spec 4.3):
    # starts at SOFT_DROP_START_FPR, loses one frame per row every
    # SOFT_DROP_ACCEL_EVERY held frames, floors at SOFT_DROP_MIN_FPR, and is
    # never slower than normal gravity.
    assert soft_drop_fpr(50, 0) == SOFT_DROP_START_FPR
    assert soft_drop_fpr(50, 3) == 6
    assert soft_drop_fpr(50, 4) == 5
    assert soft_drop_fpr(50, 8) == 4
    assert soft_drop_fpr(50, 20) == 1
    assert soft_drop_fpr(50, 100) == SOFT_DROP_MIN_FPR
    assert soft_drop_fpr(2, 0) == 2  # never slower than normal gravity
    assert soft_drop_fpr(2, 100) == 1  # still accelerates past level speed


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    """A Game on an isolated highscore file with a scripted piece stream.

    Every test in this file uses the same recipe: the highscore path is
    redirected into pytest's tmp_path (so the real Application Support
    file is never touched) and the piece sequence is dictated by a
    FixedRNG. The default (I, O) is convenient: the I falls straight
    down without rotating and the O follows it.
    """
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def test_piece_falls_one_row_per_interval(tmp_path):
    """Gravity must move the piece exactly one row per interval.

    Step 1: build a game at level 0 -- the placeholder table says 50
       frames per row.
    Step 2: advance 49 frames -- one frame short of the interval -- and
       the piece must still be at its spawn row.
    Step 3: the 50th update crosses the threshold and the piece drops
       exactly one row.

    This pins the counting model: gravity is a per-interval step, not a
    continuous drift. If the piece had moved early or by two rows, the
    whole autopilot benchmarking would be timing a different game.
    """
    game = make_game(tmp_path)
    # Placeholder level 0 speed: 50 frames per row.
    for _ in range(49):
        game.update()
    assert game._piece_y == SPAWN_Y
    game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_soft_drop_starts_gradually(tmp_path):
    """Pressing Down must NOT jump the piece to instant speed.

    Step 1: turn soft drop on (the Down key goes down).
    Step 2: advance exactly 6 frames -- the placeholder START speed is
       6 frames per row, so in 6 frames the piece falls exactly once.
    Step 3: the piece has moved exactly one row, not six.

    If soft drop were a fixed "1 row per frame" (hard-drop-like), the
    piece would be five rows lower here. The Tengen behaviour under
    test accelerates gradually instead (spec 4.3), which is what makes
    short Down taps usable for fine placement.
    """
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    # Placeholder start speed 6 fpr: exactly one row in the first 6 frames,
    # i.e. soft drop does NOT jump to instant speed on press (spec 4.3).
    for _ in range(6):
        game.update()
    assert game._piece_y == SPAWN_Y + 1


def test_soft_drop_is_faster_than_normal(tmp_path):
    """A soft-dropping piece must outrun an identical normal one.

    Step 1: build TWO identical games (same FixedRNG stream, same
       start); turn soft drop on in one only.
    Step 2: advance both 30 frames in lockstep.
    Step 3: the soft-dropping piece must be at least 5 rows lower.

    The comparison (not an absolute row count) is deliberate: the
    accelerated curve's exact rows depend on the staircase timing, but
    the contract is simply "holding Down is much faster". 30 frames is
    long enough for the acceleration steps to bite (6 fpr down toward
    the floor), which is why the gap is required to be large.
    """
    soft = make_game(tmp_path)
    normal = make_game(tmp_path)
    soft.handle_input("soft_drop_on")
    for _ in range(30):
        soft.update()
        normal.update()
    assert soft._piece_y >= normal._piece_y + 5


def test_soft_drop_off_restores_normal_speed(tmp_path):
    """Releasing Down must hand the piece back to normal gravity.

    Step 1: hold soft drop for 10 frames (the piece falls a few rows).
    Step 2: release it and remember the row.
    Step 3: advance 30 more frames -- fewer than the level-0 interval
       of 50, so normal gravity cannot move the piece again.

    The row must be unchanged after step 3. If the release failed to
    switch back (e.g. the acceleration stuck), the piece would keep
    falling fast and the row would drift. Note the 30-frame count was
    chosen because it is safely below the 50-frame normal interval --
    the only speed this test can distinguish at level 0.
    """
    game = make_game(tmp_path)
    game.handle_input("soft_drop_on")
    for _ in range(10):
        game.update()
    game.handle_input("soft_drop_off")
    y_after_soft = game._piece_y
    for _ in range(30):
        game.update()
    # 30 frames at the placeholder level 0 speed (50 fpr) = no further rows.
    assert game._piece_y == y_after_soft


def test_gravity_counter_resets_on_spawn(tmp_path):
    """A fresh piece must start its fall schedule from zero.

    Step 1: advance 20 frames -- the counter sits at 20 % 50 = 20, no
       row fallen yet (well short of the 50-frame interval).
    Step 2: force a new piece via `_spawn_next()`.
    Step 3: the counter must be back to 0 and the piece at SPAWN_Y.

    Without the reset, a piece spawning halfway through an interval
    would fall too soon -- the first row would arrive in fewer frames
    than the table promises, and every fall time measured in the
    benchmarks would be skewed by the spawn phase.
    """
    game = make_game(tmp_path)
    for _ in range(20):
        game.update()
    assert game._gravity_counter == 20 % 50
    game._spawn_next()
    assert game._gravity_counter == 0
    assert game._piece_y == SPAWN_Y
