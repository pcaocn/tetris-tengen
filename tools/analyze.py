"""Analyze reference screenshots: dimensions, palettes, and an ASCII color
map so the layout can be read as text. Throwaway tool, not shipped.

=====================================================================
WHAT THIS SCRIPT DOES
=====================================================================
For each capture it prints:

  1. the image dimensions and the number of distinct colors present,
  2. a legend ranking the most common colors (char = hex = count),
  3. a 32x30 character grid where each character is one 8x8 tile of
     the native NES screen, drawn with that tile's color.

At one character per tile the printed grid IS the screen layout: the
two playfields, the side panels, and the text rows can all be read
as text. This is the usual first tool to point at a new capture.

HOW TO RUN
----------
    python3 tools/analyze.py                  # the default captures
    python3 tools/analyze.py <name>.png ...   # specific captures

Names are resolved inside png/; captures are opened read-only.

=====================================================================
COORDINATE SYSTEM (shared by every tool in this directory)
=====================================================================
The captures in png/ are 2x the NES's logical 256x240 screen, so
NATIVE pixels are capture pixels / 2. The native screen is a grid of
8x8-PIXEL TILES: 256/8 = 32 across, 240/8 = 30 down -- exactly the
cols=32 / rows=30 of color_map() below, i.e. one character per tile.
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures of the original game (gitignored).
# Every tool in this directory reads png/ and must never write to it.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def color_map(path: Path, cols=32, rows=30):
    """Print dimensions, a ranked palette, and a 1-char-per-tile color map.

    WHY: layout questions ("where does the playfield start?", "which
    tile holds the level number?") are answered fastest by reading
    the screen as text rather than eyeballing pixels in a viewer.

    Args:
        path: the capture to analyze; opened read-only.
        cols, rows: output grid size in tiles. 32x30 covers the
            native 256x240 screen exactly at 8 px per tile.
    """
    im = Image.open(path).convert("RGB")
    w, h = im.size
    # Downsample the whole capture to one pixel per tile with NEAREST:
    # each output pixel is COPIED from the tile's top-left source pixel
    # instead of averaged. Averaging would invent blend colors that
    # exist nowhere on the real console, so exactness beats smoothness.
    im_small = im.resize((cols, rows), Image.NEAREST)
    # Histogram of EXACT RGB tuples, sampled every 2nd capture pixel
    # (i.e. at native resolution -- enough for a palette census and
    # 4x faster than touching every pixel).
    counts: dict[tuple[int, int, int], int] = {}
    px = im.load()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    # Rank colors by frequency; the most common gets '0', the next
    # '1', and so on. There are 65 characters available; anything
    # rarer than that is layout noise and collapses to '?'.
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+*/"
    mapping: dict[tuple[int, int, int], str] = {}
    for i, (color, _n) in enumerate(ranked):
        mapping[color] = chars[i] if i < len(chars) else "?"
    # Build the map. getpixel() on the NEAREST image returns the
    # top-left capture pixel of each 16x16 (capture-px) tile block --
    # one true screen color per tile, no blending.
    grid = []
    for gy in range(rows):
        row = ""
        for gx in range(cols):
            row += mapping[im_small.getpixel((gx, gy))]
        grid.append(row)
    # Header: file name, capture size (2x native), palette size. The
    # legend shows the 24 most common colors as char=#hex(count);
    # backgrounds and panel fills sort first, piece colors appear
    # further down with meaningful counts.
    print(f"\n=== {path.name}  {w}x{h}  unique-colors(sampled)={len(counts)} ===")
    print("legend (rank: hex):")
    legend = []
    for i, (color, n) in enumerate(ranked[:24]):
        legend.append(f"{chars[i]}=#{color[0]:02x}{color[1]:02x}{color[2]:02x}({n})")
    print("  " + " ".join(legend))
    for line in grid:
        print(line)


if __name__ == "__main__":
    # Default targets: the cover screenshot plus three spaced gameplay
    # frames -- enough to see the layout, the in-game palette, and the
    # level-color shifts between early and late levels.
    targets = sys.argv[1:] or [
        "00_coverscreenshot.png",
        "screenshot_00.png",
        "screenshot_05.png",
        "screenshot_10.png",
    ]
    for name in targets:
        color_map(PNG_DIR / name)
