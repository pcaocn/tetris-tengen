"""Extract 10x20 cell grids from the left and right playfield regions of
gameplay screenshots. Each 8x8 native cell is classified by its dominant
non-black color so piece shapes and colors can be read as text.

=====================================================================
WHAT THE OUTPUT LOOKS LIKE
=====================================================================
One line per playfield row (labeled 0..19 from the top), one
character per cell:

  Y O G P R B  -- the piece-color families (see FAMILIES)
  f s w        -- light-blue / gray / white (UI elements, text)
  .            -- empty (every sampled pixel was black)
  #aabbcc      -- a raw hex, for colors not yet in FAMILIES

Tengen is two-player, so each capture holds two playfields side by
side; both are printed, left field first.

=====================================================================
COORDINATES (native = capture / 2)
=====================================================================
Captures are 2x the NES's 256x240 screen. On the native screen a
playfield cell is an 8x8-pixel tile and the field is 10x20 tiles.
The LEFT field's cells start at native x=16, the RIGHT field's at
native x=160, and the field's top edge is native y=64, so visible
rows run y=64..223. Capture pixel for native (nx, ny) is (2nx, 2ny).

Use pieces.py to MEASURE colors of a blob; use this script to READ
whole fields against the known palette.
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures; read-only for every tool in here.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"

# known Tengen palette families seen so far (hex -> tag)
# Exact hexes harvested from the captures (pieces.py prints them).
# Several shades per family because locked blocks, flashing rows, and
# background tints each carry their own tone. Extend this table when
# the "unknown colors" report below surfaces a new hex.
FAMILIES = {
    "#e6b467": "Y", "#ffe092": "Y", "#9e6d20": "Y",  # gold/yellow
    "#818104": "O", "#585800": "O",  # olive
    "#7cdfa1": "G", "#349859": "G", "#0c6f30": "G",  # green
    "#e993ff": "P", "#a24cc0": "P", "#ffbfff": "P", "#6464e2": "B",  # purple/blue
    "#b05a51": "R", "#873129": "R", "#f7a199": "R",  # red
    "#8fc0ff": "f", "#4779c6": "f", "#baebff": "f",  # blues (UI?)
    "#808080": "s", "#ffffff": "w",  # gray/white
}


def grid(name: str, x0: int, label: str):
    """Print one playfield of a capture as a 10x20 grid of family tags.

    Args:
        name: capture file name inside png/.
        x0: native x of the field's leftmost cell (16 = left field,
            160 = right field; each field is 80 native px wide).
        label: human tag shown in the header line.
    """
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    print(f"\n=== {name} {label} (native x{x0}..{x0+80}, cells 8x8) ===")
    seen = {}
    for row in range(20):
        line = []
        for col in range(10):
            # Top-left native pixel of this cell (capture pixel = 2x).
            cx, cy = x0 + col * 8, 64 + row * 8
            best = None
            best_n = 0
            # Sample the center 5x5 of the 8x8 cell (offsets 2..6) and
            # skip the 1-px border ring: cell edges carry bevel and
            # outline shading plus bleed from neighbors, while the
            # interior carries the fill color that names the piece.
            for dy in range(2, 7):
                for dx in range(2, 7):
                    c = px[(cx + dx) * 2, (cy + dy) * 2]
                    h = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                    # Black is the playfield background and cell
                    # borders, never a piece color -- skip it.
                    if h == "#000000":
                        continue
                    n = FAMILIES.get(h)
                    if n is None:
                        # Not in the table yet: fall back to the raw
                        # hex so the grid still prints something and
                        # the color gets collected for the report.
                        n = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                    if h not in seen:
                        seen[h] = n
                    # prefer saturated family pixels
                    # A piece-family tag scores 2, everything else
                    # (UI grays/whites/blues, raw hexes) scores 1, so
                    # text or UI drawn over a block never outvotes the
                    # block's own color. On equal score the previous
                    # cell's tag wins, keeping a horizontal run of one
                    # piece a solid streak instead of flickering
                    # between neighboring family tags.
                    score = 2 if n in "YOGPRB" else 1
                    if score > best_n or (score == best_n and n == line[-1] if line else False):
                        best, best_n = n, score
            # No non-black pixel in the sample -> empty cell.
            line.append(best or ".")
        # Row label 0..19, then the 10 cell tags.
        print(f"{row:2d} " + "".join(line))
    # Colors sampled that FAMILIES does not cover: usually a new
    # level's tint or a UI shade -- extend the table with these.
    unknown = {h: t for h, t in seen.items() if t.startswith("#")}
    if unknown:
        print("unknown colors:", unknown)


if __name__ == "__main__":
    # Both playfields per capture: cells start at native x=16 (left)
    # and x=160 (right).
    for name in sys.argv[1:]:
        grid(name, 16, "left field")
        grid(name, 160, "right field")
