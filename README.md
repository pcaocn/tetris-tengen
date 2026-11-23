# tetris-tengen

A desktop remake of the vintage **Tetris** by Tengen (the 1989 Atari/NES
release), rebuilt with modern technology: all game rules run in a Python
engine at 60 Hz, and a Tauri + React front end renders the play in crisp
high-definition vector graphics. The title screen features an original
St. Basil's Cathedral scene, echoing the original game's Moscow theme.

The gameplay follows the owner-verified Tengen rules recorded in
[**TENGEN_TETRIS_SPEC.md**](TENGEN_TETRIS_SPEC.md) — the authoritative
design document for this project. This is an original tribute: no
sprites or artwork from the original game are used; music files in
`music/` come from the owner's own collection.

## Features

- **Tengen-style rules**: 10-frame lock delay with the classic
  land-and-slide trick, award scoring (see below), level-locked piece
  colors, and a center-out line-clear wipe with the award label drawn
  inside the cleared rows.
- **HD vector rendering**: every block, dome, and letter is drawn as
  smooth vector art at 2048x1920 logical resolution — sharp at any window
  size, with optional integer scaling for a chunkier retro look.
- **Authentic three-tone blocks**: colors sampled pixel-by-pixel from the
  owner's reference captures; locked pieces cycle through 10 level colors
  (grayish white, red, goldish yellow, blue, yellow, pink, green,
  tortoise, purple, green).
- **Stats panel**: per-piece spawn counts as vertical bars, aligned to
  equal height, with ticks every 10 pieces.
