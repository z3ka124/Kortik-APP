# c:\Kortik\Kortik-Listener-App\build\make_icon.py
"""
Pravi assets/icon.ico iz Kortik logotipa (public/avatar.png).

    python build\\make_icon.py

Koristi se pri buildu: pyinstaller.spec i installer.iss uzimaju assets/icon.ico.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO = PROJECT_ROOT.parent

CANDIDATES = [
    REPO / "Kortik-Bot Dashabord" / "Kortik-Dahabord-Fronted" / "public" / "avatar.png",
    REPO / "Kortik-Bot Dashabord" / "kortikai-frontend" / "public" / "avatar.png",
    PROJECT_ROOT / "assets" / "logo.png",
]
OUT = PROJECT_ROOT / "assets" / "icon.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("Nedostaje Pillow: python -m pip install Pillow")
        return 1

    source = next((p for p in CANDIDATES if p.exists()), None)
    if source is None:
        print("Nisam našao logo. Očekivano na jednom od:")
        for path in CANDIDATES:
            print("  -", path)
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGBA")
    side = min(image.size)
    image = image.crop(
        (
            (image.width - side) // 2,
            (image.height - side) // 2,
            (image.width + side) // 2,
            (image.height + side) // 2,
        )
    )
    image.save(OUT, format="ICO", sizes=SIZES)
    print(f"OK  {OUT}  (iz {source.name}, {len(SIZES)} veličina)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
