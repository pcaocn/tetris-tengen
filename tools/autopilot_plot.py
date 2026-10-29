"""Plot the autopilot high-score study (owner request 2026-10-28).

Reads stats/autopilot-highscore.json (from tools/autopilot_sim.py) and
writes histogram panels for survived lines, tetrises, and total points
into stats/autopilot-highscore.png, plus a text summary.

Usage: uv run --no-project --with matplotlib python tools/autopilot_plot.py
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RUNS_PATH = Path("stats/autopilot-highscore.json")
OUT_PATH = Path("stats/autopilot-highscore.png")


def pct(vals: list[float], p: float) -> float:
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def main() -> None:
    runs = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
    lines = sorted(r["lines"] for r in runs)
    tetrises = sorted(r["tetrises"] for r in runs)
    scores = sorted(r["score"] for r in runs)
    died = [r for r in runs if r["died"]]
    early = sum(1 for r in runs if r["died"] and r["lines"] < 1000)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle(
        f"Autopilot \"high score\" strategy — {len(runs)} seeded games "
        f"({len(runs) - len(died)} survived the ~111-minute cap)",
        fontsize=13,
    )
    for ax, data, title, color in (
        (axes[0], lines, "Lines survived", "#349859"),
        (axes[1], tetrises, "Tetrises (4-line clears) per run", "#b05a51"),
        (axes[2], scores, "Total points", "#e6b467"),
    ):
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
