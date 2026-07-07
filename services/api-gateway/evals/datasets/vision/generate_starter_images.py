"""Generate the deterministic synthetic starter images for the vision golden set.

Draws simple but recognisable garment renderings with PIL — enough signal for a
vision model to judge *category*, *primary colour*, and *pattern*. Fabric
texture and fit cannot be judged from flat renderings, so those fields are
labelled ``null`` (not scored) for every synthetic case; they start being
scored as real photos are added to ``images/`` (see labels.yaml header).

Deterministic on purpose: re-running produces byte-identical PNGs, so the
images can live in git and regenerate anywhere.

Run once (from services/api-gateway)::

    python -m evals.datasets.vision.generate_starter_images
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent / "images"

W, H = 512, 512
BG = (245, 245, 240)

COLORS = {
    "navy": (28, 42, 84),
    "red": (176, 32, 38),
    "white": (250, 250, 250),
    "black": (22, 22, 22),
    "green": (36, 94, 60),
    "brown": (98, 66, 38),
    "yellow": (222, 182, 44),
    "grey": (128, 130, 134),
}


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def _tshirt(color: tuple[int, int, int], stripes: bool = False) -> Image.Image:
    img, d = _canvas()
    body = [(156, 150), (356, 150), (356, 420), (156, 420)]
    d.polygon(body, fill=color)
    # Sleeves
    d.polygon([(156, 150), (86, 210), (116, 260), (156, 220)], fill=color)
    d.polygon([(356, 150), (426, 210), (396, 260), (356, 220)], fill=color)
    # Neckline
    d.ellipse([226, 130, 286, 175], fill=BG)
    if stripes:
        stripe = tuple(min(c + 90, 255) for c in color)
        for y in range(190, 420, 44):
            d.rectangle([156, y, 356, y + 16], fill=stripe)
    return img


def _trousers(color: tuple[int, int, int]) -> Image.Image:
    img, d = _canvas()
    # Hips + left leg
    d.polygon([(176, 90), (336, 90), (340, 210), (262, 250), (250, 470), (182, 470), (170, 210)], fill=color)
    # Right leg
    d.polygon([(262, 250), (340, 210), (350, 470), (282, 470)], fill=color)
    # Waistband
    d.rectangle([172, 90, 340, 114], fill=tuple(max(c - 24, 0) for c in color))
    return img


def _dress(color: tuple[int, int, int]) -> Image.Image:
    img, d = _canvas()
    # Bodice
    d.polygon([(196, 110), (316, 110), (306, 240), (206, 240)], fill=color)
    # Straps
    d.rectangle([206, 78, 222, 110], fill=color)
    d.rectangle([290, 78, 306, 110], fill=color)
    # A-line skirt
    d.polygon([(206, 240), (306, 240), (386, 460), (126, 460)], fill=color)
    return img


def _jacket(color: tuple[int, int, int]) -> Image.Image:
    img, d = _canvas()
    dark = tuple(max(c - 40, 0) for c in color)
    # Long sleeves, clearly separated from the torso by a background gap.
    d.polygon([(168, 148), (128, 168), (108, 430), (158, 430), (172, 220)], fill=dark)
    d.polygon([(344, 148), (384, 168), (404, 430), (354, 430), (340, 220)], fill=dark)
    # Torso
    d.polygon([(178, 140), (334, 140), (334, 420), (178, 420)], fill=color)
    # Open front (zip gap) + collar
    d.rectangle([250, 140, 262, 420], fill=BG)
    d.polygon([(214, 140), (250, 140), (250, 186)], fill=dark)
    d.polygon([(298, 140), (262, 140), (262, 186)], fill=dark)
    # Hem band + cuffs
    d.rectangle([178, 400, 334, 420], fill=dark)
    d.rectangle([108, 408, 158, 430], fill=color)
    d.rectangle([354, 408, 404, 430], fill=color)
    return img


def _shoe(color: tuple[int, int, int]) -> Image.Image:
    """Side-profile sneaker. Outlined so a white shoe stays visible on the
    off-white canvas."""
    img, d = _canvas()
    outline = (150, 150, 150)
    sole = (226, 226, 222)
    # Sole (side profile, toe at right)
    d.rounded_rectangle([86, 330, 426, 372], radius=20, fill=sole, outline=outline, width=3)
    # Upper: heel counter rises at left, toe box tapers at right
    d.polygon(
        [(100, 336), (104, 210), (160, 196), (232, 226), (330, 282), (412, 322), (412, 336)],
        fill=color,
        outline=outline,
    )
    # Ankle collar
    d.ellipse([104, 190, 176, 226], fill=color, outline=outline, width=2)
    # Laces across the instep
    lace = (120, 120, 120)
    for i in range(4):
        d.line([(196 + i * 34, 232 + i * 16), (232 + i * 34, 258 + i * 14)], fill=lace, width=6)
    # Toe cap
    d.pieslice([352, 288, 428, 348], start=250, end=360, fill=sole, outline=outline)
    return img


CASES = [
    ("navy_tshirt.png", lambda: _tshirt(COLORS["navy"])),
    ("red_striped_tshirt.png", lambda: _tshirt(COLORS["red"], stripes=True)),
    ("black_trousers.png", lambda: _trousers(COLORS["black"])),
    ("brown_trousers.png", lambda: _trousers(COLORS["brown"])),
    ("green_dress.png", lambda: _dress(COLORS["green"])),
    ("yellow_dress.png", lambda: _dress(COLORS["yellow"])),
    ("grey_jacket.png", lambda: _jacket(COLORS["grey"])),
    ("white_sneaker.png", lambda: _shoe(COLORS["white"])),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, render in CASES:
        img = render()
        img.save(OUT_DIR / filename, format="PNG", optimize=True)
        print(f"wrote {OUT_DIR / filename}")


if __name__ == "__main__":
    main()
