"""Draw Hookscope's app icon (a coral magnifier ring on warm paper) as a macOS .iconset folder.

Usage: python make_icon.py OUT.iconset   (then: iconutil -c icns OUT.iconset)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PAPER = (246, 242, 234)
PAPER_EDGE = (226, 217, 200)
SIGNAL = (232, 85, 61)
INK = (29, 26, 22)
SIZES = (16, 32, 64, 128, 256, 512, 1024)


def draw(size: int = 1024) -> Image.Image:
    scale = size / 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset, radius = 100 * scale, 185 * scale
    d.rounded_rectangle([inset, inset, size - inset, size - inset], radius=radius, fill=PAPER, outline=PAPER_EDGE, width=max(1, int(6 * scale)))
    # the lens
    cx, cy, r, ring = 455 * scale, 455 * scale, 215 * scale, 62 * scale
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=SIGNAL, width=int(ring))
    # three "frames" inside the lens: a nod to watching a video frame by frame
    bar_w, bar_h, gap = 52 * scale, 150 * scale, 26 * scale
    left = cx - (3 * bar_w + 2 * gap) / 2
    for i, h in enumerate((0.7, 1.0, 0.55)):
        x0 = left + i * (bar_w + gap)
        top = cy - bar_h * h / 2
        d.rounded_rectangle([x0, top, x0 + bar_w, top + bar_h * h], radius=10 * scale, fill=INK)
    # the handle
    d.line([(cx + r * 0.72, cy + r * 0.72), (760 * scale, 760 * scale)], fill=SIGNAL, width=int(78 * scale))
    end = 39 * scale
    d.ellipse([760 * scale - end, 760 * scale - end, 760 * scale + end, 760 * scale + end], fill=SIGNAL)
    return img


def main(out_dir: str) -> int:
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    master = draw(1024)
    for size in SIZES:
        if size <= 512:
            master.resize((size, size), Image.LANCZOS).save(folder / f"icon_{size}x{size}.png")
        if size >= 32:
            half = size // 2
            master.resize((size, size), Image.LANCZOS).save(folder / f"icon_{half}x{half}@2x.png")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "AppIcon.iconset"))
