"""Find falling-piece components in the left playfield: print cell mask and
exact color trio (light/mid/dark by luminance) for each component."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"


def luminance(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def components(name: str):
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    X0, Y0 = 16, 40  # include rows above y64 (spawn area is rendered)
    cells = {}
    for row in range(-3, 24):
        for col in range(10):
            cx, cy = X0 + col * 8, Y0 + row * 8
            colors = {}
            for dy in range(8):
                for dx in range(8):
                    x, y = (cx + dx) * 2, (cy + dy) * 2
                    if x >= im.width or y >= im.height:
                        continue
                    c = px[x, y]
                    if c == (0, 0, 0):
                        continue
                    colors[c] = colors.get(c, 0) + 1
            if colors:
                cells[(col, row)] = colors
    # group adjacent filled cells into components
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
        trio = sorted(colorcount, key=luminance, reverse=True)
        trio_s = " ".join(
            f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}({colorcount[c]})" for c in trio[:5]
        )
        print(f"cells at col{c0} row{r0} ({len(comp)} cells):")
        for m in mask:
            print("   ", m)
        print(f"    colors: {trio_s}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        components(name)
