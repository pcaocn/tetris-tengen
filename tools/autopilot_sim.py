"""Autopilot benchmark harness (spec 4.11; owner request 2026-10-28).

Runs full autopilot games to game over (celebrations auto-advanced) and
records per-run stats: survived lines, clear-size histogram, tetrises,
score. Used for the pilot check (is the strategy dying early?) and for
the extensive study.

Usage:
  uv run --no-project --with matplotlib python tools/autopilot_sim.py pilot
  uv run --no-project --with matplotlib python tools/autopilot_sim.py run <seconds> <out.json>
"""

from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from tetris_core.game import CLEAR_ANIM_FRAMES, Game, Status  # noqa: E402
from tetris_core.rng import PieceRNG  # noqa: E402

FRAME_CAP = 400_000  # ~111 min of 60 Hz play per run; right-censored


def run_one(seed: int) -> dict:
    game = Game(rng=PieceRNG(seed=seed))
    game.set_autopilot("highscore")
    hist = {1: 0, 2: 0, 3: 0, 4: 0}
    prev = 0
    for _ in range(FRAME_CAP):
        if game.status is Status.LEVEL_COMPLETE:
            game.pause()  # simulate the owner pressing Enter
            continue
        if game.status is not Status.PLAYING:
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
        "died": game.status is Status.GAME_OVER,
    }


def pilot() -> None:
    with multiprocessing.Pool(10) as pool:
        t0 = time.time()
        results = pool.map(run_one, range(1, 25))
    dt = time.time() - t0
    lines = sorted(r["lines"] for r in results)
    early = sum(1 for r in results if r["died"] and r["lines"] < 1000)
    print(f"24 runs on 10 cores in {dt:.1f}s -> {dt / 24 * 10:.1f}s/run/core")
    print(f"lines min/p25/median/p75/max: {lines[0]}/{lines[6]}/{lines[12]}/{lines[18]}/{lines[-1]}")
    print(f"early deaths (<1000 lines): {early}/24")
    for r in sorted(results, key=lambda r: r["lines"])[:5]:
        print("  worst:", r)


def study(seconds: float, out_path: str) -> None:
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
    if sys.argv[1] == "pilot":
        pilot()
    else:
        study(float(sys.argv[2]), sys.argv[3])
