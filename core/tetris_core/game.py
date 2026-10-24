"""Game state machine and 60 Hz frame update (Tengen rules, spec 4)."""

from enum import Enum

from . import highscore
from .board import Board, HIDDEN_ROWS
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

# Locked-piece color index per level (spec 6.2): UNVERIFIED PLACEHOLDER
# table; the owner must supply the per-level indices sampled from Tengen
# captures (open item). The UI maps the index to a hex color in theme.ts.
LOCKED_COLOR_INDICES = (0, 1, 2, 3, 4, 5, 6, 7)


class Status(Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


def locked_color_index(level: int) -> int:
    return LOCKED_COLOR_INDICES[level % len(LOCKED_COLOR_INDICES)]


class Game:
    """Owns all game state. One update() call advances one 60 Hz frame."""

    def __init__(self, highscore_path=None, rng=None) -> None:
        self._highscore_path = highscore_path
        self._rng = rng if rng is not None else PieceRNG()
        self.high_score = highscore.load(highscore_path)
        self.frame = 0
        self.new_game(0)

    # ------------------------------------------------------------------
    # Commands (protocol layer calls these)
    # ------------------------------------------------------------------

    def new_game(self, level: int = 0) -> None:
        if level < 0:
            level = 0
        self.board = Board()
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
        self.next_piece: Piece = self._rng.next_piece()
        self._spawn_next()

    def pause(self) -> None:
        if self.status is Status.PLAYING:
            self.status = Status.PAUSED
        elif self.status is Status.PAUSED:
            self.status = Status.PLAYING

    def handle_input(self, action: str) -> None:
        if self.status is not Status.PLAYING:
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
                self._spawn_next()
            return True
        changed = self._handle_das()
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
        self.board.lock_cells(self.piece_cells(), int(self._piece_kind))
        self._piece_kind = None
        rows = self.board.full_rows()
        if not rows:
            self._spawn_next()
            return
        # Lines completed (spec 4.5): score, lines, and level update
        # immediately; the rows dissolve in place for CLEAR_ANIM_FRAMES
        # before being removed and the next piece spawns.
        lines_before = self.lines
        self.lines += len(rows)
        self.score += points_for_clear(len(rows))
        self.score += BLOCK_BONUS_POINTS * block_bonuses(lines_before, self.lines)
        new_level = level_for_lines(self._start_level, self.lines)
        if new_level != self.level:
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
        if not self.board.cells_free(self.piece_cells()):
            # Game over: the new piece cannot spawn (spec 4.8).
            self._piece_kind = None
            self.status = Status.GAME_OVER
            if self.score > self.high_score:
                self.high_score = self.score
                highscore.save(self.high_score, self._highscore_path)
            return
        self.stats.increment(kind)
