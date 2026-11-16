"""Alle Posen der Dashboard-Katze auf einem Bogen: groß (4×) zum Beurteilen, darunter in Displaygröße.

    python dev/katze_bogen.py              # → dev/out/katze/posen.png (ohne Ostereier – Vorlage für docs/katze_posen.png)
    python dev/katze_bogen.py --ostereier  # → dev/out/katze/posen_ostereier.png (mit den geheimen Ostereier-Posen)

Die Strichstärke ist wie im Dashboard 0,3 × --u; groß gerendert ist --u = 32 px, also wirkt die
Linie im Verhältnis genauso dick wie auf dem Display.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DEV = Path(__file__).resolve().parent
sys.path.insert(0, str(DEV.parent / "tagesdashboard"))
import katze  # noqa: E402

CSS_FILE = DEV.parent / "tagesdashboard" / "render" / "tagesdashboard.css"


def main():
    out = DEV / "out" / "katze"
    out.mkdir(parents=True, exist_ok=True)
    font = Path(os.environ.get("INKYPI_DIR", DEV.parent.parent / "InkyPi")) / "src/static/fonts/Jost-SemiBold.ttf"
    # Nur den Katzen-Block aus dem Dashboard-CSS übernehmen (gleiche Regeln wie im Bild)
    css = CSS_FILE.read_text(encoding="utf-8")
    cat_css = css[css.index("/* ---------------- Katze"):]
    cells = ""
    eggs = "--ostereier" in sys.argv
    name_out = "posen_ostereier.png" if eggs else "posen.png"
    for name in katze.POSES:
        if name in katze.EGG_POSES and not eggs:
            continue
        p = katze.pose(name)
        style = f'style="--w:{p["w"]};--h:{p["h"]}"'
        cells += (f'<div class="c"><div class="cat-box big" {style}>{p["svg"]}</div>'
                  f'<div class="cat-box small" {style}>{p["svg"]}</div>'
                  f'<div class="n">{name}{" · flach" if katze.is_flat(name) else ""}</div></div>')
    html = f"""<!doctype html><meta charset="utf-8"><style>
    @font-face {{ font-family: Jost; src: url('file://{font}'); font-weight: 600; }}
    body {{ margin: 0; font: 600 16px Jost; background: #fff; color: #000; --bg: #fff; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 12px; }}
    .c {{ border: 2px solid #000; border-radius: 8px; padding: 8px; display: flex; flex-direction: column;
          align-items: center; gap: 6px; }}
    {cat_css}
    .cat-box {{ position: static; }}
    .big {{ --u: 32px; border-bottom: 8px solid #000; }}
    .small {{ --u: 8px; border-bottom: 2.8px solid #000; }}
    </style><div class="grid">{cells}</div>"""
    os.environ.setdefault("FONTCONFIG_FILE", str(DEV / "fonts-eink.conf"))
    exe = os.path.realpath(next(p for p in (os.popen("which chromium-headless-shell chromium chrome").read().split()) if p))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.set_content(html)
        page.screenshot(path=str(out / name_out), full_page=True)
        browser.close()
    print(out / name_out)


if __name__ == "__main__":
    main()
