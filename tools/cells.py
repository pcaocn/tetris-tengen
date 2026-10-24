"""Extract 10x20 cell grids from the left and right playfield regions of
gameplay screenshots. Each 8x8 native cell is classified by its dominant
non-black color so piece shapes and colors can be read as text."""

import sys
from pathlib import Path

from PIL import Image

PNG_DIR = Path(__file__).resolve().parent.parent / "png"

# known Tengen palette families seen so far (hex -> tag)
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
    im = Image.open(PNG_DIR / name).convert("RGB")
    px = im.load()
    print(f"\n=== {name} {label} (native x{x0}..{x0+80}, cells 8x8) ===")
    seen = {}
    for row in range(20):
        line = []
        for col in range(10):
            cx, cy = x0 + col * 8, 64 + row * 8
            best = None
            best_n = 0
            for dy in range(2, 7):
                for dx in range(2, 7):
                    c = px[(cx + dx) * 2, (cy + dy) * 2]
                    h = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                    if h == "#000000":
                        continue
                    n = FAMILIES.get(h)
                    if n is None:
                        n = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
                    if h not in seen:
                        seen[h] = n
                    # prefer saturated family pixels
                    score = 2 if n in "YOGPRB" else 1
                    if score > best_n or (score == best_n and n == line[-1] if line else False):
                        best, best_n = n, score
            line.append(best or ".")
        print(f"{row:2d} " + "".join(line))
    unknown = {h: t for h, t in seen.items() if t.startswith("#")}
    if unknown:
        print("unknown colors:", unknown)


if __name__ == "__main__":
    for name in sys.argv[1:]:
        grid(name, 16, "left field")
        grid(name, 160, "right field")
