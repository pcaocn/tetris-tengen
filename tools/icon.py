"""App icon generator (spec section 6): four vector-style blocks in the
falling-piece palette — red, blue, gold, green — with the game's
three-tone bevel look (light top+right, dark left+bottom, black
outline) on a black field. Writes a 1024px source PNG; the full icon
set is derived from it with `npx tauri icon`.

Usage: uv run --no-project --with pillow python tools/icon.py

=====================================================================
HOW THE BLOCK LOOK IS BUILT
=====================================================================
Each block is drawn in four stacked layers on a transparent tile
(see block()):

  1. a black rounded square -- this IS the outline,
  2. a dark rounded square inset by OUTLINE -- the shadow tone,
  3. light strips along the top and right edges -- the highlight,
  4. a mid-tone rectangle inset by BEVEL on all sides -- the face.

Steps 3 and 4 overwrite the dark layer's center, so the dark tone
only survives along the left and bottom edges: exactly the light /
mid / dark bevel the in-game blocks use. A rounded-rectangle alpha
mask then clips layers 2-4 back to the outline's rounded shape.

The palette triples are copied from the FALLING entries of
app/src/theme.ts, which is where the app's piece colors come from.
"""

from PIL import Image, ImageDraw

# Canvas 1024 px: the source size Tauri's icon pipeline expects.
SIZE = 1024
# Block geometry in px. CELL=360 blocks with GAP=40 between make the
# 2x2 grid 2*360+40 = 760 px wide, so margin=(1024-760)//2=132
# centers it. OUTLINE/BEVEL/RADIUS are the bevel look, eyeballed
# against the in-game block rendering.
CELL = 360
GAP = 40
OUTLINE = 16
BEVEL = 58
RADIUS = 44

# (light, mid, dark) per piece, from theme.ts.
# Light = highlight (top+right), mid = face, dark = shadow (left+
# bottom) -- the same three tones the game draws per block. The
# letter on each line is the piece whose FALLING palette it copies.
RED = ("#f7a199", "#b05a51", "#873129")      # I
BLUE = ("#8fc0ff", "#6464e2", "#1e509d")     # O
GOLD = ("#ffe092", "#e6b467", "#9e6d20")    # J
GREEN = ("#7cdfa1", "#349859", "#0c6f30")    # S


def hex_rgb(h):
    """'#rrggbb' -> (r, g, b, 255); PIL wants an explicit alpha for RGBA work."""
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def block(light, mid, dark):
    """Render one beveled block tile: CELL x CELL RGBA, transparent corners.

    Args are the three tone hexes (light, mid, dark). Transparency
    outside the rounded shape lets the black icon field show through
    at the corners when the tile is composited.
    """
    w = h = CELL
    # Layer 1: the black rounded base -- opaque inside, transparent at
    # the corners. The black rim between blocks is this base showing
    # around the inset fill below.
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=RADIUS, fill=(0, 0, 0, 255))
    # Layers 2-4 are drawn on a scratch layer and clipped with a mask
    # afterwards, so nothing bleeds past the rounded outline.
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    lo, hi = OUTLINE, w - 1 - OUTLINE
    # Layer 2: dark fill, inset by the outline width (radius shrunk by
    # the same amount so the rims stay parallel).
    dl.rounded_rectangle([lo, lo, hi, hi], radius=max(1, RADIUS - OUTLINE), fill=hex_rgb(dark))
    # Layer 3: light highlight strips, BEVEL px thick, along the two
    # "lit" edges (top and right -- the light source is up-right).
    dl.rectangle([lo, lo, hi, lo + BEVEL], fill=hex_rgb(light))       # top
    dl.rectangle([hi - BEVEL, lo, hi, hi], fill=hex_rgb(light))       # right
    # Layer 4: the mid face, BEVEL px in from every side. After this
    # overdraw, the dark tone survives only along left and bottom.
    dl.rectangle([lo + BEVEL, lo + BEVEL, hi - BEVEL, hi - BEVEL], fill=hex_rgb(mid))
    # Clip layers 2-4 to the same rounded shape as the base and paste
    # them over it: paste() uses `mask` as per-pixel alpha.
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [lo, lo, hi, hi], radius=max(1, RADIUS - OUTLINE), fill=255
    )
    img.paste(layer, (0, 0), mask)
    return img


def main():
    """Composite the 2x2 block grid on a black field and save the PNG.

    Writes assets/icon-source.png relative to the CWD -- run from the
    repo root. Then `npx tauri icon` derives every platform size.
    """
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    margin = (SIZE - 2 * CELL - GAP) // 2
    blocks = [
        block(*RED),
        block(*BLUE),
        block(*GOLD),
        block(*GREEN),
    ]
    # 2x2 grid: red/blue on top, gold/green underneath.
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
