"""End-to-end game flow, high score, and protocol tests (spec 2, 8, 9)."""

import json
import subprocess
import sys

import pytest

from tetris_core.board import HIDDEN_ROWS
from tetris_core.game import SPAWN_X, SPAWN_Y, Status, lock_delay_frames
from tetris_core.highscore import load as load_highscore
from tetris_core.highscore import save as save_highscore
from tetris_core.pieces import Piece
from tetris_core.protocol import Core

from helpers import FixedRNG


def make_core(tmp_path, pieces=(Piece.T, Piece.O)):
    return Core(
        highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces)
    )


# ----------------------------------------------------------------------
# Game flow
# ----------------------------------------------------------------------


def test_new_game_spawns_at_visible_top(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.L])
    game = core.game
    assert game.status is Status.PLAYING
    assert game.piece_kind is Piece.T
    assert game.next_piece is Piece.L
    assert game._piece_x == SPAWN_X
    assert game._piece_y == SPAWN_Y
    # Owner decision 2026-10-24: the piece is visible immediately (it must
    # not linger above the visible playfield).
    assert all(y >= HIDDEN_ROWS for _, y in game.piece_cells())
    assert game.stats.as_dict()["T"] == 1


def test_scripted_move_and_rotate(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.O])
    game = core.game
    start_x = game._piece_x
    game.handle_input("left")
    game.handle_input("left")
    assert game._piece_x == start_x - 2
    game.handle_input("rotate_cw")
    assert game._rot == 1
    assert game.board.cells_free(game.piece_cells())


def test_das_autorepeats_then_stops(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.O])
    game = core.game
    start_x = game._piece_x
    game.handle_input("left")  # press: immediate step
    assert game._piece_x == start_x - 1
    for _ in range(14):  # DAS delay elapses -> one repeat move
        game.update()
    assert game._piece_x == start_x - 2
    for _ in range(8):  # repeat every 4 frames -> two more moves
        game.update()
    assert game._piece_x == start_x - 4
    game.handle_input("left_off")
    for _ in range(20):
        game.update()
    assert game._piece_x == start_x - 4


def test_pause_freezes_and_resumes(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.O])
    game = core.game
    core.game.pause()
    assert game.status is Status.PAUSED
    frame = game.frame
    assert game.update() is False
    assert game.frame == frame
    game.handle_input("left")  # input ignored while paused
    assert game._piece_x == SPAWN_X
    game.pause()
    assert game.status is Status.PLAYING
    game.update()  # resumes ticking
    assert game.frame == frame + 1


