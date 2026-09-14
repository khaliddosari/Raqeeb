"""Renders the link preview and the iOS home screen icon from share-card.html.

Run from the repo root after editing the card:

    uv run --with playwright --with pillow python frontend/design/render_share_images.py

The card is drawn at twice its size and scaled down, which smooths the text. The preview is
saved as JPEG, since it has no transparency and link unfurlers (WhatsApp in particular) are
more reliable with a small file.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"
FONTS = ['900 84px "Thmanyah Serif Display"', '700 54px "Thmanyah Sans"', '500 31px "Thmanyah Sans"']


def shot(page, selector: str, size: tuple[int, int]) -> Image.Image:
    image = Image.open(io.BytesIO(page.locator(selector).screenshot())).convert("RGB")
    return image.resize(size, Image.LANCZOS)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 800}, device_scale_factor=2)
    page.goto((HERE / "share-card.html").as_uri(), wait_until="networkidle")
    loaded = page.evaluate(
        "async (fonts) => { await Promise.all(fonts.map(f => document.fonts.load(f, 'Raqeeb رقيب'))); "
        "await document.fonts.ready; return fonts.every(f => document.fonts.check(f, 'Raqeeb رقيب')) }",
        FONTS,
    )
    if not loaded:
        raise SystemExit("Thmanyah fonts did not load; check the network and try again.")

    card = shot(page, "#card", (1200, 675))
    card.save(PUBLIC / "og-image.jpg", "JPEG", quality=90, optimize=True, progressive=True)
    shot(page, "#icon", (180, 180)).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    browser.close()

for name in ("og-image.jpg", "apple-touch-icon.png"):
    path = PUBLIC / name
    with Image.open(path) as image:
        print(f"{name}: {image.size[0]}x{image.size[1]}, {path.stat().st_size // 1024} KB")
