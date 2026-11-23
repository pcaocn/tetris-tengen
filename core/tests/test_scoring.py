"""Scoring, level curve, and gravity tests (spec 4.3, 4.5, section 9).

WHAT THIS FILE TESTS
====================
Three layers:

1. THE RULES (pure functions from gravity.py and scoring.py): the
   fractional fall table, the soft-drop acceleration curve, the clear
   award values, the placement formula and its 999 cap, and the Tengen
   level curve with stage lengths 30/30/30/30/30 then 50 forever.

2. SCORING INTEGRATION: the clear award is accumulated into a pending
   stage award and paid once at the stage boundary. Placement points are
   awarded exactly once per lock, including locks that clear nothing.
   The stage boundary is independent of the displayed level, so 800 and
   850 still pay after the level cap at 17.

3. THE CHEAT JUMP (section 4.5): set_level moves the next stage boundary
   with the new level, preserving progress inside the current stage. The
   next single after a jump must not re-count the whole run's line total.
"""

from __future__ import annotations

import pytest

from tetris_core.game import (
    CLEAR_ANIM_FRAMES,
    Game,
    Status,
    lock_delay_frames,
)
from tetris_core.gravity import frames_per_row, soft_drop_fpr
from tetris_core.pieces import Piece
from tetris_core.scoring import (
    INITIAL_STAGE_LINES,
    LATE_STAGE_LINES,
    MAX_LEVEL,
    PLACEMENT_POINTS_CAP,
    level_for_lines,
    placement_points,
    points_for_clear,
    stage_lines_for_level,
)

from helpers import FixedRNG


def test_points_for_clear_award_values():
    """The four clear values, in points, and nothing for zero.

    The rule is value-based (spec 4.5): four rows at once is worth 25
    single rows, not four. That super-linear table is what makes the
    "highscore" autopilot want to hunt tetrises, and
    `points_for_clear(cleared) / 100` is fed to the AI as that value.
    """
    assert points_for_clear(1) == 100
    assert points_for_clear(2) == 400
    assert points_for_clear(3) == 900
    assert points_for_clear(4) == 2500
    assert points_for_clear(0) == 0
    assert points_for_clear(7) == 2500  # out-of-range input clamps to a tetris


def test_level_curve_matches_tengen_stage_lengths():
    """The level curve uses 30-line stages through level 5, then 50.

    Normal game starting at 0:
      149 -> level 4, still in stage
      150 -> level 5, stage ends
      180/199 -> level 5, still in stage
      200 -> level 6, stage ends
      749 -> level 16, 750 -> level 17 (cap), 800/850 -> still 17.
    """
    assert level_for_lines(0, 0) == 0
    assert level_for_lines(0, INITIAL_STAGE_LINES - 1) == 0
    assert level_for_lines(0, 149) == 4
    assert level_for_lines(0, 150) == 5
    assert level_for_lines(0, 180) == 5
    assert level_for_lines(0, 199) == 5
    assert level_for_lines(0, 200) == 6
    assert level_for_lines(0, 749) == 16
    assert level_for_lines(0, 750) == MAX_LEVEL
    assert level_for_lines(0, 800) == MAX_LEVEL
    assert level_for_lines(0, 850) == MAX_LEVEL

    # A nonzero start and a mid-game jump only count lines since the
    # anchor. Level 5 stages are 50 lines, so 50 lines later is level 6.
    assert level_for_lines(5, 0) == 5
    assert level_for_lines(5, 49) == 5
    assert level_for_lines(5, 50) == 6
    assert level_for_lines(5, 30, 30) == 5
    assert level_for_lines(5, 31, 30) == 5
    assert level_for_lines(5, 80, 30) == 6

    assert stage_lines_for_level(0) == INITIAL_STAGE_LINES
    assert stage_lines_for_level(4) == INITIAL_STAGE_LINES
    assert stage_lines_for_level(5) == LATE_STAGE_LINES
    assert stage_lines_for_level(MAX_LEVEL) == LATE_STAGE_LINES


def test_placement_points_formula_and_cap():
    """Placement points are min(d*r*(r+h), 999)."""
    assert placement_points(0, False, 0) == 1
    assert placement_points(0, True, 0) == 2
    assert placement_points(1, False, 0) == 4  # 1 * 2 * (2 + 0)
    assert placement_points(0, True, 2) == 6  # 2 * 1 * (1 + 2)
    assert placement_points(17, False, 100) == PLACEMENT_POINTS_CAP
    assert placement_points(17, True, 100) == PLACEMENT_POINTS_CAP


