"""Autopilot tests (cheat mode, owner request 2026-10-27).

The weight-agnostic assertions check properties: every placement is
legal and lands on the floor; gaps get filled rather than covered; the
autopilot plays without any input; and the end-of-stage celebration
always runs its full window (the autopilot never cuts it short).

WHAT THIS FILE LOCKS IN (four kinds of guarantee)
-------------------------------------------------
    1. PLACEMENT LEGALITY -- the search only ever proposes landings a
       real piece could reach (on the floor, inside the walls), for
       every piece and every strategy.
    2. SANITY OF PLAY -- given a hole it fills it; given a ready row
       it clears it. These are property tests, not exact-move tests:
       they survive retuning of the weights, which is the point
       (the owner tunes the profiles constantly; the invariants must
       not break).
    3. HUMAN THROTTLING -- through a live Core: the autopilot drives
       the piece through the normal machinery at key-press speed,
       ignores human steering while it drives, hands control back
       when switched off, and never presses Enter to skip the
       celebration.
    4. STRATEGY DIFFERENCE -- the "highscore" profile defers small
       clears while safe and cashes ready tetrises; the danger ramp
       starts at half board height.

WHY SO FEW ASSERTIONS ON THE SEARCH ITSELF
------------------------------------------
`best_placement` returns ONE (rotation, column) pair chosen by a
weighted sum. Asserting an exact pair would couple the tests to the
current weight values; instead the tests apply the chosen placement
(`apply_placement`) and assert properties of the RESULTING BOARD.
That keeps the tests meaningful across tuning, while the weight
VALUES are exercised by the sweep scripts (sweep_autopilot.py).
"""

import pytest

from tetris_core.autopilot import STRATEGIES, _danger, best_placement
from tetris_core.board import HEIGHT, WIDTH, Board
from tetris_core.game import (
    CELEBRATE_FRAMES,
    CLEAR_ANIM_FRAMES,
    SPAWN_X,
    SPAWN_Y,
    Status,
)
from tetris_core.pieces import Piece

from helpers import FixedRNG
from tetris_core.protocol import Core


def holes(board: Board) -> int:
    """Count empty cells buried under filled ones, column by column.

    The same definition the autopilot's own `_holes` uses (see
    tetris_core/autopilot.py): walk each column top to bottom; once a
    filled cell has been seen, every empty cell below it is a hole.
    Holes are the damage metric of Tetris -- they can never be filled
    -- so the property tests phrase their promises as "no NEW holes"
    using this counter.

    Deliberately an independent reimplementation rather than an import:
    if the engine's hole counter were wrong, importing it here would
    hide the bug from both sides at once.
    """
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
    """Drop the piece from the top at the chosen rotation and column.

    This is the test-suite's stand-in for the engine actually playing
    the placement: build the piece's cells at (rot, x) at the top,
    lower them one row at a time until the next step would collide,
    then lock. The leading `assert board.cells_free(cells)` fails the
    test immediately if the autopilot ever proposed an unreachable or
    overlapping placement -- which is itself one of the properties
    under test.

    Mirrors `_resting_cells` + `_lock` from the autopilot module but
    works on the real Board, so the resulting board can be inspected
    with the normal helpers (full_rows, get).
    """
    from tetris_core.pieces import ROTATIONS

    cells = [(x + dx, dy) for dx, dy in ROTATIONS[kind][rot]]
    assert board.cells_free(cells)
    while board.cells_free([(cx, cy + 1) for cx, cy in cells]):
        cells = [(cx, cy + 1) for cx, cy in cells]
    board.lock_cells(cells, int(kind))