- **Classic cheat code** on the title screen (see How to play).
- **Sound**: the original block-drop thud, line-clear sweep, and menu
  select ticks (from the owner's sound files), plus looping firework
  rockets when a run makes the top 5 — all alongside the music.
- **Top-5 high-score table** with record date/time, persisted and shown
  on qualifying game overs.
- **Autopilot (cheat)**: with the Konami code active, two strategies —
  **End** plays #1 (clear lines as fast as possible) and **Home** plays
  #2 (maximize score: defer small clears, keep a well, and hunt
  triples and tetrises). Both are pure calculation at human input speed
  — one rotation or one sideways step per frame, the same rate as a
  player tapping the keys. **Historical benchmark (earlier gravity and
  scoring rules):** on a seeded 111-minute benchmark (game seed 42)
  the high-score strategy cleared 4,881 lines with 56 tetrises and
  217 points per line, against 4,326 lines with 3 tetrises and 149
  points per line for the quick one. **Historical 100-game benchmark**
  (the shipped CSVs in `stats/`, same earlier ruleset): the high-score
  strategy averages 218 points per line and 309 tetrises per game
  against 148 points per line and 12 tetrises for the quick one —
  a higher score per game, at the price of 6 early deaths per 100
  games. The quick strategy had 0 early deaths before 3,000 lines,
  with 90 runs reaching the frame cap and 10 later top-outs.
  The high-score strategy also plays for survival once the board is more
  than half full — it stops hunting tetrises, keeps the surface flat and
  clears lines whenever it can. A historical 400-seed tuning sweep under
  the same earlier ruleset cut its early deaths from 78/400 to 33/400 on
  held-out seeds. Measured paired (every variant runs on
  identical seeds), that is 58% fewer early deaths *and* a higher
  mean score (+27,432, 95% CI [+9,944, +46,468]) — not a trade of
  one against the other. The remaining score/survival trade sits on
  the tetris-hunting dial: backing off it (`safe_h` 4) reaches
  12/400 early deaths for 19% less score.
  The strategies are tuned with a headless sweep — see
  [Autopilot sweep](#autopilot-sweep-tuning-the-strategy).
- **Original app icon**: four beveled blocks in the piece palette
  (`tools/icon.py` + `npx tauri icon`).
- **Music**: the introduction theme on the intro page only, four
  selectable gameplay themes (Loginska, Bradinsky, Kalinka, Troika;
  Silent by default) that play as a looped playlist during play,
  end-of-stage and victory celebrations, and a game-over
  theme.
- **High-score persistence**, pause, and a 60 Hz game loop driven by the
  Python core — the UI renders state and never computes game rules.

## Requirements

- macOS (the app is not yet configured for Windows/Linux)
- [Node.js](https://nodejs.org) 20.19+ (20.x line) or 22.12+ (22.x and newer), with npm
- [Rust](https://rustup.rs) toolchain and Xcode Command Line Tools
  (`xcode-select --install`)
- [uv](https://docs.astral.sh/uv/) — manages the Python interpreter
  and dependencies automatically (the core needs Python 3.11+; the
  packaged app falls back to the system `python3`, which is 3.9 on
  macOS and works because the core defers its annotations)

## Build and run

After cloning:

```sh
# 1. Set up the Python core (creates core/.venv; uv installs a suitable
#    Python if needed). The Tauri shell expects this venv.
cd core
uv sync

# 2. Install front-end dependencies and run the desktop app in dev mode.
cd ../app
npm install
npm run tauri dev
```

The first `tauri dev` compiles the Rust shell (a few minutes) and then
opens the game window: the shell spawns the Python core as a child
process and talks JSON lines over stdio.

For a release build (bundled .app / .dmg):

```sh
cd app
npm run tauri build
```

The installed app runs the Python core from the repository checkout it
was built from (its virtualenv), and also bundles a copy of the core
source in the app resources with a `/usr/bin/python3` fallback — so it
works on machines without the repo (Python 3.9+, which ships with the
Xcode Command Line Tools).

## How to play

Press **Enter** on the title screen (the cathedral scene with the
introduction theme) to open the **options page** — the cathedral dimmed
in the background: the left menu selects the gameplay music (Silent by
default, previewed as you browse) and the right menu the handicap —
0, 3, 6, 9, or 12 unfinished garbage rows. Press **Enter** again to
start.

| Key | Action |
| --- | --- |
| Left / Right arrow | Move piece (auto-repeat via core DAS) |
| Down arrow | Soft drop |
| Z | Rotate counter-clockwise |
| X | Rotate clockwise |
| Up / Down arrow (options) | Move within the focused menu |
| Left / Right arrow (options) | Switch menu focus |
| Enter | Title → options → start / Pause |
| ` (backquote, cheat only) | Next gameplay theme |
| Home (cheat only) | Autopilot: high-score strategy |
| End (cheat only) | Autopilot: quick-clear strategy |

Placement points are awarded on every lock. Per line-clear event, the
award is **SINGLE 100 · DOUBLE 400 · TRIPLE 900 · TETRIS 2500**, shown as
a label inside the cleared rows while they wipe from the center outward.
Clear awards are banked and paid once at stage completion. The locked-cell
color changes with the level and repeats every 10 levels. The stats bars
fill slowly against a shared 120-piece scale (or the current leader above
120), and each track shows its exact comma-grouped count vertically.
Clearing a stage (30 lines early, 50 later) freezes the game for the
end-of-stage celebration; press **Enter** to continue to the next level.

### Cheat mode

On the title screen, type the classic Konami code with the arrow keys
and letters — **Up Up Down Down Left Right Left Right B A**. The
cathedral's central tip dome turns green to confirm. While playing,
press **0–9** to jump to that level instantly (gravity and stack color
change immediately). Press **End** for the autopilot's quick-clear
strategy or **Home** for the high-score strategy; either key turns it
off. The autopilot plays at human input speed (an AUTO label shows
above the playfield). End-of-stage breaks play the celebration track
once and the next level starts by itself — no Enter needed.

## Development

```sh
# Python core tests (232 tests)
cd core && uv run pytest

# Front-end type check, music state-machine test, and build
cd app && npm run typecheck && npm test && npm run build

# Rust shell check
cd app/src-tauri && cargo check

# Headless autopilot benchmarks (no UI, no pacing)
cd core && uv run python simulate_autopilot.py --strategy highscore --runs 100
```

### Autopilot sweep: tuning the strategy

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

#### Prerequisites

```sh
cd core
uv sync          # once: creates core/.venv (Python 3.11+)
```

Every command below is run from `core/`.

#### 1. Sweep: compare strategy variants

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

#### 2. Analyse: is the difference real?

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

#### 3. Benchmark: one strategy, in full

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

#### 4. Apply a winning variant

The sweep prints a ranked list; the winner is a full weight profile.
Copy it into `STRATEGIES["highscore"]` in `core/tetris_core/autopilot.py`,
run the test suite (`uv run pytest`), and re-run the benchmark to confirm
the new profile reproduces the swept numbers.

#### Two rules that keep the results trustworthy

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

### Project layout

- `core/` — Python rules engine (`tetris_core/`): board, pieces, DAS,
  gravity, lock delay, scoring, protocol. 60 Hz loop, JSON lines on
  stdio. Tests in `core/tests/`.
  - `core/tetris_core/autopilot.py` — the placement search and both
    strategy weight profiles.
  - `core/sweep_autopilot.py`, `core/simulate_autopilot.py`,
    `core/analyze_frontier.py`, `core/compare_autopilot.py` — the
    headless benchmark and tuning tools (see *Autopilot sweep* above).
- `app/` — React + TypeScript UI and the Tauri (Rust) shell that
  spawns the core and bridges commands/events.
- `assets/` — icon and font files served to the UI.
- `stats/` — saved benchmark CSVs and per-run results.
- `tools/` — pixel-analysis scripts used to sample colors and layout
  from the owner's reference captures.
- `png/` — local reference captures (gitignored; not shipped).
- `TENGEN_TETRIS_SPEC.md` — the authoritative spec. Sections marked
  **VERIFY/TBD** are placeholder rules awaiting source confirmation
  (level progression is 30 lines per stage through level 5, then 50; the
  remaining open item is the exact soft-drop curve).

### Useful notes

- High score persists at
  `~/Library/Application Support/tengen-tetris/highscore.json`.
- Environment overrides for the Python core (mainly for debugging):
  `TETRIS_PYTHON` (path to the interpreter) and `TETRIS_CORE_DIR` (path
  to `core/`).
- Dev-mode auto-reload: `npm run tauri dev` watches both the React and
  Rust sources; Python core changes apply on the next launch.

## License

[MIT](LICENSE) — this project is an original tribute and is not
affiliated with Tengen, Atari, or the original Tetris rights holders.
