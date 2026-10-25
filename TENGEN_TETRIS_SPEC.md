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
{"type": "state", "frame": 1234, "board": [[0,0,...], ...], "current": {"kind": "T", "cells": [[x,y],...]}, "next": "L", "score": 0, "lines": 0, "level": 0, "high_score": 0, "stats": {"T": 0, "J": 0, "Z": 0, "O": 0, "S": 0, "L": 0, "I": 0}, "status": "playing", "color_index": 3}
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

- Spawns the Python process at startup and restarts it if it exits.
- Exposes Tauri commands that forward to Python: `send_input(action)`, `new_game(level)`, `pause()`, `get_state()`.
- Keeps the latest state in memory and emits a `game-state` event to the UI for each `state` message.
- Does not interpret game data.

### 2.4 React UI

- React with TypeScript, built with Vite. The playfield is drawn on a `<canvas>` inside a component.
- A `useGameState` hook subscribes to `game-state` and stores the latest state. Components render from that state only.
- Keyboard events are sent to Rust as commands. Auto-repeat for left and right comes from Python's DAS logic, not from the browser. Send `left` or `right` on keydown, and stop on keyup.
- Components never compute game rules.

---

## 3. Repository layout

```
tengen-tetris/
  SPEC.md
  png/                       # owner's reference screenshots (read-only, see section 6.0)
  core/                      # Python package
    pyproject.toml
    tetris_core/
      __main__.py            # stdin/stdout JSON-line loop
      game.py                # state machine, frame update
      board.py               # 10x20 grid, collision, line clear
      pieces.py              # tetromino shapes and rotation states from the Tengen table
      gravity.py             # soft drop and level speed table
      scoring.py             # line clear bonuses
      rng.py                 # piece generator
      stats.py               # per-piece counters
      highscore.py           # read/write high score JSON
      protocol.py            # parse commands, build events
    tests/
      test_board.py
      test_pieces.py
      test_rotation.py
      test_gravity.py
      test_scoring.py
      test_rng.py
      test_game_flow.py
  app/                       # Tauri project
    src-tauri/               # Rust core
    src/                     # React UI (TypeScript, Vite)
      main.tsx
      components/            # Board, NextPreview, ScorePanel, StatsPanel, Overlay
      hooks/                 # useGameState
      theme.ts
      controls.ts
  assets/
    font/                    # open-licensed pixel font (section 6.3)
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

- Each level has a fall speed: the number of frames per row. **VERIFY** the full speed table for Tengen. Do not use the Nintendo table.
- **Soft drop** speeds up gradually while held, rather than jumping to a fixed speed. This is a known Tengen behavior (confirmed by nesdev forum discussion). **VERIFY** the exact acceleration curve, including its starting and ending speeds, from a source that documents it. If no source gives exact numbers, mark it TBD and ask the owner.
- Gravity values from the Nintendo version must not be used.

### 4.4 Lock delay

- Owner decision 2026-10-24, refined the same day: when the piece cannot fall further, the player gets a **short** grace window — a fixed 10 frames (`LOCK_DELAY_FRAMES`), capped by the level's `frames_per_row` so it keeps shrinking as gravity speeds up (`lock_delay_frames(level)` in `game.py`). A full "1 drop" interval was tried first and felt too long.
- The window does not reset on movement, so it stays bounded. Moving the piece off a ledge cancels it: gravity resumes and a fresh window starts at the next landing.

### 4.5 Line clears, scoring, and levels

- Per-clear award values, owner-verified 2026-10-24 from the award table in `png/screenshot_28.png`: single **100**, double **400**, triple **900**, tetris **2500** (`POINTS_FOR_CLEAR` in `scoring.py`). Score, lines, and level update immediately when the piece locks.
- Line-clear animation (owner decisions 2026-10-24, reference `png/screenshot_11.png`): completed rows stay visible and are wiped **from the center to both sides** — one column-pair every 4 frames (pairs {4,5}, {3,6}, {2,7}, {1,8}, {0,9}; `WIPE_FRAMES_PER_PAIR` in `theme.ts`) — then the rows are removed and the next piece spawns after `CLEAR_ANIM_FRAMES` (24). While the wipe runs, the award label **SINGLE / DOUBLE / TRIPLE / TETRIS** (by number of rows) shows centered **inside the cleared row(s)** (`CLEAR_LABELS`). The core drives the timing and reports `clearing: {rows, frame}` in the state event; the UI only renders the wipe and the label.
- Tengen awards line-clear bonuses only after each 30 lines. **VERIFY** this against the source, including what happens to lines cleared that are not part of a bonus block.
- Level progression: **VERIFY** how the level advances (for example, every 10 lines, or as Tengen defines it). Do not assume the Nintendo rule.
- Cheat (owner request 2026-10-25): typing the classic Konami sequence on the title screen — **↑ ↑ ↓ ↓ ← → ← → B A**, physical keys — unlocks cheat mode. The indicator is the cathedral itself: the central tent tower's tip dome turns **green** on the title screen. During play, digit keys **0-9** jump to that level immediately via the `set_level` protocol command: gravity and the locked color change at once, and progression continues from the new level (`Game.set_level`; UI tracking in `App.tsx`).
- Score cap: **TBD**. Confirm from the source.

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
- Owner decision 2026-10-24, per the captures: the counts render as **vertical bars growing upward** — one column per piece with the glyph at the bottom and a bar above it that grows upward with the count; every bar track sits at the same height (fixed-height glyph area). Owner correction 2026-10-25: the per-piece weight is scaled so the bar fills slowly — full at **120 pieces of one kind**, which lands around level 10 (the 12-of-a-kind draft filled within a minute of play). A horizontal tick marks every 10 pieces; the numeric readout is gone (`StatsPanel.tsx`, `STATS_BAR_MAX` / `STATS_TICK_EVERY` in `theme.ts`).

### 4.10 High score

- Stored as JSON in the macOS application support folder, for example `~/Library/Application Support/tengen-tetris/highscore.json`. Created on first save.

---

## 5. Screens

- **Start / title screen** (owner request 2026-10-24): the composition follows `png/screenshot_00.png` — gold border bands with green diamond studs top and bottom, a full-screen light-blue double frame, a red italic `TETRIS` wordmark, and the **Saint Basil's Cathedral scene** filling the frame, adapted from the owner's reference render `png/Saint_Basil's_Cathedral_render.ts` (`cathedral.ts`: pale sky with sun, stone platform, terracotta walls with white arcade, onion domes — gold, blue/green spiral-striped, red checkered — each with an Orthodox cross, and the central tent tower with gold lattice). Two gold text lines near the bottom ("TENGEN-STYLE TRIBUTE" and a blinking "PRESS ENTER"). An original composition; no original artwork or text is copied (spec 1 non-goals).
- **Pause:** freezes the frame loop and shows PAUSE over the playfield.
- **Game over:** shows GAME OVER over the playfield with the final score. Press Start to play again.
- **Title music** (owner request 2026-10-25): `music/01_-_Tetris_Tengen_-_NES_-_Introduction.ogg` loops on the title screen only (imported via Vite `?url`, volume 0.6); it stops when the game starts. More tracks (gameplay themes) will be added to `music/` later. The owner supplies and tracks the music files by decision (spec 1 non-goals cover artwork, not the owner's own music files).

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

## 7. Keyboard controls

| Key | Action |
|---|---|
| Left arrow | left (DAS) |
| Right arrow | right (DAS) |
| Down arrow | soft drop (hold) |
| Z | rotate counterclockwise |
| X | rotate clockwise |
| Enter | Start / Pause |

Keep the key map as a single table in `app/src/controls.ts`.

---

## 8. Error handling

- If the Python process fails to start, the UI shows the error and a Retry button.
- If Python exits during play, the Rust core restarts it. The in-progress game is lost, and the UI shows "Game reset."
- Invalid commands never crash the game. They return an error response and are logged to stderr.
- A corrupted high score file is renamed to `highscore.json.bak`, and play starts from 0.

---

## 9. Testing

Python (pytest), required before UI work starts:

- **Board:** collision, line clear of 1 to 4 lines, no false clears.
- **Pieces:** all seven shapes and all rotation states, checked against the Tengen table.
- **Rotation:** the top-left anchoring rule, the vertical I exception, the one-square left wall kick, and rejected rotations.
- **Gravity:** the speed table at representative levels, and the soft drop acceleration curve once verified.
- **Scoring:** the 30-line bonus rule, once verified.
- **RNG:** determinism with a fixed seed, and the repeat behavior over a long sample.
- **Game flow:** a scripted input sequence produces the expected board, score, and level.

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