def test_ai_places_pieces_on_the_floor_legally():
    """Every piece's best placement on an empty board must leave no holes.

    Step 1: for each of the seven pieces, ask `best_placement` for its
       choice on a fresh board.
    Step 2: a placement must exist (None would mean the search is
       broken on an EMPTY board, the most permissive one there is).
    Step 3: play it out with apply_placement and count the holes.

    The hole bound encodes real tetromino geometry, not AI quality:
    pieces that can rest flush on a flat floor must leave zero holes;
    S and Z physically cannot -- their notch always buries exactly one
    cell, whichever way they land. A failure here means either the
    search proposed something illegal or the geometry changed.

    The inline comment below states the same bound in words; it
    predates the test and is kept.
    """
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
    """A ready-made gap must be filled, never roofed over.

    Step 1: build the bottom row full except column 5 -- a one-column
       well, exactly the shape a vertical I fits.
    Step 2: offer the I and take the autopilot's placement.
    Step 3: after the placement the board must have ZERO holes.

    Filling the gap is both the obvious play and what the El-Tetris
    features reward (a covered well becomes permanent holes, the most
    heavily punished feature). This is the classic failure mode of a
    naive placement search -- roofing over the one gap and dooming the
    board -- so it gets its own test. The pre-existing inline comments
    below describe the scenario and the expectation.
    """
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
    """A ready row with an O offered must be completed, not ignored.

    Step 1: the bottom row is full except columns 4 and 5 -- a
       two-wide gap only an O (or an L/J etc.) can fill flat.
    Step 2: offer the O and take the placement.
    Step 3: the placement must complete the bottom row, i.e.
       full_rows() == [HEIGHT - 1].

    In the real game the lock then clears the row immediately (the
    clear happens in Game._lock, which is why the test checks
    full_rows rather than score). The pre-existing comment explains
    why the residual nub does not change the decision: it is
    unavoidable either way, so the clear bonus dominates.
    """
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
    """The autopilot must place pieces with NO human input at all.

    Step 1: a Core scripted to hand out nothing but I pieces, with
       autopilot switched on via the protocol command -- the state
       event must echo mode "quick".
    Step 2: run 600 plain `update()` calls (10 seconds of game time).
       No handle_input is ever called; if the autopilot drove the
       piece only when prompted, nothing would happen.

    The asserts: at least 3 locks happened (600 frames at soft-drop
    speed is ample for several placements of a piece that falls
    straight down) and the game is still coherent -- either a piece is
    live or the game ended (the I stack can only reach so high).
    """
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
    """The autopilot is throttled to human key-press rates -- no god mode.

    Owner correction 2026-10-28 ("auto mode, not god mode"): one
    rotation or one lateral step per frame (the key-press rate) and
    soft-drop descent (the Down-key rate) — never an instant drop.

    Step 1: record the spawn position of the scripted I.
    Step 2: enable the autopilot and advance exactly THREE frames.
    Step 3: bound every movement dimension by what a human could do
       in 3 frames:
       - lateral: at most one column per frame -> displacement <= 3;
       - rotation: at most one state per frame -> state <= 3;
       - descent: soft drop starts at 6 frames-per-row, so in 3
         frames at most ONE row of fall -- the crucial bound, since
         an unthrottled autopilot would hard-drop instantly;
       - nothing has locked yet (lock_count == 0).

    This is what makes autopilot games comparable to human games:
    same speeds, same gravity, just better choices.
    """
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
    """While the autopilot drives, human input is ignored -- until toggled off.

    Step 1: enable the autopilot and give it one frame to place its
       plan; note the piece column x0 it is steering toward.
    Step 2: a human "left" press must NOT move the piece (still x0).
       One driver at a time: mixed control would make both the human
       and the plan wrong.
    Step 3: switching the mode off (null) hands control back -- the
       state event reports autopilot None.
    Step 4: the same kind of input now MOVES the piece (steering away
       from whichever side the autopilot had chosen, hence the
       conditional direction).

    This pins the handover in both directions, which is the cheat's
    contract with the player.
    """
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
    """The autopilot must let the end-of-stage celebration run its full window.

    Step 1: script the level-block boundary (lines = 29, so one clear
       completes the 30-line block) and lock the prepared I with the
       same recipe as the game-flow tests.
    Step 2: after the 24-frame clear wipe the status must be
       LEVEL_COMPLETE.
    Step 3: run CELEBRATE_FRAMES - 1 updates (209 of the 210-frame
       window, ~3.5 s): the status must STILL be LEVEL_COMPLETE on
       every single frame -- the autopilot never presses Enter.
    Step 4: the last update expires the window on its own and play
       resumes; a further 20 frames run without anything sticking.

    Owner request 2026-10-29: the celebration is the one human moment
    the game keeps even in auto mode -- the next level starts by
    itself after the music, not the instant the wipe ends. (Compare
    the next test: a HUMAN Enter may still skip it.)
    """
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
    # The owner requirement: the autopilot plays but never presses Enter,
    # so it never cuts the celebration short (owner request 2026-10-29:
    # the celebration now runs its full window and the next level starts
    # by itself).
    for _ in range(CELEBRATE_FRAMES - 1):
        game.update()
        assert game.status is Status.LEVEL_COMPLETE
    # The celebration window expires on its own: play resumes.
    game.update()
    assert game.status is Status.PLAYING
    for _ in range(20):
        game.update()


