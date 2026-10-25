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
- **Original app icon**: four beveled blocks in the piece palette
  (`tools/icon.py` + `npx tauri icon`).
- **Music**: the introduction theme on the title screen, five selectable
  gameplay themes (Silent by default) that play as a looped playlist
  during play, end-of-stage and victory celebrations, and a game-over
  theme.
- **High-score persistence**, pause, and a 60 Hz game loop driven by the
  Python core — the UI renders state and never computes game rules.

## Requirements

- macOS (the app is not yet configured for Windows/Linux)
- [Node.js](https://nodejs.org) 18+ with npm
- [Rust](https://rustup.rs) toolchain and Xcode Command Line Tools
  (`xcode-select --install`)
- [uv](https://docs.astral.sh/uv/) — manages the Python 3.13
  interpreter and dependencies automatically

## Build and run

After cloning:

```sh
# 1. Set up the Python core (creates core/.venv; uv installs Python 3.13
#    if needed). The Tauri shell expects this venv.
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

Scoring, per line-clear event: **SINGLE 100 · DOUBLE 400 · TRIPLE 900 ·
TETRIS 2500**, shown as a label inside the cleared rows while they wipe
from the center outward. The locked-cell color changes with the level
and repeats every 10 levels. The stats bars fill slowly — one bar is full
at 120 pieces of a kind (roughly level 10). Clearing a 30-line stage
freezes the game for the end-of-stage celebration; press **Enter** to
continue to the next level.

### Cheat mode

On the title screen, type the classic Konami code with the arrow keys
and letters — **Up Up Down Down Left Right Left Right B A**. The
cathedral's central tip dome turns green to confirm. While playing,
press **0–9** to jump to that level instantly (gravity and stack color
change immediately).

## Development

```sh
# Python core tests (182 tests)
cd core && uv run pytest

# Front-end type check and build
cd app && npm run typecheck && npm run build

# Rust shell check
cd app/src-tauri && cargo check
```

### Project layout

- `core/` — Python rules engine (`tetris_core/`): board, pieces, DAS,
  gravity, lock delay, scoring, protocol. 60 Hz loop, JSON lines on
  stdio. Tests in `core/tests/`.
- `app/` — React + TypeScript UI and the Tauri (Rust) shell that
  spawns the core and bridges commands/events.
- `assets/` — icon and font files served to the UI.
- `tools/` — pixel-analysis scripts used to sample colors and layout
  from the owner's reference captures.
- `png/` — local reference captures (gitignored; not shipped).
- `TENGEN_TETRIS_SPEC.md` — the authoritative spec. Sections marked
  **VERIFY/TBD** are placeholder rules awaiting source confirmation
  (level progression is currently 1 level per 30 lines, with a 30-line
  block bonus).

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
