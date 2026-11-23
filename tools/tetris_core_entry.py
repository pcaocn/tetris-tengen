"""PyInstaller entry point for the bundled game engine.

The sidecar is a standalone executable containing the Python runtime and
`tetris_core`; it speaks the same JSON-lines protocol on stdin/stdout as
the development `python -m tetris_core` process.
"""

from tetris_core.__main__ import main

if __name__ == "__main__":
    main()