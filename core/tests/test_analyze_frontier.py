"""Tests for the pooled sweep frontier analysis."""

from __future__ import annotations

import csv
import sys

import analyze_frontier


def write_sweep(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "variant",
                "seed",
                "died_early",
                "score",
                "tetrises",
                "pts_per_line",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_frontier_ranks_only_on_common_seeds(tmp_path, monkeypatch, capsys):
    """A variant with an extra seed cannot win on a different denominator.

    The reference has seeds 1 and 2. The candidate has seeds 1 and 3.
    On the only shared seed the candidate scores 90 against the
    reference's 100. Per-pair means would compare 90 against the
    reference's two-seed mean and could call the candidate superior; the
    frontier ranking must instead use the common seed set and report n=1.
    """
    path = tmp_path / "sweep.csv"
    write_sweep(
        path,
        [
            {
                "variant": "cur",
                "seed": 1,
                "died_early": "False",
                "score": 100,
                "tetrises": 1,
                "pts_per_line": 100,
            },
            {
                "variant": "cur",
                "seed": 2,
                "died_early": "True",
                "score": 10,
                "tetrises": 0,
                "pts_per_line": 10,
            },
            {
                "variant": "cand",
                "seed": 1,
                "died_early": "False",
                "score": 90,
                "tetrises": 1,
                "pts_per_line": 90,
            },
            {
                "variant": "cand",
                "seed": 3,
                "died_early": "False",
                "score": 1_000,
                "tetrises": 10,
                "pts_per_line": 100,
            },
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_frontier.py", str(path), "--ref", "cur", "--boot", "10"],
    )
    analyze_frontier.main()
    out = capsys.readouterr().out

    assert "1 seeds shared by all variants" in out
    assert "WARNING: 1 variant(s)" in out
    rows = [line for line in out.splitlines() if line.startswith(("cur ", "cand "))]
    assert any(line.startswith("cur ") and "100" in line for line in rows)
    assert any(line.startswith("cand ") and "90" in line for line in rows)
    assert all(" 1 " in line for line in rows)