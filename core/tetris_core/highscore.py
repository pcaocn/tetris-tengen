"""High score persistence (spec 4.10, error handling in spec 8).

Stored as JSON in the macOS application support folder by default:
~/Library/Application Support/tengen-tetris/highscore.json

Owner decision 2026-10-25: the file now keeps a top-5 table of
{"score", "at"} records (ISO timestamp); the previous single-score
format is migrated on first load. A corrupted file is renamed to
<name>.bak and play starts from an empty table (spec section 8).

The TETRIS_HIGHSCORE_PATH environment variable overrides the location
(used by tests and by the Rust core if needed).
"""

import json
import os
from datetime import datetime
from pathlib import Path

DEFAULT_PATH = (
    Path.home() / "Library" / "Application Support" / "tengen-tetris" / "highscore.json"
)

TABLE_SIZE = 5


def _resolve(path: str | os.PathLike | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("TETRIS_HIGHSCORE_PATH")
    if env:
        return Path(env)
    return DEFAULT_PATH


def load_table(path: str | os.PathLike | None = None) -> list[dict]:
    """The top-5 records, sorted by score descending."""
    file_path = _resolve(path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if "scores" in data:
            table = [
                {"score": int(e["score"]), "at": str(e.get("at", ""))}
                for e in data["scores"]
            ]
        else:
            # Migrate the old single-score format.
            table = [{"score": int(data["high_score"]), "at": ""}]
        table = [e for e in table if e["score"] >= 0]
        table.sort(key=lambda e: e["score"], reverse=True)
        return table[:TABLE_SIZE]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError):
        _quarantine(file_path)
        return []


def save_table(table: list[dict], path: str | os.PathLike | None = None) -> None:
    file_path = _resolve(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps({"scores": table[:TABLE_SIZE]}), encoding="utf-8"
        )
    except OSError:
        pass


def load(path: str | os.PathLike | None = None) -> int:
    """The best score ever (top of the table), for the HIGH SCORE readout."""
    table = load_table(path)
    return table[0]["score"] if table else 0


def save(score: int, path: str | os.PathLike | None = None) -> None:
    """Legacy single-score writer; kept for compatibility (spec 4.10)."""
    save_table([{"score": int(score), "at": ""}], path)


def qualifies(score: int, path: str | os.PathLike | None = None) -> bool:
    """True when a score would enter the top-5 table (owner 2026-10-25)."""
    table = load_table(path)
    if score <= 0:
        return False
    return len(table) < TABLE_SIZE or score > table[-1]["score"]


def add(score: int, path: str | os.PathLike | None = None) -> list[dict]:
    """Insert a score into the table if it qualifies, persist, and
    return the resulting top-5 table."""
    table = load_table(path)
    if qualifies(score, path):
        table.append({"score": int(score), "at": datetime.now().isoformat(timespec="seconds")})
        table.sort(key=lambda e: e["score"], reverse=True)
        table = table[:TABLE_SIZE]
        save_table(table, path)
    return table


def _quarantine(file_path: Path) -> None:
    """Rename a corrupted high score file to <name>.bak (spec section 8)."""
    try:
        file_path.rename(file_path.parent / (file_path.name + ".bak"))
    except OSError:
        pass
