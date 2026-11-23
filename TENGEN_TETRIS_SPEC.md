# Tengen-Style Tetris: Tauri + React + Python Spec

Personal practice project. Build a macOS desktop Tetris that matches the rules, feel, and look of the Tengen NES version (1989, Atari Games / Tengen label), with game logic in Python and the UI in React, inside a Tauri shell.

This file supersedes `NES_TETRIS_SPEC.md`, which followed Nintendo's NES version. Do not mix rules from the two versions.

Conventions in this document:

- **VERIFY**: a value that must be looked up in the cited source and written as a test fixture before use.
- **TBD**: a value the owner will supply. Stop and ask rather than invent it.

---

## 1. Goals and non-goals

**Goals**

- Playable single-player marathon mode with the Tengen rules in section 4.
- Game logic in a pure Python package with full unit tests and no UI dependency.
- Tauri desktop app for macOS, with a React UI that draws the board and sends input to Python.
- The same piece colors and rotation feel as Tengen, with a layout that closely follows the owner's reference screenshots.
- Event-driven architecture: the UI never computes game state.

**Non-goals (do not build in v1)**

- Two-player modes, computer opponents, handicaps, and garbage attacks.
- Sound and music.
- Nintendo or Tengen artwork, logos, font glyphs, ROM data, or music. Sprites, text, and styling are original or from open-licensed sources.
- Windows, Linux, and RHEL builds.

---

## 2. Architecture

Three processes, each with one job.

```
React UI  --invoke / events-->  Rust core (Tauri)  --JSON lines over stdio-->  Python game core
(draw + input)                  (window, routing)                              (all game state)
```

| Layer | Responsibility | Must NOT do |
|---|---|---|
| Python game core | Board, pieces, rotation, gravity, lock, line clears, scoring, levels, RNG, statistics, high score file | Touch the UI or the OS window |
| Rust core (Tauri) | Create the window, forward commands to Python, forward state events to the UI, supervise the Python process | Contain game rules |
| React UI | Draw the board and panels from the latest state; send key presses | Compute gravity, scoring, rotation, or any game rule |

### 2.1 Python process

- Entry point: `python -m tetris_core`. Reads JSON lines from stdin, writes JSON lines to stdout.
- Owns one `Game` object. Runs a fixed-rate loop at **60 Hz** using a monotonic clock. Sleep the remainder of each frame; do not sleep a fixed interval.
- Sends one state snapshot per frame in which something changed, plus one immediately after any command.
- Logs go to stderr only. stdout is reserved for protocol messages.

### 2.2 Protocol (JSON lines)

Requests from Rust to Python:

```json
{"id": 12, "cmd": "input", "action": "left"}
{"id": 13, "cmd": "new_game", "level": 0}
{"id": 14, "cmd": "pause"}
{"id": 15, "cmd": "get_state"}
```

Actions for `input`: `left`, `right`, `soft_drop_on`, `soft_drop_off`, `rotate_cw`, `rotate_ccw`.

Events from Python to Rust, forwarded to the UI:

```json
{"type": "state", "frame": 1234, "board": [[0,0,...], ...], "current": {"kind": "T", "cells": [[x,y],...]}, "next": "L", "score": 0, "lines": 0, "level": 0, "high_score": 0, "stats": {"T": 0, "J": 0, "Z": 0, "O": 0, "S": 0, "L": 0, "I": 0}, "status": "playing", "autopilot": false, "color_index": 3}
{"type": "response", "id": 12, "ok": true}
{"type": "response", "id": 12, "ok": false, "error": "message"}
{"type": "log", "level": "error", "message": "..."}
```

Rules:

- `board` is 20 rows by 10 columns, row 0 at the top. Each cell is `0` for empty, or a piece index `1` to `7` (I, O, T, S, Z, J, L).
- `color_index` is the locked-piece color for the current level (see section 6.2). The UI maps it to a hex value from `theme.ts`.
- `status` is `playing`, `paused`, or `game_over`.
- Every command gets a `response` with the same `id`. Commands are processed in order.
- Python never crashes on bad input. Malformed JSON gets an `error` response and the process keeps running.

### 2.3 Rust process

- Spawns the Python process at startup and keeps it **Starting** until the first valid state snapshot. A child that exits before that snapshot is a startup failure: the shell reaps it, emits `core-error`, and waits for a manual Retry. A child that exits after a ready state is restarted automatically.
- Exposes Tauri commands that forward to Python: `send_input(action)`, `new_game(level, music, handicap)`, `pause()`, `get_state()`, and the cheat commands `set_level`, `set_music`, `set_autopilot`.
- Keeps the latest state in memory and emits a `game-state` event to the UI for each `state` message.
- Does not interpret game data.
- Core resolution (fixed 2026-10-25; the packaged app previously spun on "connecting" because `CARGO_MANIFEST_DIR` was read at runtime, which is empty in an installed app): `TETRIS_CORE_DIR`/`TETRIS_PYTHON` env overrides; else the repository checkout baked in at compile time (`env!("CARGO_MANIFEST_DIR")/../../core`, using its `.venv/bin/python` — dev and installs on the build machine); else the core source bundled into the app resources (`bundle.resources` maps `core/tetris_core` to `Resources/tetris_core`) run with `/usr/bin/python3` (the core uses `from __future__ import annotations`, so Python 3.9+ works).

### 2.4 React UI

- React with TypeScript, built with Vite. The playfield is drawn on a `<canvas>` inside a component.
- A `useGameState` hook subscribes to `game-state` and stores the latest state. Components render from that state only.
- Keyboard events are sent to Rust as commands. Auto-repeat for left and right comes from Python's DAS logic, not from the browser. Send `left` or `right` on keydown, and stop on keyup.
- Components never compute game rules.

---

## 3. Repository layout