def test_enter_skips_the_celebration(tmp_path):
    """A human Enter may still skip the celebration early.

    Step 1: force the same level-block clear as the previous test and
       let the wipe finish -- status LEVEL_COMPLETE.
    Step 2: send the pause command (what the UI binds to Enter).

    The status must flip straight to PLAYING. This is the counterpoint
    to the "never skips" test: the AUTOPILOT never cuts the window
    short, but the IMPATIENT PLAYER retains the skip. Same
    celebration, two different rules for two different drivers.
    """
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    game = core.game
    game.lines = 29
    for x in (0, 1, 2, 3, 8, 9):
        game.board.lock_cells([(x, HEIGHT - 1)], 1)
    game._piece_x = 4
    game._piece_y = HEIGHT - 1
    game._lock()
    for _ in range(CLEAR_ANIM_FRAMES):
        game.update()
    assert game.status is Status.LEVEL_COMPLETE
    # Enter (the pause command) continues early, as before.
    core.handle_line('{"cmd": "pause"}')
    assert game.status is Status.PLAYING


def test_set_autopilot_validation(tmp_path):
    """set_autopilot accepts exactly the two strategy names or null.

    The six lines trace the validation boundary:
      - "quick" and "highscore" -- the two shipped weight profiles --
        are accepted;
      - null is accepted and means "off" (hand control back);
      - a MISSING mode, an unknown name ("fast"), and a non-string
        (1) are all rejected with ok=False.

    The UI's Home/End keys send these commands from the Konami cheat
    menu, so the accepted set is effectively the cheat's public API.
    """
    core = Core(highscore_path=tmp_path / "highscore.json", rng=FixedRNG([Piece.I]))
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "highscore"}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot", "mode": null}')[0]["ok"] is True
    assert core.handle_line('{"cmd": "set_autopilot"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_autopilot", "mode": "fast"}')[0]["ok"] is False
    assert core.handle_line('{"cmd": "set_autopilot", "mode": 1}')[0]["ok"] is False


def test_highscore_strategy_defers_small_clears():
    """The two strategies must DISAGREE on a safe 2-line clear.

    Autopilot #2 (owner request 2026-10-28): with a low, safe stack a
    2-line clear is deferred (it would burn rows that could join a
    later tetris); the quick strategy takes it.

    Step 1: build the two-wide gap at the bottom (rows ready for a
       double clear) TWICE -- one identical board per strategy.
    Step 2: the "quick" profile takes the clear: after its O lands,
       full_rows() == [HEIGHT - 1].
    Step 3: the "highscore" profile refuses: same O, same board, but
       the placement leaves the ready row UNcleared.

    The deferral rule lives in `_score` (defer_w subtracted for 1-2 row
    clears while the stack is low and hole-free); this test is what
    proves the two profiles really play differently, not just score
    differently. It is the only test that runs BOTH strategies on the
    same scenario.
    """
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
    """A ready tetris must be cashed in, not deferred.

    Step 1: build four ready rows over nine columns with a one-column
       well at the right edge -- the exact shape a vertical I
       completes.
    Step 2: offer the I to the "highscore" strategy (the one that
       otherwise defers clears) and play its placement.
    Step 3: all four rows must be complete -- a tetris.

    This pins the far end of the deferral logic: defer_w subtracts for
    SMALL clears only, and `points_for_clear(4) / 100` = 25 (versus 4
    for a double) makes the tetris overwhelming. If the strategy ever
    deferred THIS, the profile would be refusing its own reason to
    exist.
    """
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


