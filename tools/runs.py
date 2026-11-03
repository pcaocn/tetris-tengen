"""Find long horizontal/vertical color runs to locate panel boxes precisely.

=====================================================================
WHY RUNS LOCATE PANELS
=====================================================================
UI boxes (playfield border, score/next panels) are drawn with long
straight borders of one solid color. A playfield cell is only 16
capture px across, so nothing piece-sized can produce a run of one
color 60 capture px (30 native px) long -- every hit is panel
geometry, not gameplay. Reading the printed runs gives the exact
capture x/y of every panel edge; constants like cells.py's field
origins (native x=16/160, y=64) came out of this measurement.

Usage:
    python3 tools/runs.py <capture.png> ...
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures; read-only for every tool in here.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def runs(name: str):
    """Print the long solid-color runs of a capture, horizontal then vertical.

    Output lines: color, start..end (end exclusive), and the row (or
    column) the run sits on. Capped at the first 40 of each direction
    so the output stays readable.
    """
    im = Image.open(PNG_DIR / name).convert("RGB")
    w, h = im.size
    px = im.load()

    def hexc(c):
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"

    print(f"\n=== {name} ===")
    # horizontal runs >= 60 capture px
    # One pass per scanned row (every 2nd row = native resolution,
    # which is enough because panel borders are >1 native px thick):
    # when the color changes, close the current run and record it if
    # it was long enough.
    hruns = []
    for y in range(0, h, 2):
        run_start = None
        run_color = None
        for x in range(0, w + 1):
            # The x == w sentinel yields None, which differs from any
            # real color, so a run reaching the right edge is closed.
            c = px[x, y] if x < w else None
            if c == run_color:
                continue
            if run_color is not None and x - run_start >= 60:
                hruns.append((run_color, run_start, x, y))
            run_start, run_color = x, c
    # vertical runs >= 60 capture px
    # Same algorithm on columns instead of rows.
    vruns = []
    for x in range(0, w, 2):
        run_start = None
        run_color = None
        for y in range(0, h + 1):
            c = px[x, y] if y < h else None
            if c == run_color:
                continue
            if run_color is not None and y - run_start >= 60:
                vruns.append((run_color, run_start, y, x))
            run_start, run_color = y, c
    print("horizontal runs (color, x0..x1 at y):")
    for c, a, b, y in hruns[:40]:
        print(f"  {hexc(c)}  x{a}..{b}  y{y}")
    print("vertical runs (color, y0..y1 at x):")
    for c, a, b, x in vruns[:40]:
        print(f"  {hexc(c)}  y{a}..{b}  x{x}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        runs(name)