def test_lock_delay_cap_is_finite():
    """The grace is 10 frames, capped by the level's fall interval."""
    assert lock_delay_frames(0) == 10
    assert lock_delay_frames(7) == 9  # new level 7 gravity: 9 fpr
    assert lock_delay_frames(8) == 7  # new level 8 gravity: 7 fpr
    assert lock_delay_frames(10) == 5.5  # fractional gravity
    assert lock_delay_frames(13) == 4  # new level 13 gravity: 4 fpr


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    """A Game on an isolated highscore file with a scripted piece stream."""
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def _finish_clear(game) -> None:
    """Apply a pending dissolve immediately (test convenience)."""
    if game._clearing_rows is not None:
        game.board.clear_rows(game._clearing_rows)
        game._clearing_rows = None


def _lock_prepared_single(game) -> None:
    """Clear any prior dissolve, prepare the bottom row, and lock an I."""
    _finish_clear(game)
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_kind = Piece.I
    game._rot = 0
    game._piece_x = 4
    game._piece_y = 22
    game._lock()


def _lock_prepared_double(game) -> None:
    """Clear any prior dissolve, prepare two rows, and lock an O."""
    _finish_clear(game)
    for y in (21, 22):
        for x in (0, 1, 2, 3, 6, 7, 8, 9):
            game.board.lock_cells([(x, y)], 6)
    game._piece_kind = Piece.O
    game._rot = 0
    game._piece_x = 4
    game._piece_y = 21
    game._lock()


def _lock_prepared_triple(game) -> None:
    """Clear any prior dissolve, prepare three rows, and lock a vertical I.

    Rows 20-22 are complete except column 5; row 19 is left with column
    0 empty so the vertical I completes exactly three rows, not four.
    """
    _finish_clear(game)
    for y in (20, 21, 22):
        for x in range(10):
            if x != 5:
                game.board.lock_cells([(x, y)], 6)
    for x in range(1, 10):
        if x != 5:
            game.board.lock_cells([(x, 19)], 6)
    game._piece_kind = Piece.I
    game._rot = 1
    game._piece_x = 4
    game._piece_y = 19
    game._lock()


def test_single_line_clear_awards_are_pending_until_stage_end(tmp_path):
    """A clear updates lines immediately but banks its award.

    Step 1: fill the bottom row except where a horizontal I lands.
    Step 2: lock it. Lines become 1; the single's 100 points go into the
       pending stage award, not into `score` yet. Placement points (1 at
       level 0, height 0) are immediate.
    Step 3: the row is still on the board during the dissolve, and the
       next piece waits.
    """
    game = make_game(tmp_path)
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()

    assert game.lines == 1
    assert game.score == placement_points(0, False, 0)
    assert game._pending_stage_award == points_for_clear(1)
    assert not game.board.is_row_empty(22)
    assert game.piece_kind is None
    assert game.status is Status.PLAYING

    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.board.is_row_empty(22)
    assert game.piece_kind is Piece.O


def test_clearing_state_event_reports_rows_and_frame(tmp_path):
    """The protocol must translate the clear into VISIBLE coordinates."""
    from tetris_core.protocol import Core

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
    assert state["clearing"] == {"rows": [19], "frame": 0}
    game.update()
    assert core.state_event()["clearing"]["frame"] == 1
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert core.state_event()["clearing"] is None
    assert game.piece_kind is Piece.O


def test_stage_payout_accumulates_clear_awards(tmp_path):
    """20 singles + 5 doubles pay 4,000 at the 30-line stage end.

    Each clear banks its award. The 20th single is line 20; the five
    doubles take the stage to exactly 30. The stage payout is credited
    once, in addition to the 25 placement points (1 each at level 0).
    """
    game = make_game(tmp_path)
    assert game._next_stage_line == INITIAL_STAGE_LINES

    for i in range(20):
        _lock_prepared_single(game)
        assert game.lines == i + 1
        assert game._pending_stage_award == (i + 1) * 100

    for i in range(5):
        _lock_prepared_double(game)
        assert game.lines == 20 + 2 * (i + 1)

    assert game.lines == INITIAL_STAGE_LINES
    assert game.level == 1
    assert game._next_stage_line == INITIAL_STAGE_LINES + stage_lines_for_level(1)
    assert game._pending_stage_award == 0
    assert game.score == 25 + 4_000