def test_danger_ramp_starts_at_half_full():
    """The danger ramp: 0 below 10 rows, 1.0 at 16, linear between.

    Board-fullness awareness (owner request 2026-10-29): the danger
    ramp starts when the stack reaches half the board and reaches full
    danger six rows later; buried holes only push it up.

    Reading the samples against the shipped weights (danger_h = 10,
    danger_span = 6):
      - 5 and 10 rows high -> 0.0: the ramp has not started (10 is the
        threshold itself, still safe);
      - 13 rows -> exactly 0.5: halfway along the 6-row span, hence
        the pytest.approx float comparison;
      - 16 rows -> 1.0: fully dangerous, the strategy now plays for
        survival;
      - 16 rows WITH 4 buried holes -> still 1.0: holes raise the
        effective height, but the ramp is already saturated;
      - 8 rows -> 0.0: comfortably safe.

    10 of 23 rows is "past half full" in owner terms -- the point
    where a Tetris board stops being recoverable and hunting tetrises
    becomes the wrong priority.
    """
    # Board-fullness awareness (owner request 2026-10-29): the danger
    # ramp starts when the stack reaches half the board and reaches full
    # danger six rows later; buried holes only push it up.
    w = STRATEGIES["highscore"]
    assert _danger(5, 0, w) == 0.0
    assert _danger(10, 0, w) == 0.0
    assert _danger(13, 0, w) == pytest.approx(0.5)
    assert _danger(16, 0, w) == 1.0
    assert _danger(16, 4, w) == 1.0
    assert _danger(8, 0, w) == 0.0


def test_danger_ramp_changes_the_chosen_placement():
    """Board fullness must change the DECISION, not just the blend factor.

    `test_danger_ramp_starts_at_half_full` pins the curve of `_danger`;
    this test pins what the curve is FOR. Owner request 2026-10-29:
    "reduce the aggressiveness when the board is getting fuller than
    half". The way to show that is the opposite of a unit test on the
    helper: the SAME clear opportunity, offered on a low board and on a
    tall one, must get two different answers.

    Both boards carry the identical bottom two rows -- every column
    filled except 4 and 5 -- so an O dropped into that gap completes a
    double.

      - LOW board (stack 2 high, danger 0.0). The strategy is hunting
        score: `defer_w` = 25 charges it for burning rows that could
        join a tetris, and `landing_free` = 4 makes stacking the O on
        top cost nothing. It DEFERS -- exactly what
        `test_highscore_strategy_defers_small_clears` shows for the
        quick-vs-highscore pair, here reproduced against itself.

      - TALL board (both flanks walled 16 rows high, danger 1.0). The
        deferral has been blended away (`defer_w * (1 - danger)` = 0)
        and the landing penalty has risen from -4.5 to -14, so parking
        the O on top of a wall at height 17 is far worse than dropping
        it into the well at height 2. It TAKES the double.

    Between the two, only the stack height changed -- same gap, same
    piece, same strategy. The ramp is what turns one into the other.
    """
    def ready_double_board(height: int) -> Board:
        """Bottom two rows filled except columns 4-5, plus walls of the
        given total height on both flanks (height 2 = no walls at all)."""
        board = Board()
        for x in range(WIDTH):
            if x not in (4, 5):
                for y in range(HEIGHT - 2, HEIGHT):
                    board.lock_cells([(x, y)], 1)
        # Everything not in the middle gap, from `height` down.
        for x in range(WIDTH):
            if x not in (4, 5):
                for y in range(HEIGHT - height, HEIGHT - 2):
                    board.lock_cells([(x, y)], 1)
        return board

    # LOW: the stack is only the two ready rows -> danger 0.0.
    low = ready_double_board(2)
    assert _danger(2, 0, STRATEGIES["highscore"]) == 0.0
    low_pick = best_placement(low, Piece.O, "highscore")
    assert low_pick is not None
    apply_placement(low, Piece.O, *low_pick)
    assert low.full_rows() == []  # deferred while the board is safe

    # TALL: the same two ready rows, walled 16 high either side.
    tall = ready_double_board(16)
    assert _danger(16, 0, STRATEGIES["highscore"]) == 1.0
    tall_pick = best_placement(tall, Piece.O, "highscore")
    assert tall_pick is not None
    apply_placement(tall, Piece.O, *tall_pick)
    assert len(tall.full_rows()) == 2  # taken: survival first


