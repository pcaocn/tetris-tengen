// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The design vocabulary of the whole UI, in one place: the logical
// resolution, the layout grid (where every panel sits), the measured Tengen
// palettes, and the display-only piece shapes. Everything that a reader
// would otherwise have to guess — "why is the playfield at x=144?", "what
// color is a locked J on level 2?" — is answered here, next to the number.
//
// The two consumers are the React components (which position absolutely
// using LAYOUT) and the canvas painters (which scale logical units to
// device pixels). Nothing in this file computes game rules; the numbers
// are either measured from the owner's captures or owner decisions, and
// each carries its date and reason.
//
// Logical resolution (spec 6.4): 8x the NES 256x240 output in each
// direction (2048x1920), keeping the 256:240 aspect ratio, so every block,
// bevel, and frame is drawn with high-definition vector detail at any
// window size. Changeable by the owner; keep the aspect ratio.
//
// Why 8x and not a smaller multiple: the Tengen sprites have a 3-tone
// bevel and a 1px outline, and a low logical resolution forces those
// bevel bands to collapse into flat pixel mush when scaled up. The extra
// headroom is what lets drawBlock shade edges with smooth gradients and
// still land on integer device pixels at typical window sizes. All
// LAYOUT numbers below are in this 2048x1920 space; App.tsx multiplies by
// the window scale factor when positioning.
export const LOGICAL_WIDTH = 2048;
export const LOGICAL_HEIGHT = 1920;

// Smooth UI font stack (owner decision 2026-10-24): the Press Start 2P
// pixel font read as low-resolution at display sizes, so all UI text now
// uses a smooth font that stays crisp at any scale (spec 6.3 note, 6.4).
export const FONT_SMOOTH =
  '-apple-system, "Helvetica Neue", "Segoe UI", Arial, sans-serif';

// Layout measured proportionally from the owner's Tengen captures
// (png/screenshot_05..27): playfield on the left, NEXT preview and
// readouts on the right, all in logical units (never raw window pixels).
//
// How to read it: every panel records its top-left origin (x, y) in the
// 2048x1920 logical space plus the sizes it needs. Components multiply
// these by the current window `scale` for CSS positioning; the canvas
// painters draw in raw logical units and let logicalCanvas() apply the
// scale. Cell sizes are per-block squares in the same units.
export const LAYOUT = {
  // The 10x20 playfield. The double frame around it is drawn by Board.tsx:
  // `frameOuter` is the dark-blue band's thickness and `frameInner` the
  // light-blue one's, so the visible frame is (12 + 8) = 20 logical px
  // thick on every side and the cells start at origin x+20, y+20.
  playfield: { x: 144, y: 120, cols: 10, rows: 20, cell: 84, frameOuter: 12, frameInner: 8 },
  // The NEXT box: 400x224 with 56-px preview cells (smaller than playfield
  // cells on purpose — the preview is decorative, not playable).
  next: { x: 1120, y: 176, boxW: 400, boxH: 224, cell: 56, labelSize: 40 },
  // Four readout rows (SCORE/HIGH SCORE/LINES/LEVEL), 136 px apart so the
  // label bar + value stack never collides with the next row.
  score: { x: 1120, y: 480, rowHeight: 136, labelSize: 40, valueSize: 52 },
  // The stats histogram: 16-px glyphs, 28-px bars, 560 px of bar height
  // shared by all seven columns with a 6-px pitch between columns.
  stats: { x: 1120, y: 1104, titleSize: 48, cell: 16, barWidth: 28, barHeight: 560, gap: 6 },
};

// Stats bars (spec 4.9, owner decisions 2026-10-24/25): one vertical bar
// per piece, growing upward from the glyph, all tracks at the same
// height. Each piece's weight is scaled so the bar fills slowly: full at
// 120 pieces of one kind (about when the player reaches level 10).
// A horizontal tick marks every 10 pieces.
export const STATS_BAR_MAX = 120;
export const STATS_TICK_EVERY = 10;

// Stats bar fill (owner correction 2026-10-27, closest to the original):
// one yellowish color for every bar, between the T and J shape colors;
// black track with no boundary line, tight even pitch.
export const STATS_BAR_FILL = "#b49b36";

// Line-clear wipe (spec 4.5, owner decision 2026-10-24): cleared rows are
// wiped from the center outward, one column-pair every this many frames
// (5 pairs: {4,5}, {3,6}, {2,7}, {1,8}, {0,9}; 4 frames each = 20 of the
// 24 CLEAR_ANIM_FRAMES, the label stays for the rest).
export const WIPE_FRAMES_PER_PAIR = 4;

// Award label shown over the playfield during the wipe (spec 4.5).
export const CLEAR_LABELS: Record<number, string> = {
  1: "SINGLE",
  2: "DOUBLE",
  3: "TRIPLE",
  4: "TETRIS",
};

// Title screen (spec 5, owner request 2026-10-24): modeled on the layout
// of png/screenshot_00.png — gold border bands with green diamond studs, a
// full-screen light-blue double frame, decorative falling-piece artwork,
// and two gold text lines near the bottom (the second is the blinking
// start prompt). No original artwork or text is copied (spec 1 non-goals).
export const TITLE_GOLD = "#e6b467";
export const TITLE_GOLD_DARK = "#9e6d20";
export const TITLE_GREEN = "#449a25";
export const TITLE_TEXT_SIZE = 60;
export const TITLE_PROMPT_SIZE = 52;

