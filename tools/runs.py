"""Find long horizontal/vertical color runs to locate panel boxes precisely."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def runs(name: str):
    im = Image.open(PNG_DIR / name).convert("RGB")
    w, h = im.size
    px = im.load()

    def hexc(c):
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"

    print(f"\n=== {name} ===")
    # horizontal runs >= 60 capture px
    hruns = []
    for y in range(0, h, 2):
        run_start = None
        run_color = None
        for x in range(0, w + 1):
            c = px[x, y] if x < w else None
            if c == run_color:
                continue
            if run_color is not None and x - run_start >= 60:
                hruns.append((run_color, run_start, x, y))
            run_start, run_color = x, c
    # vertical runs >= 60 capture px
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