def test_stage_overshoot_triple_pays_one_stage(tmp_path):
    """A triple from 149 to 152 completes exactly one stage.

    The triple is worth 900 in that stage's payout. The next boundary is
    200, not 180: the stage that just ended was the 30-line level-4
    stage, and level 5 uses 50-line stages.
    """
    game = make_game(tmp_path)
    game.lines = 149
    game.level = 4
    game._next_stage_line = 150

    _lock_prepared_triple(game)

    assert game.lines == 152
    assert game.level == 5
    assert game._next_stage_line == 200
    assert game._pending_stage_award == 0
    assert game.score == placement_points(4, False, 0) + points_for_clear(3)


def test_stage_payouts_continue_after_level_cap(tmp_path):
    """At the level cap, 800 and 850 are still real stage boundaries."""
    game = make_game(tmp_path)
    game.lines = 799
    game.level = MAX_LEVEL
    game._next_stage_line = 800

    _lock_prepared_single(game)

    assert game.lines == 800
    assert game.level == MAX_LEVEL
    assert game._next_stage_line == 850
    assert game._pending_stage_award == 0
    assert game.score == placement_points(MAX_LEVEL, False, 0) + points_for_clear(1)


def test_nonzero_start_uses_its_own_stage_length(tmp_path):
    """A game started at level 5 has a 50-line first stage."""
    game = make_game(tmp_path)
    game.new_game(level=5)
    assert game.level == 5
    assert game._next_stage_line == LATE_STAGE_LINES

    game.lines = LATE_STAGE_LINES - 1
    _lock_prepared_single(game)
    assert game.lines == LATE_STAGE_LINES
    assert game.level == 6
    assert game._next_stage_line == LATE_STAGE_LINES * 2
    assert game.score == placement_points(5, False, 0) + points_for_clear(1)


def test_placement_uses_lowest_cell(tmp_path):
    """Placement row height is the piece's lowest occupied cell.

    A vertical I resting with its bottom cell on row 21 has height 1
    (the bottom visible row is 0), so a normal level-0 placement earns
    2 points.
    """
    game = make_game(tmp_path)
    game._piece_kind = Piece.I
    game._rot = 1
    game._piece_x = 4
    game._piece_y = 18  # cells on rows 18..21; lowest is 21 -> h = 1
    game._lock()
    assert game.score == placement_points(0, False, 1)


def _run_until_first_contact(game, max_frames: int = 1000) -> None:
    """Run the real update loop until the piece first rests on something."""
    for _ in range(max_frames):
        if game._rest_frames > 0:
            return
        game.update()
    raise AssertionError("piece never made contact")


def _run_until_lock(game, max_frames: int = 50) -> None:
    """Run the real update loop through the lock-delay window."""
    for _ in range(max_frames):
        game.update()
        if game.lock_count > 0:
            return
    raise AssertionError("piece never locked")


@pytest.mark.parametrize(
    ("hold_at_contact", "action_during_lock", "expected"),
    [
        (True, "release", 2),
        (True, "keep", 2),
        (False, "press", 1),
        (False, "keep", 1),
    ],
)
def test_soft_drop_captured_at_first_contact(
    tmp_path, hold_at_contact, action_during_lock, expected
):
    """Placement points use the drop state at contact, not at lock.

    This exercises the real update loop and input actions. Down may be
    released during the lock delay; the piece still earns the soft-drop
    award if Down was held when it first touched down.
    """
    game = make_game(tmp_path, pieces=(Piece.O, Piece.T))
    if hold_at_contact:
        game.handle_input("soft_drop_on")

    _run_until_first_contact(game)
    assert game._landing_soft_drop is hold_at_contact

    if action_during_lock == "release":
        game.handle_input("soft_drop_off")
    elif action_during_lock == "press":
        game.handle_input("soft_drop_on")

    score_before_lock = game.score
    _run_until_lock(game)
    assert game.score == score_before_lock + expected
    # The next piece starts with a fresh landing state even if Down is
    # still physically held.
    assert game._landing_soft_drop is False


