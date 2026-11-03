"""Plot the autopilot high-score study (owner request 2026-10-28).

Reads stats/autopilot-highscore.json (from tools/autopilot_sim.py) and
writes histogram panels for survived lines, tetrises, and total points
into stats/autopilot-highscore.png, plus a text summary.

Usage: uv run --no-project --with matplotlib python tools/autopilot_plot.py

=====================================================================
WHAT THE OUTPUT MEANS
=====================================================================
The PNG holds three histograms of the same N seeded games:

  - Lines survived: how far each run got before dying (or before the
    ~111-minute frame cap stopped it; those runs pile up at the right
    edge -- they are censored, not finished).
  - Tetrises: 4-line clears per run. The "highscore" strategy is
    built around tetrises, so this is its signature metric.
  - Total points: what the strategy is actually optimizing.

The text summary repeats the story as numbers: run count, death
rate, "early" deaths (< 1000 lines), median/p10/max of lines, and
points-per-line (score efficiency).

=====================================================================
HOW TO READ IT (caveats)
=====================================================================
- These are N independent runs of ONE profile, so the histograms show
  that profile's distribution. A single run is noise; only the bulk
  of the distribution (median, early-death rate) means anything.
- To compare TWO profiles head-to-head, use core/sweep_autopilot.py
  instead: it measures variants on identical seeds under identical
  frame budgets (a paired comparison), which this study predates.
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

# Force the headless backend BEFORE pyplot is imported: this script
# only writes a PNG file and must never try to open a GUI window (no
# display exists when run from a shell or CI).
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Relative paths: run this from the repository root, where stats/ lives.
RUNS_PATH = Path("stats/autopilot-highscore.json")
OUT_PATH = Path("stats/autopilot-highscore.png")


def pct(vals: list[float], p: float) -> float:
    """Nearest-rank percentile of an ALREADY-SORTED list.

    Returns vals[int(len(vals) * p)], clamped to the last element so
    p near 1.0 (or a rounding-up) never overruns the list. E.g. p=0.5
    on 100 sorted runs is vals[50] -- the median. Callers sort, so no
    sorting happens here.
    """
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def main() -> None:
    """Load the study JSON, draw the three histograms, print the summary."""
    runs = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
    # Each run dict is one entry of autopilot_sim.run_one()'s output.
    # Sort each metric ascending so pct() can pick ranks out of it.
    lines = sorted(r["lines"] for r in runs)
    tetrises = sorted(r["tetrises"] for r in runs)
    scores = sorted(r["score"] for r in runs)
    died = [r for r in runs if r["died"]]
    # "Early" deaths -- game over before line 1000 -- are the failure
    # mode strategy tuning cares about; a death after a huge run is a
    # non-event.
    early = sum(1 for r in runs if r["died"] and r["lines"] < 1000)

    # Three side-by-side panels in one wide figure.
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle(
        f"Autopilot \"high score\" strategy — {len(runs)} seeded games "
        f"({len(runs) - len(died)} survived the ~111-minute cap)",
        fontsize=13,
    )
    # One panel per metric. The bar colors reuse the piece palette
    # (green #349859, red #b05a51, gold #e6b467 -- the same hexes as
    # cells.py's families / theme.ts) so the charts echo the game.
    for ax, data, title, color in (
        (axes[0], lines, "Lines survived", "#349859"),
        (axes[1], tetrises, "Tetrises (4-line clears) per run", "#b05a51"),
        (axes[2], scores, "Total points", "#e6b467"),
    ):
        # 60 bins: fine enough to show the distribution's shape,
        # coarse enough that the bars read as a curve.
        ax.hist(data, bins=60, color=color, edgecolor="black", linewidth=0.3)
        ax.set_title(title)
        ax.set_ylabel("runs")
        ax.grid(alpha=0.2)
    axes[0].set_xlabel("lines (runs at the right edge hit the frame cap)")
    axes[1].set_xlabel("tetrises")
    axes[2].set_xlabel("points")
    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=110)
    print(f"wrote {OUT_PATH}")
    # Headline numbers. pts/line is the efficiency metric: points
    # scored per line survived. Score only accrues from clears, so it
    # separates "far because of tetrises" from "far because of time".
    print(
        f"runs={len(runs)} died={len(died)} ({len(died) / len(runs) * 100:.1f}%) "
        f"early(<1000 lines)={early} ({early / len(runs) * 100:.1f}%)"
    )
    print(
        f"lines median={pct(lines, 0.5)} p10={pct(lines, 0.1)} max={lines[-1]} | "
        f"tetrises median={pct(tetrises, 0.5)} | "
        f"points median={pct(scores, 0.5)} | "
        f"pts/line median={st.median(round(r['score'] / max(1, r['lines'])) for r in runs):.0f}"
    )


if __name__ == "__main__":
    main()
