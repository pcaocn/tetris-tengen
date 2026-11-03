"""Zoom into a region of a screenshot and print a native-pixel (2x2 grouped)
color map with a legend, so piece glyphs and exact colors can be read.

=====================================================================
ZOOM VS CROP
=====================================================================
crop.py addresses the image in NATIVE pixels (capture / 2); zoom()
takes RAW CAPTURE pixel coordinates plus a `group` factor: the map
samples every `group`-th capture pixel in x, so with group=2 (the
default) each printed character is one native pixel -- the "2x2
grouped" of the one-liner above.

Rows stride by 2*group, not `group`. The likely reason: terminal
characters are about twice as tall as wide, so printing every OTHER
sampled row makes the map look square on screen instead of vertically
stretched. (This was inferred from the code -- the original author did
not record it -- so treat it as a best guess, not an established fact.)

Usage:
    python3 tools/zoom.py <capture.png> <x0> <y0> <x1> <y1> [group]

Coordinates are capture pixels, x1/y1 exclusive, region clamped to
the image.
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures; read-only for every tool in here.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def zoom(name: str, x0: int, y0: int, x1: int, y1: int, group: int = 2):
    """Print a color-census legend plus the grouped char map of a region.

    One character per sampled point (every `group` capture px in x,
    every 2*group px in y). The legend shows the 20 most common
    colors as char=#hex(count) in count order.
    """
    im = Image.open(PNG_DIR / name).convert("RGB")
    # Census of exact colors on the group-strided sample grid.
    counts: dict[tuple[int, int, int], int] = {}
    px = im.load()
    for y in range(y0, min(y1, im.height), group):
        for x in range(x0, min(x1, im.width), group):
            counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    # 46 characters cover up to 46 distinct colors in the region.
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
    mapping = {c: chars[i] for i, (c, _) in enumerate(ranked)}
    print(f"\n=== {name} region x{x0}..{x1} y{y0}..{y1} (group {group}) ===")
    print(" ".join(
        f"{chars[i]}=#{c[0]:02x}{c[1]:02x}{c[2]:02x}({n})"
        for i, (c, n) in enumerate(ranked[:20])
    ))
    # The map: columns step by `group`, rows by 2*group (see the
    # module docstring -- the halved row rate compensates for tall
    # terminal glyphs).
    for y in range(y0, min(y1, im.height), group * 2):
        line = []
        for x in range(x0, min(x1, im.width), group):
            line.append(mapping[px[x, y]])
        print("".join(line))


if __name__ == "__main__":
    # File name, then the region in capture px, then optionally the
    # group factor (default 2 = one char per native pixel).
    name = sys.argv[1]
    x0, y0, x1, y1 = map(int, sys.argv[2:6])
    group = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    zoom(name, x0, y0, x1, y1, group)