def test_soft_drop_locks_piece_at_floor(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    game.handle_input("soft_drop_on")
    for _ in range(300):
        if game.update() and game.piece_kind is Piece.O:
            break
    # I locked at the bottom row of the extended board. The I spawns with
    # its box left at column 5 (spec 4.1): cells at columns 5..8.
    for x in range(5, 9):
        assert game.board.get(x, 22) == int(Piece.I)
    # A new piece took over at spawn.
    assert game.piece_kind is Piece.O
    assert game._piece_y == SPAWN_Y
    assert game.stats.as_dict()["I"] == 1


# ----------------------------------------------------------------------
# Lock delay: "1 drop" grace window (spec 4.4, owner decision 2026-10-24)
# ----------------------------------------------------------------------


def test_lock_delay_is_short_and_shrinks_with_gravity():
    # Owner decision 2026-10-24: a short fixed window (not a full "1 drop"),
    # capped by the level's frames-per-row as gravity speeds up.
    assert lock_delay_frames(0) == 10
    assert lock_delay_frames(7) == 10  # fpr 12: cap not yet binding
    assert lock_delay_frames(8) == 9  # fpr 9: gravity cap binds
    assert lock_delay_frames(13) == 2  # fpr 2


def test_landed_piece_stays_movable_then_locks(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    game.handle_input("soft_drop_on")
    while game._can_move(0, 1):
        game.update()
    # The landing frame already counted as the first resting frame.
    assert game._rest_frames == 1
    assert game.piece_kind is Piece.I
    rest_x, rest_y = game._piece_x, game._piece_y
    # While resting, lateral moves still work: the classic slide trick.
    game.handle_input("left")
    game.handle_input("left_off")
    assert game._piece_x == rest_x - 1
    game.handle_input("right")
    game.handle_input("right_off")
    assert game._piece_x == rest_x
    # The full level-0 window (10 resting frames) elapses without locking.
    for _ in range(lock_delay_frames(0) - 2):
        game.update()
        assert game.piece_kind is Piece.I
    assert game._rest_frames == lock_delay_frames(0) - 1
    game.update()  # 10th resting frame: window not yet expired.
    assert game.piece_kind is Piece.I
    assert game._piece_y == rest_y
    # One frame past the window: the piece locks and the next one spawns.
    game.update()
    assert game.piece_kind is Piece.O


def test_resting_piece_slides_off_ledge_and_gets_fresh_window(tmp_path):
    core = make_core(tmp_path, [Piece.O, Piece.I])
    game = core.game
    # A ledge across the bottom row with a two-column pit at the far left.
    game.board.lock_cells([(x, 22) for x in range(2, 10)], 6)
    game.handle_input("soft_drop_on")
    while game._can_move(0, 1):
        game.update()
    assert game.piece_kind is Piece.O
    ledge_y = game._piece_y
    # Slide left across the ledge during the grace window.
    for _ in range(5):
        game.handle_input("left")
    game.handle_input("left_off")
    assert game._piece_x == 0
    assert game.piece_kind is Piece.O  # still the same un-locked piece
    # Over the pit the piece falls one row within the same frame and lands
    # at the pit bottom: the old window is cancelled and a fresh, full one
    # starts (the landing frame counts as its first resting frame).
    game.update()
    assert game._piece_y == ledge_y + 1
    assert game._rest_frames == 1


def test_game_over_when_spawn_blocked_saves_high_score(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.L])
    game = core.game
    game.score = 1234
    # Fill the visible field from one row below the spawn, leaving holes at
    # column 0 (no row completes) and at the T's own spawn cells, so that:
    # the current T rests and locks where it spawned, and the next spawn
    # (L: cells (6,3), (6,4), (6,5), (5,5)) is blocked -> game over.
    holes = {(0, y) for y in range(HIDDEN_ROWS, 23)} | set(game.piece_cells())
    for y in range(HIDDEN_ROWS + 1, 23):
        for x in range(10):
            if (x, y) not in holes:
                game.board.lock_cells([(x, y)], 6)
    # Land the current piece to force the blocked spawn.
    game.handle_input("soft_drop_on")
    for _ in range(300):
        game.update()
        if game.status is Status.GAME_OVER:
            break
    assert game.status is Status.GAME_OVER
    assert game.piece_kind is None
    assert game.high_score == 1234
    assert load_highscore(tmp_path / "highscore.json") == 1234


def test_high_score_roundtrip_and_corruption(tmp_path):
    path = tmp_path / "highscore.json"
    assert load_highscore(path) == 0  # missing file
    save_highscore(4321, path)
    assert load_highscore(path) == 4321
    path.write_text("{corrupted json")
    assert load_highscore(path) == 0
    assert (tmp_path / "highscore.json.bak").exists()  # renamed, spec section 8


# ----------------------------------------------------------------------
# Protocol (spec 2.2)
# ----------------------------------------------------------------------


def test_get_state_returns_full_snapshot(tmp_path):
    core = make_core(tmp_path)
    events = core.handle_line('{"id": 7, "cmd": "get_state"}')
    assert len(events) == 2
    response, state = events
    assert response == {"type": "response", "id": 7, "ok": True}
    assert state["type"] == "state"
    assert state["frame"] == 0
    assert len(state["board"]) == 20
    assert all(len(row) == 10 for row in state["board"])
    assert state["current"]["kind"] == "T"
    assert state["current"]["cells"] == [
        [SPAWN_X + x, SPAWN_Y + y - HIDDEN_ROWS]
        for x, y in ((1, 0), (0, 1), (1, 1), (2, 1))
    ]
    assert state["next"] == "O"
    assert state["stats"] == {"T": 1, "J": 0, "Z": 0, "O": 0, "S": 0, "L": 0, "I": 0}
    assert state["status"] == "playing"
    assert isinstance(state["color_index"], int)


def test_every_command_gets_response_with_same_id(tmp_path):
    core = make_core(tmp_path)
    lines = [
        '{"id": 12, "cmd": "input", "action": "left"}',
        '{"id": 13, "cmd": "new_game", "level": 0}',
        '{"id": 14, "cmd": "pause"}',
        '{"id": 15, "cmd": "get_state"}',
    ]
    ids = []
    for line in lines:
        events = core.handle_line(line)
        assert events[0]["type"] == "response"
        ids.append(events[0]["id"])
    assert ids == [12, 13, 14, 15]


def test_new_game_and_pause_commands(tmp_path):
    core = make_core(tmp_path)
    state = core.handle_line('{"id": 1, "cmd": "new_game", "level": 5}')[1]
    assert state["level"] == 5
    state = core.handle_line('{"id": 2, "cmd": "pause"}')[1]
    assert state["status"] == "paused"
    state = core.handle_line('{"id": 3, "cmd": "pause"}')[1]
    assert state["status"] == "playing"


def test_malformed_input_never_crashes(tmp_path):
    core = make_core(tmp_path)
    events = core.handle_line("this is not json")
    response, log_event = events
    assert response["ok"] is False
    assert response["id"] is None
    assert log_event["type"] == "log"
    assert log_event["level"] == "error"
    # The process keeps running: a valid command still works.
    events = core.handle_line('{"id": 9, "cmd": "get_state"}')
    assert events[0]["ok"] is True


def test_unknown_cmd_and_bad_action_error(tmp_path):
    core = make_core(tmp_path)
    events = core.handle_line('{"id": 1, "cmd": "teleport"}')
    assert events[0]["ok"] is False
    assert "unknown cmd" in events[0]["error"]
    events = core.handle_line('{"id": 2, "cmd": "input", "action": "hyperjump"}')
    assert events[0]["ok"] is False


def test_stdio_loop_scripted_commands(tmp_path):
    """Milestone 4: `python -m tetris_core` answers scripted commands."""
    env = {
        "PATH": "/usr/bin:/bin",
        "TETRIS_HIGHSCORE_PATH": str(tmp_path / "highscore.json"),
    }
    script = "\n".join(
        [
            '{"id": 1, "cmd": "new_game", "level": 0}',
            '{"id": 2, "cmd": "input", "action": "left"}',
            '{"id": 3, "cmd": "get_state"}',
        ]
    )
    proc = subprocess.run(
        [sys.executable, "-m", "tetris_core"],
        input=script,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    events = [json.loads(line) for line in proc.stdout.splitlines()]
    assert events[0]["type"] == "state"  # initial snapshot
    responses = {e["id"] for e in events if e["type"] == "response"}
    assert {1, 2, 3} <= responses
    final_state = [e for e in events if e["type"] == "state"][-1]
    assert final_state["status"] == "playing"
    assert all(len(row) == 10 for row in final_state["board"])
