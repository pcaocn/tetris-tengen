"""High score persistence (spec 4.10, error handling in spec 8).

Stored as JSON in the macOS application support folder by default:
~/Library/Application Support/tengen-tetris/highscore.json

The TETRIS_HIGHSCORE_PATH environment variable overrides the location
(used by tests and by the Rust core if needed). A corrupted file is
renamed to <name>.bak and play starts from 0 (spec section 8).
"""

import json
import os
from pathlib import Path

DEFAULT_PATH = (
    Path.home() / "Library" / "Application Support" / "tengen-tetris" / "highscore.json"
)


def _resolve(path: str | os.PathLike | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("TETRIS_HIGHSCORE_PATH")
    if env:
        return Path(env)
    return DEFAULT_PATH


def load(path: str | os.PathLike | None = None) -> int:
    file_path = _resolve(path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        score = int(data["high_score"])
        if score < 0:
            raise ValueError("negative high score")
        return score
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        _quarantine(file_path)
        return 0


def save(score: int, path: str | os.PathLike | None = None) -> None:
    file_path = _resolve(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps({"high_score": int(score)}), encoding="utf-8"
        )
    except OSError:
        pass


def _quarantine(file_path: Path) -> None:
    """Rename a corrupted high score file to <name>.bak (spec section 8)."""
    try:
        file_path.rename(file_path.parent / (file_path.name + ".bak"))
    except OSError:
        pass
