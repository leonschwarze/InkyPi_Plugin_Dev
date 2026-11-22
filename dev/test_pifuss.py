"""Pi-Zeile der Wochenvorschau wird nie abgeschnitten (fitPi im Template, seit 1.39).

  python dev/test_pifuss.py            # rendert mit dev/render.py --html, misst die Seiten mit Playwright
  python dev/test_pifuss.py --inkypi ../InkyPi-alt   # Gegenprobe gegen einen alten Stand (render.py dort)

Fehlermeldung vom 22.11.: Bei mehreren Ausfällen in der Woche wurde der Text unten in der Wochenübersicht
abgeschnitten (CSS kürzte blind an der Kante: „GA 1× we…“, alles dahinter fehlte).

Geprüft je Fall und Auflösung (800x480, 480x800 hochkant, 600x448, 1600x1200):
  * die Zeile läuft weder seitlich noch nach unten über (scrollWidth; scrollHeight mit einer halben Zeile
    Toleranz, weil die Schriftfläche von Jost über die Zeilenhöhe ragt) und liegt im Bild
  * quer eine Zeile, hochkant höchstens zwei
  * der erste Eintrag ist immer zu sehen; wird etwas weggelassen, dann zuerst die ruhigen Werte,
    und verborgene Probleme stehen als „+N weitere“ da (die Zahl stimmt)
  * ohne Platzmangel (Woche ohne Ausfälle) steht alles in Langform da, als ein Text wie bis 1.38
Fälle: --pi ok, ausfall, warn, viele; viele zusätzlich mit Warnband und Laufzeile (weniger Platz für die Woche).
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEV = Path(__file__).resolve().parent
ROOT = DEV.parent
SIZES = {"800x480": (800, 480), "480x800v": (480, 800), "600x448": (600, 448), "1600x1200": (1600, 1200)}
CASES = [  # (Name, render.py-Argumente, alles in Langform erwartet?)
    ("ok", ["--pi", "ok"], True),
    ("ausfall", ["--pi", "ausfall"], None),
    ("warn", ["--pi", "warn"], None),
    ("viele", ["--pi", "viele"], False),
    ("viele+band+lauf", ["--pi", "viele", "--nina", "bombe", "--lauf", "normal"], False),
]
FAILED = []

MEASURE = """() => {
  const el = document.querySelector('.wk-pi');
  if (!el) return null;
  const cs = getComputedStyle(el), r = el.getBoundingClientRect();
  const parts = [...el.querySelectorAll('.pp')];
  const more = el.querySelector('.pp-more');
  return {
    sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight,
    bottom: r.bottom, vh: window.innerHeight, lh: parseFloat(cs.lineHeight),
    lines: Math.round((r.height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)
                       - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth)) / parseFloat(cs.lineHeight)),
    text: el.innerText,
    parts: parts.map(p => ({kind: p.className.includes('pp-fact') ? 'fact' : 'problem', hidden: p.hidden,
                            long: p.dataset.long, shown: p.querySelector('.pt') ? p.querySelector('.pt').textContent : ''})),
    more: more ? more.textContent : null,
    data: el.dataset.parts ? JSON.parse(el.dataset.parts) : null,
  };
}"""


def check(name, condition, detail=""):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}" + (f" – {detail}" if detail and not condition else ""))
    if not condition:
        FAILED.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inkypi", default=None, help="InkyPi-Ordner (Standard wie render.py)")
    ap.add_argument("--repo", default=str(ROOT), help="Repo, dessen dev/render.py rendert (Gegenprobe: alter Worktree)")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = Path(tempfile.mkdtemp(prefix="pifuss-"))
    env = dict(os.environ, FONTCONFIG_FILE=str(DEV / "fonts-eink.conf"))
    pages = []
    for name, extra, _ in CASES:
        cmd = [sys.executable, str(Path(args.repo) / "dev" / "render.py"), "tagesdashboard",
               "--time", "2026-11-15 19:10", "--html", "--sizes", ",".join(SIZES), "--out", str(out)] + extra
        if args.inkypi:
            cmd += ["--inkypi", args.inkypi]
        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if res.returncode:
            check(f"{name}: render.py läuft", False, res.stderr[-400:])
            continue
        for label in SIZES:
            found = sorted(out.glob(f"*pi-{name.split('+')[0]}*_{label}.html") if name != "ok"
                           else [p for p in out.glob(f"*_{label}.html") if "_pi-" not in p.name])
            found = [p for p in found if ("nina" in p.name) == ("band" in name)]
            check(f"{name} {label}: Seite gespeichert", len(found) == 1, str(found))
            if found:
                pages.append((name, label, found[0]))
    print(f"{len(pages)} Seiten zu prüfen")

    with sync_playwright() as p:
        browser = p.chromium.launch(env=env)
        for name, label, path in pages:
            w, h = SIZES[label]
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(path.as_uri())
            page.wait_for_timeout(400)
            m = page.evaluate(MEASURE)
            page.close()
            tag = f"{name} {label}"
            if m is None:
                check(f"{tag}: Pi-Zeile vorhanden", False)
                continue
            check(f"{tag}: läuft seitlich nicht über", m["sw"] <= m["cw"] + 1, f"{m['sw']} > {m['cw']}: {m['text']!r}")
            # Unten zählt eine verborgene Zeile; die Schriftfläche von Jost ragt ohnehin ein paar Pixel über die Zeilenhöhe
            check(f"{tag}: läuft unten nicht über", m["sh"] < m["ch"] + m["lh"] / 2, f"{m['sh']} > {m['ch']}: {m['text']!r}")
            check(f"{tag}: liegt im Bild", m["bottom"] <= m["vh"] + 0.5, f"{m['bottom']} > {m['vh']}")
            check(f"{tag}: Zeilenzahl", m["lines"] <= (2 if label.endswith("v") else 1), f"{m['lines']} Zeilen")
            check(f"{tag}: Teile im Template (data-parts für fitPi)", bool(m["data"]), m["text"])
            if not m["data"]:
                continue
            parts = m["parts"]
            if not parts:  # passt: ein Text wie bis 1.38, dann muss alles dastehen
                parts = [{"kind": q["kind"], "hidden": False, "long": q["text"], "shown": q["text"]} for q in m["data"]]
                whole = "Pi: " + " · ".join(q["text"] for q in m["data"])
                check(f"{tag}: ganzer Text", " ".join(m["text"].split()) == " ".join(whole.split()), m["text"])
            check(f"{tag}: erster Eintrag sichtbar", not parts[0]["hidden"])
            hidden_problems = sum(1 for q in parts if q["kind"] == "problem" and q["hidden"])
            if hidden_problems:
                check(f"{tag}: ruhige Werte zuerst weg", all(q["hidden"] for q in parts if q["kind"] == "fact"))
                check(f"{tag}: „+{hidden_problems} weitere“", m["more"] == f" · +{hidden_problems} weitere", m["more"])
            else:
                check(f"{tag}: kein „weitere“ ohne verborgene Probleme", m["more"] is None, m["more"])
            full = all(not q["hidden"] and q["shown"] == q["long"] for q in parts)
            expect = dict((c[0], c[2]) for c in CASES)[name]
            if expect is not None:
                check(f"{tag}: {'alles in Langform' if expect else 'gekürzt'}", full == expect, m["text"])
        browser.close()

    print()
    if FAILED:
        print(f"{len(FAILED)} Fehler:")
        for name in FAILED:
            print("  -", name)
        sys.exit(1)
    print(f"Alle Prüfungen bestanden ({len(pages)} Seiten).")


if __name__ == "__main__":
    main()
