"""Game state machine and 60 Hz frame update (Tengen rules, spec 4)."""

from __future__ import annotations


from enum import Enum

from . import autopilot
from . import highscore
from .board import HEIGHT, Board, HIDDEN_ROWS
from .gravity import frames_per_row, soft_drop_fpr
from .pieces import Piece, ROTATIONS
from .rng import PieceRNG
from .scoring import (
    BLOCK_BONUS_POINTS,
    block_bonuses,
    level_for_lines,
    points_for_clear,
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


def lock_delay_frames(level: int) -> int:
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
        if level < 0:
            level = 0
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
        self._start_level = level
        self.level = level
        self.stats = PieceStats()
        self.status = Status.PLAYING
        self._piece_kind: Piece | None = None
        self._piece_x = 0
        self._piece_y = 0
        self._rot = 0
        self._gravity_counter = 0
        self._rest_frames = 0
        self._soft_drop = False
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
            self.status = Status.PAUSED
        elif self.status is Status.PAUSED:
            self.status = Status.PLAYING
        elif self.status is Status.LEVEL_COMPLETE:
            # Enter during the end-of-stage celebration (owner request
            # 2026-10-25): stop it and continue play; the next piece
            # spawns now (it was deferred by the celebration).
            self._resume_after_celebration()

    def _resume_after_celebration(self) -> None:
        """Leave the end-of-stage celebration and start the next level."""
        self.status = Status.PLAYING
        self._celebrate_frames = 0
        self._spawn_next()

    def handle_input(self, action: str) -> None:
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
        elif action == "left_off":
            if self._das_dir == -1:
                self._stop_das()
        elif action == "right_off":
            if self._das_dir == 1:
                self._stop_das()
        elif action == "soft_drop_on":
            self._soft_drop = True
        elif action == "soft_drop_off":
            self._soft_drop = False
            self._soft_held = 0
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
        """Advance one frame. Returns True if observable state changed."""
        if self.status is Status.LEVEL_COMPLETE:
            # End-of-stage celebration (owner request 2026-10-29): the
            # celebration track plays once, then the next level starts
            # automatically.
            self._celebrate_frames += 1
            if self._celebrate_frames >= CELEBRATE_FRAMES:
                self._resume_after_celebration()
            return True
        if self.status is not Status.PLAYING:
            return False
        self.frame += 1
        if self._clearing_rows is not None:
            # Line-clear dissolve (spec 4.5): the completed rows flicker
            # in place; afterwards they vanish and the next piece spawns.
            self._clearing_frame += 1
            if self._clearing_frame >= CLEAR_ANIM_FRAMES:
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
        changed = self._handle_das()
        if self.autopilot and self._piece_kind is not None:
            # Autopilot (owner request 2026-10-27, throttled 2026-10-28):
            # drive the piece toward the planned placement at human
            # input speed; the gravity, lock-delay, and clear machinery
            # below run unchanged underneath it.
            changed |= self._autopilot_step()
        if self._can_move(0, 1):
            # Airborne: the rest window is cancelled (spec 4.4). Gravity
            # moves the piece down one row when its counter expires; a
            # fresh window starts at the next landing.
            self._rest_frames = 0
            changed |= self._apply_gravity()
            if self._can_move(0, 1):
                return changed
        # The piece is resting on the floor/stack this frame (the landing
        # frame counts as the first resting frame). It keeps a grace window
        # of one gravity interval ("1 drop", spec 4.4): the player can still
        # move or rotate it until the window expires.
        self._rest_frames += 1
        if self._rest_frames > lock_delay_frames(self.level):
            self._lock()
            return True
        return changed

    def set_level(self, level: int) -> bool:
        """Cheat (owner request 2026-10-25): jump to the given level
        mid-game. Gravity and the locked color change immediately; the
        start level moves too, so progression continues from the new
        level instead of reverting on the next clear.
        """
        if self.status is not Status.PLAYING:
            return False
        self.level = max(0, min(level, 9))
        self._start_level = self.level
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
        placement exists, the piece is abandoned to fall naturally."""
        assert self._piece_kind is not None  # caller checked
        # Descend at soft-drop speed (the fastest a player can drop).
        self._soft_drop = True
        if self._autopilot_abandoned:
            return False
        if self._autopilot_plan is None:
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
            direction = 1 if (rot - self._rot) % 4 <= 2 else -1
            if self._try_rotate(direction) or self._try_rotate(-direction):
                return True
            self._autopilot_abandoned = True
            return False
        # One lateral step per frame (the arrow key-mash rate).
        if self._piece_x != x:
            dx = 1 if x > self._piece_x else -1
            if self._move(dx):
                return True
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
        """Auto-repeat for left/right, as frame counters (spec 4.7)."""
        if self._das_dir == 0:
            return False
        self._das_counter += 1
        if not self._das_repeating:
            if self._das_counter >= DAS_DELAY:
                self._das_repeating = True
                self._das_counter = 0
                return self._move(self._das_dir)
            return False
        if self._das_counter >= DAS_REPEAT:
            self._das_counter = 0
            return self._move(self._das_dir)
        return False

    def _apply_gravity(self) -> bool:
        if self._soft_drop:
            self._soft_held += 1
            fpr = soft_drop_fpr(frames_per_row(self.level), self._soft_held)
        else:
            self._soft_held = 0
            fpr = frames_per_row(self.level)
        self._gravity_counter += 1
        if self._gravity_counter >= fpr:
            self._gravity_counter = 0
            self._piece_y += 1
            return True
        return False

    def _try_rotate(self, direction: int) -> bool:
        """Rotate with the Tengen one-square kick (spec 4.2).

        Try the rotation in place; if it overlaps anything (wall, floor, or
        stack), try shifting one square to the left; reject if that also
        fails. VERIFY (spec 4.2): whether the kick also applies to the
        right wall and floor contact.
        """
        if self._piece_kind is None:
            return False
        new_rot = (self._rot + direction) % 4
        base = ROTATIONS[self._piece_kind][new_rot]
        for kick in (0, -1):
            cells = [
                (x + kick + self._piece_x, y + self._piece_y) for x, y in base
            ]
            if self.board.cells_free(cells):
                self._rot = new_rot
                self._piece_x += kick
                return True
        return False

    def _lock(self) -> None:
        if self._piece_kind is None:
            return
        # Landing pop (owner request 2026-10-25): every lock bumps the
        # counter; the state event carries it and the UI plays a
        # synthesized brick-thud on each increment.
        self.lock_count += 1
        self.board.lock_cells(self.piece_cells(), int(self._piece_kind))
        self._piece_kind = None
        rows = self.board.full_rows()
        if not rows:
            self._spawn_next()
            return
        # Row-clear sound (owner request 2026-10-25): one counter bump
        # per clear event (1-4 rows); the UI plays a dismantle "poo-ch"
        # on each increment.
        self.clear_count += 1
        # Lines completed (spec 4.5): score, lines, and level update
        # immediately; the rows dissolve in place for CLEAR_ANIM_FRAMES
        # before being removed and the next piece spawns.
        lines_before = self.lines
        self.lines += len(rows)
        self.score += points_for_clear(len(rows))
        self.score += BLOCK_BONUS_POINTS * block_bonuses(lines_before, self.lines)
        new_level = level_for_lines(self._start_level, self.lines)
        if new_level > self.level:
            self._celebrate = True
            self.level = new_level
        elif new_level < self.level:
            self.level = new_level
        self._clearing_rows = rows
        self._clearing_frame = 0

    def _spawn_next(self) -> None:
        kind = self.next_piece
        self.next_piece = self._rng.next_piece()
        self._piece_kind = kind
        self._piece_x = SPAWN_X
        self._piece_y = SPAWN_Y
        self._rot = 0
        self._gravity_counter = 0
        self._soft_held = 0
        self._rest_frames = 0
        self._autopilot_plan = None  # replan for the new piece
        self._autopilot_abandoned = False
        if not self.board.cells_free(self.piece_cells()):
            # Game over: the new piece cannot spawn (spec 4.8). Top-5
            # runs enter the table and set top_run for the fireworks
            # screen (owner request 2026-10-25).
            self._piece_kind = None
            self.status = Status.GAME_OVER
            self.high_score = max(self.high_score, self.score)
            self.top_run = highscore.qualifies(self.score, self._highscore_path)
            if self.top_run:
                self.top_scores = highscore.add(self.score, self._highscore_path)
                self.high_score = max(self.high_score, self.top_scores[0]["score"])
            return
        self.stats.increment(kind)
