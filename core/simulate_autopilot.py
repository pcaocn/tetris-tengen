#!/usr/bin/env python3
"""
Headless autopilot benchmark.

Runs many full games with the autopilot driving (no UI, no frame pacing,
no delay) and reports the distribution of lines cleared, score, and
clear-type mix for a given strategy.

Usage:
    uv run python simulate_autopilot.py [--strategy highscore] [--runs 100]
                                         [--seed 20261028] [--max-frames 600000]

The game logic is the real `tetris_core.Game` — only the wall-clock pacing
is removed, so results match what the app would play.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import random
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from tetris_core.game import Game, Status
from tetris_core.rng import PieceRNG

# The master seed drives seed selection, so a whole benchmark run is
# reproducible from the single --seed argument.
DEFAULT_MASTER_SEED = 20261028
DEFAULT_RUNS = 100
DEFAULT_MAX_FRAMES = 600_000


@dataclass
class RunResult:
    seed: int
    lines: int
    score: int
    level: int
    singles: int
    doubles: int
    triples: int
    tetrises: int
    pieces: int
    frames: int
    timed_out: bool

    @property
    def points_per_line(self) -> float:
        return self.score / self.lines if self.lines else 0.0

    @property
    def lines_per_piece(self) -> float:
        return self.lines / self.pieces if self.pieces else 0.0

    @property
    def score_per_piece(self) -> float:
        return self.score / self.pieces if self.pieces else 0.0


def run_one(seed: int, strategy: str, max_frames: int) -> RunResult:
    """Play one full game with the autopilot driving."""
    game = Game(rng=PieceRNG(seed))
    game.set_autopilot(strategy)

    singles = doubles = triples = tetrises = 0
    prev_lines = 0
    frames = 0

    while game.status is not Status.GAME_OVER and frames < max_frames:
        game.update()
        frames += 1

        # The autopilot never presses Enter, so the end-of-stage
        # celebration would wait for a human forever. Resume it the same
        # way the UI's Enter key does (Game.pause on LEVEL_COMPLETE).
        if game.status is Status.LEVEL_COMPLETE:
            game.pause()

        if game.lines > prev_lines:
            cleared = game.lines - prev_lines
            if cleared == 1:
                singles += 1
            elif cleared == 2:
                doubles += 1
            elif cleared == 3:
                triples += 1
            elif cleared == 4:
                tetrises += 1
            prev_lines = game.lines

    return RunResult(
        seed=seed,
        lines=game.lines,
        score=game.score,
        level=game.level,
        singles=singles,
        doubles=doubles,
        triples=triples,
        tetrises=tetrises,
        pieces=sum(game.stats.as_dict().values()),
        frames=frames,
        timed_out=game.status is not Status.GAME_OVER,
    )


def _worker(args) -> RunResult:
    seed, strategy, max_frames = args
    return run_one(seed, strategy, max_frames)


def describe(values: Sequence[float], name: str) -> None:
    n = len(values)
    mean = statistics.mean(values)
    med = statistics.median(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    print(
        f"  {name:<22} mean={mean:>12,.1f}   median={med:>12,.1f}   "
        f"stdev={sd:>11,.1f}   min={min(values):>10,.1f}   max={max(values):>12,.1f}"
    )


def histogram(values: Sequence[float], name: str, bins: int = 16) -> None:
    lo, hi = min(values), max(values)
    if hi == lo:
        print(f"\n  {name}: all runs identical at {lo:,.0f}")
        return
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    peak = max(counts) or 1
    print(f"\n  {name} distribution ({bins} bins over {lo:,.0f}..{hi:,.0f}):")
    for i, c in enumerate(counts):
        edge_lo = lo + i * width
        edge_hi = edge_lo + width
        bar = "#" * round(38 * c / peak)
        print(f"    {edge_lo:>12,.0f} - {edge_hi:>12,.0f} | {bar:<38} {c}")


def report(results: list[RunResult], strategy: str) -> None:
    timed_out = sum(1 for r in results if r.timed_out)
    print()
    print("=" * 78)
    print(f"  AUTOPILOT '{strategy}' STRATEGY  -  {len(results)} runs")
    print("=" * 78)
    if timed_out:
        print(
            f"  NOTE: {timed_out} run(s) hit the frame cap while still alive "
            "(the strategy never topped out)."
        )
    print()

    describe([r.lines for r in results], "lines cleared")
    describe([r.score for r in results], "score")
    describe([r.level for r in results], "level reached")
    describe([r.points_per_line for r in results], "points per line")
    describe([r.lines_per_piece for r in results], "lines per piece")
    describe([r.score_per_piece for r in results], "score per piece")
    describe([r.pieces for r in results], "pieces played")
    print()

    total_s = sum(r.singles for r in results)
    total_d = sum(r.doubles for r in results)
    total_t = sum(r.triples for r in results)
    total_q = sum(r.tetrises for r in results)
    total_clears = total_s + total_d + total_t + total_q
    print(f"  Clear mix over all runs ({total_clears:,} clear events):")
    if total_clears:
        for label, count, pts in (
            ("single  (100)", total_s, 100),
            ("double  (400)", total_d, 400),
            ("triple  (900)", total_t, 900),
            ("tetris (2500)", total_q, 2500),
        ):
            share = count / total_clears * 100
            print(
                f"    {label}  {count:>8,} events  {share:>5.1f}%   "
                f"{count * pts:>12,} pts"
            )
        print(
            f"    -> {total_q / total_clears * 100:.1f}% of clears were tetrises; "
            f"mean tetris rate {statistics.mean([r.tetrises for r in results]):.1f}/run"
        )
    print()

    describe([r.tetrises for r in results], "tetrises per run")
    describe([r.triples for r in results], "triples per run")

    for metric, name in (("lines", "Lines cleared"), ("score", "Score")):
        vals = sorted(getattr(r, metric) for r in results)
        print(f"\n  {name} percentiles:")
        for p in (10, 25, 50, 75, 90, 95, 99):
            idx = min(len(vals) - 1, int(len(vals) * p / 100))
            print(f"    P{p:<3} {vals[idx]:>14,.0f}")
        print(f"    min  {vals[0]:>14,.0f}")
        print(f"    max  {vals[-1]:>14,.0f}")

    histogram([r.lines for r in results], "Lines cleared")
    histogram([r.score for r in results], "Score")

    print("\n  Top 5 runs by score:")
    for i, r in enumerate(
        sorted(results, key=lambda r: r.score, reverse=True)[:5], 1
    ):
        print(
            f"    #{i} seed={r.seed:<8} score={r.score:>10,}  lines={r.lines:>6,}  "
            f"lvl={r.level:>4}  tetrises={r.tetrises:>4}  "
            f"pts/line={r.points_per_line:>6.1f}  "
            f"{'CAPPED' if r.timed_out else 'died'}"
        )
    print("\n  Bottom 5 runs by score:")
    for i, r in enumerate(sorted(results, key=lambda r: r.score)[:5], 1):
        print(
            f"    #{i} seed={r.seed:<8} score={r.score:>10,}  lines={r.lines:>6,}  "
            f"lvl={r.level:>4}  tetrises={r.tetrises:>4}  "
            f"pts/line={r.points_per_line:>6.1f}  "
            f"{'CAPPED' if r.timed_out else 'died'}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="highscore", choices=["quick", "highscore"])
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--seed", type=int, default=DEFAULT_MASTER_SEED)
    ap.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    ap.add_argument("--csv", default=None, help="write per-run CSV here")
    ap.add_argument(
        "--workers",
        type=int,
        default=min(8, mp.cpu_count()),
        help="parallel workers (keep it modest on a busy machine)",
    )
    args = ap.parse_args()

    # Distinct random seeds for the piece generator, reproducible from the
    # master seed.
    seed_rng = random.Random(args.seed)
    seeds = seed_rng.sample(range(1, 2**31 - 1), args.runs)

    print(
        f"Running {args.runs} autopilot '{args.strategy}' games "
        f"(max {args.max_frames:,} frames each, no pacing)..."
    )
    print(f"Master seed {args.seed}; game seeds are the first {len(seeds)} of:")
    print("  " + ", ".join(str(s) for s in seeds))
    print()

    jobs = [(s, args.strategy, args.max_frames) for s in seeds]
    results: list[RunResult] = []
    with mp.Pool(processes=args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(_worker, jobs), 1):
            results.append(res)
            print(
                f"  [{i:>3}/{args.runs}] seed={res.seed:<11} lines={res.lines:>7,} "
                f"score={res.score:>10,} lvl={res.level:>4} "
                f"tetrises={res.tetrises:>4} "
                f"pts/line={res.points_per_line:>6.1f} "
                f"{'CAPPED' if res.timed_out else 'died'}"
            )

    results.sort(key=lambda r: r.seed)
    report(results, args.strategy)

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write(
                "seed,lines,score,level,singles,doubles,triples,tetrises,"
                "pieces,frames,timed_out,points_per_line,lines_per_piece\n"
            )
            for r in results:
                fh.write(
                    f"{r.seed},{r.lines},{r.score},{r.level},{r.singles},"
                    f"{r.doubles},{r.triples},{r.tetrises},{r.pieces},{r.frames},"
                    f"{int(r.timed_out)},{r.points_per_line:.2f},"
                    f"{r.lines_per_piece:.4f}\n"
                )
        print(f"\n  CSV written to {args.csv}")
    else:
        print("\n  CSV: seed,lines,score,level,singles,doubles,triples,tetrises,"
              "pieces,frames,timed_out,points_per_line,lines_per_piece")
        for r in results:
            print(
                f"    {r.seed},{r.lines},{r.score},{r.level},{r.singles},"
                f"{r.doubles},{r.triples},{r.tetrises},{r.pieces},{r.frames},"
                f"{int(r.timed_out)},{r.points_per_line:.2f},"
                f"{r.lines_per_piece:.4f}"
            )


if __name__ == "__main__":
    sys.exit(main())
