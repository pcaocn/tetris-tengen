"""End-to-end game flow, high score, and protocol tests (spec 2, 8, 9).

WHAT THIS FILE TESTS
====================
The full life of a game, at three layers:

    - GAME FLOW: spawn position, movement, DAS auto-repeat, pause,
      soft-drop landing, and the game-over path when a spawn is
      blocked.
    - LOCK DELAY: the grace window (10 frames, capped by the level's
      frames-per-row) that lets a landed piece still be moved or slid
      off a ledge -- including the fresh-window rule.
    - PROTOCOL: the JSON-line contract the Rust/TS UI speaks -- every
      command answered with the same id, malformed input never
      crashing the process, the state snapshot's shape, and the
      stdio loop as a real subprocess.
    - MUSIC FLOW: the phase machine (gameplay / level_complete /
      milestone / game_over), the end-of-stage celebration window,
      the sound-counter events, the handicap rows, and the top-5
      high-score table with its fireworks flag.

WHY THIS FILE DRIVES A REAL CORE
--------------------------------
Most tests here go through `Core.handle_line()` -- the same entry
point the UI process uses -- rather than poking `game` internals. That
is deliberate: the protocol is a contract, and these tests are its
executable documentation. The few white-box reads (`game._piece_x`,
`game._rest_frames`) target state that has no protocol representation.

FRAME ARITHMETIC IN THE COMMENTS
--------------------------------
All timings are 60 Hz frames (spec 2.1): DAS_DELAY 14 (~233 ms) and
DAS_REPEAT 4 (~67 ms), CLEAR_ANIM_FRAMES 24 (~400 ms), CELEBRATE_FRAMES
210 (~3.5 s -- long enough for the 2.48 s stage-clear track or the
3.24 s milestone track to play once).
"""

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
    """A full Core (protocol + Game) pointed at an isolated highscore file.

    The (T, O) default gives every test a T first -- the most
    "interesting" piece to steer (asymmetric, all states distinct) --
    followed by an inert O. Tests that need a different script pass
    their own list, e.g. [Piece.I, Piece.O] when an I must complete a
    prepared row.
    """
    return Core(
        highscore_path=tmp_path / "highscore.json", rng=FixedRNG(pieces)
    )


# ----------------------------------------------------------------------
# Game flow
# ----------------------------------------------------------------------