```
tengen-tetris/
  TENGEN_TETRIS_SPEC.md      # this document
  README.md                  # build/run instructions and the sweep workflow
  png/                       # owner's reference screenshots (read-only, see section 6.0)
  core/                      # Python package
    pyproject.toml
    tetris_core/
      __main__.py            # stdin/stdout JSON-line loop, 60 Hz frame loop
      game.py                # state machine, frame update, autopilot execution
      board.py               # 10x23 grid (20 visible + 3 hidden), collision, line clear
      pieces.py              # tetromino shapes and rotation states from the Tengen table
      gravity.py             # soft drop and level speed table
      scoring.py             # line clear bonuses
      rng.py                 # piece generator
      stats.py               # per-piece counters
      highscore.py           # read/write high score JSON
      protocol.py            # parse commands, build events
      autopilot.py           # placement search + the two strategy profiles (section 4.11)
    simulate_autopilot.py    # headless benchmark of one strategy
    sweep_autopilot.py       # variant comparison over a shared seed set
    analyze_frontier.py      # paired statistics for a sweep CSV
    compare_autopilot.py     # side-by-side table of two benchmark CSVs
    tests/
      helpers.py             # shared fixtures for the test files
      test_board.py
      test_pieces.py
      test_rotation.py
      test_gravity.py
      test_scoring.py
      test_rng.py
      test_game_flow.py
      test_autopilot.py
  app/                       # Tauri project
    src-tauri/               # Rust shell (spawns Python, routes commands/events)
      src/main.rs            # executable entry point
      src/lib.rs             # Tauri setup, commands, and registration
      src/python_core.rs     # Python child process and protocol transport
    src/                     # React UI (TypeScript, Vite)
      main.tsx
      App.tsx                # screen flow and wiring
      components/            # Board, NextPreview, ScorePanel, StatsPanel, Overlay,
                             # OptionsScreen, TitleScreen, cathedral.ts, draw.ts
      hooks/                 # useGameState, useGameAudio, useGameKeyboard
      theme.ts               # logical resolution, palette, layout metrics
      controls.ts            # the keyboard binding table
      audioPlan.ts           # music-track state machine
      sfxPlan.ts             # sound-effect / AudioContext policy
    scripts/                 # front-end tests (music state machine, SFX plan)
  assets/
    font/                    # open-licensed pixel font (section 6.3)
  tools/                     # pixel-analysis scripts for the reference captures
  stats/                     # saved benchmark CSVs and per-run results
```

---

## 4. Game rules (Tengen)

### 4.1 Playfield and spawn

- Playfield: 10 columns by 20 rows.
- Seven tetrominoes: I, O, T, S, Z, J, L.
- Spawn: the piece's bounding box has its left side at column 5. Owner decision 2026-10-24: the piece spawns at the top of the **visible** playfield (extended-board row `HIDDEN_ROWS`, i.e. `SPAWN_Y = HIDDEN_ROWS` in `game.py`), not hidden above it — the next piece must show immediately after the previous one locks. Game over triggers when the spawn cells are blocked by the stack (spec 4.8).
- Next-piece preview: one piece.
- No hold piece. No hard drop.

### 4.2 Rotation (critical: this differs from NES Tetris)

- Rotations are the Atari arcade system, not the Nintendo rotation system.
- In every rotation state, the piece touches the **left and top edges of its 3×3 bounding box**. The exception is the vertical I, which sits in the second column of its box.
- This means rotation is anchored to the top-left corner. A classic T-spin is not possible.
- **Wall kick:** if a rotation would overlap the wall, the game tries shifting the piece one square to the left, and rejects the rotation if that also fails. This is the same one-square kick as the arcade original. **VERIFY** whether the kick also applies to the right wall and to floor contact, and write tests for each case.
- Rotation clockwise and counterclockwise both use this table.
- **VERIFY** all rotation states for all seven pieces against the source. Write one test per piece per state.

### 4.3 Gravity and soft drop

The normal-gravity intervals are the Tengen cartridge table (frames per row at 60 Hz):

```
level:  0   1   2   3   4   5   6  7  8  9  10   11  12   13   14   15   16  17
fpr:   33  28  24  20  17  14  11  9  7  6  5.5  5   4.5  4    3.75 3.5  3.25 3
```

Levels past 17 use the last entry (3 fpr); a negative level uses level 0. The game keeps fractional progress in quarter-frame units (add 4 per tick, drop when the accumulator reaches `fpr * 4`, subtract the threshold), so 5.5, 3.75, 3.25 and 3.5 are exact. When the effective speed increases (Down pressed or a level-up), stale accumulator progress is discarded rather than banked, so a speed change cannot cause a burst of drops or a backlog. The accumulator resets on each new piece.

Soft drop is a provisional Tengen-style acceleration curve, not a source-confirmed cartridge curve: while Down is held, use the faster of normal gravity and a curve that starts at 6 fpr, loses one frame per row every four held frames, and floors at 1 fpr. Holding Down therefore always helps, never hurts.

Source: TetrisWiki, "Tetris (NES, Tengen)" gravity table. Open item: the exact soft-drop curve.

### 4.4 Lock delay

- Owner decision 2026-10-24, refined the same day: when the piece cannot fall further, the player gets a **short** grace window — a fixed 10 frames (`LOCK_DELAY_FRAMES`), capped by the level's `frames_per_row` so it keeps shrinking as gravity speeds up (`lock_delay_frames(level)` in `game.py`). A full "1 drop" interval was tried first and felt too long.
- The window does not reset on movement, so it stays bounded. Moving the piece off a ledge cancels it: gravity resumes and a fresh window starts at the next landing.

### 4.5 Line clears, scoring, and levels

- **Placement points** are awarded exactly once per lock, including locks that clear nothing. Use the level and drop state at landing, before any stage advance:
  `min(d * r * (r + h), 999)` where `r = level + 1`, `d = 2` for a soft-drop landing (Down held at first contact, even if released during the lock delay) and `1` otherwise, and `h` is the height of the piece's **lowest occupied cell**, counted from 0 on the bottom visible row. The lowest-cell mapping is the disassembly's bitmap-scan behavior (`main.asm` L8658-L8692 keeps the last occupied cell before L9A47 adds it to the level term). Source: TetrisWiki, "Tetris (NES, Tengen)".
