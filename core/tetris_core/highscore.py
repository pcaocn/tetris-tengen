"""High score persistence (spec 4.10, error handling in spec 8).

Stored as JSON in the macOS application support folder by default:
~/Library/Application Support/tengen-tetris/highscore.json

Owner decision 2026-10-25: the file now keeps a top-5 table of
{"score", "at"} records (ISO timestamp); the previous single-score
format is migrated on first load. A corrupted file is renamed to
<name>.bak and play starts from an empty table (spec section 8).

The TETRIS_HIGHSCORE_PATH environment variable overrides the location
(used by tests and by the Rust core if needed).

FILE FORMAT
    {
      "scores": [
        {"score": 123456, "at": "2026-10-29T14:32:10"},
        ...
      ]
    }

ROBUSTNESS RULE (spec 8): a high score file must never be able to crash
the game. Every read therefore catches its own errors, and a file that
cannot be parsed is QUARANTINED (renamed to <name>.bak) rather than
deleted -- the owner's data is preserved even when it is unreadable, and
play continues with an empty table.
"""

from __future__ import annotations


import json
import os
from datetime import datetime
from pathlib import Path

# The macOS convention for per-application writable data. Created on
# first save (see save_table), so a fresh machine has no file at all.
DEFAULT_PATH = (
    Path.home() / "Library" / "Application Support" / "tengen-tetris" / "highscore.json"
)

# How many records the table keeps (owner decision 2026-10-25).
TABLE_SIZE = 5


class _NoSave:
    """Sentinel type for a score store that never touches disk."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NO_SAVE"


# Headless benchmark workers pass this instead of the player's real
# highscore file. Loads see an empty table and saves are discarded, so a
# benchmark cannot overwrite the desktop app's leaderboard.
NO_SAVE = _NoSave()


def _resolve(path: str | os.PathLike | None | _NoSave) -> Path | None:
    """Work out which file to use.

    Four levels of override, in priority order:
      1. NO_SAVE: a private sink for headless runs.
      2. An explicit path argument (what the tests use).
      3. The TETRIS_HIGHSCORE_PATH environment variable.
      4. The default location in Application Support.
    """
    if isinstance(path, _NoSave):
        return None
    if path is not None:
        return Path(path)
    env = os.environ.get("TETRIS_HIGHSCORE_PATH")
    if env:
        return Path(env)
    return DEFAULT_PATH


def load_table(path: str | os.PathLike | None | _NoSave = None) -> list[dict]:
    """The top-5 records, sorted by score descending.

    Returns [] when there is no file yet -- a missing file is the normal
    state on a fresh install, not an error.
    """
    file_path = _resolve(path)
    if file_path is None:
        # NO_SAVE: benchmark/headless workers get a private empty table.
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if "scores" in data:
            # Current format: a list of records.
            table = [
                {"score": int(e["score"]), "at": str(e.get("at", ""))}
                for e in data["scores"]
            ]
        else:
            # Migrate the old single-score format: the old file had one
            # {"high_score": N} object; keep it as a one-entry table.
            table = [{"score": int(data["high_score"]), "at": ""}]
        # Drop nonsensical entries, sort best-first, and keep only the
        # top TABLE_SIZE records.
        table = [e for e in table if e["score"] >= 0]
        table.sort(key=lambda e: e["score"], reverse=True)
        return table[:TABLE_SIZE]
    except FileNotFoundError:
        # No file yet: an empty table, and the game starts at 0.
        return []
    except (OSError, ValueError, KeyError, TypeError):
        # Corrupted or unreadable file: quarantine it and start empty
        # rather than letting a bad file break the game (spec 8).
        _quarantine(file_path)
        return []


def save_table(table: list[dict], path: str | os.PathLike | None | _NoSave = None) -> None:
    """Write the table to disk, creating the folder if needed.

    Write errors are swallowed on purpose: failing to save a high score
    must never interrupt a game that is otherwise fine.
    """
    file_path = _resolve(path)
    if file_path is None:
        # NO_SAVE: benchmark workers must never write the player's table.
        return
    try:
        # The Application Support folder usually does not exist yet on a
        # fresh machine, so create the whole path.
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps({"scores": table[:TABLE_SIZE]}), encoding="utf-8"
        )
    except OSError:
        pass


def load(path: str | os.PathLike | None | _NoSave = None) -> int:
    """The best score ever (top of the table), for the HIGH SCORE readout.

    The in-game HIGH SCORE number is the table's first entry, so it
    survives restarts and is independent of the current run.
    """
    table = load_table(path)
    return table[0]["score"] if table else 0


def save(score: int, path: str | os.PathLike | None | _NoSave = None) -> None:
    """Legacy single-score writer; kept for compatibility (spec 4.10)."""
    save_table([{"score": int(score), "at": ""}], path)


def qualifies(score: int, path: str | os.PathLike | None | _NoSave = None) -> bool:
    """True when a score would enter the top-5 table (owner 2026-10-25).

    Two rules:
      - A score of 0 or less never qualifies (an empty run is not a record).
      - While the table still has room, any positive score qualifies;
        once it is full, the score must beat the LAST (worst) entry.

    NO_SAVE never qualifies, so headless benchmark games also report
    top_run = False instead of claiming a leaderboard entry they cannot
    persist.
    """
    if isinstance(path, _NoSave):
        return False
    table = load_table(path)
    if score <= 0:
        return False
    return len(table) < TABLE_SIZE or score > table[-1]["score"]


def add(score: int, path: str | os.PathLike | None | _NoSave = None) -> list[dict]:
    """Insert a score into the table if it qualifies, persist, and
    return the resulting top-5 table.

    This is called from `Game._spawn_next` when the game ends. The
    timestamp is ISO-8601 with second precision -- enough to show
    "2026-10-29 14:32" on the game-over screen, without storing noise.
    """
    table = load_table(path)
    if qualifies(score, path):
        table.append({"score": int(score), "at": datetime.now().isoformat(timespec="seconds")})
        # Re-sort and trim to TABLE_SIZE so the file always holds the
        # five best scores in descending order.
        table.sort(key=lambda e: e["score"], reverse=True)
        table = table[:TABLE_SIZE]
        save_table(table, path)
    return table


def _quarantine(file_path: Path) -> None:
    """Rename a corrupted high score file to <name>.bak (spec section 8).

    The original file is KEPT (renamed, not deleted) so the owner can
    inspect or recover it by hand.
    """
    try:
        file_path.rename(file_path.parent / (file_path.name + ".bak"))
    except OSError:
        pass
