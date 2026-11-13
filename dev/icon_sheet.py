"""Zeigt alle Symbole (Wetter, Messwerte, Kleidung) auf einer Übersichtsseite.

  python dev/icon_sheet.py            -> dev/out/icons.png

Nützlich, um neue oder geänderte Icons zu prüfen. Braucht nur Chromium
(google-chrome, chromium oder chromium-browser) im PATH.
"""
import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ic = load(REPO / "dwd_wetter" / "dwd_icons.py", "dwd_icons")
    kl = load(REPO / "tagesdashboard" / "kleidung.py", "kleidung")
    cell = '<div class="c {cls}">{svg}<span>{name}</span></div>'
    rows = [
        "".join(cell.format(cls="", svg=ic.weather_icon(n), name=n) for n in ic.WEATHER_ICONS),
        "".join(cell.format(cls="s", svg=ic.metric_icon(n), name=n) for n in ic.METRIC_ICONS),
        "".join(cell.format(cls="s", svg=svg, name=n) for n, svg in kl.ICONS.items()),
    ]
    html = ("<html><body style='margin:0;font-family:sans-serif;background:#fff;color:#000'><style>"
            ".g{display:flex;flex-wrap:wrap;border-bottom:2px solid #000}"
            ".c{width:140px;height:140px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:12px}"
            ".c svg{width:100px;height:100px}.s{width:110px;height:100px}.s svg{width:56px;height:56px}"
            "</style>" + "".join(f"<div class='g'>{r}</div>" for r in rows) + "</body></html>")
    browser = next((b for b in ("chromium-headless-shell", "chromium", "chromium-browser", "google-chrome")
                    if shutil.which(b)), None)
    if not browser:
        raise SystemExit("Kein Chromium gefunden.")
    out = REPO / "dev" / "out"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
    subprocess.run([browser, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                    f"--screenshot={out / 'icons.png'}", "--window-size=1260,720", f"file://{f.name}"],
                   check=True, stderr=subprocess.DEVNULL)
    print(f"gespeichert: {out / 'icons.png'}")


if __name__ == "__main__":
    main()
