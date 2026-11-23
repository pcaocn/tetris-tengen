"""Autopilot benchmark harness (spec 4.11; owner request 2026-10-28).

Runs full autopilot games to game over (celebrations auto-advanced) and
records per-run stats: survived lines, clear-size histogram, tetrises,
score. Used for the pilot check (is the strategy dying early?) and for
the extensive study.

Usage:
  uv run --no-project --with matplotlib python tools/autopilot_sim.py pilot
  uv run --no-project --with matplotlib python tools/autopilot_sim.py run <seconds> <out.json>

=====================================================================
WHAT ONE RUN MEASURES
=====================================================================
run_one() plays ONE complete game with the "highscore" autopilot
profile (the weights in core/tetris_core/autopilot.py) from a given
RNG seed and returns a dict:

  seed, lines, level, score, pieces  -- the run's final state
  singles/doubles/triples/tetrises   -- count of 1/2/3/4-line clears
  died                               -- True only on actual game over

Every run is capped at FRAME_CAP frames (~111 minutes of 60 Hz play).
A run still alive at the cap is stopped with died=False: it is
RIGHT-CENSORED -- we know it survived at least that long, not how
long it would have gone on. This cap is what autopilot_plot.py means
by "runs at the right edge hit the frame cap".

=====================================================================
CAVEAT: SINGLE RUNS ARE NOISE
=====================================================================
This harness measures ONE profile's distribution across seeds. To
decide whether profile A beats profile B, use core/sweep_autopilot.py
instead: it plays every variant on the SAME seeds under the SAME
frame budget (paired comparison) and ranks by median score. This
script predates that methodology.

=====================================================================
OUTPUT FILES
=====================================================================
study() writes the list of run dicts as JSON to out.json, which
tools/autopilot_plot.py reads. Run everything from the repo root.
"""

from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path

# tools/ is not a package, so put the repo's core/ on sys.path to make
# `import tetris_core` resolve regardless of the caller's CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from tetris_core import highscore  # noqa: E402
from tetris_core.game import CLEAR_ANIM_FRAMES, Game, Status  # noqa: E402
from tetris_core.rng import PieceRNG  # noqa: E402

# Hard stop per run: 400,000 frames at 60 Hz is ~111 minutes of game
# time. Chosen long enough that a good "highscore" run is usually
# censored (still alive) rather than finished, so survival is visible.
FRAME_CAP = 400_000  # ~111 min of 60 Hz play per run; right-censored


def run_one(seed: int) -> dict:
    """Play one full seeded autopilot game to game over; return its stats.

    Deterministic: the same seed always produces the same game (the
    piece sequence comes from PieceRNG(seed) and the autopilot adds no
    randomness), so a strange run can be replayed exactly.
    """
    # A fresh game on a seeded RNG with a private score sink: benchmark
    # workers must not write the desktop player's top-five table.
    game = Game(highscore_path=highscore.NO_SAVE, rng=PieceRNG(seed=seed))
    game.set_autopilot("highscore")
    # Clear-size histogram, keyed 1..4 (singles..tetrises). Counted by
    # watching game.lines jump: one update() clears at most one set of
    # rows, so a jump of k in a single frame is exactly one k-clear.
    hist = {1: 0, 2: 0, 3: 0, 4: 0}
    prev = 0
    for _ in range(FRAME_CAP):
        if game.status is Status.LEVEL_COMPLETE:
            # Stage cleared: the celebration screen halts PLAYING.
            # pause() flips the same flag as the owner pressing Enter
            # to continue to the next stage, so multi-stage runs need
            # no human in the loop.
            game.pause()  # simulate the owner pressing Enter
            continue
        if game.status is not Status.PLAYING:
            # GAME_OVER (or anything unexpected): stop counting.
            break
        game.update()
        if game.lines > prev:
            hist[game.lines - prev] += 1
            prev = game.lines
    return {
        "seed": seed,
        "lines": game.lines,
        "level": game.level,
        "score": game.score,
        "pieces": game.lock_count,
        "singles": hist[1],
        "doubles": hist[2],
        "triples": hist[3],
        "tetrises": hist[4],
        # False also for runs censored at FRAME_CAP (still alive).
        "died": game.status is Status.GAME_OVER,
    }


def pilot() -> None:
    """Quick sanity check: 24 seeds in parallel, worst runs printed.

    Answers "is the strategy dying early?" in minutes.
    """
    with multiprocessing.Pool(10) as pool:
        t0 = time.time()
        results = pool.map(run_one, range(1, 25))
    dt = time.time() - t0
    lines = sorted(r["lines"] for r in results)
    early = sum(1 for r in results if r["died"] and r["lines"] < 1000)
    # dt/24*10 converts wall time into core-seconds per run: how long
    # one game takes on one core (the unit for budgeting study()).
    print(f"24 runs on 10 cores in {dt:.1f}s -> {dt / 24 * 10:.1f}s/run/core")
    # For 24 sorted values, indices 0 / 6 / 12 / 18 / -1 are exactly
    # min / p25 / median / p75 / max.
    print(f"lines min/p25/median/p75/max: {lines[0]}/{lines[6]}/{lines[12]}/{lines[18]}/{lines[-1]}")
    # Early deaths (fewer than 1000 lines) are the failure mode the
    # strategy tuning is trying to eliminate.
    print(f"early deaths (<1000 lines): {early}/24")
    for r in sorted(results, key=lambda r: r["lines"])[:5]:
        print("  worst:", r)


def study(seconds: float, out_path: str) -> None:
    """Run autopilot games for a wall-clock budget; save runs as JSON.

    Seeds are handed out in deterministic batches of 20 (1..20, then
    21..40, ...) until `seconds` elapses, so re-running the study
    extends the same seed sequence instead of resampling it. The last
    batch can overshoot the budget by up to one batch of games.
    """
    results = []
    seed = 1
    t0 = time.time()
    with multiprocessing.Pool(10) as pool:
        while time.time() - t0 < seconds:
            batch = [seed + i for i in range(20)]
            seed += 20
            results.extend(pool.map(run_one, batch))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"{len(results)} runs in {(time.time() - t0) / 60:.1f} min -> {out_path}")


if __name__ == "__main__":
    # argv dispatch: "pilot" takes no argument; anything else is read
    # as "run <seconds> <out.json>".
    if sys.argv[1] == "pilot":
        pilot()
    else:
        study(float(sys.argv[2]), sys.argv[3])