- **Clear awards** are single **100**, double **400**, triple **900**, tetris **2500** (`points_for_clear` in `scoring.py`). The award for each clear event is accumulated into a **pending stage award** and credited once, on stage completion. It is not paid immediately on every clear. The flat 300-point block bonus is removed. The immediate clear label **SINGLE / DOUBLE / TRIPLE / TETRIS** still appears while the rows wipe.
- Line-clear animation (owner decisions 2026-10-24, reference `png/screenshot_11.png`): completed rows stay visible and are wiped **from the center to both sides** — one column-pair every 4 frames (pairs {4,5}, {3,6}, {2,7}, {1,8}, {0,9}; `WIPE_FRAMES_PER_PAIR` in `theme.ts`) — then the rows are removed and the next piece spawns after `CLEAR_ANIM_FRAMES` (24). The core drives the timing and reports `clearing: {rows, frame}` in the state event; the UI only renders the wipe and the label.
- **Level curve and stage boundaries** (Tengen manual p. 9; TetrisWiki): stages are 30 lines for levels 0-4, then 50 lines for level 5 and above. The displayed level caps at 17. Stage boundaries are tracked independently of the displayed level, so 800, 850, ... still end stages and pay the pending award after the cap. For a normal game starting at 0: 30, 60, 90, 120, 150, 200, 250, ..., 750, 800, 850. A clear that overshoots a boundary completes exactly one stage if only one threshold is crossed (for example, a triple from 149 to 152 completes the level-4 stage and leaves the next boundary at 200).
- Cheat (owner request 2026-10-25): typing the classic Konami sequence on the title screen — **↑ ↑ ↓ ↓ ← → ← → B A**, physical keys — unlocks cheat mode. The indicator is the cathedral itself: the central tent tower's tip dome turns **green** on the title screen. During play, digit keys **0-9** jump to that level immediately via the `set_level` protocol command: gravity and the locked color change at once. The jump anchors at the start of the current stage, preserving progress inside it; selecting level 5 at line 30 must keep level 5 on line 31. Owner addition 2026-10-27: the **Home** key toggles the AI autopilot (section 4.11), and the backquote key cycles the gameplay music — both only while the cheat is active.
- Score cap: the placement formula caps at 999 per lock; there is no separate total-score cap in the implementation. **VERIFY** whether the cartridge has a total cap.

### 4.6 Piece generator (RNG)

- **VERIFY** the Tengen randomizer. Do not assume the Nintendo reroll rule, and do not use 7-bag.
- The generator must be seedable so tests are deterministic.

### 4.7 DAS and input timing

- Delayed Auto Shift: after a left or right press, wait a fixed number of frames, then repeat the movement at a fixed rate while held.
- **VERIFY** the Tengen DAS and repeat values. Implement them as frame counters in Python.

### 4.8 Game over

- The game ends when a new piece cannot spawn. Set `status` to `game_over`, save the high score if it was beaten, and stop the frame loop.

### 4.9 Statistics

- Count how many times each piece has spawned in the current game. Show all seven counts in the stats panel.
- Owner decision 2026-10-24, per the captures: the counts render as **vertical bars growing upward** — one column per piece with the glyph at the bottom and a bar above it that grows upward with the count; every bar track sits at the same height (fixed-height glyph area). Owner correction 2026-10-25: the per-piece weight is scaled so the bar fills slowly — full at **120 pieces of one kind**, which lands around level 10 (the 12-of-a-kind draft filled within a minute of play). A horizontal tick marks every 10 pieces. The exact count is drawn vertically inside each track (English comma grouping, rotated 90° counter-clockwise so the first digit is nearest the bottom). One shared ceiling per snapshot keeps all bars comparable: `max(120, current leader)`, so a leader above 120 fills its track without dropping the others to half height, and a new game returns to the 120 scale. Ticks are 12 evenly spaced subdivisions of the current ceiling (`StatsPanel.tsx`, `STATS_BAR_MAX` / `STATS_TICK_EVERY` in `theme.ts`).
- Owner correction 2026-10-27, closest to the original: the bar tracks are **black** with **no boundary line**, every bar fills with one **yellowish** color (`STATS_BAR_FILL` in `theme.ts`, between the T and J shape colors) with translucent-white ticks, and the columns are tightly and evenly pitched (about half the earlier spacing; the piece glyphs shrank to match, cell 16 — their bounding boxes must fit the column so nothing overlaps).

### 4.10 High score

- Stored as JSON in the macOS application support folder, for example `~/Library/Application Support/tengen-tetris/highscore.json`. Created on first save.
- Owner decision 2026-10-25: the file keeps a **top-5 table** of `{"score", "at"}` records (ISO timestamp), sorted by score descending; the old single-score format is migrated on first load. On game over, a score that would enter the table is inserted, persisted, and reported (`top_scores`, `top_run` in the state event) — see the game-over fireworks screen in section 5. Scores of 0 never qualify; with an under-filled table any positive score qualifies.

### 4.11 Autopilot (cheat; owner request 2026-10-27, throttled and given two strategies 2026-10-28)

- With the Konami cheat active, **End** selects strategy #1 and **Home** selects strategy #2; either key turns the autopilot off again, and switching keys switches strategies. Outside cheat mode neither key does anything. The mode persists across games. The UI shows `AUTO - QUICK CLEAR LINES` or `AUTO - HIGH SCORE` above the playfield while it drives.
- The placement search (`core/tetris_core/autopilot.py`) enumerates every landing for the current piece, simulates the lock and line clears, and scores the result with published **El-Tetris** feature weights — landing height, cleared rows, row/column transitions, holes, well sums (one-piece lookahead). Pure functions; no game rules live there. Named "autopilot", not "AI": it is pure calculation.
- Execution (`Game._autopilot_step`) is throttled to **human input speed** (owner correction 2026-10-28: "auto mode, not god mode"): one rotation or one lateral step per frame — the discrete key-press rate of tapping X or the arrows — while the piece descends at soft-drop speed through the normal gravity machinery (the Down-key rate). The plan is computed once per piece; a blocked step (or no legal placement at all) abandons the piece to fall naturally.
- While the autopilot drives, human movement inputs are ignored; Enter (pause) still works. **The end-of-stage celebration is never skipped by the autopilot itself** — the celebration plays for its full window and the next level starts by itself (owner request 2026-10-29, section 5).
- Protocol: `set_autopilot` command (`{"cmd": "set_autopilot", "mode": "quick" | "highscore" | null}`); the state event reports `"autopilot"`.

