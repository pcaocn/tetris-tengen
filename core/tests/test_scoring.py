"""Scoring, clear dissolve, and level progression tests (spec 4.5)."""

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


def test_color_index_changes_with_level():
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
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I, Piece.O]))
    replies = core.handle_line('{"cmd": "set_level", "level": 8}')
    assert replies[0]["ok"] is True
    assert replies[1]["level"] == 8
    assert replies[1]["color_index"] == 8
    # Out-of-range, missing, and non-integer levels are rejected.
    assert core.handle_line('{"cmd": "set_level", "level": 10}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_level", "level": "eight"}')[0]["ok"] is False
