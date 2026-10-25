// Logical resolution (spec 6.4): 8x the NES 256x240 output in each
// direction (2048x1920), keeping the 256:240 aspect ratio, so every block,
// bevel, and frame is drawn with high-definition vector detail at any
// window size. Changeable by the owner; keep the aspect ratio.
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
export const LAYOUT = {
  playfield: { x: 144, y: 120, cols: 10, rows: 20, cell: 84, frameOuter: 12, frameInner: 8 },
  next: { x: 1120, y: 176, boxW: 400, boxH: 224, cell: 56, labelSize: 40 },
  score: { x: 1120, y: 480, rowHeight: 136, labelSize: 40, valueSize: 52 },
  stats: { x: 1120, y: 1104, titleSize: 48, cell: 28, barWidth: 28, barHeight: 560, gap: 6 },
};

// Stats bars (spec 4.9, owner decisions 2026-10-24/25): one vertical bar
// per piece, growing upward from the glyph, all tracks at the same
// height. Each piece's weight is scaled so the bar fills slowly: full at
// 120 pieces of one kind, which lands around level 10 (10x slower than
// the previous draft of 12, per the 30-lines-per-level progression).
// A horizontal tick marks every 10 pieces.
export const STATS_BAR_MAX = 120;
export const STATS_TICK_EVERY = 10;

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
