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

WHAT THIS SCRIPT IS FOR
-----------------------
It answers "how good is strategy X?" for ONE strategy at a time, with a
full statistical picture: the distribution, the percentiles, the clear
mix, and the best and worst runs.

Compare it with `sweep_autopilot.py`:
  - simulate_autopilot.py: ONE strategy, many seeds, full distribution.
    Use it to describe a strategy and to produce the CSV files in
    `stats/`.
  - sweep_autopilot.py: MANY strategy variants, shared seeds, ranked
    against each other. Use it to decide WHICH strategy is better.

WHY THE GAME STILL BEHAVES LIKE THE REAL THING
-----------------------------------------------
The script drives the real `Game` object and calls the real
`update()` once per frame — the same call the 60 Hz loop makes. The only
thing removed is the SLEEP between frames, so 100 games finish in
minutes instead of hours. Everything else (gravity, lock delay, the
autopilot's one-key-per-frame throttle, scoring, game over) is exactly
what the app does, so a score measured here is a score the app could
really produce.
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
    """Everything one benchmark run produced.

    A dataclass rather than a dict so the fields are named and
    type-checked; the summary code below reads much better.
    """

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
        """Score efficiency: the average value of a cleared line.

        This is the number that separates the two strategies most
        clearly -- the "quick" strategy clears many lines cheaply, the
        "highscore" strategy clears fewer but far more valuable ones.
        """
        return self.score / self.lines if self.lines else 0.0

    @property
    def lines_per_piece(self) -> float:
        """How many lines each piece placed produced."""
        return self.lines / self.pieces if self.pieces else 0.0

    @property
    def score_per_piece(self) -> float:
        """How much score each piece placed produced."""
        return self.score / self.pieces if self.pieces else 0.0


def run_one(seed: int, strategy: str, max_frames: int) -> RunResult:
    """Play one full game with the autopilot driving.

    Runs in a worker process, so it returns a plain dataclass (which is
    picklable) and takes only simple arguments.
    """
    # A seeded game: the same seed always gives the same piece sequence.
    game = Game(rng=PieceRNG(seed))
    # Turn the autopilot on. "quick" clears lines fast, "highscore"
    # maximizes the score.
    game.set_autopilot(strategy)

    singles = doubles = triples = tetrises = 0
    prev_lines = 0
    frames = 0

    # The frame loop. Identical to the game's own loop except for the
    # missing sleep, so the game plays out exactly as it would in the app.
    while game.status is not Status.GAME_OVER and frames < max_frames:
        game.update()
        frames += 1

        # The autopilot never presses Enter, so the end-of-stage
        # celebration would wait for a human forever. Resume it the same
        # way the UI's Enter key does (Game.pause on LEVEL_COMPLETE).
        if game.status is Status.LEVEL_COMPLETE:
            game.pause()

        # Classify the clear by how much the line count jumped.
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
        # "timed_out" means the run hit the frame cap while still alive
        # -- the strategy never topped out. Such a run's score is a
        # LOWER bound, not a final score.
        timed_out=game.status is not Status.GAME_OVER,
    )


def _worker(args) -> RunResult:
    seed, strategy, max_frames = args
    return run_one(seed, strategy, max_frames)


def describe(values: Sequence[float], name: str) -> None:
    """Print one metric's distribution summary.

    Mean, median, standard deviation, min and max. The median is the
    number to trust for these runs: the score distribution has a long
    right tail (a few great runs), so the mean is pulled far above the
    typical run.
    """
    n = len(values)
    mean = statistics.mean(values)
    med = statistics.median(values)
    # The stdev needs at least two samples to be defined.
    sd = statistics.stdev(values) if n > 1 else 0.0
    print(
        f"  {name:<22} mean={mean:>12,.1f}   median={med:>12,.1f}   "
        f"stdev={sd:>11,.1f}   min={min(values):>10,.1f}   max={max(values):>12,.1f}"
    )