#### 4.11.1 How the placement search works

Both strategies use the **same** search; only the weights differ.

For the piece that is about to fall, the search tries every legal placement — each of the four rotation states, at every column where the piece fits — and for each candidate it:

1. **Simulates the drop.** The piece is lowered straight down at that column until it comes to rest (`_resting_cells`). This simplified drop ignores the lock delay and the DAS; it only answers "where would it land?".
2. **Simulates the lock and the clears.** The piece is written into a *copy* of the board, and any completed rows are removed and everything above them shifted down (`_lock`). The live board is never touched.
3. **Measures the resulting board** (`_score`), producing these El-Tetris features:
   - **Landing height** — the average height of the piece's resting cells, measured on the *pre-lock* board.
   - **Cleared rows** and **clear points** — how much was cleared, and what the Tengen award table pays for it (single 100, double 400, triple 900, tetris 2500).
   - **Row transitions** — how many times a row alternates between empty and filled (the walls count as filled). A jagged surface has many; a flat one has none.
   - **Column transitions** — the same idea vertically (the floor counts as filled). This is what punishes overhangs and buried gaps.
   - **Holes** — empty cells buried under the stack. These can never be filled again, so they are permanent damage and the most heavily punished feature.
   - **Well sums** — the depth of single-column gaps flanked by filled cells, charged quadratically (a depth-4 well costs 10). A *shallow* well is good: it is the pocket an I-piece later fills for a tetris. A *deep* well is a trap.
4. **Combines them linearly** into one number with the strategy's weight profile, and keeps the highest-scoring candidate.

There are at most 4 rotations x 10 columns = 40 candidates per piece, so the search is cheap — but it is still run **once per piece**, not once per frame.

> **Historical measurements.** The benchmark numbers in sections 4.11.2–4.11.3 and the comparison summary were measured under the earlier gravity and scoring rules, before the Tengen update. They are kept to describe the archived CSVs and the earlier tuning record; they are not measurements of what the current ruleset produces.

#### 4.11.2 Strategy #1 "quick" — clear lines as fast as possible

Selected with **End**; the UI shows `AUTO - QUICK CLEAR LINES`.

The classic linear El-Tetris objective: **clear lines as quickly as possible**. A single is worth exactly as much as one row of a tetris.

| Weight | Value | Effect |
| --- | --- | --- |
| `lines_w` | +3.418 | Every cleared row earns the same amount. |
| `landing_w` | −4.500 | Landing high is bad, at the published El-Tetris rate. |
| `landing_free` | 0 | Every row of landing height costs; there is no free stacking band. |
| `points_w` | 0 | The *value* of a clear is ignored — only its size counts. |
| `defer_w` | 0 | Never refuses a clear. |
| `safe_h` | 0 | No deferral, so no stack-height threshold either. |
| `well_w` | −3.386 | Published well penalty; deep wells are punished. |
| `holes_w` | −7.899 | Published hole penalty. |

**What it looks like in play:** the stack is kept low and flat, lines are cleared the moment they are available, and it does not care whether a clear was a single or a tetris. Because the objective is line *rate*, it clears many lines cheaply.

**Historical measurement** (seeded benchmark under the earlier rules: seed 42, 399,600 frames = 111 minutes at 60 Hz): **4,326 lines** cleared, **3 tetrises**, **149 points per line**.

That is a single seed at a fixed window: enough to show the *shape* of the strategy, not enough to compare two strategies. Comparing strategies needs the paired sweep (4.11.5).

**Historical measurement over 100 games** (master seed 20261028, 3,000,000-frame cap — the shipped artifact `stats/autopilot-quick-100games.csv`): **31,943 lines** and **11.9 tetrises** per game on average, **148 points per line**. The archived quick-clear CSV records **0 early deaths before 3,000 lines**, **90 runs reaching the 3,000,000-frame cap**, and **10 later top-outs**. It does not show a strategy that never dies; it shows a strategy that survives the early game and can still top out later.

#### 4.11.3 Strategy #2 "highscore" — maximize the score

Selected with **Home**; the UI shows `AUTO - HIGH SCORE`.

Maximizes score rather than line rate. Because the Tengen award table is strongly super-linear (a tetris pays 25x a single), the strategy is built around **hunting tetrises and triples** and refusing the small clears that would get in their way.

| Weight | Value | Effect |
| --- | --- | --- |
| `points_w` | +1.0 | Clears are paid by their **point value** (1/4/9/25 per 100 points), so a tetris is worth 25x a single. |
| `lines_w` | 0 | No flat per-row payment while the stack is safe — size alone does not earn. |
| `defer_w` | 25.0 | The cost of **refusing** a 1–2 line clear while the stack is safe and clean. |
| `safe_h` | 10 | At or above this stack height (the tallest column) the deferral is waived — survival first. |
| `landing_free` | 4.0 | Stacking below 4 rows is **free**; the stack may build up a little without cost. |
| `landing_w` | −4.500 | Above the free band, landing high is charged at the published rate. |
| `well_w` | −2.0 | **Relaxed** (half the published −3.386): the strategy *needs* a well column to hold for the I-piece. Roofing a well must never pay, but holding one open is intended. |
| `holes_w` | −12.0 | **Extra caution**: buried wells are catastrophic, so holes are punished harder than in the published weights. |

