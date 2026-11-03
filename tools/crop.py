"""Crop a region in NATIVE NES coordinates (capture/2) and print 1 char per
native pixel, so text and piece glyphs are readable.

=====================================================================
WHAT THIS IS FOR
=====================================================================
The other tools summarize by tile or cell; this one shows EVERY
native pixel of a small region as one character -- which is how tile
glyphs (digits, letters) and the exact pixel layout of a piece cell
get read. Give it native coordinates, i.e. divide capture pixel
coordinates by 2.

Usage:
    python3 tools/crop.py <capture.png> <nx0> <ny0> <nx1> <ny1>

Output: a header with the legend (char = hex) for the region's most
common colors, then one line per native row. x1/y1 are exclusive
bounds and the region is clamped to the image.
"""

import sys
from pathlib import Path

from PIL import Image

# The owner's reference captures; read-only for every tool in here.
PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def crop(name: str, nx0: int, ny0: int, nx1: int, ny1: int):
    """Print a native-coordinate region of a capture as a 1-char-per-pixel map.

    Only every 2nd capture pixel (the top-left of each 2x2 group) is
    read: the capture is a clean 2x scale of the 256x240 screen, so
    all four capture pixels of a native pixel are identical and
    sampling one of them is lossless at half the work.

    Colors are ranked by count and assigned '0', '1', ... in order.
    There are 32 characters; a region with more distinct colors than
    that crashes while building the map, so keep crops small.
    """
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    # Census of exact colors inside the crop, at native resolution
    # (the min() clamps keep the region inside the image).
    counts: dict[tuple[int, int, int], int] = {}
    for ny in range(ny0, min(ny1, im.height // 2)):
        for nx in range(nx0, min(nx1, im.width // 2)):
            c = px[nx * 2, ny * 2]
            counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    # 32 characters for up to 32 distinct colors in the crop.
    chars = "0123456789abcdefghijklmnopqrstuv"
    mapping = {c: chars[i] for i, (c, _) in enumerate(ranked)}
    # Legend: the 22 most common colors. Legend order = count order =
    # the order characters were assigned, so the first char is always
    # the region's dominant color.
    print(f"\n=== {name} native x{nx0}..{nx1} y{ny0}..{ny1} (1 char = 1 native px) ===")
    print(" ".join(f"{chars[i]}=#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for i, (c, _) in enumerate(ranked[:22])))
    for ny in range(ny0, min(ny1, im.height // 2)):
        print("".join(mapping[px[nx * 2, ny * 2]] for nx in range(nx0, min(nx1, im.width // 2))))


if __name__ == "__main__":
    # One crop per invocation: file name plus the four native bounds.
    crop(sys.argv[1], *map(int, sys.argv[2:6]))
