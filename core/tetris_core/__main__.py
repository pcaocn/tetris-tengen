"""Entry point: `python -m tetris_core`.

Reads JSON-line commands from stdin, writes JSON-line events to stdout
(spec 2.1). Runs a fixed-rate 60 Hz loop on a monotonic clock, sleeping the
remainder of each frame. stdout is reserved for protocol messages; logs go
to stderr only.
"""

import json
import logging
import queue
import sys
import threading
import time

from .protocol import Core

TICK_SECONDS = 1.0 / 60.0

log = logging.getLogger("tetris_core")


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    core = Core()
    commands: queue.SimpleQueue = queue.SimpleQueue()

    def read_stdin() -> None:
        try:
            for raw in sys.stdin:
                line = raw.strip()
                if line:
                    commands.put(line)
        finally:
            commands.put(None)

    threading.Thread(target=read_stdin, daemon=True, name="stdin-reader").start()

    def emit(event: dict) -> None:
        sys.stdout.write(json.dumps(event, separators=(",", ":")))
        sys.stdout.write("\n")
        sys.stdout.flush()

    log.info("tetris_core started")
    emit(core.state_event())  # initial snapshot so the UI can draw at once

    next_tick = time.monotonic()
    while True:
        while True:
            try:
                item = commands.get_nowait()
            except queue.Empty:
                break
            if item is None:
                log.info("stdin closed; exiting")
                return
            for event in core.handle_line(item):
                emit(event)
        if core.game.update():
            emit(core.state_event())
        next_tick += TICK_SECONDS
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            # Fell behind (e.g. long stall): re-anchor instead of spiraling.
            next_tick = time.monotonic()


if __name__ == "__main__":
    main()