**The deferral rule.** A placement that clears 1 or 2 rows is charged the `defer_w` cost — so the strategy has to be *convinced* the small clear is not worth taking — but only when all of these hold: the stack is below `safe_h` (10 rows), there are **no holes** anywhere, and the board is not yet dangerous. As soon as the stack grows, holes appear, or the danger ramp engages, the deferral is waived and the strategy takes every clear it can get.

**What it looks like in play:** the stack is allowed to build up to about ten rows; a single column is kept open as a well; small clears are refused in the hope that an I-piece or a triple follows; and when the stack approaches the ceiling the behaviour changes completely — see below.

**Historical measurement** (same seed and window as the quick strategy, under the earlier rules): **4,881 lines** cleared, **56 tetrises**, **217 points per line** — roughly **16x** the tetris rate of the quick strategy (11.5 vs 0.7 tetrises per 1,000 lines), for 13% more lines.

> **Why this number is lower than earlier revisions of this spec.** An earlier revision quoted 95 tetrises and 234 points per line for the same seed and window. The 2026-10-29 board-fullness ramp (4.11.4) deliberately changed the strategy's behaviour once the stack fills: it stops holding a well open for an I-piece and starts taking the small clears it was previously refusing. That is the same change that bought the early-death improvement below, and it costs tetris rate. The numbers above are historical measurements under the earlier ruleset, not measurements of the current post-update code.

**Historical measurement over 100 games** (master seed 20261028, 3,000,000-frame cap — the shipped artifact `stats/autopilot-highscore-100games.csv`): **25,941 lines** and **308.6 tetrises** per game on average, **218 points per line**, and **6/100 early deaths**.

**Historical comparison (earlier gravity/scoring rules).** The two strategies answer different questions, and the archived 100-game table shows the trade-off plainly:

| | quick ("End") | highscore ("Home") |
| --- | --- | --- |
| Score per game (mean) | 4,726,478 | **5,666,758** |
| Lines per game | **31,943** | 25,941 |
| Tetrises per game | 11.9 | **308.6** |
| Points per line | 148 | **218** |
| Early deaths (died under 3,000 lines) | **0/100** | 6/100 |

The quick strategy wins on raw line count and had no early deaths before 3,000 lines; the archived quick-clear CSV records 90 runs reaching the frame cap and 10 later top-outs. The high-score strategy earns **47% more points per line** and lands **26x** as many tetrises, at the cost of dying sometimes and clearing 19% fewer lines. Because a tetris pays 25x a single, the high-score strategy still posts a **higher score per game** (+20% on the mean, +60% on the median) — that is the whole point of the mode.

#### 4.11.4 Board-fullness awareness (the "danger" ramp)

Owner request 2026-10-29: *"reduce the aggressiveness when the board is getting fuller than half, that will reduce chance of early death, because when the board is half full it is difficult to recover."*

The "highscore" profile therefore **blends its weights** toward a set of *danger* weights as the stack rises. The blend factor runs from 0.0 (safe) to 1.0 (fully dangerous) over `danger_h` = 10 rows and `danger_span` = 6 rows, so the strategy is fully in survival mode at a stack height of 16 rows. The danger level is measured on the board **before** the candidate placement, so every candidate is judged in the same context and the comparison stays fair.

| Weight | Safe value | Danger value | Effect at full danger |
| --- | --- | --- | --- |
| `landing_w` | −4.500 | **−14.0** | A much stronger pull toward low landings. |
| `landing_free` | 4.0 | **0.0** | The free stacking allowance disappears. |
| `well_w` | −2.0 | **−14.0** | Stop holding a deep well open — a well plus a tower is how the board dies. |
| `holes_w` | −12.0 | **−32.0** | Buried holes are fatal when the board is full. |
| `points_w` | 1.0 | 1.0 | Clears stay worth their point value. |
| `flat_w` | 0.0 | **−8.0** | A flatness penalty: the sum of the height steps between neighbouring columns. |

**Why the flatness penalty exists.** A deep canyon next to a tall tower is the death shape, and the **well metric cannot see it** — a well needs *both* neighbours filled at that row, and in a canyon one neighbour is empty. The flatness term measures the surface roughness directly, so it catches the shape the well term misses.

**Measured** on 400 held-out seeds (master seed 77777, 250k-frame budget): early deaths (fewer than 3000 lines) fell from **78/400 to 33/400** against the pre-2026-10-29 profile, with the median score within 1%.

#### 4.11.5 Measurement rules

The autopilot strategies are tuned with a headless sweep, and the rules below are what make the numbers trustworthy:

- **Headless benchmark scripts.** `core/simulate_autopilot.py` (distribution over a seed set, one strategy) and `core/sweep_autopilot.py` (variant comparison under one frame budget). `core/analyze_frontier.py` performs the paired statistical test; `core/compare_autopilot.py` prints a plain side-by-side table. All of them run the real `Game` and the real autopilot code — only the 60 Hz sleep between frames is removed, so a headless score is a score the app could really produce. The commands are documented in the README section "Autopilot sweep".
- **The same seeds for every variant.** Every sweep variant plays an identical seed list, so variant-to-variant comparison is **paired** — McNemar's exact test on the discordant seeds plus a paired bootstrap CI on the score deltas. Comparing two independent death rates is misleading: on 400 seeds, differences of 4–6 deaths sit at the noise floor, and one earlier apparent 6-death improvement tested at p = 0.36. Re-measured the paired way, the board-fullness change is **not** a trade of score for survival — it delivers both: 33/400 vs 78/400 early deaths (McNemar p < 0.0001, b/c = 69/24) *and* a mean score up 27,432 (95% CI [+9,944, +46,468]). The 400-seed figures above were measured with `--master-seed 77777`; a sweep on the default master seed (11111) draws a different seed list and is a different — equally valid, but not comparable — sample, so the master seed is quoted alongside every published number.
- **Candidate seeds must not be drawn from the set where the current profile dies.** That screen is biased, and an earlier round built on it was a mirage.
- **Never judge on one seed.** A single run is luck; use ≥ 400 seeds and the paired test before believing any change.