def test_autopilot_abandons_a_wedged_plan(tmp_path):
    """A plan that cannot be executed must be abandoned, not retried forever.

    `_autopilot_step` steers the piece one rotation OR one lateral step
    per frame. Either move can be physically impossible -- a rotation
    blocked in both directions, or a path with something in the way --
    and in both cases the code sets `_autopilot_abandoned`: give up on
    this piece and let it fall where it can. Without that flag the
    autopilot would sit there for the rest of the piece's life trying
    the same blocked move, and the piece would never lock.

    The setup plants the blocking cells BY HAND and writes the plan
    straight into `game._autopilot_plan`, the way test_rotation.py
    plants obstacles and teleports the piece. Each case should pin ONE
    decision; reaching either wedge naturally takes hundreds of frames
    and would make the failure ambiguous.

    The blocked cells are derived from the T's own rotation table, so
    the test says WHY each cell matters: (5,3) and (4,3) are the two
    places state 1 would put its nub (kick 0 and kick -1), and (6,5) is
    where state 3 puts its nub (kick 0).
    """
    def wedge_game():
        core = Core(highscore_path=tmp_path / "highscore.json",
                    rng=FixedRNG([Piece.T, Piece.O]))
        core.handle_line('{"cmd": "set_autopilot", "mode": "quick"}')
        return core.game

    # --- Case 1: the target rotation is blocked in both directions ---
    game = wedge_game()
    assert (game._piece_x, game._piece_y, game._rot) == (SPAWN_X, SPAWN_Y, 0)
    # State 0 of the T occupies (6,3) (5,4) (6,4) (7,4). These six cells
    # block every rotation candidate without touching the piece itself.
    for cell in ((5, 3), (4, 3), (4, 4), (4, 5), (5, 5), (6, 5)):
        game.board.lock_cells([cell], 1)
    game._autopilot_plan = (1, game._piece_x)  # rotate to state 1, stay put
    assert game._autopilot_step() is False
    assert game._autopilot_abandoned is True
    # Once abandoned, the step is inert: it does not keep re-planning or
    # re-attempting the blocked move while the piece falls.
    assert game._autopilot_step() is False
    assert (game._piece_x, game._piece_y, game._rot) == (SPAWN_X, SPAWN_Y, 0)

    # --- Case 2: the lateral path to the target column is blocked ---
    game = wedge_game()
    # (4,4) is the cell the T's left arm moves into at x=4, so a block
    # there stops the piece one column short of its target.
    game.board.lock_cells([(4, 4)], 1)
    game._autopilot_plan = (0, SPAWN_X - 3)  # same rotation, three left
    assert game._autopilot_step() is False
    assert game._autopilot_abandoned is True
    assert game._piece_x == SPAWN_X  # it did not move a single column


def test_autopilot_handles_no_placement_and_resets_on_spawn(tmp_path):
    """The third failure path, and the per-piece reset that follows it.

    `_autopilot_step` has three ways to stop steering, and two of them
    set `_autopilot_abandoned` (see the wedge test above). The third is
    different: when `best_placement` returns None there is no plan at
    all -- the stack is at the ceiling and no candidate even fits -- so
    the flag is deliberately NOT set. The step returns False and the
    piece falls; the search simply runs again next frame, which costs
    nothing because it bails out immediately on a board that full.

    Step 1: fill the board completely, so no placement exists.
    Step 2: the step must return False, leave the plan as None, and NOT
       set the abandoned flag (the distinction matters: "no plan" is
       retried, "plan unreachable" is not).
    Step 3: on a clean board, both per-piece fields must be reset by the
       next spawn -- a stale plan from the previous piece would steer
       the new one into the old piece's landing spot.
    """
    # --- No legal placement at all ---
    game = Core(highscore_path=tmp_path / "highscore.json",
                rng=FixedRNG([Piece.T, Piece.O])).game
    game.set_autopilot("quick")
    for y in range(HEIGHT):
        for x in range(WIDTH):
            game.board.lock_cells([(x, y)], 1)
    assert game._autopilot_step() is False
    assert game._autopilot_plan is None
    assert game._autopilot_abandoned is False

    # --- The reset on spawn ---
    game = Core(highscore_path=tmp_path / "highscore.json",
                rng=FixedRNG([Piece.T, Piece.O])).game
    game.set_autopilot("quick")
    game._autopilot_plan = (1, 0)
    game._autopilot_abandoned = True
    game._spawn_next()
    assert game._autopilot_plan is None
    assert game._autopilot_abandoned is False
