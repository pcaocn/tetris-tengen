"""Scoring, clear dissolve, and level progression tests (spec 4.5).

WHAT THIS FILE TESTS
====================
The scoring model from scoring.py, at both levels:

    1. PURE FUNCTIONS -- the award table (single 100 / double 400 /
       triple 900 / tetris 2500, owner-verified from screenshot_28.png),
       the 30-line block-bonus counter, and the level progression rule.
    2. LIVE GAME -- an actual lock through `Game._lock()`: score and
       lines update IMMEDIATELY while the cleared rows are still
       dissolving on screen, the protocol reports the clearing rows in
       VISIBLE coordinates, the block bonus lands on the exact
       30-line boundary, and the cheat commands (set_level, set_music)
       validate their inputs.

WHY THE TIMING ASSERTIONS MATTER
--------------------------------
Several tests check that the score changes BEFORE the dissolve finishes
(`game.update()` has not run yet). That is a real game-feel decision:
the player must see the points land the instant the piece locks, not a
second later when the rows vanish. If these assertions ever fail, the
award has been moved into the wrong phase of the clear animation.
"""

from tetris_core.game import (
    CLEAR_ANIM_FRAMES,
    Game,
    Status,
    locked_color_index,
)
from tetris_core.scoring import (
    BONUS_BLOCK_LINES,
    BLOCK_BONUS_POINTS,
    LEVEL_LINES,
    block_bonuses,
    level_for_lines,
    points_for_clear,
)
from tetris_core.board import HIDDEN_ROWS

from helpers import FixedRNG
from tetris_core.pieces import Piece
from tetris_core.protocol import Core


def test_points_for_clear_award_values():
    """The per-clear award values, pinned exactly (owner-verified).

    Owner-verified 2026-10-24 from the award table in
    png/screenshot_28.png: single 100, double 400, triple 900,
    tetris 2500.

    These four numbers are the game's economy: the super-linear ratio
    (a tetris pays 25x a single) is what makes the highscore autopilot
    hunt tetrises, and `points_for_clear(cleared) / 100` is fed
    straight into its weights. The 0-row case returns 0 so callers can
    pass a count straight through.
    """
    # Owner-verified 2026-10-24 from the award table in
    # png/screenshot_28.png: single 100, double 400, triple 900,
    # tetris 2500.
    assert points_for_clear(1) == 100
    assert points_for_clear(2) == 400
    assert points_for_clear(3) == 900
    assert points_for_clear(4) == 2500
    assert points_for_clear(0) == 0


def test_block_bonuses_counts_completed_blocks():
    """How many 30-line blocks a clear crossed, including zero and many.

    Each line is a boundary case of the integer-division rule:
      - exactly reaching a boundary (0 -> 30) completes one block;
      - stopping one line short (0 -> 29) completes none;
      - crossing from just before a boundary (29 -> 31) completes one;
      - a huge clear can complete several at once (0 -> 90 = 3 blocks);
      - the leftover lines of an unfinished block pay nothing
        (25 -> 95 crosses the 30/60/90 boundaries = 3 bonuses, with 5
        lines left over).
    The autopilot's block bonus and the level rule both sit on this
    helper, so an off-by-one here would corrupt two systems at once.
    """
    assert block_bonuses(0, BONUS_BLOCK_LINES) == 1
    assert block_bonuses(0, BONUS_BLOCK_LINES - 1) == 0
    assert block_bonuses(BONUS_BLOCK_LINES - 1, BONUS_BLOCK_LINES + 1) == 1
    assert block_bonuses(0, 3 * BONUS_BLOCK_LINES) == 3
    assert block_bonuses(25, 95) == 3  # 95//30 = 3 blocks completed in total


