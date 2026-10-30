#!/usr/bin/env python3
"""Paired frontier analysis for a sweep CSV.

The sweep runs every variant on the SAME seeds, so the comparison
between two variants is PAIRED: only the seeds where they disagree
carry information. That is far more powerful than comparing two
independent binomial death rates, which is what the raw counts invite
(and is how a 12-vs-18 difference gets mistaken for a real effect).

For each variant, against a reference:
  - early deaths, and McNemar's exact test on the discordant pairs
    (b = reference died / variant survived, c = the reverse)
  - mean score@cap delta with a paired bootstrap CI
  - tetrises and points-per-line

Usage:
    uv run python analyze_frontier.py SWEEP.csv --ref cur
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections import defaultdict


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    # P(X <= min(b,c)) * 2 under Binomial(n, 0.5)
    k = min(b, c)
    tail = sum(_binomial_pmf(i, n) for i in range(k + 1))
    return min(1.0, 2.0 * tail)


def _binomial_pmf(k: int, n: int) -> float:
    from math import comb

    return comb(n, k) * 0.5**n


def bootstrap_ci(deltas: list[float], iters: int = 4000, seed: int = 7) -> tuple:
    rng = random.Random(seed)
    n = len(deltas)
    means = []
    for _ in range(iters):
        s = sum(deltas[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters)]
    return lo, hi


def plot_frontier(points: list[tuple[str, int, float]]) -> None:
    """ASCII plot of the score/survival frontier.

    Each point is a variant: x = early deaths (fewer is better), y =
    mean score (higher is better). Only the Pareto set is plotted.
    """
    if not points:
        return
    width = 66
    height = 18
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_span = max(1, x_hi - x_lo)
    y_span = max(1.0, y_hi - y_lo)

    grid = [[" "] * width for _ in range(height)]
    for name, early, mean_score in points:
        col = int((early - x_lo) / x_span * (width - 1))
        row = int((mean_score - y_lo) / y_span * (height - 1))
        row = height - 1 - row  # higher score at the top
        label = name[:6]
        for i, ch in enumerate(label):
            if col + i < width:
                grid[row][col + i] = ch

    print("\n  score/survival frontier (x = early deaths, y = mean score)")
    print(f"  {x_lo} {'-' * 10} early deaths {'-' * 10} {x_hi}")
    for i, row in enumerate(grid):
        label = ""
        if i == 0:
            label = f"{y_hi:>10,.0f} |"
        elif i == height - 1:
            label = f"{y_lo:>10,.0f} |"
        elif i == height // 2:
            label = f"{(y_lo + y_hi) / 2:>10,.0f} |"
        else:
            label = " " * 10 + " |"
        print("  " + label + "".join(row))
    print(" " * 13 + "+" + "-" * width)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="+", help="one or more sweep CSVs")
    ap.add_argument("--ref", default="cur", help="reference variant name")
    ap.add_argument("--boot", type=int, default=4000)
    args = ap.parse_args()

    rows: list[dict] = []
    for path in args.csv_path:
        rows.extend(csv.DictReader(open(path, encoding="utf-8")))
    by_variant: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in rows:
        by_variant[r["variant"]][int(r["seed"])] = r

    if args.ref not in by_variant:
        print(f"reference variant {args.ref!r} not in {args.csv_path}")
        sys.exit(1)
    ref = by_variant[args.ref]

    print(f"Paired frontier analysis vs {args.ref!r} "
          f"({len(ref)} seeds, {args.csv_path})\n")

    header = (
        f"{'variant':<16} {'early':>6} {'McNemar p':>11} {'b/c':>7} "
        f"{'mean score':>11} {'d score':>10} {'95% CI':>19} "
        f"{'tetri':>6} {'pts/line':>9}"
    )
    print(header)
    print("-" * len(header))

    out = []
    for name, res in by_variant.items():
        seeds = sorted(set(res) & set(ref))
        if not seeds:
            continue
        b = c = 0
        deltas = []
        for s in seeds:
            r_ref = ref[s]
            r_var = res[s]
            if r_ref["died_early"] == "True" and r_var["died_early"] == "False":
                b += 1
            elif r_ref["died_early"] == "False" and r_var["died_early"] == "True":
                c += 1
            deltas.append(float(r_var["score"]) - float(r_ref["score"]))
        p = mcnemar_exact(b, c)
        early = sum(res[s]["died_early"] == "True" for s in seeds)
        mean_score = statistics.mean(float(res[s]["score"]) for s in seeds)
        d_mean = statistics.mean(deltas)
        lo, hi = bootstrap_ci(deltas, args.boot)
        tetrises = statistics.mean(float(res[s]["tetrises"]) for s in seeds)
        ppl = statistics.mean(float(res[s]["pts_per_line"]) for s in seeds)
        out.append((name, early, p, b, c, mean_score, d_mean, lo, hi, tetrises, ppl))

    for name, early, p, b, c, mean_score, d_mean, lo, hi, tetrises, ppl in out:
        star = " *" if p < 0.05 else ""
        print(
            f"{name:<16} {early:>6} {p:>11.4f}{star:>2} {f'{b}/{c}':>7} "
            f"{mean_score:>11,.0f} {d_mean:>10,.0f} "
            f"{f'[{lo:,.0f}, {hi:,.0f}]':>19} "
            f"{tetrises:>6.1f} {ppl:>9.1f}"
        )

    print("\n  b = reference died & variant survived, c = the reverse")
    print("  * = McNemar p < 0.05 (paired, so it accounts for seed difficulty)")

    # Pareto frontier: a variant is dominated when another is at least as
    # good on both axes (fewer early deaths AND higher score).
    print("\n  Pareto frontier (not dominated on both axes):")
    pareto = []
    for row in out:
        name, early, mean_score = row[0], row[1], row[5]
        dominated = any(
            (o[1] <= early and o[5] >= mean_score)
            and (o[1] < early or o[5] > mean_score)
            for o in out
            if o[0] != name
        )
        if not dominated:
            pareto.append((name, early, mean_score))
    for name, early, mean_score in sorted(pareto, key=lambda p: p[1]):
        print(f"    {name:<16} early={early:>3}  mean score={mean_score:>11,.0f}")

    plot_frontier(pareto)

    # A frontier BENDER dominates the reference on BOTH axes: fewer
    # early deaths AND a higher mean score. A variant that only trades
    # one for the other is sliding along the frontier, not bending it.
    print("\n  frontier benders (dominate the reference on BOTH axes):")
    ref_row = next(r for r in out if r[0] == args.ref)
    ref_early, ref_score = ref_row[1], ref_row[5]
    benders = []
    for row in out:
        name, early, p, b, c, mean_score = row[0], row[1], row[2], row[3], row[4], row[5]
        if name == args.ref:
            continue
        if early < ref_early and mean_score > ref_score:
            benders.append((name, early, mean_score, p, b, c))
    if not benders:
        print("    (none -- every variant trades score for survival, or the "
              "reverse)")
    for name, early, mean_score, p, b, c in benders:
        print(f"    {name:<16} early={early:>3} (ref {ref_early})  "
              f"mean score={mean_score:>11,.0f} (ref {ref_score:,.0f})  "
              f"McNemar p={p:.4f} b/c={b}/{c}")


if __name__ == "__main__":
    main()
