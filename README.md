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
`app/src/assets/audio/` come from the owner's own collection.

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
  equal height, with 12 ticks across the current shared scale.
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
  [Autopilot tuning](docs/autopilot.md).
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
- [uv](https://docs.astral.sh/uv/) — manages the Python interpreter and
  dependencies for both development and the release sidecar (the core
  needs Python 3.11+; PyInstaller is fetched by `uv` when packaging)

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

For a release build, run one command from the repository root:

```sh
(cd app && npm run tauri build -- --bundles app)
# Omit `--bundles app` to build the DMG as well.
```

Tauri's `beforeBuildCommand` runs `tools/build_sidecar.sh` first, so the
standalone Python engine is rebuilt for the current target triple even if
a staged executable already exists. Packaging prerequisites are the same
Rust/Node/uv/Xcode Command Line Tools listed above; PyInstaller is fetched
by `uv`. The sidecar is staged at
`app/src-tauri/binaries/tetris-core-<target-triple>`.

The installed app runs the bundled `tetris-core` sidecar next to the
executable. The sidecar contains the Python runtime and this release's
engine, so the checkout is not needed at runtime. Developer overrides
(`TETRIS_PYTHON`, `TETRIS_CORE_DIR`) still force a checkout interpreter
for local experiments.

## How the app works

The repository keeps three runtime boundaries:

| Location | Responsibility |
| --- | --- |
| `app/src/main.tsx`, `App.tsx`, `components/`, `hooks/` | Mount React, compose the screen, render snapshots, and manage UI effects. |
| `app/src/api/game.ts` | Typed functions for the Rust commands the UI calls. |
| `app/src/types/game.ts` | The game snapshot, game status, and startup status types. |
| `app/src/assets/audio/`, `app/public/` | Vite-imported audio and public files served by URL. |
| `app/src-tauri/src/main.rs`, `lib.rs`, `python_core.rs` | Enter the desktop app, register commands and managed state, and supervise the Python child. |
| `core/tetris_core/`, `core/tests/` | Game rules, the JSON-lines protocol, and engine tests. |
| `docs/autopilot.md` | The detailed autopilot tuning guide. |

Pressing **Enter** during play is a complete round trip:

1. `useGameKeyboard` maps Enter to `pressStart` in
   [`App.tsx`](app/src/App.tsx).
2. `pressStart` calls [`gameApi.pause()`](app/src/api/game.ts).
3. The Rust [`pause`](app/src-tauri/src/lib.rs) command calls
   `PythonCore::send_command` in
   [`python_core.rs`](app/src-tauri/src/python_core.rs).
4. The shell writes one JSON line, `{"cmd":"pause"}`, to the child's
   stdin.
5. The Python protocol dispatches the command to
   [`Game.pause()`](core/tetris_core/game.py).
6. The next snapshot comes back as a `game-state` event;
   [`useGameState`](app/src/hooks/useGameState.ts) stores it, and
   [`Overlay`](app/src/components/Overlay.tsx) renders the pause overlay
   from `state.status`.

The same path is used for movement, rotation, new games, and the cheat
commands. Commands are fire-and-forget: the UI observes the next snapshot,
not the command's return value. `get_state` is the exception — it asks for
a fresh snapshot and returns the cached one immediately.

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

Run these from the repository root; each subshell leaves the shell at the
root afterward.

```sh
# Python core tests (232 tests)
(cd core && uv run pytest)

# Front-end type check, music/SFX tests, and production build
(cd app && npm run typecheck && npm test && npm run build)

# Rust shell check
(cd app/src-tauri && cargo check)

# Headless autopilot benchmarks (no UI, no pacing)
(cd core && uv run python simulate_autopilot.py --strategy highscore --runs 100)
```

For the full packaged build (sidecar + `.app`), see
[Build and run](#build-and-run).

### Autopilot tuning

The detailed sweep, benchmark, and analysis workflow lives in
[**docs/autopilot.md**](docs/autopilot.md).

### Project layout

- `core/` — Python rules engine (`tetris_core/`): board, pieces, DAS,
  gravity, lock delay, scoring, protocol. 60 Hz loop, JSON lines on
  stdio. Tests in `core/tests/`.
  - `core/tetris_core/autopilot.py` — the placement search and both
    strategy weight profiles.
  - `core/sweep_autopilot.py`, `core/simulate_autopilot.py`,
    `core/analyze_frontier.py`, `core/compare_autopilot.py` — the
    headless benchmark and tuning tools (see
    [docs/autopilot.md](docs/autopilot.md)).
- `app/` — React + TypeScript UI and the Tauri (Rust) shell that
  spawns the core and bridges commands/events.
  - `app/src/api/game.ts` — typed wrappers around the Rust commands.
  - `app/src/types/game.ts` — shared snapshot and startup types.
  - `app/src/assets/audio/` — Vite-imported music and sound effects.
  - `app/public/` — files served by URL (the open-licensed font).
  - `app/src-tauri/src/main.rs`, `lib.rs`, `python_core.rs` — executable
    entry point, Tauri setup/commands, and the Python child supervisor.
  - `app/src-tauri/binaries/` — staged `tetris-core-<target-triple>`
    sidecars for release builds (generated; not committed).
- `stats/` — saved benchmark CSVs and per-run results.
- `tools/` — icon, sidecar, and pixel-analysis scripts.
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