def test_level_for_lines_placeholder_rule():
    """One level per completed 30-line block (PLACEHOLDER rule).

    Level progression is computed from the START level plus total lines
    -- not from the current level -- so the last line proves a cheat
    jump to level 2 plus three blocks of lines lands on level 5: the
    whole curve shifts, it does not double-count. This is the
    placeholder structure (spec 4.5 VERIFY); the Nintendo every-10
    rule must NOT creep in, which is exactly what the 29-line case
    guards.
    """
    assert level_for_lines(0, 0) == 0
    assert level_for_lines(0, LEVEL_LINES) == 1
    assert level_for_lines(0, LEVEL_LINES - 1) == 0
    assert level_for_lines(2, 3 * LEVEL_LINES) == 5


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    """A Game on an isolated highscore file with a scripted piece stream.

    The (I, O) default is the scoring recipe: the I completes a
    prepared bottom row, the O is the next piece the test expects to
    take over after the clear.
    """
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def test_single_line_clear_scores_and_counts(tmp_path):
    """A single clear must score, count, dissolve, then hand over.

    Step 1: fill the bottom row EXCEPT columns 4..7, where the
       horizontal I (spawning with its box at column 5, cells 5..8)
       will drop in.
    Step 2: teleport the I to row 22 and call `_lock()` directly --
       the scoring event happens at lock time, so the test bypasses
       the fall.
    Step 3: assert the immediate effects, BEFORE any update() has run:
       lines == 1, score == 100, and the row is still ON the board
       (the dissolve has not removed it yet), with no piece active.
    Step 4: advance CLEAR_ANIM_FRAMES (24 frames, about 0.4 s at
       60 Hz) -- now the row is truly gone and the next piece (the O
       from the FixedRNG script) has spawned.

    The two-phase structure is the point: scoring is instant, board
    cleanup takes a quarter of a second, and a new piece waits for it.
    """
    game = make_game(tmp_path)
    # Fill the bottom row except where the I piece will land (columns 4..7).
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()
    # Score, lines, and the dissolve start immediately; the rows stay
    # visible and no new piece spawns until the dissolve finishes.
    assert game.lines == 1
    assert game.score == points_for_clear(1)
    assert not game.board.is_row_empty(22)  # still dissolving
    assert game.piece_kind is None
    assert game.status is Status.PLAYING
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.board.is_row_empty(22)  # cleared and shifted
    assert game.piece_kind is Piece.O  # next piece took over


def test_clearing_state_event_reports_rows_and_frame(tmp_path):
    """The protocol must translate the clear into VISIBLE coordinates.

    Step 1: prepare and lock a single-row clear (same recipe as the
       previous test) through a Core, the protocol layer.
    Step 2: the state event's `clearing` must name board row 22 as
       visible row 19 (22 - HIDDEN_ROWS = 19 -- the extended-to-
       visible shift the UI depends on) with frame 0.
    Step 3: one update later the frame counter reads 1; after the full
       24-frame dissolve, `clearing` is None and the next piece is
       live.

    The UI draws the flicker from this field alone; if the rows came
    through in extended coordinates the flicker would appear three
    rows too high (or be clipped away entirely).
    """
    core = Core(
        highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O])
    )
    game = core.game
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()
    state = core.state_event()
    # Board row 22 is visible row 22 - HIDDEN_ROWS = 19.
    assert state["clearing"] == {"rows": [19], "frame": 0}
    game.update()
    assert core.state_event()["clearing"]["frame"] == 1
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert core.state_event()["clearing"] is None
    assert game.piece_kind is Piece.O


