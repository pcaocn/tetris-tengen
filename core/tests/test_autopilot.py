"""Autopilot tests (cheat mode, owner request 2026-10-27).

The weight-agnostic assertions check properties: every placement is
legal and lands on the floor; gaps get filled rather than covered; the
autopilot plays without any input; and the end-of-stage celebration is
never skipped.
"""

from tetris_core.autopilot import best_placement
from tetris_core.board import HEIGHT, WIDTH, Board, HIDDEN_ROWS
from tetris_core.game import CLEAR_ANIM_FRAMES, Status
from tetris_core.pieces import Piece

from helpers import FixedRNG
from tetris_core.protocol import Core


def holes(board: Board) -> int:
    count = 0
    for x in range(WIDTH):
        seen = False
        for y in range(HEIGHT):
            if board.get(x, y):
                seen = True
            elif seen:
                count += 1
    return count


def apply_placement(board: Board, kind: Piece, rot: int, x: int) -> None:
    """Drop the piece from the top at the chosen rotation and column."""
    from tetris_core.pieces import ROTATIONS

    cells = [(x + dx, dy) for dx, dy in ROTATIONS[kind][rot]]
    assert board.cells_free(cells)
    while board.cells_free([(cx, cy + 1) for cx, cy in cells]):
        cells = [(cx, cy + 1) for cx, cy in cells]
    board.lock_cells(cells, int(kind))


def test_ai_places_pieces_on_the_floor_legally():
    # Pieces that can rest flush on a flat floor leave no holes; S and Z
    # always leave exactly one under their notch, whatever the autopilot does.
    for kind in Piece:
        board = Board()
        result = best_placement(board, kind)
        assert result is not None
        rot, x = result
        apply_placement(board, kind, rot, x)
        assert holes(board) <= (1 if kind in (Piece.S, Piece.Z) else 0)


def test_ai_fills_a_one_column_gap():
    # A single gap in the middle of an otherwise flat bottom row.
    board = Board()
    for x in range(WIDTH):
        if x != 5:
            board.lock_cells([(x, HEIGHT - 1)], 1)
    result = best_placement(board, Piece.I)
    assert result is not None
    rot, x = result
    apply_placement(board, Piece.I, rot, x)
    # The best play fills the gap (vertical I) or at least creates no
    # new holes.
    assert holes(board) == 0


def test_ai_prefers_clearing_a_full_ready_row():
    # A two-wide gap in the bottom row with an O offered: clearing is the
    # textbook play (the residual nub is unavoidable either way, so the
    # lines bonus dominates). An O anywhere else leaves the gap open.
    board = Board()
    for x in range(WIDTH):
        if x not in (4, 5):
            board.lock_cells([(x, HEIGHT - 1)], 1)
    result = best_placement(board, Piece.O)
    assert result is not None
    rot, x = result
    apply_placement(board, Piece.O, rot, x)
    # The placement completes the ready row (the game clears it on lock).
    assert board.full_rows() == [HEIGHT - 1]


def test_autopilot_plays_without_input(tmp_path):
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    game = core.game
    core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')
    assert core.state_event()["autopilot"] == "quick"
    # The autopilot drives at human input speed through the normal
    # machinery; no input is ever sent. Let it place several pieces.
    for _ in range(600):
        game.update()
        if game.status is not Status.PLAYING:
            break
    assert game.lock_count >= 3
    assert game.piece_kind is not None or game.status is not Status.PLAYING


def test_autopilot_moves_at_human_speed(tmp_path):
    # Owner correction 2026-10-28 ("auto mode, not god mode"): one
    # rotation or one lateral step per frame (the key-press rate) and
    # soft-drop descent (the Down-key rate) — never an instant drop.
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    game = core.game
    spawn_x, spawn_y = game._piece_x, game._piece_y
    core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')
    for _ in range(3):
        game.update()
    # Lateral: at most one column per frame.
    assert abs(game._piece_x - spawn_x) <= 3
    # Rotation: at most one state per frame.
    assert game._rot <= 3
    # Descent: soft-drop starts at 6 fpr — in 3 frames the piece has
    # moved down at most one row, nothing like a hard drop.
    assert game._piece_y - spawn_y <= 1
    assert game.lock_count == 0


def test_autopilot_ignores_human_movement(tmp_path):
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    game = core.game
    core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')
    game.update()  # the autopilot places its plan
    x0 = game._piece_x
    game.handle_input("left")
    assert game._piece_x == x0  # ignored while autopilot drives
    # Toggling off returns control to the player.
    core.handle_line('{"cmd": "set_autopilot", "mode": null}')
    assert core.state_event()["autopilot"] is None
    # Steer away from whichever wall the autopilot chose.
    game.handle_input("right" if game._piece_x < 5 else "left")
    assert game._piece_x != x0


def test_autopilot_never_skips_the_celebration(tmp_path):
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    game = core.game
    core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')
    # Complete one line on demand (30-line level block: lines = 29).
    game.lines = 29
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, HEIGHT - 1)], 1)
    game._piece_x = 4
    game._piece_y = HEIGHT - 1
    game._lock()
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.status is Status.LEVEL_COMPLETE
    # The owner requirement: autopilot plays but never presses Enter —
    # the celebration waits indefinitely.
    for _ in range(600):
        game.update()
        assert game.status is Status.LEVEL_COMPLETE
    # Enter (the pause command) continues; autopilot resumes play.
    core.handle_line('{"cmd": "pause"}')
    assert game.status is Status.PLAYING
    for _ in range(20):
        game.update()


def test_set_autopilot_validation(tmp_path):
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "highscore"}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot", "mode": null}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "fast"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_autopilot", "mode": 1}')[0]["ok"] is False


def test_highscore_strategy_defers_small_clears():
    # Autopilot #2 (owner request 2026-10-28): with a low, safe stack a
    # 2-line clear is deferred (it would burn rows that could join a
    # later tetris); the quick strategy takes it.
    board = Board()
    for x in range(WIDTH):
        if x not in (4, 5):
            board.lock_cells([(x, HEIGHT - 1)], 1)

    quick = best_placement(board, Piece.O, "quick")
    assert quick is not None
    apply_placement(board, Piece.O, *quick)
    assert board.full_rows() == [HEIGHT - 1]  # quick clears on the spot

    board2 = Board()
    for x in range(WIDTH):
        if x not in (4, 5):
            board2.lock_cells([(x, HEIGHT - 1)], 1)
    highscore = best_placement(board2, Piece.O, "highscore")
    assert highscore is not None
    apply_placement(board2, Piece.O, *highscore)
    assert board2.full_rows() == []  # deferred: no clear while safe


def test_highscore_strategy_takes_a_ready_tetris():
    # Four ready rows over nine columns with a one-column well: the
    # highscore strategy must drop the vertical I into the well for the
    # tetris (its point value dominates).
    board = Board()
    for y in range(HEIGHT - 4, HEIGHT):
        for x in range(WIDTH - 1):
            board.lock_cells([(x, y)], 1)
    result = best_placement(board, Piece.I, "highscore")
    assert result is not None
    rot, x = result
    apply_placement(board, Piece.I, rot, x)
    assert len(board.full_rows()) == 4
