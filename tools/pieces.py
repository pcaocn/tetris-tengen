"""Find falling-piece components in the left playfield: print cell mask and
exact color trio (light/mid/dark by luminance) for each component.

=====================================================================
WHAT THIS ANSWERS
=====================================================================
cells.py classifies cells against a KNOWN color table; this script
goes the other way and MEASURES colors. It groups each piece-sized
blob of filled cells into a connected component and prints the exact
hex of every color in the blob, sorted light -> dark. That trio is
the source of the (light, mid, dark) entries in app/src/theme.ts and
of the FAMILIES table in cells.py.

=====================================================================
COORDINATES (native = capture / 2)
=====================================================================
Cells are 8x8 native tiles. The scan starts at native x=16 (left
playfield) and y=40 -- three rows ABOVE the visible playfield top
(y=64) -- because Tengen renders the spawn area: a new piece exists
above row 0 for a moment before it enters the visible field. Row r
of this scan is native y = 40 + 8*r, so rows 3..22 are the 20
visible rows and rows -3..2 are the hidden/spawn rows above them.

Unlike cells.py, the FULL 8x8 cell is sampled: the bevel tones live
on the cell edges, and the edges are exactly what is being measured.
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures; read-only for every tool in here.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def luminance(c):
    """Perceived brightness of an RGB tuple (ITU-R BT.601 weights).

    Sorting a blob's colors by this, descending, puts the bevel's
    light tone first, the mid tone second, the dark tone last.
    """
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def components(name: str):
    """Print the cell mask and exact colors of every piece blob on the field.

    Pipeline: sample every cell -> keep the non-empty ones -> flood
    fill 4-adjacent filled cells into components -> print each
    component's bounding-box mask and its aggregated color counts.
    """
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    X0, Y0 = 16, 40  # include rows above y64 (spawn area is rendered)
    # Pass 1: per-cell color census. cells[(col, row)] maps to the
    # exact colors of its non-black pixels; a cell with no non-black
    # pixel is background and is left out entirely.
    cells = {}
    for row in range(-3, 24):
        for col in range(10):
            cx, cy = X0 + col * 8, Y0 + row * 8
            colors = {}
            for dy in range(8):
                for dx in range(8):
                    # Capture pixel for native (x, y) is (2x, 2y). The
                    # bounds check drops cells whose sample runs past
                    # the capture's edge (bottom scan rows, and the
                    # right playfield is simply never sampled).
                    x, y = (cx + dx) * 2, (cy + dy) * 2
                    if x >= im.width or y >= im.height:
                        continue
                    c = px[x, y]
                    # Black = background and cell borders, never part
                    # of a piece.
                    if c == (0, 0, 0):
                        continue
                    colors[c] = colors.get(c, 0) + 1
            if colors:
                cells[(col, row)] = colors
    # group adjacent filled cells into components
    # Pass 2: stack flood fill -- no recursion, so blob size is
    # unbounded. A piece in play is one component; two separate
    # pieces never join because their cells never touch.
    seen = set()
    comps = []
    for key in cells:
        if key in seen:
            continue
        stack, comp = [key], []
        seen.add(key)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            cx, cy = cur
            for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(comp)
    print(f"\n=== {name} ===")
    # Pass 3: report each blob. The mask is relative to the blob's
    # bounding box, so an O reads as a 2x2 '#' block wherever it
    # sits. Colors are aggregated over the blob's cells; printing the
    # 5 brightest shows the bevel trio plus any overlap (e.g. text
    # drawn over the piece).
    for comp in comps:
        if len(comp) < 1:
            continue
        cols = [c for c, _ in comp]
        rows = [r for _, r in comp]
        c0, r0 = min(cols), min(rows)
        mask = ["." * (max(cols) - c0 + 1) for _ in range(max(rows) - r0 + 1)]
        colorcount = {}
        for (c, r) in comp:
            line = list(mask[r - r0])
            line[c - c0] = "#"
            mask[r - r0] = "".join(line)
            for hexc, n in cells[(c, r)].items():
                colorcount[hexc] = colorcount.get(hexc, 0) + n
        # Light -> dark by luminance: [0] is the highlight tone, [1]
        # the mid face, [2] the shadow of a clean 3-tone block.
        trio = sorted(colorcount, key=luminance, reverse=True)
        trio_s = " ".join(
            f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}({colorcount[c]})" for c in trio[:5]
        )
        print(f"cells at col{c0} row{r0} ({len(comp)} cells):")
        for m in mask:
            print("   ", m)
        print(f"    colors: {trio_s}")


if __name__ == "__main__":
    # Left playfield only; run over several captures to cover every
    # piece and every level's palette shift.
    for name in sys.argv[1:]:
        components(name)
