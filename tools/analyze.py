"""Analyze reference screenshots: dimensions, palettes, and an ASCII color
map so the layout can be read as text. Throwaway tool, not shipped."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def color_map(path: Path, cols=32, rows=30):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im_small = im.resize((cols, rows), Image.NEAREST)
    counts: dict[tuple[int, int, int], int] = {}
    px = im.load()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+*/"
    mapping: dict[tuple[int, int, int], str] = {}
    for i, (color, _n) in enumerate(ranked):
        mapping[color] = chars[i] if i < len(chars) else "?"
    grid = []
    for gy in range(rows):
        row = ""
        for gx in range(cols):
            row += mapping[im_small.getpixel((gx, gy))]
        grid.append(row)
    print(f"\n=== {path.name}  {w}x{h}  unique-colors(sampled)={len(counts)} ===")
    print("legend (rank: hex):")
    legend = []
    for i, (color, n) in enumerate(ranked[:24]):
        legend.append(f"{chars[i]}=#{color[0]:02x}{color[1]:02x}{color[2]:02x}({n})")
    print("  " + " ".join(legend))
    for line in grid:
        print(line)


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "00_coverscreenshot.png",
        "screenshot_00.png",
        "screenshot_05.png",
        "screenshot_10.png",
    ]
    for name in targets:
        color_map(PNG_DIR / name)
