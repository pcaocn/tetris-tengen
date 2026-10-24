"""Crop a region in NATIVE NES coordinates (capture/2) and print 1 char per
native pixel, so text and piece glyphs are readable."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def crop(name: str, nx0: int, ny0: int, nx1: int, ny1: int):
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    counts: dict[tuple[int, int, int], int] = {}
    for ny in range(ny0, min(ny1, im.height // 2)):
        for nx in range(nx0, min(nx1, im.width // 2)):
            c = px[nx * 2, ny * 2]
            counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    chars = "0123456789abcdefghijklmnopqrstuv"
    mapping = {c: chars[i] for i, (c, _) in enumerate(ranked)}
    print(f"\n=== {name} native x{nx0}..{nx1} y{ny0}..{ny1} (1 char = 1 native px) ===")
    print(" ".join(f"{chars[i]}=#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for i, (c, _) in enumerate(ranked[:22])))
    for ny in range(ny0, min(ny1, im.height // 2)):
        print("".join(mapping[px[nx * 2, ny * 2]] for nx in range(nx0, min(nx1, im.width // 2))))


if __name__ == "__main__":
    crop(sys.argv[1], *map(int, sys.argv[2:6]))
