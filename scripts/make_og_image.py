#!/usr/bin/env python3
"""Generate the ClozéHive social-share (Open Graph) image — 1200x630 PNG.

Run with the project venv:  .venv/bin/python scripts/make_og_image.py
Writes og-image.png into the marketing site and the app's public/ dir.
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630

# Brand palette (matches tailwind.config brand teal → emerald)
TEAL = (13, 148, 136)      # #0D9488
EMERALD = (5, 150, 105)    # #059669
MINT = (45, 212, 191)      # #2DD4BF
AMBER = (217, 119, 6)      # #D97706
CREAM = (250, 250, 248)    # #FAFAF8
INK = (17, 24, 39)         # #111827
MUTED = (71, 85, 105)      # slate-600


def _font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc"]
REG = ["/System/Library/Fonts/Supplemental/Arial.ttf",
       "/System/Library/Fonts/Helvetica.ttc"]

f_brand = _font(BOLD, 52)
f_head = _font(BOLD, 92)
f_sub = _font(REG, 40)
f_tag = _font(REG, 30)


def main() -> None:
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # Soft diagonal brand wash in the top-right, like the hero glow.
    glow = Image.new("RGB", (W, H), CREAM)
    gd = ImageDraw.Draw(glow)
    for i in range(H):
        t = i / H
        r = int(CREAM[0] + (236 - CREAM[0]) * (1 - t) * 0.25)
        g = int(CREAM[1] + (253 - CREAM[1]) * (1 - t) * 0.25)
        b = int(CREAM[2] + (245 - CREAM[2]) * (1 - t) * 0.25)
        gd.line([(0, i), (W, i)], fill=(r, g, b))
    img.paste(glow)
    d = ImageDraw.Draw(img)

    pad = 90

    # Logo lockup: rounded teal tile + wordmark.
    tile = 76
    ty = pad
    d.rounded_rectangle([pad, ty, pad + tile, ty + tile], radius=20, fill=TEAL)
    # simple spark glyph
    cx, cy = pad + tile / 2, ty + tile / 2
    d.line([(cx, cy - 20), (cx, cy + 20)], fill="white", width=6)
    d.line([(cx - 20, cy), (cx + 20, cy)], fill="white", width=6)
    d.line([(cx - 13, cy - 13), (cx + 13, cy + 13)], fill="white", width=4)
    d.line([(cx - 13, cy + 13), (cx + 13, cy - 13)], fill="white", width=4)
    d.text((pad + tile + 24, ty + 8), "ClozéHive", font=f_brand, fill=INK)

    # Headline (two lines), the second line in brand color.
    hy = 230
    d.text((pad, hy), "Stop Guessing.", font=f_head, fill=INK)
    d.text((pad, hy + 104), "Start Dressing Smart.", font=f_head, fill=EMERALD)

    # Tagline.
    d.text((pad, hy + 232),
           "AI wardrobe & personal stylist — outfits from clothes you own.",
           font=f_tag, fill=MUTED)

    # Bottom accent bar (brand gradient).
    by = H - 14
    for x in range(W):
        t = x / W
        r = int(MINT[0] + (AMBER[0] - MINT[0]) * t)
        g = int(MINT[1] + (AMBER[1] - MINT[1]) * t)
        b = int(MINT[2] + (AMBER[2] - MINT[2]) * t)
        d.line([(x, by), (x, H)], fill=(r, g, b))

    out_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "closetiq-integrated", "og-image.png"),
        os.path.join(os.path.dirname(__file__), "..",
                     "frontend", "public", "og-image.png"),
    ]
    for p in out_paths:
        p = os.path.abspath(p)
        img.save(p, "PNG", optimize=True)
        print("wrote", p)


if __name__ == "__main__":
    main()
