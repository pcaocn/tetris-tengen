# Autopilot sweep: tuning the strategy

The autopilot's behaviour is a set of weights in
`core/tetris_core/autopilot.py`. The sweep scripts in `core/` play those
weights headlessly and compare them, so a change to the strategy can be
chosen on measurements instead of on a hunch.

Four scripts, each with a distinct job:

| Script | Job |
| --- | --- |
| `sweep_autopilot.py` | Compare **many strategy variants** on shared seeds and rank them. |
| `simulate_autopilot.py` | Benchmark **one strategy** and print its full distribution. |
| `analyze_frontier.py` | Test a sweep CSV **statistically** (paired McNemar + bootstrap CI). |
| `compare_autopilot.py` | Print a plain side-by-side table of two benchmark CSVs. |

All of them run the real `Game` object with the real autopilot code — only
the 60 Hz sleep between frames is removed, so a score measured headlessly
is a score the app could really produce.

## Prerequisites

```sh
cd core
uv sync          # once: creates core/.venv (Python 3.11+)
```

Every command below is run from `core/`.

## 1. Sweep: compare strategy variants

```sh
# A quick look at a few candidates (a couple of minutes).
uv run python sweep_autopilot.py --seeds 100 --only cur,sh4,sh6 --workers 4

# The measurement the spec quotes: 400 seeds, 250k-frame budget.
# The master seed must be 77777 -- that is the seed the spec's 400-seed
# numbers were measured on. With the default (11111) you get a different
# (equally valid, but not comparable) seed set.
uv run python sweep_autopilot.py --seeds 400 --master-seed 77777 --workers 4 \
    --out ../stats/sweep.csv

# Every variant in the catalogue (long — hours; run it in the background).
uv run python sweep_autopilot.py --seeds 400 --master-seed 77777 --workers 4 \
    --out ../stats/sweep-all.csv
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--seeds N` | 100 | How many seeds to play. More seeds = less noise; the spec's numbers use 400. |
| `--cap N` | 250000 | Frame budget per run (≈ 69 min of game time at 60 Hz). |
| `--master-seed N` | 11111 | The seed the **seed list** is drawn from. Fixes the whole sweep. |
| `--only A,B,C` | all | Run only these variants (names come from `build_variants()`). |
| `--out PATH` | — | Write the per-run rows to a CSV for `analyze_frontier.py`. |
| `--workers N` | ≤ 8 | Parallel worker processes. **Use 4** on a busy machine. |

Variant names worth knowing: `baseline` (the pre-2026-10-29 profile),
`cur` (the currently shipped profile), `sh4`/`sh6`/`sh8`/`sh12` (the
score/survival trade-off curve), `dw0`…`dw60` (the aggressiveness dial),
`dwl2`…`dwl4` and `dmax1` (the deferral refinements). The full list —
and the history of each round — is in `build_variants()` in
`sweep_autopilot.py`.

**CPU note:** a sweep is a long, unattended, CPU-heavy job. Keep it to
`--workers 4`, and lower its priority so it never starves the rest of
your machine:

```sh
nice -n 15 uv run python sweep_autopilot.py --seeds 400 --workers 4 --out ../stats/sweep.csv
```

## 2. Analyse: is the difference real?

Comparing "12 early deaths" with "18 early deaths" as two independent
rates is misleading — on 400 seeds, differences of 4–6 deaths sit at the
noise floor. Because every variant plays the *same* seeds, the
comparison is **paired**, and `analyze_frontier.py` uses the paired test:

```sh
uv run python analyze_frontier.py ../stats/sweep.csv --ref cur
```

The output gives, for every variant against the reference:

- **McNemar p** and **b/c** — the paired death-rate test (`b` = reference
  died & variant survived, `c` = the reverse). A `*` marks p < 0.05.
- **d score** and its **95% CI** — the paired mean score difference with
  a bootstrap confidence interval. If the interval excludes 0, the
  difference is real.
- the **Pareto frontier** — the variants not beaten on *both* axes at
  once, i.e. the genuine trade-off choices.
- the **frontier benders** — the variants that beat the reference on
  **both** axes. Those are improvements, not trades.

## 3. Benchmark: one strategy, in full

```sh
# The shipped high-score strategy.
uv run python simulate_autopilot.py --strategy highscore --runs 100 --workers 4

# The quick-clear strategy, saving the per-run rows.
uv run python simulate_autopilot.py --strategy quick --runs 100 --workers 4 \
    --csv ../stats/autopilot-quick-100games.csv
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--strategy S` | highscore | `quick` (clear lines fast) or `highscore` (maximize score). |
| `--runs N` | 100 | How many games to play. |
| `--seed N` | 20261028 | The master seed the **seed list** is drawn from. |
| `--max-frames N` | 600000 | Frame cap per game. A run that hits it is reported `CAPPED`. |
| `--csv PATH` | — | Write the per-run rows to a CSV. |
| `--workers N` | ≤ 8 | Parallel worker processes. **Use 4**. |

> **Reproducing the shipped CSVs.** The two files in `stats/` were run
> with the **default** master seed (20261028) but a **3,000,000-frame**
> cap, not the 600,000 default — long enough that a surviving run
> usually ends by topping out rather than by hitting the cap. To
> reproduce them exactly, add `--max-frames 3000000`:
>
> ```sh
> uv run python simulate_autopilot.py --strategy quick --runs 100 \
>     --max-frames 3000000 --workers 4 \
>     --csv ../stats/autopilot-quick-100games.csv
> ```
>
> That run takes roughly an hour on four workers; it is a background
> job, not an interactive one.
>
> **Ruleset note:** the shipped CSVs predate the Tengen gravity,
> placement-scoring, stage-payout and level-curve changes. They are kept
> as measurements of the old ruleset; label any new comparison with its
> commit or ruleset.

The report prints the score and line distributions, the **clear mix**
(what share of the clears were singles/doubles/triples/tetrises — the
clearest statement of what a strategy actually does), the percentiles,
and the best and worst runs.

To compare two benchmark files directly:

```sh
uv run python compare_autopilot.py \
    ../stats/autopilot-quick-100games.csv \
    ../stats/autopilot-highscore-100games.csv quick highscore
```

## 4. Apply a winning variant

The sweep prints a ranked list; the winner is a full weight profile.
Copy it into `STRATEGIES["highscore"]` in `core/tetris_core/autopilot.py`,
run the test suite (`uv run pytest`), and re-run the benchmark to confirm
the new profile reproduces the swept numbers.

## Two rules that keep the results trustworthy

1. **Compare only on the same seeds.** The seed list comes from a single
   master seed, and every variant must play all of it. Quote that master
   seed alongside any number you publish — the spec's 400-seed figures
   were measured on `--master-seed 77777`, and a run on the default
   (11111) is a *different*, equally valid, but not comparable sample.
   Candidate seeds must never be drawn from the set where the current
   profile dies — that screen is biased, and one earlier round built on
   it was a mirage.
2. **Never judge on one seed.** A single run is luck. Use ≥ 400 seeds
   and the paired test before believing any change.
