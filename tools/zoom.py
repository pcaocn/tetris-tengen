"""Zoom into a region of a screenshot and print a native-pixel (2x2 grouped)
color map with a legend, so piece glyphs and exact colors can be read."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def zoom(name: str, x0: int, y0: int, x1: int, y1: int, group: int = 2):
    im = Image.open(PNG_DIR / name).convert("RGB")
    counts: dict[tuple[int, int, int], int] = {}
    px = im.load()
    for y in range(y0, min(y1, im.height), group):
        for x in range(x0, min(x1, im.width), group):
            counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
    mapping = {c: chars[i] for i, (c, _) in enumerate(ranked)}
    print(f"\n=== {name} region x{x0}..{x1} y{y0}..{y1} (group {group}) ===")
    print(" ".join(
        f"{chars[i]}=#{c[0]:02x}{c[1]:02x}{c[2]:02x}({n})"
        for i, (c, n) in enumerate(ranked[:20])
    ))
    for y in range(y0, min(y1, im.height), group * 2):
        line = []
        for x in range(x0, min(x1, im.width), group):
            line.append(mapping[px[x, y]])
        print("".join(line))


if __name__ == "__main__":
    name = sys.argv[1]
    x0, y0, x1, y1 = map(int, sys.argv[2:6])
    group = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    zoom(name, x0, y0, x1, y1, group)
