"""Game state machine and 60 Hz frame update (Tengen rules, spec 4).

This is the heart of the engine: it owns the board, the current piece, the
score, and the status, and it advances all of them by exactly one frame
per `update()` call.

THE FRAME UPDATE, IN ORDER
---------------------------
`update()` runs these steps in this order, and the order matters:

    1. STATUS CHECKS -- a celebration or a paused game does nothing else.
    2. CLEAR ANIMATION -- if rows are dissolving, that is the whole frame.
    3. DAS -- apply any auto-repeat movement from a held arrow key.
    4. AUTOPILOT -- if the cheat autopilot is on, drive the piece.
    5. GRAVITY -- let the piece fall one row if its counter expired.
    6. LOCK DELAY -- if the piece is resting, count the grace frames and
       lock when the window expires.

Two design rules run through the whole file:
  - The UI never computes a rule; the UI only sends inputs and renders
    the state this class produces.
  - The autopilot does not get special powers. It drives the SAME piece
    through the SAME movement, rotation and gravity code a human uses --
    it just chooses which key to press (spec 4.11).
"""

from __future__ import annotations


from enum import Enum

from . import autopilot
from . import highscore
from .board import HEIGHT, Board, HIDDEN_ROWS
from .gravity import frames_per_row, soft_drop_fpr
from .pieces import Piece, ROTATIONS
from .rng import PieceRNG
from .scoring import (
    MAX_LEVEL,
    placement_points,
    points_for_clear,
    stage_lines_for_level,
)
from .stats import PieceStats

# Spawn (spec 4.1): the piece bounding box has its left side at column 5.
# Owner decision 2026-10-24: spawn at the top of the visible playfield
# (SPAWN_Y = HIDDEN_ROWS), not hidden above it — the next piece must show
# immediately after the previous one locks. Game over triggers when the
# spawn cells are blocked by the stack (spec 4.8).
SPAWN_X = 5
SPAWN_Y = HIDDEN_ROWS

# DAS (spec 4.7): delay before auto-repeat and repeat rate, in frames.
# VERIFY: UNVERIFIED PLACEHOLDER values (open item).
DAS_DELAY = 14
DAS_REPEAT = 4

# Lock delay (spec 4.4): owner decision 2026-10-24 — a short grace window
# while the piece rests, so the land-and-slide trick works without the
# piece lingering (a full "1 drop" was tried and felt too long): a fixed
# 10 frames, capped by the level's frames-per-row so the window keeps
# shrinking as gravity speeds up. It does not reset on movement, and
# sliding off a ledge cancels it (gravity resumes; a fresh window starts
# at the next landing).
LOCK_DELAY_FRAMES = 10


def lock_delay_frames(level: int) -> float:
    return min(LOCK_DELAY_FRAMES, frames_per_row(level))


# Line-clear dissolve (spec 4.5): completed rows stay visible and flicker
# for this many frames before they are removed and the next piece spawns,
# as in the owner's reference png/screenshot_11.png. The core drives the
# timing and reports `clearing: {rows, frame}` in the state event; the UI
# only renders the flicker (owner request 2026-10-24).
CLEAR_ANIM_FRAMES = 24

# End-of-stage celebration (spec 5, owner request 2026-10-29): clearing a
# 30-line block freezes the game for the celebration track (06 End of
# Stage, or 09 Victory on milestone levels), then the next level starts
# by itself -- no Enter needed. The window is long enough for either
# track to play once (06 is 2.48 s, 09 is 3.24 s); Enter still skips
# ahead for the impatient.
CELEBRATE_FRAMES = 210

# Locked-piece color index per level (spec 6.2): UNVERIFIED PLACEHOLDER
# table; the owner must supply the per-level indices sampled from Tengen
# captures (open item). The UI maps the index to a hex color in theme.ts.
# Locked-cell color cycle (spec 6.2): owner decision 2026-10-24 — the
# locked color changes with the level and repeats every 10 levels
# (0 grayish white, 1 red, 2 goldish yellow, 3 blue, 4 yellow, 5 pink,
# 6 green, 7 tortoise, 8 purple, 9 green again; level 10 back to 0).
# The UI indexes its LOCKED_COLORS table with this value.
LOCKED_COLOR_INDICES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)