def test_new_game_spawns_at_visible_top(tmp_path):
    """A new game starts with the scripted piece, visibly, at the spawn box.

    Step 1: build a core scripted [T, L].
    Step 2: the status is PLAYING, the current piece is the T, and the
       NEXT piece is the L (the preview the UI shows).
    Step 3: the piece box sits at SPAWN_X (5) / SPAWN_Y (3 =
       HIDDEN_ROWS), and every cell is at row >= HIDDEN_ROWS -- the
       first visible row or below.

    That last assert is the owner decision of 2026-10-24: the piece is
    visible the instant the game starts, never lurking in the hidden
    rows. The stats counter for T is already 1 because spawning counts
    the piece.
    """
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
    """The basic controls: two taps move two columns, one tap rotates once.

    Step 1: note the spawn column.
    Step 2: two "left" presses -- the piece must be exactly two columns
       left (one step per press, no auto-repeat yet).
    Step 3: one "rotate_cw" -- state 0 -> 1, and the result must be a
       legal position on the board.

    This is the floor of the input contract: if taps do not map to
    single steps, every timing test downstream is meaningless.
    """
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
    """DAS: immediate step, delay, steady repeat, and a hard stop.

    Step 1: press "left" -- one step RIGHT NOW (the press itself moves).
    Step 2: advance 14 frames (DAS_DELAY, ~233 ms) -- the delay expires
       and fires exactly ONE repeat move (total -2).
    Step 3: advance 8 more frames -- at DAS_REPEAT = 4 (~67 ms) per
       move that is exactly two more steps (total -4).
    Step 4: release the key and advance 20 frames -- no further
       movement.

    The exact frame counts matter because they ARE the game feel: a
    held key must scroll smoothly but never teleport. The final assert
    proves keyup truly stops the auto-shift.
    """
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
    """Pause must freeze the frame clock AND ignore input; resume ticks on.

    Step 1: pause -- status becomes PAUSED.
    Step 2: one update() returns False (nothing changed) and the frame
       counter does NOT advance -- the whole world stops, not just the
       piece.
    Step 3: a "left" press while paused is ignored (piece still at the
       spawn column).
    Step 4: pause again (the toggle) -- status is PLAYING, and the next
       update() advances the frame by exactly one.

    The return value of update() is how the protocol decides whether
    to emit a state event, so "False while paused" also means no
    redraw spam while the game sits still.
    """
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
    """Soft-dropping an I must land it on the floor row, intact, then spawn.

    Step 1: hold soft drop; loop up to 300 updates (~5 s of game time)
       until the update reports a change AND the O (the scripted next
       piece) is live -- meaning the I has locked.
    Step 2: the bottom row must hold the I's four cells at columns
       5..8 (the I spawns with its box left at column 5 per spec 4.1).

    The 300-frame cap is a safety net, not the timing: soft drop at
    level 0 (6 fpr accelerating) covers the 20 visible rows in well
    under 100 frames. Step 3 checks the handover -- the O is at the
    spawn row and the I's stat counter reads 1.
    """
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
    """The lock window is 10 frames, capped by the level's own fall speed.

    Owner decision 2026-10-24: a short fixed window (not a full "1 drop"),
    capped by the level's frames-per-row as gravity speeds up.

    The four samples trace the rule across levels:
      - level 0 -> 10 frames (the fixed window, ~167 ms);
      - level 7 (fpr 12) -> still 10: the cap is not binding yet;
      - level 8 (fpr 9) -> 9: from here gravity is FASTER than the
        window, so the window shrinks with it;
      - level 13 (fpr 2) -> 2: essentially land-and-lock.

    The cap keeps high-level play honest -- a piece can never linger
    longer than one gravity interval, or the fastest levels would be
    trivially slow-motion at the bottom.
    """
    # Owner decision 2026-10-24: a short fixed window (not a full "1 drop"),
    # capped by the level's frames-per-row as gravity speeds up.
    assert lock_delay_frames(0) == 10
    assert lock_delay_frames(7) == 10  # fpr 12: cap not yet binding
    assert lock_delay_frames(8) == 9  # fpr 9: gravity cap binds
    assert lock_delay_frames(13) == 2  # fpr 2