#### 4.11.6 The score/survival tradeoff

The tradeoff lives on the *tetris-hunting* axis, not the board-fullness axis. `safe_h` decides when the strategy stops deferring small clears to hunt a tetris; on 400 seeds, `safe_h` 4 (barely defer) gives 12/400 early deaths at a mean score of 514,204, against 20/400 and 635,189 for the shipped `safe_h` 10 — 40% fewer early deaths for 19% less score. The score side of that trade is solid (paired delta −120,985, 95% CI [−131,952, −108,669]); the survival side is directional but underpowered at 400 seeds (McNemar p = 0.22) and would need ~1200–1600 seeds to resolve.

Two decompositions explain the shape of the trade: a deferred piece is followed by a tetris within 12 pieces at the *same* rate as a non-deferred one (33.5% vs 30.5% measured in live games — **the deferral is not buying extra tetrises, it is refusing points**), and tetrises are only 13.6% of the score (doubles 40.1%, triples 27.3%, singles 14.5%, block bonuses 4.6%) even though the strategy is built around hunting them.

#### 4.11.7 Three further profile knobs, implemented but inert

- **`landing_credit`** credits a placement for the stack height its own clear removes. The landing height is measured on the pre-lock board, so a tetris was charged the landing cost of four rows it had just deleted — a modelling bug rather than a tuning choice.
- **`defer_well`** holds back a small clear only when a big one is actually reachable (a one-column well at least `defer_well` deep — measured live to fire on 42%/16%/6% of decisions at thresholds 2/3/4, so it is not inert).
- **`defer_max`** caps the size of a clear still worth refusing. A single is worth 100 points and a double 400, so refusing a double to chase a 2500-point tetris is a worse bet than refusing a single.

All three default to the behaviour of the validated profile, so the shipped strategy is unchanged; they await the measurement that would justify enabling one.

---

## 5. Screens

