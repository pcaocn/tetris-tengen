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

WHY THE PAIRED TEST MATTERS
---------------------------
Suppose the reference dies early on 20 of 400 seeds and a variant dies
early on 12. Taken as two independent rates, that difference is not
significant at all: with 400 seeds, 4 to 6 deaths sit at the noise
floor, and an earlier apparent 6-death improvement tested at p = 0.36.

But the variants played the SAME seeds, so most of that difference is
shared. The McNemar test only looks at the seeds where the two variants
DISAGREE -- the reference died and the variant survived (b), or the
reverse (c). If b is much larger than c, the difference is real; if
they are close, the variant simply got lucky on a few hard seeds.

The same logic applies to the score: the paired bootstrap resamples the
per-seed DIFFERENCES, so seed difficulty cancels out.

READING THE OUTPUT
------------------
    early        early deaths of the variant (lower is better)
    McNemar p    p-value of the paired death-rate difference
                 (a "*" marks p < 0.05)
    b/c          reference died & variant survived / the reverse
    d score      the paired mean score difference vs the reference
    95% CI       the bootstrap confidence interval for that difference;
                 if it excludes 0, the difference is real
    tetri        mean tetrises per run
    pts/line     mean points per line

Then two extra sections:
  - the PARETO frontier: the variants that are not beaten on BOTH axes
    at the same time. These are the real trade-off choices.
  - the frontier BENDERS: variants that beat the reference on BOTH
    axes at once -- those are not a trade, they are an improvement.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections import defaultdict


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs.

    Under the null hypothesis ("the two variants are equally likely to
    die early on any given seed"), the discordant pairs split like a
    Binomial(n, 0.5) where n = b + c. The p-value is the probability of
    seeing a split at least as extreme as the observed one, doubled for
    the two-sided test.

    The EXACT version is used (rather than the chi-square approximation)
    because b and c are often small -- exactly the case where the
    approximation is unreliable.
    """
    n = b + c
    if n == 0:
        # The two variants agreed on every seed: no evidence of a
        # difference.
        return 1.0
    # P(X <= min(b,c)) * 2 under Binomial(n, 0.5)
    k = min(b, c)
    tail = sum(_binomial_pmf(i, n) for i in range(k + 1))
    return min(1.0, 2.0 * tail)


def _binomial_pmf(k: int, n: int) -> float:
    """P(X = k) for a Binomial(n, 0.5) distribution."""
    from math import comb

    # comb(n, k) ways to place the successes, times (0.5)^n for all
    # outcomes being equally likely.
    return comb(n, k) * 0.5**n


def bootstrap_ci(deltas: list[float], iters: int = 4000, seed: int = 7) -> tuple:
    """A 95% confidence interval for the mean of the paired deltas.

    The bootstrap works by RESAMPLING the per-seed differences with
    replacement and recomputing the mean each time. Because the
    differences are already paired (seed difficulty removed), the
    resampled means form the sampling distribution of the difference.

    The interval is the 2.5th and 97.5th percentiles of those means.
    The RNG is seeded, so the interval is reproducible.
    """
    rng = random.Random(seed)
    n = len(deltas)
    means = []
    for _ in range(iters):
        # Draw n differences with replacement and average them.
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

    The bottom-left corner is the ideal spot: few deaths AND a high
    score. A variant that sits up and to the right of another one has
    paid score for survival (or survival for score).
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
    """Command-line entry point.

    USAGE
    -----
        # Analyse one sweep CSV against the shipped profile.
        uv run python analyze_frontier.py ../stats/sweep.csv --ref cur

        # Analyse several CSVs together (they are pooled).
        uv run python analyze_frontier.py a.csv b.csv --ref cur

    THE OPTIONS
    -----------
        csv_path    one or more sweep CSVs (positional)
        --ref NAME  the reference variant to compare against. "cur" is
                    the shipped highscore profile -- the natural choice,
                    because the question is usually "is this candidate
                    better than what we ship?"
        --boot N    bootstrap iterations for the CI (default 4000).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="+", help="one or more sweep CSVs")
    ap.add_argument("--ref", default="cur", help="reference variant name")
    ap.add_argument("--boot", type=int, default=4000)
    args = ap.parse_args()

    # ---- Load the rows ------------------------------------------------
    rows: list[dict] = []
    for path in args.csv_path:
        rows.extend(csv.DictReader(open(path, encoding="utf-8")))
    # Index by variant, then by seed: the seed is the join key that makes
    # the comparison paired.
    by_variant: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in rows:
        by_variant[r["variant"]][int(r["seed"])] = r

    if args.ref not in by_variant:
        print(f"reference variant {args.ref!r} not in {args.csv_path}")
        sys.exit(1)
    ref = by_variant[args.ref]

    # A Pareto/bender ranking compares RAW means and death counts across
    # variants. Those numbers are only comparable when every variant was
    # measured on the same seeds. Use the intersection of all seed sets and
    # say so loudly when a variant does not cover the reference set.
    common_seeds = set(ref)
    for res in by_variant.values():
        common_seeds.intersection_update(res)
    if not common_seeds:
        print("no seed set is shared by every variant; cannot rank")
        sys.exit(1)
    partial = [
        name for name, res in by_variant.items() if set(res) != set(ref)
    ]

    print(f"Paired frontier analysis vs {args.ref!r} "
          f"({len(common_seeds)} seeds shared by all variants, {args.csv_path})\n")
    if partial:
        print(
            f"WARNING: {len(partial)} variant(s) do not cover the reference "
            f"seed set; ranking uses the {len(common_seeds)} shared seeds."
        )
        print(f"         affected: {', '.join(sorted(partial))}\n")

    header = (
        f"{'variant':<16} {'n':>4} {'early':>6} {'McNemar p':>11} {'b/c':>7} "
        f"{'mean score':>11} {'d score':>10} {'95% CI':>19} "
        f"{'tetri':>6} {'pts/line':>9}"
    )
    print(header)
    print("-" * len(header))

    out = []
    for name, res in by_variant.items():
        # Every comparison uses the same seed set, so raw means and counts
        # in the frontier ranking below are directly comparable.
        seeds = sorted(common_seeds)
        b = c = 0
        deltas = []
        for s in seeds:
            r_ref = ref[s]
            r_var = res[s]
            # Count the DISCORDANT seeds: the ones where the two
            # variants disagreed about dying early.
            if r_ref["died_early"] == "True" and r_var["died_early"] == "False":
                b += 1  # the reference died, the variant survived
            elif r_ref["died_early"] == "False" and r_var["died_early"] == "True":
                c += 1  # the variant died, the reference survived
            # The per-seed score difference -- the paired measurement.
            deltas.append(float(r_var["score"]) - float(r_ref["score"]))
        # The paired test on the discordant seeds.
        p = mcnemar_exact(b, c)
        early = sum(res[s]["died_early"] == "True" for s in seeds)
        mean_score = statistics.mean(float(res[s]["score"]) for s in seeds)
        d_mean = statistics.mean(deltas)
        lo, hi = bootstrap_ci(deltas, args.boot)
        tetrises = statistics.mean(float(res[s]["tetrises"]) for s in seeds)
        ppl = statistics.mean(float(res[s]["pts_per_line"]) for s in seeds)
        out.append(
            (
                name,
                early,
                p,
                b,
                c,
                mean_score,
                d_mean,
                lo,
                hi,
                tetrises,
                ppl,
                len(seeds),
            )
        )

    # ---- The comparison table ----------------------------------------
    for name, early, p, b, c, mean_score, d_mean, lo, hi, tetrises, ppl, n in out:
        # A star marks a significant McNemar result.
        star = " *" if p < 0.05 else ""
        print(
            f"{name:<16} {n:>4} {early:>6} {p:>11.4f}{star:>2} {f'{b}/{c}':>7} "
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
        # Dominated = some other variant is at least as good on BOTH
        # axes AND strictly better on at least one.
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
        n = row[-1]
        if name == args.ref:
            continue
        if early < ref_early and mean_score > ref_score:
            benders.append((name, early, mean_score, p, b, c, n))
    if not benders:
        print("    (none -- every variant trades score for survival, or the "
              "reverse)")
    for name, early, mean_score, p, b, c, n in benders:
        print(f"    {name:<16} early={early:>3} (ref {ref_early})  "
              f"mean score={mean_score:>11,.0f} (ref {ref_score:,.0f})  "
              f"McNemar p={p:.4f} b/c={b}/{c} n={n}")


if __name__ == "__main__":
    main()