def test_landed_piece_stays_movable_then_locks(tmp_path):
    """The full lock-delay lifecycle: land, slide, wait, lock.

    Step 1: soft-drop the I until it can no longer move down
       (`_can_move(0, 1)` false). The landing frame itself already
       counts as resting frame 1.
    Step 2: while resting, lateral moves must still work -- one left,
       then one right back -- the classic "land and slide" trick the
       window exists for.
    Step 3: burn the rest of the level-0 window (10 frames). Through
       the 9th resting frame the piece must STILL be there (this is
       why the window is short: it never resets on movement, so the
       piece locks on schedule no matter how much the player fidgets).
    Step 4: the update that pushes past 10 resting frames locks the I
       and spawns the scripted O.

    A regression here shows up as either pieces locking instantly (no
    slide trick) or hanging forever at the bottom (window resetting).
    """
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
    """Sliding off a ledge must cancel the window and grant a fresh one.

    Step 1: build a ledge -- the bottom row filled from column 2 to 9,
       with a two-column pit (0, 1) at the far left -- and soft-drop
       the O onto it.
    Step 2: during the grace window, slide the O left five times to
       column 0 (over the pit) without it locking.
    Step 3: the next update drops it one row into the pit and it lands
       at the pit bottom; `_rest_frames` is back to 1.

    The fresh window is the fairness rule: gravity resumed, so the
    player gets a full new grace period at the deeper resting spot
    rather than inheriting the almost-expired one from the ledge.
    """
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
    """A blocked spawn ends the game and persists the score.

    Step 1: set the score to 1234.
    Step 2: fill the field from one row below the spawn downward,
       leaving exactly two kinds of gap: column 0 (so NO row ever
       completes -- the death must come from the blocked spawn, not a
       clear) and the current T's own spawn cells (so the T can rest
       where it is).
    Step 3: soft-drop; the T locks, then the next spawn (the L, whose
       cells (6,3), (6,4), (6,5), (5,5) are now walled in) fails --
       status GAME_OVER, no active piece.
    Step 4: the 1234 was saved to the isolated highscore file and is
       now the recorded high score.

    This is the spec 4.8 death rule: the game ends when a piece cannot
    APPEAR, not when the stack visually touches the ceiling.
    """
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
    """The highscore file survives missing, valid, and corrupt states.

    Step 1: no file at all -> load returns 0 (a fresh machine starts
       at zero, no crash).
    Step 2: save 4321 -> load reads it back.
    Step 3: corrupt the file with garbage -> load returns 0 AND the
       broken file has been renamed to .bak.

    The .bak rename is the robustness rule of spec section 8: the
    player's data is quarantined, never silently deleted, and the game
    keeps running. A highscore file is the one file a player might
    hand-edit, so it must be able to survive that.
    """
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
    """get_state must return a response PLUS a complete, correct snapshot.

    Step 1: send {"id": 7, "cmd": "get_state"} -- two events come back.
    Step 2: the response echoes the id with ok=True (the UI matches
       replies to requests by id).
    Step 3: the state event carries the whole renderable picture: a
       20x10 board (the visible grid only -- hidden rows never cross
       the protocol boundary), the current T with its cells converted
       to visible coordinates (SPAWN_Y + y - HIDDEN_ROWS per the
       extended->visible shift), the next piece, the full stats
       counter, the status string, and an integer color index.

    This is the single most load-bearing protocol test: the UI is a
    pure renderer over exactly this snapshot.
    """
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
    """Every command must be answered with a response bearing its own id.

    Four different commands (input, new_game, pause, get_state) are
    sent, each with a distinct id; each first event must be a response
    echoing exactly the id that was sent, in order.

    The id echo is how the async UI pairs answers with requests; a
    mismatched or missing id would leave the frontend hanging. Note
    commands that also emit state events still put the response FIRST.
    """
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
    """new_game sets the level; pause toggles both ways over the protocol.

    Step 1: new_game at level 5 -- the returned state must report
       level 5 (the game can start at a chosen level, not just 0).
    Step 2: the first pause command flips the state to "paused"; the
       second flips it back to "playing".

    The pause command is the SAME one the UI binds to Enter, which is
    why it toggles rather than sets.
    """
    core = make_core(tmp_path)
    state = core.handle_line('{"id": 1, "cmd": "new_game", "level": 5}')[1]
    assert state["level"] == 5
    state = core.handle_line('{"id": 2, "cmd": "pause"}')[1]
    assert state["status"] == "paused"
    state = core.handle_line('{"id": 3, "cmd": "pause"}')[1]
    assert state["status"] == "playing"


def test_malformed_input_never_crashes(tmp_path):
    """Garbage on stdin must produce an error event, never a crash.

    Step 1: send a line that is not JSON at all.
    Step 2: the answer is a response with ok=False and id=None (there
       was no id to echo) plus a "log" event at level "error" the UI
       can surface in a console pane.
    Step 3: a valid command afterwards still works -- the process is
       alive and serving.

    This is the spec-8 robustness rule applied to the protocol: the
    core is a long-lived process feeding off a pipe, so ONE bad line
    must never take the game down.
    """
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
    """Unknown commands and unknown actions must be rejected with reasons.

    Step 1: "teleport" is not a command -> ok=False and the error text
       names the problem ("unknown cmd").
    Step 2: a valid command (input) with an invalid action
       ("hyperjump") is also rejected.

    The error message content matters: the UI shows it in the log
    pane, so it must identify what was wrong, not just that something
    was.
    """
    core = make_core(tmp_path)
    events = core.handle_line('{"id": 1, "cmd": "teleport"}')
    assert events[0]["ok"] is False
    assert "unknown cmd" in events[0]["error"]
    events = core.handle_line('{"id": 2, "cmd": "input", "action": "hyperjump"}')
    assert events[0]["ok"] is False


