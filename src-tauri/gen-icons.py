#!/usr/bin/env python3
"""Generate the tanAI app icon set from a single drawn source.

Draws the brand mark — a violet gradient rounded square with a white spark — at
1024px, then writes every file Tauri references. Re-run after changing the mark.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")
os.makedirs(ICONS, exist_ok=True)

S = 1024
ACCENT = (109, 94, 252)  # violet
ACCENT2 = (168, 85, 247)  # purple


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def gradient(size, top, bottom):
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        # Diagonal-ish blend for a livelier look.
        row = lerp(top, bottom, t)
        for x in range(size):
            tx = x / (size - 1)
            px[x, y] = lerp(row, bottom, tx * 0.35)
    return grad


def spark(draw, cx, cy, r, color, thin=0.34):
    """A four-point sparkle: two crossed concave diamonds."""
    for ang in (0, 90):
        a = math.radians(ang)
        # tips
        tip1 = (cx + r * math.cos(a), cy + r * math.sin(a))
        tip2 = (cx - r * math.cos(a), cy - r * math.sin(a))
        # waist points (perpendicular)
        w = r * thin
        p = math.radians(ang + 90)
        s1 = (cx + w * math.cos(p), cy + w * math.sin(p))
        s2 = (cx - w * math.cos(p), cy - w * math.sin(p))
        draw.polygon([tip1, s1, tip2, s2], fill=color)


def build_source():
    base = gradient(S, ACCENT, ACCENT2)
    mask = rounded_mask(S, radius=int(S * 0.235))
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    white = (255, 255, 255, 255)
    soft = (255, 255, 255, 205)
    # Main spark, slightly up-left; two small accent sparks.
    spark(draw, S * 0.46, S * 0.47, S * 0.30, white)
    spark(draw, S * 0.72, S * 0.30, S * 0.10, soft)
    spark(draw, S * 0.70, S * 0.68, S * 0.075, soft)
    return icon


def main():
    src = build_source()
    src.save(os.path.join(ICONS, "icon-source.png"))

    # PNGs Tauri lists.
    for name, size in [
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
        ("icon.png", 512),
    ]:
        src.resize((size, size), Image.LANCZOS).save(os.path.join(ICONS, name))

    # Windows .ico (multi-size).
    src.resize((256, 256), Image.LANCZOS).save(
        os.path.join(ICONS, "icon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # macOS .icns.
    src.resize((512, 512), Image.LANCZOS).save(os.path.join(ICONS, "icon.icns"))

    print("Wrote icons to", ICONS)


if __name__ == "__main__":
    main()
