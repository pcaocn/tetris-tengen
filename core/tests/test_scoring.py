"""Scoring, clear dissolve, and level progression tests (spec 4.5)."""

from tetris_core.game import CLEAR_ANIM_FRAMES, Game, Status
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
    # Owner-verified 2026-10-24 from the award table in
    # png/screenshot_28.png: single 100, double 400, triple 900,
    # tetris 2500.
    assert points_for_clear(1) == 100
    assert points_for_clear(2) == 400
    assert points_for_clear(3) == 900
    assert points_for_clear(4) == 2500
    assert points_for_clear(0) == 0


def test_block_bonuses_counts_completed_blocks():
    assert block_bonuses(0, BONUS_BLOCK_LINES) == 1
    assert block_bonuses(0, BONUS_BLOCK_LINES - 1) == 0
    assert block_bonuses(BONUS_BLOCK_LINES - 1, BONUS_BLOCK_LINES + 1) == 1
    assert block_bonuses(0, 3 * BONUS_BLOCK_LINES) == 3
    assert block_bonuses(25, 95) == 3  # 95//30 = 3 blocks completed in total


def test_level_for_lines_placeholder_rule():
    assert level_for_lines(0, 0) == 0
    assert level_for_lines(0, LEVEL_LINES) == 1
    assert level_for_lines(0, LEVEL_LINES - 1) == 0
    assert level_for_lines(2, 3 * LEVEL_LINES) == 5


def make_game(tmp_path, pieces=(Piece.I, Piece.O)):
    return Game(highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces))


def test_single_line_clear_scores_and_counts(tmp_path):
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


def test_color_index_changes_with_level(tmp_path):
    from tetris_core.game import LOCKED_COLOR_INDICES, locked_color_index

    assert locked_color_index(0) == LOCKED_COLOR_INDICES[0]
    assert locked_color_index(len(LOCKED_COLOR_INDICES)) == LOCKED_COLOR_INDICES[0]
    assert locked_color_index(1) != locked_color_index(0)