def test_stdio_loop_scripted_commands(tmp_path):
    """Milestone 4: `python -m tetris_core` answers scripted commands.

    This is the only test that boots the core as a REAL PROCESS: a
    subprocess of `python -m tetris_core`, fed three JSON lines on
    stdin, read back from stdout.

    The environment is pinned hard -- PATH stripped to the system
    dirs and TETRIS_HIGHSCORE_PATH pointed into tmp_path -- so the
    test neither touches the real highscore file nor depends on the
    developer's shell.

    What the assertions pin: exit code 0, an initial state snapshot
    before any command, a response for every sent id, and a final
    state that is playing with a 10-wide board. This is the exact
    contract the Rust/TS host relies on when it spawns the core.
    """
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
    """Locks an I to complete the bottom row and runs the clear wipe.

    The shared recipe of the music tests: fill the bottom row except
    columns 4..7, teleport the scripted I there, and lock -- the clear
    (and therefore the level block / celebration) starts immediately.
    The caller then advances CLEAR_ANIM_FRAMES to reach the phase
    transition.
    """
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, 22)], 6)
    game._piece_x = 4
    game._piece_y = 22
    game._lock()


def test_music_selection_echoes_in_state_events(tmp_path):
    """The chosen track echoes back; a non-string track id is rejected.

    Step 1: new_game with music "03" -- the state event must carry
       music_track "03" and phase "gameplay" (the core does not
       interpret the id, it just remembers and reports it; the UI
       owns the actual audio files).
    Step 2: music given as the NUMBER 7 is refused with ok=False --
       track ids are strings by contract, and accepting an int here
       would silently break the UI's lookup.
    """
    core = make_core(tmp_path, [Piece.I, Piece.O])
    core.handle_line('{"cmd": "new_game", "level": 0, "music": "03"}')
    state = core.state_event()
    assert state["music_track"] == "03"
    assert state["music_phase"] == "gameplay"
    assert core.handle_line('{"cmd": "new_game", "level": 0, "music": 7}')[0]["ok"] is False


def test_level_complete_celebration_then_resume(tmp_path):
    """Clearing a 30-line block freezes the game for the celebration.

    Step 1: set lines to 29 so the single clear completes level 0.
    Step 2: lock the I. The 24-frame wipe runs FIRST -- during it the
       status is still PLAYING and the music phase is still gameplay.
    Step 3: when the wipe finishes, status LEVEL_COMPLETE, phase
       "level_complete" (track 06), level 1, and NO piece spawned --
       the spawn is deferred for the whole celebration.
    Step 4: movement input during the celebration is ignored (still
       LEVEL_COMPLETE afterwards).
    Step 5: Enter -- the pause command -- skips the celebration: back
       to PLAYING, phase "gameplay", and the deferred O spawns now.

    The two-phase design (wipe then freeze) is what lets the UI fade
    the rows out before the stage-clear jingle starts.
    """
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
    """A level that is a multiple of 10 gets the milestone track (09).

    Step 1: set lines to 299 -- one short of 300, i.e. completing
       level 9 (levels advance every 30 lines).
    Step 2: complete one line and let the wipe finish.

    The status is LEVEL_COMPLETE (same celebration window) but the
    phase is "milestone" because the new level is 10: the UI plays the
    longer Victory track instead of the ordinary End-of-Stage one. The
    modulo test (`level % 10 == 0`) inside music_phase is what this
    pins.
    """
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
    """The clear sound fires once per clear EVENT, not per row.

    Row-clear sound (owner request 2026-10-25): one bump per clear
    event, regardless of how many rows cleared at once.

    Step 1: the state event starts with clear_count 0.
    Step 2: lock the prepared I (a single-row clear).
    Step 3: the counter reads exactly 1 -- on the game object and in
       the state event.

    The UI plays its bump sound when it sees this counter INCREASE, so
    a double clear that bumped twice would sound like two separate
    clears. (A multi-row variant of this recipe would still count 1.)
    """
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
    """The landing pop fires on every lock, via a monotonic counter.

    Landing pop (owner request 2026-10-25): every lock bumps the
    counter carried in the state event; the UI plays a synthesized
    brick-thud on each increment.

    Step 1: the counter starts at 0.
    Step 2: soft-drop until the I locks and the O appears -- the
       counter reads 1, on the game and in the event.
    Step 3: keep soft-dropping until the O locks too -- the counter
       reads 2.

    A counter (rather than a boolean) is what makes overlapping sounds
    safe: the UI fires on every observed increment and can queue the
    thuds.
    """
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
    """Handicap rows start filled EXCEPT for one hole per row.

    Handicap (owner request 2026-10-25): the chosen number of bottom
    rows start filled except for one random hole each.

    Step 1: new_game with handicap 3.
    Step 2: each of the bottom three rows of the protocol board must
       hold exactly 9 filled cells and exactly one 0 -- a hole -- and
       the rows above must be completely empty.

    The rows are deliberately NOT full (one hole each), so nothing
    clears at spawn and the player starts digging instead of getting
    a free board. The holes come from the rng's hole_column(); with
    the FixedRNG cycle (0, 3, 6) they are predictable, which is what
    the final assert pins.
    """
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
    """Handicap must be an integer in 0..12; anything else is rejected.

    13 rows is impossible (the board is only 23 tall and rows must
    stay below the spawn), -1 is nonsense, "six" is the wrong type --
    each is answered with ok=False. 12 is the largest legal value and
    must be ACCEPTED, which pins the boundary as inclusive.

    The title screen builds these requests from raw widget state, so
    the validation has to live in the core.
    """
    core = make_core(tmp_path, [Piece.I, Piece.O])
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": 13}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": -1}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": "six"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "new_game", "level": 0, "handicap": 12}')[0]["ok"] is True


