"""Ausschaltbild rendern und prüfen (ohne Display, ohne systemd).

  python dev/render_ausschaltbild.py                      # alle Testauflösungen nach dev/out/ausschaltbild/
  python dev/render_ausschaltbild.py --time "2026-11-15 9:05"
  python dev/render_ausschaltbild.py --saturation 0.8     # Mischpalette des Treibers
  python dev/render_ausschaltbild.py --docs               # zusätzlich docs/ausschaltbild_*.png (gelber Streifen „Beispieldaten“)

Je Auflösung entstehen:
  aus_<größe>.png          in Leserichtung, eingerastet (so sieht man es auf dem Display)
  aus_<größe>_panel.png    so, wie es an den Treiber geht (hochkant gedreht)
  aus_<größe>_zoom.png     Katze und kleine Schrift 4× vergrößert, ohne Glättung
und die Meldung, wie viele Pixel der Treiber noch verändert (Ziel: 0).
Die Schrift kommt aus ../InkyPi/src/static/fonts (wie auf dem Pi), sonst INKYPI_DIR setzen.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ausschaltbild"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ausschaltbild as aus  # noqa: E402
import inky_sim  # noqa: E402

INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi"))
SIZES = [("800x480", 800, 480, "horizontal"), ("480x800v", 800, 480, "vertical"),
         ("600x448", 600, 448, "horizontal"), ("1600x1200", 1600, 1200, "horizontal")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time", default="2026-11-15 22:14")
    ap.add_argument("--saturation", type=float, default=0.5)
    ap.add_argument("--out", default=str(ROOT / "dev" / "out" / "ausschaltbild"))
    ap.add_argument("--inverted", action="store_true")
    ap.add_argument("--docs", action="store_true", help="Screenshots für die README nach docs/")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    aus.FONT_DIRS = [INKYPI / "src" / "static" / "fonts"]
    if not aus.find_font() or "Jost" not in aus.find_font():
        print(f"Warnung: Jost nicht gefunden unter {aus.FONT_DIRS[0]} – Ersatzschrift")
    when = datetime.strptime(a.time, "%Y-%m-%d %H:%M")
    worst = 0
    for name, w, h, orient in SIZES:
        cfg = {"width": w, "height": h, "orientation": orient, "inverted": a.inverted,
               "saturation": a.saturation}
        logical = aus.build(*aus.logical_size(cfg), when)
        panel = aus.for_display(logical, cfg)
        assert panel.size == (w, h), (panel.size, w, h)
        read = panel.rotate(180) if a.inverted else panel
        read = read.rotate(-90, expand=1) if orient == "vertical" else read
        read.save(out / f"aus_{name}.png")
        panel.save(out / f"aus_{name}_panel.png")
        changed = inky_sim.changed_by_driver(panel, a.saturation)
        worst = max(worst, changed)
        zoom(read, out / f"aus_{name}_zoom.png")
        print(f"{name}: gespeichert, vom Treiber verändert: {changed} Pixel")
        if a.docs and name in ("800x480", "480x800v"):
            doc = ROOT / "docs" / f"ausschaltbild_{name.rstrip('v')}.png"
            footer(read, "Beispieldaten: Zeitpunkt erfunden").save(doc)
            print(f"  Screenshot: {doc.relative_to(ROOT)}")
    return 1 if worst else 0


def footer(img, text):
    """Gelber Streifen unter dem Bild wie bei den übrigen Screenshots in docs/."""
    from PIL import ImageDraw
    out = Image.new("RGB", (img.width, img.height + 26), (255, 229, 0))
    out.paste(img, (0, 0))
    fnt = aus.font(aus.find_font(), 14)   # wie die übrigen Screenshots
    ImageDraw.Draw(out).text((8, img.height + 13), text, font=fnt, fill=(0, 0, 0), anchor="lm")
    return out


def zoom(img, path):
    """Mittleres Band (Katze und kleine Schrift) 4× ohne Glättung."""
    w, h = img.size
    box = (0, int(h * 0.2), w, int(h * 0.8)) if w > h else (0, int(h * 0.12), w, int(h * 0.88))
    c = img.crop(box)
    f = max(1, min(4, 1600 // c.width))
    c.resize((c.width * f, c.height * f), Image.NEAREST).save(path)


if __name__ == "__main__":
    sys.exit(main())
