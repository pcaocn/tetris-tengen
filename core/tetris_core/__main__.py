"""Entry point: `python -m tetris_core`.

Reads JSON-line commands from stdin, writes JSON-line events to stdout
(spec 2.1). Runs a fixed-rate 60 Hz loop on a monotonic clock, sleeping the
remainder of each frame. stdout is reserved for protocol messages; logs go
to stderr only.

WHY A SEPARATE THREAD FOR STDIN
--------------------------------
The game loop must run at a steady 60 Hz whether or not a command
arrives, and it must react to a command the moment it arrives. Reading
stdin inside the loop would mean either blocking on input (freezing the
game between frames) or polling with a timeout (busy-waiting).

So stdin gets its own thread that does nothing but push whole lines onto
a queue. The game loop drains that queue with `get_nowait()` once per
frame, then advances the game. Commands are therefore applied at the next
frame boundary (within 16.7 ms) without ever blocking the loop.

THE LOOP, STEP BY STEP
----------------------
    1. Drain every pending command, emitting its events.
    2. Advance the game one frame; emit a state if anything changed.
    3. Sleep until the next 60 Hz boundary.

The sleep is computed from an absolute target time (`next_tick`), not by
adding a fixed sleep to the previous sleep. That keeps the average frame
rate at exactly 60 Hz instead of drifting slower with every frame.

stdout is a PROTOCOL CHANNEL: only JSON events may be written there, and
each one is flushed immediately, because the Rust shell is reading it
line by line and waiting for the answer. Everything diagnostic goes to
stderr.
"""

from __future__ import annotations


import json
import logging
import queue
import sys
import threading
import time

from .protocol import Core

# One frame at 60 Hz. The game advances in these units.
TICK_SECONDS = 1.0 / 60.0

log = logging.getLogger("tetris_core")


def main() -> None:
    # Logs go to stderr, never stdout -- stdout carries the protocol.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    core = Core()
    # An unbounded FIFO queue between the stdin thread and the game loop.
    commands: queue.SimpleQueue = queue.SimpleQueue()

    def read_stdin() -> None:
        """Reader thread: push each complete stdin line onto the queue.

        Iterating over `sys.stdin` blocks until a full line is available
        and yields it without the trailing newline, which is exactly the
        unit the protocol wants.
        """
        try:
            for raw in sys.stdin:
                line = raw.strip()
                if line:
                    commands.put(line)
        finally:
            # The sentinel None tells the game loop that stdin is closed
            # and the process should shut down cleanly.
            commands.put(None)

    # Daemon thread: if the process is killed, the reader dies with it
    # instead of keeping the interpreter alive.
    threading.Thread(target=read_stdin, daemon=True, name="stdin-reader").start()

    def emit(event: dict) -> None:
        """Write one event as a single JSON line and flush it.

        The separators are tightened (no spaces) to keep the stream small,
        and the flush is essential -- without it the Rust shell would
        wait for a full buffer instead of getting the line at once.
        """
        sys.stdout.write(json.dumps(event, separators=(",", ":")))
        sys.stdout.write("\n")
        sys.stdout.flush()

    log.info("tetris_core started")
    # Send the initial snapshot immediately, so the UI can draw the board
    # before the player touches anything.
    emit(core.state_event())

    # The absolute time of the next frame boundary. Anchoring this to the
    # start (rather than accumulating sleeps) is what keeps the loop at
    # a true 60 Hz.
    next_tick = time.monotonic()
    while True:
        # ---- Step 1: apply every command that arrived since last frame.
        while True:
            try:
                item = commands.get_nowait()
            except queue.Empty:
                break  # queue drained
            if item is None:
                # stdin closed: the parent process is gone, so exit.
                log.info("stdin closed; exiting")
                return
            for event in core.handle_line(item):
                emit(event)
        # ---- Step 2: advance the game one frame.
        # `update()` returns True when something observable changed, so
        # an idle frame costs no state event (and no UI redraw).
        if core.game.update():
            emit(core.state_event())
        # ---- Step 3: sleep until the next boundary.
        next_tick += TICK_SECONDS
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            # Fell behind (e.g. long stall): re-anchor instead of spiraling.
            # Without this, every subsequent frame would be "late" and the
            # loop would try to catch up forever, burning CPU.
            next_tick = time.monotonic()


if __name__ == "__main__":
    main()