class Status(Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    LEVEL_COMPLETE = "level_complete"
    GAME_OVER = "game_over"


def locked_color_index(level: int) -> int:
    return LOCKED_COLOR_INDICES[level % len(LOCKED_COLOR_INDICES)]


class Game:
    """Owns all game state. One update() call advances one 60 Hz frame."""

    def __init__(self, highscore_path=None, rng=None) -> None:
        self._highscore_path = highscore_path
        self._rng = rng if rng is not None else PieceRNG()
        self.high_score = highscore.load(highscore_path)
        self.top_scores = highscore.load_table(highscore_path)
        self.top_run = False
        self.autopilot: str | None = None  # None | "quick" | "highscore"
        self._autopilot_plan: tuple[int, int] | None = None
        self._autopilot_abandoned = False
        self.frame = 0
        self.new_game(0)

    # ------------------------------------------------------------------
    # Commands (protocol layer calls these)
    # ------------------------------------------------------------------

    def new_game(
        self,
        level: int = 0,
        music: str | None = None,
        handicap: int = 0,
    ) -> None:
        level = max(0, min(level, MAX_LEVEL))
        self.music = music
        self.board = Board()
        # Handicap rows (owner request 2026-10-25): unfinished garbage
        # rows at the bottom of the playfield — each with one random
        # hole — chosen on the title screen (0/3/6/9/12).
        if handicap > 0:
            handicap = min(handicap, HEIGHT - 1)
            for i in range(handicap):
                row = HEIGHT - 1 - i
                hole = self._rng.hole_column()
                self.board.lock_cells(
                    [(x, row) for x in range(10) if x != hole], int(Piece.I)
                )
        self.score = 0
        self.lines = 0
        self.level = level
        # The next stage boundary is tracked independently of the displayed
        # level. The level caps at 17, but 800, 850, ... are still real
        # stage boundaries that pay and celebrate.
        self._next_stage_line = stage_lines_for_level(self.level)
        # Clear awards accumulate here and are credited once, at stage end.
        # They are not paid immediately on each clear.
        self._pending_stage_award = 0
        self.stats = PieceStats()
        self.status = Status.PLAYING
        self._piece_kind: Piece | None = None
        self._piece_x = 0
        self._piece_y = 0
        self._rot = 0
        self._gravity_counter = 0
        self._gravity_threshold = 0
        self._rest_frames = 0
        self._soft_drop = False
        self._landing_soft_drop = False
        self._soft_held = 0
        self._das_dir = 0
        self._das_counter = 0
        self._das_repeating = False
        self._clearing_rows: list[int] | None = None
        self._clearing_frame = 0
        self._celebrate = False
        self._celebrate_frames = 0
        self.top_run = False
        self.lock_count = 0
        self.clear_count = 0
        self.next_piece: Piece = self._rng.next_piece()
        self._spawn_next()

    def set_music(self, music: str | None) -> bool:
        """Cheat (owner request 2026-10-25): change the gameplay music
        mid-game (the UI cycles tracks with the backquote key while the
        Konami cheat is active)."""
        if self.status is not Status.PLAYING:
            return False
        self.music = music
        return True

    def set_autopilot(self, mode: str | None) -> None:
        """Cheat autopilot control (owner request 2026-10-27, strategies
        2026-10-28): with the Konami cheat active, the UI drives this —
        Home selects "highscore", End selects "quick", either key turns
        it off. While on, the autopilot picks and executes placements at
        human input speed; human movement inputs are ignored. The
        end-of-stage celebration is never cut short — the autopilot only
        plays, it does not press Enter, so the celebration runs its full
        window and the next level starts by itself (owner request
        2026-10-29). The mode persists across games."""
        self.autopilot = mode
        self._autopilot_plan = None
        self._autopilot_abandoned = False
        if mode is None:
            # The autopilot held soft drop; hand back a clean key state.
            self._soft_drop = False

    def pause(self) -> None:
        if self.status is Status.PLAYING:
            # A key-up can arrive after the pause (or be lost entirely when
            # the window loses focus). Clear the held state here so resuming
            # never inherits a stuck DAS or soft-drop flag.
            self._clear_held_input()
            self.status = Status.PAUSED
        elif self.status is Status.PAUSED:
            self.status = Status.PLAYING
        elif self.status is Status.LEVEL_COMPLETE:
            # Enter during the end-of-stage celebration (owner request
            # 2026-10-25): stop it and continue play; the next piece
            # spawns now (it was deferred by the celebration).
            self._resume_after_celebration()

    def _clear_held_input(self) -> None:
        """Drop every held-key latch without touching the piece."""
        self._stop_das()
        self._soft_drop = False
        self._soft_held = 0

    def _resume_after_celebration(self) -> None:
        """Leave the end-of-stage celebration and start the next level."""
        self._clear_held_input()
        self.status = Status.PLAYING
        self._celebrate_frames = 0
        self._spawn_next()

    def handle_input(self, action: str) -> None:
        # Releases are accepted in EVERY state. A key can be released while
        # paused, during a celebration, or after focus was lost; dropping the
        # release would leave the core's held-key latch armed and the piece
        # would keep moving when play resumes.
        if action == "left_off":
            if self._das_dir == -1:
                self._stop_das()
            return
        if action == "right_off":
            if self._das_dir == 1:
                self._stop_das()
            return
        if action == "soft_drop_off":
            self._soft_drop = False
            self._soft_held = 0
            return
        if self.status is not Status.PLAYING:
            return
        if self.autopilot:
            # The autopilot owns the piece while it drives (owner
            # request 2026-10-27); human movement inputs are ignored.
            return
        if action == "left":
            self._start_das(-1)
        elif action == "right":
            self._start_das(1)
        elif action == "soft_drop_on":
            self._soft_drop = True
        elif action == "rotate_cw":
            self._try_rotate(1)
        elif action == "rotate_ccw":
            self._try_rotate(-1)
        else:
            raise ValueError(f"unknown action: {action!r}")

    # ------------------------------------------------------------------
    # Frame update (60 Hz)
    # ------------------------------------------------------------------

    def update(self) -> bool:
        """Advance one frame. Returns True if observable state changed.

        The return value is how the protocol layer decides whether to
        send a state event: an idle frame (nothing moved, nothing
        cleared) costs no message and no UI redraw.
        """
        # ---- Step 1: status gates -------------------------------------
        if self.status is Status.LEVEL_COMPLETE:
            # End-of-stage celebration (owner request 2026-10-29): the
            # celebration track plays once, then the next level starts
            # automatically. Nothing else may happen during this window.
            #
            # Only the entry and exit frames are observable. The timer is
            # internal; emitting an identical snapshot for every one of the
            # 210 frames made the UI redraw a static board hundreds of times.
            self._celebrate_frames += 1
            if self._celebrate_frames >= CELEBRATE_FRAMES:
                self._resume_after_celebration()
                return True
            return False
        if self.status is not Status.PLAYING:
            # Paused or game over: the game is frozen.
            return False
        self.frame += 1
        # ---- Step 2: the line-clear dissolve owns the frame -----------
        if self._clearing_rows is not None:
            # Line-clear dissolve (spec 4.5): the completed rows flicker
            # in place; afterwards they vanish and the next piece spawns.
            # While this runs the piece does not exist yet, so the rest
            # of the frame update is skipped entirely.
            self._clearing_frame += 1
            if self._clearing_frame >= CLEAR_ANIM_FRAMES:
                # The animation is over: actually remove the rows now.
                self.board.clear_rows(self._clearing_rows)
                self._clearing_rows = None
                if self._celebrate:
                    # End of stage (owner request 2026-10-25/29): freeze
                    # for the celebration music (06/09 in the UI); the
                    # next level starts by itself when the track is done
                    # (Enter skips ahead).
                    self._celebrate = False
                    self.status = Status.LEVEL_COMPLETE
                    self._celebrate_frames = 0
                else:
                    self._spawn_next()
            return True
        # ---- Step 3: held-arrow auto-repeat (DAS) --------------------
        changed = self._handle_das()
        # ---- Step 4: the autopilot drives the piece, if enabled ------
        if self.autopilot and self._piece_kind is not None:
            # Autopilot (owner request 2026-10-27, throttled 2026-10-28):
            # drive the piece toward the planned placement at human
            # input speed; the gravity, lock-delay, and clear machinery
            # below run unchanged underneath it.
            changed |= self._autopilot_step()
        # ---- Step 5: gravity ------------------------------------------
        if self._can_move(0, 1):
            # Airborne: the rest window is cancelled (spec 4.4). Gravity
            # moves the piece down one row when its counter expires; a
            # fresh window starts at the next landing.
            self._rest_frames = 0
            # Falling resumed, so the previous landing's drop state no
            # longer applies (for example after sliding off a ledge).
            self._landing_soft_drop = False
            changed |= self._apply_gravity()
            if self._can_move(0, 1):
                # Still airborne after gravity: nothing else to do this
                # frame (the piece did not land).
                return changed
        # ---- Step 6: lock delay ---------------------------------------
        # The piece is resting on the floor/stack this frame (the landing
        # frame counts as the first resting frame). It keeps a grace window
        # of one gravity interval ("1 drop", spec 4.4): the player can still
        # move or rotate it until the window expires.
        #
        # Capture the drop state at FIRST contact only. Releasing Down
        # during the lock delay must not erase the fact that Down was held
        # when the piece landed. Slides along the floor and grounded
        # rotations preserve this value; sliding off a ledge clears it in
        # the airborne branch above and captures again at the next contact.
        if self._rest_frames == 0:
            self._landing_soft_drop = self._soft_drop
        self._rest_frames += 1
        if self._rest_frames > lock_delay_frames(self.level):
            # The window expired: freeze the piece into the board.
            self._lock()
            return True
        return changed

    def set_level(self, level: int) -> bool:
        """Cheat (owner request 2026-10-25): jump to the given level
        mid-game. Gravity and the locked color change immediately; the
        next stage boundary moves with the new level.

        The jump anchors at the start of the current stage, preserving
        the progress already made inside it. Without that, selecting
        level 5 at line 30 would make line 31 jump straight to level 6
        (the old whole-run line total would be counted again).
        """
        if self.status is not Status.PLAYING:
            return False
        stage_start = self._next_stage_line - stage_lines_for_level(self.level)
        self.level = max(0, min(level, 9))
        self._next_stage_line = stage_start + stage_lines_for_level(self.level)
        return True

    # ------------------------------------------------------------------
    # Read accessors
    # ------------------------------------------------------------------

    @property
    def piece_kind(self) -> Piece | None:
        return self._piece_kind

    @property
    def clearing(self) -> tuple[list[int], int] | None:
        """(board rows, frame) while the clear dissolve runs, else None."""
        if self._clearing_rows is None:
            return None
        return (self._clearing_rows, self._clearing_frame)

    @property
    def music_phase(self) -> str:
        """Which music the UI should play (owner request 2026-10-25):
        "gameplay" (the selected track), "level_complete" (06, played
        once), "milestone" (09, when a level 9/19/29... was cleared, i.e.
        the new level is a multiple of 10), or "game_over" (08)."""
        if self.status is Status.LEVEL_COMPLETE:
            return "milestone" if self.level % 10 == 0 else "level_complete"
        if self.status is Status.GAME_OVER:
            return "game_over"
        return "gameplay"

    def piece_cells(self) -> list[tuple[int, int]]:
        """Absolute (x, y) cells of the current piece on the board."""
        if self._piece_kind is None:
            return []
        return [
            (x + self._piece_x, y + self._piece_y)
            for x, y in ROTATIONS[self._piece_kind][self._rot]
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _can_move(self, dx: int, dy: int) -> bool:
        cells = [(x + dx, y + dy) for x, y in self.piece_cells()]
        return self.board.cells_free(cells)

    def _autopilot_step(self) -> bool:
        """Autopilot step (owner request 2026-10-27, throttled
        2026-10-28): drive the piece toward the planned (rotation,
        column) at human input speed — never faster than a player holding
        Down and tapping X. One rotation or one lateral step per frame
        (the discrete key-press rate), descending at soft-drop speed via
        the normal gravity machinery (the Down-key rate). The plan is
        computed once per piece; if the way is blocked or no legal
        placement exists, the piece is abandoned to fall naturally.

        THE THROTTLE IS THE POINT
        --------------------------
        The autopilot gets no special abilities: it moves the piece by
        calling the same `_try_rotate` and `_move` methods a human
        keypress reaches. At most ONE of those happens per frame, which
        is the rate at which a person can tap X or mash an arrow. It
        also holds soft drop, so the piece descends at the Down-key rate.

        The consequence is that the autopilot's games are directly
        comparable to human games — it is "auto mode", not "god mode"
        (owner request 2026-10-28).
        """
        assert self._piece_kind is not None  # caller checked
        # Descend at soft-drop speed (the fastest a player can drop).
        # Setting the flag is enough: the normal gravity machinery below
        # picks it up, so the piece falls exactly like a held Down key.
        self._soft_drop = True
        if self._autopilot_abandoned:
            # The plan is unreachable; just let the piece fall.
            return False
        if self._autopilot_plan is None:
            # Plan once per piece, not once per frame: the search is the
            # expensive part, and the board does not change while the
            # piece is still in the air.
            self._autopilot_plan = autopilot.best_placement(
                self.board, self._piece_kind, self.autopilot or "quick"
            )
        if self._autopilot_plan is None:
            return False  # stack at the ceiling; let it fall
        rot, x = self._autopilot_plan
        # One rotation per frame toward the target (the X-key rate);
        # the rotation takes the shortest direction, other way if
        # blocked.
        if self._rot != rot:
            # `% 4` makes the direction wrap correctly: a rotation from
            # state 3 to state 0 is one step FORWARD (+1), not three
            # steps backward.
            direction = 1 if (rot - self._rot) % 4 <= 2 else -1
            # Try the short way first; if that is blocked, try the other
            # way around (a rotation may be reachable only counter-clockwise).
            if self._try_rotate(direction) or self._try_rotate(-direction):
                return True
            # Neither direction works: the piece is wedged. Abandon it.
            self._autopilot_abandoned = True
            return False
        # One lateral step per frame (the arrow key-mash rate).
        if self._piece_x != x:
            dx = 1 if x > self._piece_x else -1
            if self._move(dx):
                return True
            # The path is blocked (something is in the way). Abandon the
            # plan rather than stalling: the piece falls and lands where
            # it can, which is better than never locking.
            self._autopilot_abandoned = True
            return False
        return False

    def _move(self, dx: int) -> bool:
        if self._piece_kind is None:
            return False
        if self._can_move(dx, 0):
            self._piece_x += dx
            return True
        return False

    def _start_das(self, direction: int) -> None:
        self._das_dir = direction
        self._das_counter = 0
        self._das_repeating = False
        self._move(direction)

    def _stop_das(self) -> None:
        self._das_dir = 0
        self._das_counter = 0
        self._das_repeating = False

    def _handle_das(self) -> bool:
        """Auto-repeat for left/right, as frame counters (spec 4.7).

        DAS = Delayed Auto Shift: the key moves the piece ONCE
        immediately, waits `DAS_DELAY` frames, and then repeats every
        `DAS_REPEAT` frames for as long as the key is held.

        The state machine has two phases:
          - not repeating yet: count up to DAS_DELAY, then make the first
            auto-shift move and switch to the repeating phase.
          - repeating: count up to DAS_REPEAT, then move again.

        Both values are frame counters in Python, not in the UI — the
        browser sends one "left" on keydown and one "left_off" on keyup,
        and everything between is decided here (spec 2.4).
        """
        if self._das_dir == 0:
            return False  # no arrow key held
        self._das_counter += 1
        if not self._das_repeating:
            # Phase 1: waiting for the initial delay to expire.
            if self._das_counter >= DAS_DELAY:
                self._das_repeating = True
                self._das_counter = 0
                return self._move(self._das_dir)
            return False
        # Phase 2: repeating at the steady rate.
        if self._das_counter >= DAS_REPEAT:
            self._das_counter = 0
            return self._move(self._das_dir)
        return False

    def _apply_gravity(self) -> bool:
        """Move the piece down one row if the fall timer has expired.

        Gravity is measured in quarter-frame units so the cartridge's
        fractional intervals (5.5, 3.75, ...) are exact. Each tick adds 4
        units; a row is dropped when the accumulator reaches the interval
        times 4. At most one row is dropped per tick.

        When the effective speed increases (Down pressed, or a level-up),
        any excess accumulated time is discarded rather than banked: it
        must not cause a burst of drops or a backlog that keeps dropping
        after the speed changes back.
        """
        if self._soft_drop:
            # Count how long Down has been held: the soft drop accelerates
            # the longer it is held (spec 4.3).
            self._soft_held += 1
            fpr = soft_drop_fpr(frames_per_row(self.level), self._soft_held)
        else:
            # Not soft dropping: reset the hold counter so the next soft
            # drop starts from the slow end of the curve again.
            self._soft_held = 0
            fpr = frames_per_row(self.level)
        threshold = max(1, int(round(fpr * 4)))
        if threshold < self._gravity_threshold and self._gravity_counter >= threshold:
            # Speed increased: keep at most one tick of progress, not the
            # whole stale backlog.
            self._gravity_counter = threshold - 4
        self._gravity_threshold = threshold
        self._gravity_counter += 4
        if self._gravity_counter >= threshold:
            self._gravity_counter -= threshold
            self._piece_y += 1
            return True
        return False

    def _try_rotate(self, direction: int) -> bool:
        """Rotate with the Tengen one-square kick (spec 4.2).

        Try the rotation in place; if it overlaps anything (wall, floor, or
        stack), try shifting one square to the left; reject if that also
        fails. VERIFY (spec 4.2): whether the kick also applies to the
        right wall and floor contact.

        THE KICK IS THE WHOLE RULE
        ---------------------------
        Two candidates are tried, in order:
            kick = 0  -- rotate where the piece is
            kick = -1 -- rotate one square to the LEFT
        The first one whose cells are all free wins. There is no
        right-hand kick and no floor kick in this table (both are still
        VERIFY items in the spec).

        Note that the rotation is anchored to the piece's bounding-box
        top-left corner (see pieces.py) — the piece does NOT spin around
        its centre the way it does in Nintendo Tetris.
        """
        if self._piece_kind is None:
            return False
        # The new rotation state, wrapping in both directions.
        new_rot = (self._rot + direction) % 4
        base = ROTATIONS[self._piece_kind][new_rot]
        for kick in (0, -1):
            # Place the rotated shape at the piece's current position,
            # shifted by the kick amount.
            cells = [
                (x + kick + self._piece_x, y + self._piece_y) for x, y in base
            ]
            if self.board.cells_free(cells):
                # Accept: update the rotation AND the position, because a
                # kicked piece is now one column further left.
                self._rot = new_rot
                self._piece_x += kick
                return True
        return False

    def _lock(self) -> None:
        """Freeze the piece into the board and resolve any line clears.

        The order here is the spec's order (spec 4.5): the piece is
        written into the grid FIRST, then the completed rows are found,
        then the score/lines/level are updated immediately — even though
        the rows themselves stay on screen for the dissolve animation.

        Scoring has two parts:
          - placement points for the lock itself, using the level and
            drop state at landing (before any stage advance);
          - clear awards accumulated into a pending stage award, paid
            once when the stage ends.
        """
        if self._piece_kind is None:
            return
        # Landing pop (owner request 2026-10-25): every lock bumps the
        # counter; the state event carries it and the UI plays a
        # synthesized brick-thud on each increment.
        self.lock_count += 1
        cells = self.piece_cells()
        # Write the piece's four cells into the grid. The value stored is
        # the piece index; the UI paints it with the LEVEL's locked color
        # (spec 6.2), which is why the grid stores the piece kind and not
        # a color.
        self.board.lock_cells(cells, int(self._piece_kind))
        # Placement points are awarded exactly once per lock. The row
        # height is the lowest occupied cell, with 0 on the bottom visible
        # row (the disassembly's bitmap-scan mapping).
        row_height = (HEIGHT - 1) - max(y for _, y in cells)
        self.score += placement_points(
            self.level, self._landing_soft_drop, row_height
        )
        # There is no active piece until the next one spawns. During the
        # clear animation this is what makes the UI draw no piece.
        self._piece_kind = None
        # Which rows are now complete?
        rows = self.board.full_rows()
        if not rows:
            # No clear: spawn the next piece immediately.
            self._spawn_next()
            return
        # Row-clear sound (owner request 2026-10-25): one counter bump
        # per clear event (1-4 rows); the UI plays a dismantle "poo-ch"
        # on each increment.
        self.clear_count += 1
        # Lines completed (spec 4.5): lines update immediately; the rows
        # dissolve in place for CLEAR_ANIM_FRAMES before being removed and
        # the next piece spawns.
        self.lines += len(rows)
        # The clear award (100/400/900/2500) is NOT paid immediately. It
        # accumulates in the pending stage award and is credited once the
        # stage ends. This is the cartridge's stage-payout rule.
        self._pending_stage_award += points_for_clear(len(rows))
        # Stage boundary crossed? Pay the pending award once, advance the
        # displayed level (capped at 17), and schedule the celebration.
        # The next boundary is tracked separately so 800/850/... still
        # pay after the cap.
        while self.lines >= self._next_stage_line:
            self._complete_stage()
        # Remember the rows and start the dissolve animation. The rows
        # are still IN the grid at this point -- they are removed later,
        # when the animation ends in `update()`.
        self._clearing_rows = rows
        self._clearing_frame = 0

    def _complete_stage(self) -> None:
        """Pay the pending stage award and open the next stage."""
        self.score += self._pending_stage_award
        self._pending_stage_award = 0
        self.level = min(MAX_LEVEL, self.level + 1)
        self._next_stage_line += stage_lines_for_level(self.level)
        self._celebrate = True

    def _spawn_next(self) -> None:
        """Promote the previewed piece to the active piece, or end the game.

        The piece order is: `next_piece` becomes active, and a NEW piece
        is drawn into the preview slot. Doing it in this order means the
        preview always shows the piece AFTER the active one.
        """
        kind = self.next_piece
        self.next_piece = self._rng.next_piece()
        self._piece_kind = kind
        # Spawn position (spec 4.1): the bounding box's left side at
        # column 5, and the box's TOP at the top of the VISIBLE playfield
        # (SPAWN_Y = HIDDEN_ROWS), so the piece is visible immediately
        # after the previous one locks.
        self._piece_x = SPAWN_X
        self._piece_y = SPAWN_Y
        self._rot = 0  # every piece spawns in rotation state 0
        # Reset the per-piece timers.
        self._gravity_counter = 0
        self._gravity_threshold = 0
        self._soft_held = 0
        self._rest_frames = 0
        # A fresh piece has not landed yet; do not inherit the previous
        # piece's soft-drop-at-contact state.
        self._landing_soft_drop = False
        # The autopilot must plan again for the new piece (the board
        # changed, so the old plan is worthless).
        self._autopilot_plan = None  # replan for the new piece
        self._autopilot_abandoned = False
        if not self.board.cells_free(self.piece_cells()):
            # Game over: the new piece cannot spawn (spec 4.8). Top-5
            # runs enter the table and set top_run for the fireworks
            # screen (owner request 2026-10-25).
            self._piece_kind = None
            self.status = Status.GAME_OVER
            self.high_score = max(self.high_score, self.score)
            # Does this run make the top 5?
            self.top_run = highscore.qualifies(self.score, self._highscore_path)
            if self.top_run:
                # It qualifies: write it to the table and refresh the
                # HIGH SCORE readout with the new best.
                self.top_scores = highscore.add(self.score, self._highscore_path)
                self.high_score = max(self.high_score, self.top_scores[0]["score"])
            return
        # The piece spawned successfully: count it for the stats panel.
        self.stats.increment(kind)
