"""App icon generator (spec section 6): four vector-style blocks in the
falling-piece palette — red, blue, gold, green — with the game's
three-tone bevel look (light top+right, dark left+bottom, black
outline) on a black field. Writes a 1024px source PNG; the full icon
set is derived from it with `npx tauri icon`.

Usage: uv run --no-project --with pillow python tools/icon.py
"""

from PIL import Image, ImageDraw

SIZE = 1024
CELL = 360
GAP = 40
OUTLINE = 16
BEVEL = 58
RADIUS = 44

# (light, mid, dark) per piece, from theme.ts.
RED = ("#f7a199", "#b05a51", "#873129")      # I
BLUE = ("#8fc0ff", "#6464e2", "#1e509d")     # O
GOLD = ("#ffe092", "#e6b467", "#9e6d20")    # J
GREEN = ("#7cdfa1", "#349859", "#0c6f30")    # S


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def block(light, mid, dark):
    w = h = CELL
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=RADIUS, fill=(0, 0, 0, 255))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    lo, hi = OUTLINE, w - 1 - OUTLINE
    dl.rounded_rectangle([lo, lo, hi, hi], radius=max(1, RADIUS - OUTLINE), fill=hex_rgb(dark))
    dl.rectangle([lo, lo, hi, lo + BEVEL], fill=hex_rgb(light))       # top
    dl.rectangle([hi - BEVEL, lo, hi, hi], fill=hex_rgb(light))       # right
    dl.rectangle([lo + BEVEL, lo + BEVEL, hi - BEVEL, hi - BEVEL], fill=hex_rgb(mid))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [lo, lo, hi, hi], radius=max(1, RADIUS - OUTLINE), fill=255
    )
    img.paste(layer, (0, 0), mask)
    return img


def main():
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    margin = (SIZE - 2 * CELL - GAP) // 2
    blocks = [
        block(*RED),
        block(*BLUE),
        block(*GOLD),
        block(*GREEN),
    ]
    positions = [
        (margin, margin),
        (margin + CELL + GAP, margin),
        (margin, margin + CELL + GAP),
        (margin + CELL + GAP, margin + CELL + GAP),
    ]
    for img, pos in zip(blocks, positions):
        icon.alpha_composite(img, pos)
    icon.save("assets/icon-source.png")
    print("wrote assets/icon-source.png")


if __name__ == "__main__":
    main()