def histogram(values: Sequence[float], name: str, bins: int = 16) -> None:
    """Print an ASCII histogram of a metric.

    Sixteen equal-width bins between the smallest and largest value,
    each drawn as a bar of '#' characters scaled to the busiest bin.
    """
    lo, hi = min(values), max(values)
    if hi == lo:
        # Every run gave the same value: no distribution to show.
        print(f"\n  {name}: all runs identical at {lo:,.0f}")
        return
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        # The min() keeps the largest value inside the last bin instead
        # of running off the end.
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    # The busiest bin is drawn at full width (38 characters).
    peak = max(counts) or 1
    print(f"\n  {name} distribution ({bins} bins over {lo:,.0f}..{hi:,.0f}):")
    for i, c in enumerate(counts):
        edge_lo = lo + i * width
        edge_hi = edge_lo + width
        bar = "#" * round(38 * c / peak)
        print(f"    {edge_lo:>12,.0f} - {edge_hi:>12,.0f} | {bar:<38} {c}")


def report(results: list[RunResult], strategy: str) -> None:
    """Print the full statistical report for a benchmark run.

    Sections, in order:
      1. How many runs hit the frame cap (their score is a lower bound).
      2. The summary statistics of each metric.
      3. The clear-type mix -- the single most informative table, since
         it shows WHAT the strategy actually does.
      4. Percentiles for lines and score.
      5. The two histograms.
      6. The best and the worst runs.
    """
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
    """Command-line entry point.

    USAGE
    -----
        # Benchmark the shipped high-score strategy (the default).
        uv run python simulate_autopilot.py --strategy highscore --runs 100

        # Benchmark the quick-clear strategy, and save the per-run rows.
        uv run python simulate_autopilot.py --strategy quick --runs 100 \
            --csv ../stats/autopilot-quick-100games.csv

    THE OPTIONS
    -----------
        --strategy S     "quick" or "highscore" (default highscore).
        --runs N         how many games to play (default 100).
        --seed N         the master seed the seed LIST is drawn from
                         (default 20261028). The same master seed always
                         produces the same list of game seeds, so a run
                         is reproducible.
        --max-frames N   frame cap per game (default 600,000 = about
                         2.8 hours of game time at 60 Hz). A run that
                         hits the cap is reported as CAPPED.
        --csv PATH       write the per-run rows to a CSV file.
        --workers N      parallel worker processes. Keep it modest on a
                         busy machine -- 4 is a good value for a long
                         unattended benchmark.
    """
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
    # master seed. Drawing them ONCE (rather than per game) means the
    # same benchmark always plays the same set of games.
    seed_rng = random.Random(args.seed)
    seeds = seed_rng.sample(range(1, 2**31 - 1), args.runs)

    print(
        f"Running {args.runs} autopilot '{args.strategy}' games "
        f"(max {args.max_frames:,} frames each, no pacing)..."
    )
    print(f"Master seed {args.seed}; game seeds are the first {len(seeds)} of:")
    print("  " + ", ".join(str(s) for s in seeds))
    print()

    # One job per seed; the pool runs them in parallel.
    jobs = [(s, args.strategy, args.max_frames) for s in seeds]
    results: list[RunResult] = []
    with mp.Pool(processes=args.workers) as pool:
        # Print each result as it arrives, so a long run shows progress.
        for i, res in enumerate(pool.imap_unordered(_worker, jobs), 1):
            results.append(res)
            print(
                f"  [{i:>3}/{args.runs}] seed={res.seed:<11} lines={res.lines:>7,} "
                f"score={res.score:>10,} lvl={res.level:>4} "
                f"tetrises={res.tetrises:>4} "
                f"pts/line={res.points_per_line:>6.1f} "
                f"{'CAPPED' if res.timed_out else 'died'}"
            )

    # Sort by seed for a stable output order, then print the full report.
    results.sort(key=lambda r: r.seed)
    report(results, args.strategy)

    # ---- The CSV output ---------------------------------------------
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
        # Without --csv, print the rows in the same CSV format, so the
        # output can simply be redirected into a file.
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