def test_cheat_set_music_cycles_during_play(tmp_path):
    """The music cheat swaps tracks mid-game -- but only while playing.

    Step 1: set_music "04" during play -> ok=True, and the state echo
       carries the new track with phase still "gameplay" (the UI's
       backquote key cycles tracks with this command).
    Step 2: a non-string id (4) is rejected.
    Step 3: after pausing, set_music is refused -- the music switch is
       a gameplay-time cheat, and honouring it while paused would let
       the game's state and its soundtrack drift apart.

    This is the last test in the file pinned to a cheat key, in spec-8
    style: the core validates so the UI does not have to.
    """
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
    """Game over must report phase "game_over" and suppress the fireworks.

    Step 1: pre-fill the top-5 table (500..100) and set the game's
       score to 5 -- far below the table's worst entry.
    Step 2: build the same blocked-spawn wall as the game-over test
       (holes at column 0 and the T's spawn cells) and soft-drop until
       the blocked L spawn kills the game.
    Step 3: status GAME_OVER, music phase "game_over" (track 08), and
       top_run is False -- both on the game and in the state event.

    The owner rule of 2026-10-25: the fireworks screen is ONLY for a
    score that actually entered the table. A trivial death must not
    celebrate.
    """
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
    """A top-5 death earns the fireworks flag and publishes the table.

    from tetris_core.highscore import add as add_highscore -- imported
    here because this is the only test that adds entries directly.

    Step 1: fill the table with five scores; the worst is 100.
    Step 2: `qualifies` is the entry test -- 250 beats the worst (True),
       50 does not (False) -- and `add` inserts 250 in sorted position,
       keeping exactly five rows, each stamped with a timestamp.
    Step 3: a fresh game with score 350 dies of a blocked spawn: this
       time top_run is True (350 beats 100), the state event carries
       the flag AND the updated table [500, 400, 350, 300, 250] plus
       the all-time high of 500.
    Step 4: starting a new game clears the flag but KEEPS the table.

    This is the whole fireworks feature: qualify at death, celebrate
    once, carry the table to the UI, then reset the flag for the next
    run.
    """
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
    """The old single-score file format must migrate to the top-5 table.

    Step 1: write a file in the OLD format -- {"high_score": 777}, a
       bare int, no timestamps, no list.
    Step 2: load_table must upgrade it in place to the new format: a
       one-entry table [{"score": 777, "at": ""}] with an empty
       timestamp (the old format never recorded when the score was
       set).
    Step 3: the legacy `load` accessor still reports 777, so older
       callers (and the packaged app mid-upgrade) keep working.

    This protects owners of an existing install: their single saved
    score must survive the format change rather than be discarded as
    corrupt.
    """
    import json as json_mod

    path = tmp_path / "highscore.json"
    path.write_text(json_mod.dumps({"high_score": 777}))
    table = highscore.load_table(path)
    assert table == [{"score": 777, "at": ""}]
    assert highscore.load(path) == 777
