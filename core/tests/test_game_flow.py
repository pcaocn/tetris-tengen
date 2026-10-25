"""End-to-end game flow, high score, and protocol tests (spec 2, 8, 9)."""

import json
import subprocess
import sys

import pytest

from tetris_core.board import HIDDEN_ROWS
from tetris_core.game import (
    CLEAR_ANIM_FRAMES,
    SPAWN_X,
    SPAWN_Y,
    Status,
    lock_delay_frames,
)
from tetris_core.scoring import BONUS_BLOCK_LINES
from tetris_core import highscore
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


# ----------------------------------------------------------------------
# Music flow (owner request 2026-10-25): end-of-stage celebration with
# music phases 06/07, milestone 09, game over 08, selected track echo.
# ----------------------------------------------------------------------


def complete_one_line(game):
    """Locks an I to complete the bottom row and runs the clear wipe."""
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()


def test_music_selection_echoes_in_state_events(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    core.handle_line('{"cmd": "new_game", "level": 0, "music": "03"}')
    state = core.state_event()
    assert state["music_track"] == "03"
    assert state["music_phase"] == "gameplay"
    assert core.handle_line('{"cmd": "new_game", "level": 0, "music": 7}')[0]["ok"] is False


def test_level_complete_celebration_then_resume(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    game.lines = BONUS_BLOCK_LINES - 1  # clearing one line finishes level 0
    complete_one_line(game)
    # The wipe runs first; the celebration starts when it finishes.
    assert game.status is Status.PLAYING
    assert game.music_phase == "gameplay"
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.status is Status.LEVEL_COMPLETE
    assert game.music_phase == "level_complete"
    assert game.level == 1
    assert game.piece_kind is None  # spawn deferred until Enter
    # Movement inputs are ignored during the celebration.
    game.handle_input("left")
    assert game.status is Status.LEVEL_COMPLETE
    # Enter (the pause command) resumes: play continues, music returns to
    # the gameplay phase, and the deferred piece spawns.
    core.handle_line('{"cmd": "pause"}')
    assert game.status is Status.PLAYING
    assert game.piece_kind is Piece.O
    assert game.music_phase == "gameplay"


def test_milestone_celebration_every_tenth_level(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    # Completing level 9 (lines 299 -> 300) bumps the level to 10.
    game.lines = BONUS_BLOCK_LINES * 10 - 1
    complete_one_line(game)
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.status is Status.LEVEL_COMPLETE
    assert game.level == 10
    assert game.music_phase == "milestone"


def test_clear_count_drives_row_clear_sound(tmp_path):
    # Row-clear sound (owner request 2026-10-25): one bump per clear
    # event, regardless of how many rows cleared at once.
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    assert core.state_event()["clear_count"] == 0
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()
    assert game.clear_count == 1
    assert core.state_event()["clear_count"] == 1


def test_lock_count_drives_landing_pop(tmp_path):
    # Landing pop (owner request 2026-10-25): every lock bumps the
    # counter carried in the state event; the UI plays a synthesized
    # brick-thud on each increment.
    core = make_core(tmp_path, [Piece.I, Piece.O])
    game = core.game
    assert core.state_event()["lock_count"] == 0
    game.handle_input("soft_drop_on")
    for _ in range(300):
        game.update()
        if game.piece_kind is Piece.O:
            break
    assert game.lock_count == 1
    assert core.state_event()["lock_count"] == 1
    for _ in range(300):
        game.update()
        if game.piece_kind is None or game.lock_count == 2:
            break
    assert game.lock_count == 2


def test_handicap_rows_are_unfinished(tmp_path):
    # Handicap (owner request 2026-10-25): the chosen number of bottom
    # rows start filled except for one random hole each.
    core = make_core(tmp_path, [Piece.I, Piece.O])
    replies = core.handle_line(
        '{"cmd": "new_game", "level": 0, "music": null, "handicap": 3}'
    )
    assert replies[0]["ok"] is True
    board = replies[1]["board"]
    for row in board[-3:]:
        assert row.count(0) == 1
        assert sum(1 for v in row if v > 0) == 9
    assert all(v == 0 for row in board[:-3] for v in row)
    assert core.game.status is Status.PLAYING
    # Rows are not full, so nothing clears; holes can differ per row
    # (FixedRNG cycles holes 0, 3, 6 here).
    assert board[-1].index(0) in (0, 3, 6)


def test_handicap_validation(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": 13}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": -1}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": "six"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": 12}')[0]["ok"] is True


def test_cheat_set_music_cycles_during_play(tmp_path):
    core = make_core(tmp_path, [Piece.I, Piece.O])
    # Changing the gameplay music mid-game (the UI's backquote cheat key).
    replies = core.handle_line('{"cmd": "set_music", "music": "04"}')
    assert replies[0]["ok"] is True
    assert replies[1]["music_track"] == "04"
    assert replies[1]["music_phase"] == "gameplay"
    # Non-string ids are rejected.
    assert core.handle_line('{"cmd": "set_music", "music": 4}')[0]["ok"] is False
    # Not while the game is paused.
    core.handle_line('{"cmd": "pause"}')
    assert core.handle_line('{"cmd": "set_music", "music": "05"}')[0]["ok"] is False


def test_game_over_reports_music_phase(tmp_path):
    core = make_core(tmp_path, [Piece.T, Piece.L])
    game = core.game
    game.score = 5
    # Pre-fill the top-5 table so a score of 5 cannot qualify.
    for s in (500, 400, 300, 200, 100):
        highscore.add(s, tmp_path / "highscore.json")
    # Block the spawn cells so the next piece cannot appear.
    holes = {(0, y) for y in range(HIDDEN_ROWS, 23)} | set(game.piece_cells())
    for y in range(HIDDEN_ROWS + 1, 23):
        for x in range(10):
            if (x, y) not in holes:
                game.board.lock_cells([(x, y)], 6)
    game.handle_input("soft_drop_on")
    for _ in range(300):
        game.update()
        if game.status is Status.GAME_OVER:
            break
    assert game.status is Status.GAME_OVER
    assert game.music_phase == "game_over"
    # Below the table's worst entry: no fireworks (owner rule 2026-10-25).
    assert game.top_run is False
    assert core.state_event()["top_run"] is False


def test_top5_table_game_over_fireworks(tmp_path):
    from tetris_core.highscore import add as add_highscore

    path = tmp_path / "highscore.json"
    # Pre-fill the table with 5 scores; the worst is 100.
    for s in (500, 400, 300, 200, 100):
        add_highscore(s, path)
    core = make_core(tmp_path, [Piece.T, Piece.L])
    game = core.game
    # A score better than the worst enters the table; a worse one does not.
    game.score = 250
    assert highscore.qualifies(250, path) is True
    assert highscore.qualifies(50, path) is False
    table = highscore.add(250, path)
    assert [e["score"] for e in table] == [500, 400, 300, 250, 200]
    assert table[3]["at"] != ""

    # End a fresh game with a top-5 score: top_run reports for the
    # fireworks screen and the state event carries the table.
    core2 = Core(highscore_path=path, rng=FixedRNG([Piece.T, Piece.L]))
    game2 = core2.game
    game2.score = 350
    holes = {(0, y) for y in range(HIDDEN_ROWS, 23)} | set(game2.piece_cells())
    for y in range(HIDDEN_ROWS + 1, 23):
        for x in range(10):
            if (x, y) not in holes:
                game2.board.lock_cells([(x, y)], 6)
    game2.handle_input("soft_drop_on")
    for _ in range(300):
        game2.update()
        if game2.status is Status.GAME_OVER:
            break
    assert game2.status is Status.GAME_OVER
    assert game2.top_run is True
    state = core2.state_event()
    assert state["top_run"] is True
    assert [e["score"] for e in state["top_scores"]] == [500, 400, 350, 300, 250]
    assert state["high_score"] == 500
    # A new game resets the flag but keeps the table.
    game2.new_game(0)
    assert game2.top_run is False
    assert game2.top_scores[0]["score"] == 500


def test_top5_table_migration_from_single_score(tmp_path):
    import json as json_mod

    path = tmp_path / "highscore.json"
    path.write_text(json_mod.dumps({"high_score": 777}))
    table = highscore.load_table(path)
    assert table == [{"score": 777, "at": ""}]
    assert highscore.load(path) == 777