def test_soft_drop_capture_resets_after_sliding_off_ledge(tmp_path):
    """A ledge slide starts a new landing opportunity.

    Land on a raised block with Down held, release Down, slide into open
    space, then land on the floor. The final landing must earn 1 point,
    not the earlier soft-drop award.
    """
    game = make_game(tmp_path, pieces=(Piece.I, Piece.O))
    game.board.lock_cells([(5, 21)], 6)

    game.handle_input("soft_drop_on")
    _run_until_first_contact(game)
    assert game._piece_y == 20  # resting on the block
    assert game._landing_soft_drop is True

    game.handle_input("soft_drop_off")
    for _ in range(4):
        game.handle_input("left")
    # The piece is now over open space; one update detects airborne and
    # clears the captured landing state.
    game.update()
    assert game._landing_soft_drop is False

    _run_until_first_contact(game)
    assert game._landing_soft_drop is False
    score_before_lock = game.score
    _run_until_lock(game)
    assert game.score == score_before_lock + 1


def test_tetris_clear_awards_2500(tmp_path):
    """Four rows at once pays 2,500 into the pending stage award.

    Rows 19-22 are complete except for column 5; a vertical I fills that
    column and clears all four rows. The clear value is 2,500, but it is
    banked until the stage ends; the immediate score is only the
    placement points.
    """
    game = make_game(tmp_path)
    for y in range(19, 23):
        for col in range(10):
            if col != 5:
                game.board.lock_cells([(col, y)], 6)
    game._piece_kind = Piece.I
    game._rot = 1
    game._piece_x = 4
    game._piece_y = 19
    game._lock()

    assert game.lines == 4
    assert game._pending_stage_award == points_for_clear(4) == 2500
    assert game.score == placement_points(0, False, 0)


def test_color_index_changes_with_level():
    """The locked-piece color cycles with a period of 10 levels."""
    from tetris_core.game import LOCKED_COLOR_INDICES, locked_color_index

    assert len(LOCKED_COLOR_INDICES) == 10
    assert locked_color_index(0) == 0
    assert locked_color_index(6) == 6
    assert locked_color_index(8) == 8
    assert locked_color_index(9) == 9
    assert locked_color_index(10) == 0
    assert locked_color_index(11) == 1


def test_cheat_set_level_jumps_level(tmp_path):
    """The set_level cheat jumps level, color, and the stage boundary.

    The cheat range stays 0..9 (the UI's digit keys), while normal
    progression may reach 17. The jump anchors at the start of the
    current stage, so progress inside that stage is preserved.
    """
    from tetris_core.game import locked_color_index
    from tetris_core.protocol import Core

    core = Core(
        highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O])
    )
    game = core.game
    assert game.level == 0
    assert game._next_stage_line == INITIAL_STAGE_LINES
    assert game.set_level(8) is True
    assert game.level == 8
    assert game._next_stage_line == stage_lines_for_level(8)
    assert locked_color_index(game.level) == 8
    assert game.set_level(12) is True
    assert game.level == 9
    game.status = Status.GAME_OVER
    assert game.set_level(3) is False


def test_cheat_set_level_command(tmp_path):
    """The protocol command wraps the cheat with input validation."""
    from tetris_core.protocol import Core

    core = Core(
        highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O])
    )
    replies = core.handle_line('{"cmd": "set_level", "level": 8}')
    assert replies[0]["ok"] is True
    assert replies[1]["level"] == 8
    assert replies[1]["color_index"] == 8
    assert core.handle_line('{"cmd": "set_level", "level": 10}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level", "level": "eight"}')[0]["ok"] is False


def test_level_jump_does_not_recount_old_lines(tmp_path):
    """A level jump anchors progression at the current stage start.

    Regression for the 30-to-31 boundary: at 30 lines the game is level 1.
    Selecting level 5 must not make the next single (line 31) jump to
    level 6. With level 5's 50-line stages the next level arrives at 80.
    """
    game = make_game(tmp_path)
    game.lines = INITIAL_STAGE_LINES
    game.level = 1
    game._next_stage_line = INITIAL_STAGE_LINES + stage_lines_for_level(1)

    assert game.set_level(5) is True
    assert game.level == 5
    assert game._next_stage_line == INITIAL_STAGE_LINES + LATE_STAGE_LINES

    _lock_prepared_single(game)
    assert game.lines == INITIAL_STAGE_LINES + 1
    assert game.level == 5

    game.lines = INITIAL_STAGE_LINES + LATE_STAGE_LINES - 1
    game._next_stage_line = INITIAL_STAGE_LINES + LATE_STAGE_LINES
    _lock_prepared_single(game)
    assert game.lines == INITIAL_STAGE_LINES + LATE_STAGE_LINES
    assert game.level == 6
    assert game._next_stage_line == INITIAL_STAGE_LINES + LATE_STAGE_LINES * 2