def test_bonus_block_awarded_at_30_line_boundary(tmp_path):
    """Clearing the line that completes a 30-block pays the 300 bonus.

    Step 1: set the game to 29 lines (one short of the block) and
       level 0.
    Step 2: lock the prepared I to clear exactly one row.
    Step 3: the counters move in one frame, before the dissolve: lines
       29 -> 30 (the block completes), score = 100 (the single) + 300
       (the block bonus), level 0 -> 1.

    This is the payout structure of the whole game in miniature: the
    clear award and the block bonus are separate line items, and both
    are granted at lock time. It also drives the end-of-stage
    celebration -- `game.py` notices the level change and freezes for
    the 06/09 music.
    """
    game = make_game(tmp_path)
    game.lines = BONUS_BLOCK_LINES - 1
    game.level = 0
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()
    # One line cleared: crosses the 30-line boundary exactly once. Score
    # and level update immediately, before the dissolve finishes.
    assert game.lines == BONUS_BLOCK_LINES
    assert game.score == points_for_clear(1) + BLOCK_BONUS_POINTS
    assert game.level == 1  # placeholder rule: one level per 30-line block


def test_color_index_changes_with_level():
    """The locked-piece color cycles with a period of 10 levels.

    Owner decision 2026-10-24 (spec 6.2): the locked color cycles every
    10 levels — level 0 grayish white ... 8 purple, 9 green again —
    then repeats (10 back to 0, 11 = 1, ...).

    The mapping is `level % 10` into a 10-entry table, and the
    assertions walk one full period to pin both ends of the wrap: level
    9 is still index 9, level 10 wraps back to 0. The UI indexes its
    LOCKED_COLORS table with this value, so a wrong wrap would repaint
    every locked cell of every high level.
    """
    # Owner decision 2026-10-24 (spec 6.2): the locked color cycles every
    # 10 levels — level 0 grayish white ... 8 purple, 9 green again —
    # then repeats (10 back to 0, 11 = 1, ...).
    from tetris_core.game import LOCKED_COLOR_INDICES, locked_color_index

    assert len(LOCKED_COLOR_INDICES) == 10
    assert locked_color_index(0) == 0
    assert locked_color_index(6) == 6
    assert locked_color_index(8) == 8
    assert locked_color_index(9) == 9
    assert locked_color_index(10) == 0
    assert locked_color_index(11) == 1


def test_cheat_set_level_jumps_level(tmp_path):
    """The set_level cheat jumps level, color, AND the progression base.

    Cheat (owner request 2026-10-25): jump to a level mid-game; gravity
    and the locked color change immediately and progression continues
    from the new level.

    Three rules in one test:
      - the jump works (level 8, and `_start_level` moves with it so
        the next 30-line block builds on the new base rather than
        snapping back);
      - it clamps to the cheat range 0..9 (asking for 12 grants 9);
      - it is refused once the game is over (False, state unchanged).
    """
    # Cheat (owner request 2026-10-25): jump to a level mid-game; gravity
    # and the locked color change immediately and progression continues
    # from the new level.
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O]))
    game = core.game
    assert game.level == 0
    assert game.set_level(8) is True
    assert game.level == 8
    assert game._start_level == 8
    assert locked_color_index(game.level) == 8
    # Clamped to the cheat range 0..9.
    assert game.set_level(12) is True
    assert game.level == 9
    # Not while the game is over.
    game.status = Status.GAME_OVER
    assert game.set_level(3) is False


def test_cheat_set_level_command(tmp_path):
    """The protocol command wraps the cheat with input validation.

    Step 1: a well-formed command gets TWO events: the response
       (ok=True) and a state echo carrying the new level and the color
       index the UI should switch to.
    Step 2: three rejections -- out of range (10 > 9), missing
       parameter, and a non-integer ("eight") -- each answered with
       ok=False instead of a crash.

    The UI's level-jump key sends this raw JSON; every one of these
    malformed variants is something a user can produce with a stuck
    key or a modified frontend.
    """
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O]))
    replies = core.handle_line('{"cmd": "set_level", "level": 8}')
    assert replies[0]["ok"] is True
    assert replies[1]["level"] == 8
    assert replies[1]["color_index"] == 8
    # Out-of-range, missing, and non-integer levels are rejected.
    assert core.handle_line('{"cmd": "set_level", "level": 10}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level", "level": "eight"}')[0]["ok"] is False
