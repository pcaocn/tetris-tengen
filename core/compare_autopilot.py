#!/usr/bin/env python3
"""Compare two autopilot benchmark CSV runs side by side (per-seed + aggregate).

Usage:
    uv run python compare_autopilot.py QUICK.csv HIGHSCORE.csv quick highscore

This is the LIGHTWEIGHT comparison tool: it takes two CSVs produced by
`simulate_autopilot.py` and prints an aggregate table plus the
per-seed rows.

Use it when you want to see the raw side-by-side picture between two
strategy runs. Use `analyze_frontier.py` instead when you need the
STATISTICS -- the p-value and the confidence interval -- because that
tool knows the runs are paired on the same seeds.

The last two arguments are optional labels for the two files; they only
change the column headings.
"""

from __future__ import annotations

import csv
import statistics
import sys


def load(path: str) -> dict[int, dict]:
    """Read a benchmark CSV into {seed: {metric: value}}.

    The two derived metrics are floats and everything else is an int,
    so the division below cannot silently truncate.
    """
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[int(row["seed"])] = {
                k: (float(v) if k in ("points_per_line", "lines_per_piece") else int(v))
                for k, v in row.items()
            }
    return out


def main() -> None:
    """Print the aggregate comparison and the per-seed table."""
    # The two CSVs to compare, and the optional display labels.
    a_path, b_path = sys.argv[1], sys.argv[2]
    a_name = sys.argv[3] if len(sys.argv) > 3 else "A"
    b_name = sys.argv[4] if len(sys.argv) > 4 else "B"
    a, b = load(a_path), load(b_path)
    # Only the seeds both files have: a benchmark run with a different
    # --seed or --runs has a different seed set, and comparing those
    # head-to-head would be meaningless.
    seeds = sorted(set(a) & set(b))
    print(f"Comparing {len(seeds)} shared seeds: '{a_name}' vs '{b_name}'\n")

    # The metrics to compare, with their display labels.
    metrics = [
        ("lines", "lines cleared"),
        ("score", "score"),
        ("level", "level"),
        ("pieces", "pieces played"),
        ("tetrises", "tetrises"),
        ("triples", "triples"),
        ("points_per_line", "points per line"),
        ("lines_per_piece", "lines per piece"),
    ]
    print(f"  {'metric':<20} {a_name + ' mean':>16} {b_name + ' mean':>16} "
          f"{'B/A':>8}   {'B wins':>7}")
    print("  " + "-" * 74)
    for key, label in metrics:
        av = [a[s][key] for s in seeds]
        bv = [b[s][key] for s in seeds]
        am, bm = statistics.mean(av), statistics.mean(bv)
        # The ratio: above 1.0 means B did better on this metric.
        ratio = bm / am if am else float("nan")
        # How many of the shared seeds B won -- a paired win count,
        # which is more informative than the means alone.
        wins = sum(1 for x, y in zip(av, bv) if y > x)
        print(f"  {label:<20} {am:>16,.2f} {bm:>16,.2f} {ratio:>8.2f}   "
              f"{wins:>3}/{len(seeds)}")

    print("\n  Per-seed (lines / score / tetrises):")
    print(f"  {'seed':<12} {a_name+' lines':>13} {a_name+' score':>14} "
          f"{a_name+' tetr':>11} | {b_name+' lines':>13} {b_name+' score':>14} "
          f"{b_name+' tetr':>11}")
    print("  " + "-" * 100)
    for s in seeds:
        print(f"  {s:<12} {a[s]['lines']:>13,} {a[s]['score']:>14,} "
              f"{a[s]['tetrises']:>11,} | {b[s]['lines']:>13,} "
              f"{b[s]['score']:>14,} {b[s]['tetrises']:>11,}")


if __name__ == "__main__":
    main()