- **Start / title screen** (owner request 2026-10-24, refined 2026-10-25): the composition follows `png/screenshot_00.png` — gold border bands with green diamond studs top and bottom, a full-screen light-blue double frame, a red italic `TETRIS` wordmark, the Saint Basil's Cathedral scene (adapted from the owner's reference render `png/Saint_Basil's_Cathedral_render.ts`: pale sky with sun, stone platform, terracotta walls with white arcade, onion domes with Orthodox crosses, central tent tower with gold lattice — `cathedral.ts`), and a blinking `PRESS ENTER` with the introduction theme (01) looping. No menus on the title (owner decision 2026-10-25).
- **Options page** (owner request 2026-10-25, refined the same day): reached from the title with Enter, with the cathedral drawn dimmed as the background and no background music. The left column lists the gameplay music — **Silent (first, default)**, Loginska (02), Bradinsky (03), Kalinka (04), Troika (05) — each previewed as the selection lands on it; the right column lists the handicap levels **0, 3, 6, 9, 12** as a full menu. Up/Down move within the focused column, Left/Right switch focus, Enter starts the game with the selections (`new_game` carries the track id and handicap; the state event reports `music_track` and `music_phase`). Pausing the game also pauses the music; it resumes in place on unpause. The cheat sequence's arrow presses net out to no menu movement on this page.
- **Pause:** freezes the frame loop and shows PAUSE over the playfield.
- **Game over:** shows GAME OVER over the playfield with the final score. Press Start to play again. Owner addition 2026-10-25: if the run's score enters the **top 5**, the game-over screen instead shows the top-5 records (rank, date/time, score) and plays the four firework rockets (`music/tetris_firework1..4.mp3`) in a loop until Enter restarts.
- **Title music** (owner request 2026-10-25): `music/01_-_Tetris_Tengen_-_NES_-_Introduction.ogg` loops on the intro/title page only. Owner correction 2026-10-27 (matching the original game): Introduction is not selectable on the options page and is not part of the gameplay loop. The owner supplies and tracks the music files by decision (spec 1 non-goals cover artwork, not the owner's own music files).
- **End-of-stage celebration** (owner request 2026-10-25, changed by the owner 2026-10-29): clearing a 30-line block freezes the game in the new `level_complete` status — 06 (End of Stage) plays **once** and then **the next level starts by itself**; there is no Katyusha (07) chain and no wait for Enter (Enter still skips ahead for the impatient). The celebration window is 210 frames (3.5 s), long enough for 06 (2.48 s) or 09 (3.24 s) to play once. Clearing level 9/19/29... (the new level is a multiple of 10) plays 09 (Victory) instead (`music_phase: "milestone"`). Game over plays 08 once (`music_phase: "game_over"`).
- **Audio playback** (owner request 2026-10-29, after "the music sometime got interrupted and be silent for 1 second, sometime this happen very often ... later in the game, sound of 'clear line' and 'block drop' are complete gone"): the music is driven by a state machine (`app/src/audioPlan.ts`, pure and unit-tested in `app/scripts/audio-plan.test.ts`) that never reloads a track it already holds — assigning a new `src` makes the browser load and decode the whole file (up to 2.9 MB) again, which was the second of silence. Concretely: the theme element keeps its source and position across a celebration (only the cue element plays over it), the gameplay playlist hands over by swapping two elements — the next track is preloaded in the spare one — and the sound effects release their `GainNode`/`AudioBufferSourceNode` when they end and rebuild an `AudioContext` that the browser left *interrupted* (WebKit's spelling of *suspended*), which is what killed the block-drop and line-clear sounds later in a game.
- **Cheat music change** (owner request 2026-10-25): with the Konami cheat active, the backquote key cycles the gameplay music mid-game (Loginska → Bradinsky → Kalinka → Troika) via the `set_music` protocol command; normally the music is fixed during play.
- **Gameplay playlist** (owner request 2026-10-25): when a theme (not Silent) is selected, gameplay starts with the selected theme and then loops through the four gameplay themes in order; each track advances on its own `ended` event. Owner correction 2026-10-27: after an end-of-stage celebration, the playlist continues with the theme that was playing right before the level ended, at its position — it does not restart from the selection. New games and the cheat music change still start fresh; Silent stays silent. Owner addition 2026-10-29: the advance is seamless — the next track is preloaded in a second element and the two swap, so the music never falls silent between tracks.
- **Landing pop & row-clear sound** (owner request 2026-10-25): every piece lock bumps `lock_count` and every clear event bumps `clear_count` in the state event; the UI plays the owner's exact original samples — `music/tetris_block_drop.mp3` and `music/tetris_line_clear.mp3` — on each increment.
- **Menu select sounds** (owner request 2026-10-25): `music/tetris_select1.mp3` plays when a menu selection moves down, `music/tetris_select2.mp3` when it moves up (both title-screen menus on the options page).
- **Handicap** (owner request 2026-10-25): the options page offers **0, 3, 6, 9, 12** unfinished rows. The chosen count of bottom rows starts filled with exactly one random hole each (`new_game` carries the handicap; `PieceRNG.hole_column` picks the gap).

Exact text, positions, and timing: **TBD**, from the owner's reference captures.

---

## 6. Visual design

The target is the look of the Tengen version, implemented with original code and open-licensed assets.

### 6.1 Layout

Use the owner's reference screenshot as the layout guide. Main regions:

- A header or side panel with labels for next piece, score, high score, lines, level, and statistics.
- The playfield, inside a bordered frame.
- A next-piece preview.
- A statistics panel listing the seven piece counts.

Measurements (playfield offset, cell size, panel sizes): **TBD**. Capture the Tengen version at native 256×240 resolution, measure positions in those pixels, then convert them to the logical coordinate space described in section 6.4. Do not render at 256×240 directly. See section 6.4.

**Note on the reference:** the earlier screenshot shows the labels NEXT, SCORE, HIGH SCORE, LINES, LEVEL, and STATS, and stacked pieces in yellow-olive tones. The owner must confirm whether that screenshot is from the Tengen version. If it is not, all layout measurements must come from a Tengen capture.

### 6.0 Reference screenshots (`png/` folder)

- The owner has downloaded reference screenshots into the `png/` folder at the repository root. Use them to measure layout and to sample colors.
- Treat the folder as read-only reference material. Do not copy images, sprites, or text glyphs from it into `app/` or `core/`, and do not ship any of these images in the build.
- Before measuring, check each file's name and content to see which version it shows. Only Tengen captures should drive the layout and palette. Ask the owner about any file you cannot identify.

### 6.2 Piece colors (critical: differs from NES Tetris)

- **Falling pieces** show their own color by kind, as in the reference.
- **Locked pieces** all become the same color when they lock, due to NES picture memory limits. The color changes from level to level. This is the Tengen behavior.
- The locked color changes with the level. Owner decision 2026-10-24 (replaces the previous TBD): the color cycles every **10 levels** — level 0 **grayish white**, 1 red (piece I), 2 goldish yellow (T), 3 blue (O), 4 yellow (J), 5 pink (L), 6 green (S), 7 tortoise (Z), 8 purple, 9 green (S) again — then repeats (level 10 back to grayish white, 11 = 1, 12 = 2, and so on). The core sends `color_index = level % 10` (`locked_color_index`); the UI maps it through the `LOCKED_COLORS` table in `theme.ts`.
- The falling-piece colors and the locked-color table are the two palettes. Store both in `theme.ts`.

### 6.3 Palette and blocks

- **Background, frame, border, falling-piece colors, locked-piece colors, text:** TBD. Sample from the owner's Tengen captures. Do not invent a palette.
- **Blocks:** draw each block as a square with a two-tone bevel: a lighter top and left edge, a darker bottom and right edge, and a one-pixel outline. Do not copy any sprite art from a capture. Changed 2026-10-24 at the owner's request: flat bevel bands read as one big pixel, so blocks are now drawn with rounded corners (radius ~12% of the cell), a thin black outline (~2%), and gradient edge shading — light top+right, dark left+bottom, each fading to transparent over ~13% of the cell (`drawBlock` in `app/src/components/draw.ts`).
- **Text:** use an open-licensed pixel font. Recommended: Press Start 2P (open-licensed, Google Fonts). Do not extract glyphs from any capture or ROM. Changed 2026-10-24 at the owner's request: the pixel font read as low-resolution at display sizes, so the UI now uses the smooth system font stack `FONT_SMOOTH` in `theme.ts` (spec 6.4 permits this switch). The Press Start 2P file stays in `assets/font` in case the retro look is wanted later.

---

### 6.4 Resolution and scaling (finer than the NES, independent of window size)

- **Logical resolution:** the UI is laid out in a fixed logical coordinate space, separate from the window size. Default: **1024 × 960**, which is 4× the NES's 256 × 240 in each direction. Store the width and height in `theme.ts` so the owner can change them. Propose any other value that works better, but keep the 4:3-equivalent aspect ratio of the NES output (256:240).
- **Measurements convert to logical space:** a position measured in a 256 × 240 capture is multiplied by the logical scale factor (4 by default). The layout code must use logical units only, never raw screen pixels.
- **Canvas backing store:** the canvas size equals the window's CSS size multiplied by `window.devicePixelRatio`. Recompute it on every window resize, and redraw immediately.
- **Fit to window:** scale the logical space to fit the window with uniform scaling and letterboxing. Keep the aspect ratio. Do not stretch.
- **Drawing:** draw every block, bevel, frame, and piece with vector-style shapes (rectangles and paths) at logical coordinates, so edges stay sharp at any window size. Do not upscale a small bitmap with CSS or canvas `scale()`, which blurs the output.
- **Text:** render text at the device pixel size. Use a font that stays crisp at non-integer scales. The pixel font from section 6.3 can look uneven when scaled, so test it at several window sizes and pick a font size that stays clean. If it looks wrong, switch to a smooth font and note the change.
- **Optional integer-scale mode:** provide a setting that snaps the scale factor to a whole number, for a chunkier retro look. Default: off.
- **Performance:** redraw only when the state changes or the window resizes. Keep the board drawing to one pass per frame.

### 6.5 App icon (owner request 2026-10-25)

- Four vector-style blocks in a 2×2 arrangement — red (I), blue (O), gold (J), green (S) — with the game's three-tone bevel look (light top+right, dark left+bottom, black outline) on a black field. Generated by `tools/icon.py` into `assets/icon-source.png` (1024px), and the full platform set is derived with `npx tauri icon` into `app/src-tauri/icons/` (referenced from `tauri.conf.json`).

## 7. Keyboard controls

| Key | Action |
|---|---|
| Left arrow | left (DAS) |
| Right arrow | right (DAS) |
| Down arrow | soft drop (hold) |
| Z | rotate counterclockwise |
| X | rotate clockwise |
| Enter | Start / Pause |
| Home (cheat only) | autopilot #2: high-score strategy (section 4.11) |
| End (cheat only) | autopilot #1: quick-clear strategy (section 4.11) |

Keep the key map as a single table in `app/src/controls.ts`.

---

## 8. Error handling

- A child is **Starting** after the OS spawn succeeds. It becomes **Running** only when the first valid game-state snapshot is cached; a log line or command response is not readiness.
- If stdout closes before that first snapshot, the shell reaps the child, caches a readable startup error, emits the error event, releases the supervisor guard, and stops automatic restarts. The UI shows Retry. A manual Retry starts exactly one fresh child, clears the old error, and waits for its first state.
- If a previously ready child exits during play, the Rust core restarts it automatically. The in-progress game is lost, and the UI shows "Game reset."
- If the Python process fails to spawn outright, the UI shows the error and a Retry button.
- Invalid commands never crash the game. They return an error response and are logged to stderr.
- A corrupted high score file is renamed to `highscore.json.bak`, and play starts from 0.

---

## 9. Testing

Python (pytest), required before UI work starts:

- **Board:** collision, line clear of 1 to 4 lines, no false clears.
- **Pieces:** all seven shapes and all rotation states, checked against the Tengen table.
- **Rotation:** the top-left anchoring rule, the vertical I exception, the one-square left wall kick, and rejected rotations.
- **Gravity:** the Tengen table at representative levels, the fractional 5.5/3.75/3.25 intervals, quarter-frame accumulation, speed-change backlog prevention, and the soft-drop curve.
- **Scoring:** placement points and the 999 cap, clear awards accumulating into the pending stage award, stage payouts at 30/50-line boundaries, threshold overshoot, the level cap at 17, and the cheat-jump boundary.
- **RNG:** determinism with a fixed seed, and the repeat behavior over a long sample.
- **Game flow:** a scripted input sequence produces the expected board, score, and level. The tools runner is also tested with a pre-seeded player high-score file and must leave it byte-for-byte unchanged.
- **Landing input:** Down held at first contact is captured for placement scoring even if released during the lock delay; sliding off a ledge starts a new landing; a fresh piece does not inherit the previous piece's landing state.

Rust and UI:

- Smoke test: the app starts, connects to the Python core, and shows a state update.
- Manual checklist: play one full game, confirm the locked-piece color changes between levels, and confirm game over and high score saving.

---

## 10. Milestones

Build in this order. Don't start a milestone until the previous one passes its checks.

1. **Python: board and pieces.** Board, seven pieces, Tengen rotation table, wall kick. Tests pass.
2. **Python: gravity, soft drop, lock, and line clears.** Tests pass.
3. **Python: scoring, levels, RNG, stats, high score.** Tests pass.
4. **Protocol and stdio loop.** `python -m tetris_core` answers a scripted set of commands.
5. **Rust core.** Spawns Python, forwards commands and events. Smoke test passes.
6. **UI: static board.** Draws a fixed state. Layout matches the owner's measurements.
7. **UI: live play.** Key input, live state, pause, game over, level-based locked colors.
8. **Polish.** Start screen, high score display, error notices, complete theme file.

---

## 11. Instructions for the implementing agent

- Work milestone by milestone. Commit after each one, with tests passing.
- Do not guess Tengen values. For every **VERIFY** item, find the source, record the value in a test fixture, and note the source in a comment.
- Do not use Nintendo NES rules: no Nintendo rotation system, no Nintendo gravity table, no 7-bag, no Nintendo reroll.
- Do not add features outside section 1's goals.
- Do not add Nintendo or Atari artwork, logos, font glyphs, ROM data, or sound files.
- Use the screenshots in `png/` as the visual reference. Measure and sample from them, but do not copy artwork, sprites, or glyphs.
- Lay out the UI in logical units (section 6.4). Never place elements in raw window pixels, and never render at 256 × 240 and scale it up.
- If a **TBD** value is needed, stop and ask the owner. Do not invent it.
- Keep the Python core free of UI and Tauri imports, so it can be tested alone.
- Use React function components and hooks. Keep TypeScript in strict mode. Do not add a global state library in v1.

---

## 12. Platform notes

- Target macOS only for v1. Tauri renders the UI with WKWebView.
- Stack: Tauri v2, React 18 or newer, TypeScript in strict mode, Vite.
- Python 3.11 or newer, in a virtual environment.

---

## 13. Open items for the owner

- Which files in `png/` are Tengen captures, and which are other versions. Re-capture any Tengen screenshot at native resolution if the layout measurements need it.
- Sampled hex colors: background, frame, falling-piece colors, text, and the per-level locked-piece color table.
- Confirmation that the earlier screenshot is or is not from the Tengen version.
- Lock delay: a source, or permission to use immediate lock until one is found.
- Soft drop acceleration: exact values, or permission to mark it TBD.
- Level advancement and score cap for Tengen.
- Logical resolution: confirm the default of 1024 × 960, or choose another value (section 6.4).
- Packaging for a release build: bundled Python (for example PyInstaller, launched as a Tauri sidecar), or the system Python. Dev builds use the system Python.
