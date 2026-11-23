"""Streupixel-Prüfstand für die Katzen-Posen (seit 1.34, erweitert 1.35 und 1.43, wie dev/kranz_pruefstand.py).

    python dev/katze_pruefstand.py            # nur die Posen seit 1.34
    python dev/katze_pruefstand.py --alle     # alle Posen
    python dev/katze_pruefstand.py --wo       # dazu die Lage jedes fremden Pixels (Einheiten der Pose)

Jede Pose wird in den drei Größen von placeCat (k = 1, 0,9, 0,8) und vier Lagen im Subpixel-Raster
(Viertelpixel) gerendert, mit eink.snap eingerastet und gezählt: Pixel in einer Displayfarbe, die die Pose gar
nicht verwendet (z. B. ein rotes Pixel am gelben Hut). Solche Pixel entstehen an Kanten aus drei Farben.
Ziel: 0.
"""
import io
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

DEV = Path(__file__).resolve().parent
sys.path.insert(0, str(DEV.parent / "tagesdashboard"))
sys.path.insert(0, str(DEV.parent / "shared"))
import eink  # noqa: E402
import katze  # noqa: E402

NEW = ["südwester", "fenster", "schneeflocke", "schneemann", "mütze", "decke", "sonnenbrille", "eis",
       "drachen", "blätter", "winkt", "pflanze", "fisch", "lichterkette",
       # seit 1.35
       "nebel", "gewitter", "fernglas", "helm", "haltestelle", "niest", "plakat", "karte", "zipfelmütze",
       "hängematte", "laptop", "kopfhörer", "ball", "flieger", "seifenblasen",
       # seit 1.43
       "schlitten", "glatteis", "stirnband", "comic", "thermometer", "plätzchen", "laterne"]
COLORS = {"red": ((227, 0, 27), "--cat-red"), "yellow": ((255, 196, 0), "--cat-yellow"),
          "blue": ((0, 130, 201), "--cat-blue"), "green": ((46, 158, 63), "--cat-green")}


def main():
    names = list(katze.POSES) if "--alle" in sys.argv else NEW
    css = (DEV.parent / "tagesdashboard/render/tagesdashboard.css").read_text(encoding="utf-8")
    cat_css = css[css.index("/* ---------------- Katze"):css.index("/* ---------------- Statusanzeige")]
    exe = os.path.realpath(os.popen("which chromium-headless-shell").read().strip())
    bad_total = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe)
        page = b.new_page(viewport={"width": 300, "height": 200})
        for name in names:
            p = katze.pose(name)
            used = {c for c, (_, var) in COLORS.items() if f"var({var})" in p["svg"] or f"var({var}-ink)" in p["svg"]}
            worst = 0
            for k in (1, 0.9, 0.8):
                for off in (0, 0.25, 0.5, 0.75):
                    html = (f'<!doctype html><style>body{{margin:0;background:#fff;color:#000;--bg:#fff}}{cat_css}'
                            f'.cat-box{{left:{10 + off}px;top:{10 + off}px;--u:8px}}</style>'
                            f'<div class="cat-box" style="--w:{p["w"]};--h:{p["h"]};--k:{k}">{p["svg"]}</div>')
                    page.set_content(html)
                    img = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
                    a = np.asarray(eink.snap(img)).reshape(-1, 3).astype(int)
                    bad = 0
                    for c, (rgb, _) in COLORS.items():
                        if c not in used:
                            hit = np.flatnonzero(np.abs(a - rgb).sum(1) < 60)
                            bad += len(hit)
                            if len(hit) and "--wo" in sys.argv:  # Lage in Einheiten der Pose
                                print(f"    {name} k={k} +{off}: {c} bei",
                                      [(round((i % img.width - 10 - off) / k, 1), round((i // img.width - 10 - off) / k, 1))
                                       for i in hit])
                    worst = max(worst, bad)
            if name in NEW:  # ältere Posen nur melden (spielt, schwarz, kürbis: je 1 Pixel, Stand 1.33)
                bad_total += worst
            print(f"  {'ok    ' if worst == 0 else 'FEHLER'}  {name}: höchstens {worst} fremde Pixel ({', '.join(sorted(used)) or 'nur Schwarz'})")
        b.close()
    print("Alles in Ordnung." if bad_total == 0 else f"{bad_total} fremde Pixel.")
    sys.exit(1 if bad_total else 0)


if __name__ == "__main__":
    main()
