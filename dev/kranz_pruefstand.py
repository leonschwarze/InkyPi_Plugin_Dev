"""Prüfstand für den Adventskranz (seit 1.29): Streupixel nach dem Einrasten.

Rendert den Kranz (1–4 Kerzen) in den Größen, in denen er im Dashboard vorkommt, an 4×4 Lagen auf
Bruchteilen eines Pixels, rastet ihn mit eink.snap ein und zählt Pixel in Farben, die im Kranz nicht
vorkommen (Blau) oder an der falschen Stelle stehen (Grün oberhalb des Wulstes, Rot/Gelb/Grün außerhalb
der Zeichnung). Ziel: 0. Hintergrund: An spitzen Ecken treffen drei Farben in einem Pixel zusammen;
eink.py erklärt nur Mischungen aus zwei und macht daraus falsche Einzelpixel.

  python dev/kranz_pruefstand.py            # Zusammenfassung
  python dev/kranz_pruefstand.py --bild     # zusätzlich dev/out/kranz/pruefstand.png (4×)
"""
import argparse
import io
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tagesdashboard"))
sys.path.insert(0, os.path.join(ROOT, "shared"))
import advent  # noqa: E402
import eink  # noqa: E402

# Breite in px: quer 800×480 (Kopf 4,3 u, Woche 4 u, u = 8), hochkant (u ≈ 6,96), 1600×1200 (u = 16)
SIZES = [("quer", 34.4, 8), ("woche", 32.0, 8), ("hoch", 29.9, 6.96), ("hoch-woche", 27.8, 6.96), ("groß", 68.8, 16)]
SW = 0.24  # Strichstärke in --u, wie .adv-ic im CSS
OFFS = [0, 0.25, 0.5, 0.75]


def page():
    cells = []
    for name, w, u in SIZES:
        for lit in range(1, 5):
            for oy in OFFS:
                for ox in OFFS:
                    cells.append((name, w, lit, ox, oy, u))
    html = ["<html><head><style>svg * { vector-effect: non-scaling-stroke; stroke-width: var(--sw); }</style></head>"
            "<body style='margin:0;background:#fff;color:#000'>"]
    pitch = 90
    for k, (name, w, lit, ox, oy, u) in enumerate(cells):
        x, y = (k % 16) * pitch + ox + 10, (k // 16) * pitch + oy + 10
        h = w * 36 / 40
        svg = advent.wreath(lit).replace('class="adv-ic"', f'style="position:absolute;left:{x}px;top:{y}px;'
                                                             f'width:{w}px;height:{h}px;overflow:visible;'
                                                             f'--sw:{SW * u:.2f}px"')
        html.append(svg)
    html.append("</body></html>")
    return "".join(html), cells, pitch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bild", action="store_true")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    html, cells, pitch = page()
    rows = (len(cells) + 15) // 16
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 16 * pitch + 20, "height": rows * pitch + 20})
        pg.set_content(html)
        png = pg.screenshot()
        b.close()
    raw = Image.open(io.BytesIO(png)).convert("RGB")
    img = np.asarray(eink.snap(raw, 0.5).convert("RGB")).astype(int)
    blue = np.array([0, 0, 255]); green = np.array([0, 255, 0])
    bad_total, by_size = 0, {}
    for k, (name, w, lit, ox, oy, u) in enumerate(cells):
        x0, y0 = (k % 16) * pitch + 10, (k // 16) * pitch + 10
        h = w * 36 / 40
        cell = img[y0 - 4:y0 + int(h) + 6, x0 - 4:x0 + int(w) + 6]
        n_blue = int(np.all(cell == blue, axis=2).sum())
        band_top = int(26 / 36 * h) - 1  # Oberkante des Wulstes (mit Kontur) in der Zelle (+4 Rand)
        n_green = int(np.all(cell[:band_top + 4 - 1] == green, axis=2).sum())
        bad = n_blue + n_green
        bad_total += bad
        by_size.setdefault(name, 0)
        by_size[name] += bad
    for name, n in by_size.items():
        print(f"{name:11s} Streupixel: {n}")
    print("gesamt", bad_total, f"({len(cells)} Lagen)")
    if args.bild:
        out = os.path.join(ROOT, "dev", "out", "kranz"); os.makedirs(out, exist_ok=True)
        im = Image.fromarray(img.astype("uint8"))
        im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(os.path.join(out, "pruefstand.png"))
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main())
