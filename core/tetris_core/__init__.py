"""Tengen-style Tetris game core.

Pure Python game logic for the Tengen (Atari) NES Tetris ruleset.
No UI or OS dependencies; communicates via the JSON-line protocol
in `protocol.py` and the 60 Hz loop in `__main__.py`.

WHAT LIVES IN HERE
------------------
    board.py      the 10x23 grid, collision, line clears
    pieces.py     the seven tetrominoes and their rotation states
    gravity.py    the frames-per-row table and soft-drop acceleration
    scoring.py    the Tengen award table
    rng.py        the seedable piece generator
    stats.py      per-piece counters
    highscore.py  the top-5 table on disk
    protocol.py   command parsing and event building
    game.py       the state machine and the 60 Hz frame update
    autopilot.py  the placement search and the two strategy profiles
    __main__.py   the stdin/stdout loop that the Rust shell drives

This package is the ONLY place the game rules exist. The React front
end draws what this package reports and never decides anything itself,
which is what lets the whole game be benchmarked headlessly (see
`core/sweep_autopilot.py`).
"""

from __future__ import annotations


# The package version, reported by the Tauri shell when it builds.
__version__ = "0.1.0"
