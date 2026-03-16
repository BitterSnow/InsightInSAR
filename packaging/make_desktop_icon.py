# -*- coding: utf-8 -*-
"""从 public/img/InSAR_Insight_Logo_Focused.png 生成 desktop_icon.ico，供 Desktop exe 使用。
Run from repo root: python packaging/make_desktop_icon.py
Requires: pip install Pillow
"""
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Please install Pillow: pip install Pillow")
    raise

REPO_ROOT = Path(__file__).resolve().parent.parent
PNG_PATH = REPO_ROOT / "public" / "img" / "InSAR_Insight_Logo_Focused.png"
OUT_ICO = Path(__file__).resolve().parent / "desktop_icon.ico"
SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def main():
    if not PNG_PATH.is_file():
        print(f"Logo not found: {PNG_PATH}")
        raise SystemExit(1)
    img = Image.open(PNG_PATH).convert("RGBA")
    img.save(OUT_ICO, format="ICO", sizes=SIZES)
    print(f"Wrote {OUT_ICO}")


if __name__ == "__main__":
    main()