// ---------------------------------------------------------------------------
// Exact Tengen palettes, sampled pixel-by-pixel from the owner's captures
// (see tools/ for the extraction scripts). Each piece renders with the
// authentic three-tone bevel sprite: light top+right edges, dark left+bottom
// edges, mid body, on a 1px black outline.
// ---------------------------------------------------------------------------

// The three tones of one block sprite, sampled from the captures. `mid`
// is the body, `light` shades the top+right bevel edges and `dark` the
// left+bottom ones — see drawBlock() for how they are painted.
export interface BlockTrio {
  light: string;
  mid: string;
  dark: string;
}

// Falling pieces show their own color by kind (spec 6.2). Sampled from
// falling pieces and the NEXT preview across screenshot_05..27; S and Z
// from the stats-panel glyphs (their state-1 minis match the core rotation
// table exactly).
export const FALLING_COLORS: Record<string, BlockTrio> = {
  I: { light: "#f7a199", mid: "#b05a51", dark: "#873129" }, // red
  O: { light: "#8fc0ff", mid: "#6464e2", dark: "#1e509d" }, // blue
  T: { light: "#e6b467", mid: "#818104", dark: "#585800" }, // olive
  S: { light: "#7cdfa1", mid: "#349859", dark: "#0c6f30" }, // green
  Z: { light: "#baebff", mid: "#8fc0ff", dark: "#4779c6" }, // light blue
  J: { light: "#ffe092", mid: "#e6b467", dark: "#9e6d20" }, // gold
  L: { light: "#ffbfff", mid: "#e993ff", dark: "#a24cc0" }, // pink
};

// Locked pieces all take one color per level (spec 6.2), indexed by
// color_index in the state event. Owner decision 2026-10-24: the color
// cycles every 10 levels — 0 grayish white, 1 red (I), 2 goldish yellow
// (T), 3 blue (O), 4 yellow (J), 5 pink (L), 6 green (S), 7 tortoise
// (Z), 8 purple, 9 green (S) again — then repeats (level 11 = 1, 12 = 2,
// and so on).
const LOCKED_GRAY: BlockTrio = { light: "#f0f0f0", mid: "#c8c8c8", dark: "#878787" };
const LOCKED_PURPLE: BlockTrio = { light: "#e993ff", mid: "#a24cc0", dark: "#661f8c" };
export const LOCKED_COLORS: BlockTrio[] = [
  LOCKED_GRAY,
  FALLING_COLORS.I,
  FALLING_COLORS.T,
  FALLING_COLORS.O,
  FALLING_COLORS.J,
  FALLING_COLORS.L,
  FALLING_COLORS.S,
  FALLING_COLORS.Z,
  LOCKED_PURPLE,
  FALLING_COLORS.S,
];

// Screen chrome, sampled from the captures: decorative double frame around
// the whole screen, gray label bars with white text, pale-blue values.
export const FRAME_DARK = "#1e509d";
export const FRAME_LIGHT = "#8fc0ff";
export const FRAME_PALE = "#baebff";
export const PANEL_BG = "#808080";
export const TEXT_BRIGHT = "#ffffff";
export const TEXT_COLOR = "#baebff";
export const FIELD_BG = "#000000";
export const BACKGROUND = "#000000";
export const OVERLAY_DIM = "rgba(0, 0, 0, 0.72)";

// Display-only piece shapes for the NEXT preview and the stats-panel mini
// glyphs. Offsets are (x, y) cell coordinates; the rotation states match
// core/tetris_core/pieces.py (source of truth). The stats minis reproduce
// the exact orientations seen in the captures' stats panel.
//
// WHY A COPY, AND NOT pieces.py's LIVE TABLE
// ------------------------------------------
// The UI would need to import from Python to reuse the core's table, and
// the preview is render-only — it must never drift into computing rules.
// So these four-cell lists are a frozen snapshot of each piece's spawn
// orientation (x grows right, y grows down). If pieces.py ever changes a
// shape, this table must be updated by hand; the duplication is deliberate
// to keep the dependency direction one-way (core -> UI, never UI -> core).
// Consumers (NextPreview, StatsPanel) re-center the cells by their min/max
// bounds, so the absolute offset origin does not matter.
export const DISPLAY_SHAPES: Record<string, [number, number][]> = {
  I: [
    [1, 0],
    [1, 1],
    [1, 2],
    [1, 3],
  ],
  O: [
    [0, 0],
    [1, 0],
    [0, 1],
    [1, 1],
  ],
  T: [
    [0, 0],
    [0, 1],
    [0, 2],
    [1, 1],
  ],
  S: [
    [0, 0],
    [0, 1],
    [1, 1],
    [1, 2],
  ],
  Z: [
    [1, 0],
    [1, 1],
    [0, 1],
    [0, 2],
  ],
  J: [
    [1, 0],
    [1, 1],
    [1, 2],
    [0, 2],
  ],
  L: [
    [0, 0],
    [0, 1],
    [0, 2],
    [1, 2],
  ],
};

// Stats panel order as seen in the captures: I, T, O, J, L, S, Z.
export const STATS_ORDER = ["I", "T", "O", "J", "L", "S", "Z"] as const;
