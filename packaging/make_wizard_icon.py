# -*- coding: utf-8 -*-
"""Generate wizard_icon.ico for InSAR WSL Deploy Wizard.
Run from repo root: python packaging/make_wizard_icon.py
Requires: pip install Pillow
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Please install Pillow: pip install Pillow")
    raise

OUT_DIR = Path(__file__).resolve().parent
SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def draw_icon(size: int) -> Image.Image:
    """Draw a simple WSL/terminal deployment icon: window + gear style."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Scale for size
    s = size
    pad = max(1, s // 8)
    # Blue rounded-rect window background (#0d47a1 / WSL blue)
    d.rounded_rectangle(
        [pad, pad, s - pad, s - pad],
        radius=max(1, s // 6),
        fill=(13, 71, 161, 255),
        outline=(33, 150, 243, 255),
        width=max(1, s // 24),
    )
    # Simple "terminal" bar at top (title bar)
    bar_h = max(2, s // 6)
    d.rectangle(
        [pad + 1, pad + 1, s - pad - 1, pad + bar_h],
        fill=(25, 118, 210, 255),
    )
    # Three circles (minimize/maximize/close style or "WSL" dots)
    dot_y = pad + bar_h // 2
    dot_r = max(1, s // 24)
    for i, x_off in enumerate([0.2, 0.5, 0.8]):
        cx = pad + int((s - 2 * pad) * x_off)
        d.ellipse(
            [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
            fill=(255, 255, 255, 255),
        )
    # Chevron/play symbol in center (deploy/run)
    cy = pad + bar_h + (s - 2 * pad - bar_h) // 2
    cx = s // 2
    tri_h = max(2, (s - 2 * pad - bar_h) // 3)
    tri_w = tri_h
    d.polygon(
        [
            (cx - tri_w // 2, cy - tri_h // 2),
            (cx - tri_w // 2, cy + tri_h // 2),
            (cx + tri_w // 2, cy),
        ],
        fill=(255, 255, 255, 255),
    )
    return img


def main():
    images = []
    for w, h in SIZES:
        images.append(draw_icon(w).resize((w, h), Image.Resampling.LANCZOS))
    out = OUT_DIR / "wizard_icon.ico"
    # Save as multi-size ico (PIL accepts list of sizes from a single image for ICO)
    img_256 = draw_icon(256)
    img_256.save(
        out,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
