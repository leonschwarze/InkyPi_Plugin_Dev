"""Rand des Dashboards und Beschriftungen der Kleidungsempfehlung (seit 1.48).

  python dev/test_rand.py            # rendert mit dev/render.py --html, misst die Seiten mit Playwright
  python dev/test_rand.py --repo ../alt --inkypi ../InkyPi-alt   # Gegenprobe gegen einen alten Stand

Fehlermeldung vom 24.11.: „Bei der Kleidungsempfehlung ist je nach Wortlänge das Wort ganz links am
1. Buchstaben angeschnitten“ (z. B. „bergangsjacke“), dazu der Wunsch „randloser, ein bisschen Rand darf sein“.

Geprüft je Auflösung (800x480, 480x800 hochkant, 600x448, 1600x1200):
  * Rand: Ansichten mit Rahmen (normal, Woche, Monat, Nacht ohne Silhouette) haben rundum 1 × --u statt
    InkyPis 1,5vw + 5 px; ein in InkyPis Stileinstellungen eingetragener Rand gilt als genauer Pixelwert
    (auch 0). Im Nachtbild mit Silhouette ist body randlos und der Text um denselben Wert eingerückt.
  * Kleidung: Jede Beschriftung (alle Texte aus kleidung.py, an erster und letzter Stelle bei 3, 4 und
    5 Teilen) bleibt in ihrer Spalte und im Bild; dazu fünf lange Wörter zugleich ohne Überlappung.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEV = Path(__file__).resolve().parent
ROOT = DEV.parent
SIZES = {"800x480": (800, 480), "480x800v": (480, 800), "600x448": (600, 448), "1600x1200": (1600, 1200)}
# (Name, render.py-Argumente, Wurzel der Ansicht, erwarteter Rand oben/rechts/unten/links in px oder None = 1 u)
CASES = [
    ("normal", [], ".db", None),
    ("woche", ["--time", "2026-11-15 19:00"], ".wk", None),
    ("monat", ["--time", "2026-12-01 07:00"], ".mo", None),
    ("nacht-ohne", ["--time", "2026-11-10 23:40", "--set", "nightArt=false"], ".nt", None),
    ("nacht", ["--time", "2026-11-10 23:40"], ".nt.has-art", None),
    ("rand20", ["--set", "margin=20"], ".db", (20, 20, 20, 20)),
    ("einzeln", ["--set", "margin=20", "--set", "leftMargin=0", "--set", "topMargin=12"], ".db", (12, 20, 20, 0)),
]
FAILED = []

MEASURE = """(sel) => {
  const root = document.querySelector('body > .container > ' + sel);
  if (!root) return null;
  const probe = document.createElement('i');   // --u der Ansicht in px
  probe.style.cssText = 'position:absolute;visibility:hidden;width:calc(var(--u) * 100)';
  root.appendChild(probe); const u = probe.getBoundingClientRect().width / 100; probe.remove();
  const b = getComputedStyle(document.body), n = getComputedStyle(root);
  const px = (cs, k) => ['Top', 'Right', 'Bottom', 'Left'].map(s => parseFloat(cs[k + s]));
  return {u, pad: px(b, 'padding'), margin: px(b, 'margin'), rootPad: px(n, 'padding')};
}"""

# Kleidung: Spalten wie im Template klonen, Text einsetzen, Lage messen
WEAR = """([labels, five]) => {
  const db = document.querySelector('.db'), box = document.querySelector('.wear-items');
  if (!db || !box) return null;
  const D = db.getBoundingClientRect(), tpl = box.children[0], bad = [];
  const fill = texts => { box.innerHTML = '';
    texts.forEach(t => { const c = tpl.cloneNode(true); c.querySelector('span').textContent = t; box.appendChild(c); }); };
  const rects = () => [...box.children].map(c => ({col: c.getBoundingClientRect(),
                                                   txt: c.querySelector('span').getBoundingClientRect()}));
  for (const n of [3, 4, 5]) for (const pos of [0, n - 1]) for (const l of labels) {
    const t = Array(n).fill('Mütze'); t[pos] = l; fill(t);
    const r = rects()[pos];
    const out = Math.max(r.col.left - r.txt.left, r.txt.right - r.col.right, D.left - r.txt.left, r.txt.right - D.right);
    if (out > 0.5) bad.push(`${l} (${pos + 1}. von ${n}): ${out.toFixed(1)} px`);
  }
  fill(five); const r = rects();
  for (let i = 0; i < r.length; i++) {
    if (D.left - r[i].txt.left > 0.5 || r[i].txt.right - D.right > 0.5) bad.push(`fünf lange: ${five[i]} ragt aus dem Bild`);
    if (i && r[i - 1].txt.right - r[i].txt.left > 0.5) bad.push(`fünf lange: ${five[i - 1]} / ${five[i]} überlappen`);
  }
  return bad;
}"""


def check(name, condition, detail=""):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}" + (f" – {detail}" if detail and not condition else ""))
    if not condition:
        FAILED.append(name)


def labels():
    """Alle Beschriftungen aus kleidung.py (Tupel (Rang, Symbol, Text))."""
    src = (ROOT / "tagesdashboard" / "kleidung.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'\(\d, "\w+", "([^"]+)"\)', src)) | {"warme Jacke zum Ausziehen"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inkypi", default=None, help="InkyPi-Ordner (Standard wie render.py)")
    ap.add_argument("--repo", default=str(ROOT), help="Repo, dessen dev/render.py rendert (Gegenprobe: alter Worktree)")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    texts = labels()
    check("Beschriftungen aus kleidung.py gelesen", len(texts) >= 20, str(texts))
    five = ["Übergangsjacke", "Sonnenschutz", "Daunenjacke", "Handschuhe", "Thermo-Unterwäsche"]
    out = Path(tempfile.mkdtemp(prefix="rand-"))
    env = dict(os.environ, FONTCONFIG_FILE=str(DEV / "fonts-eink.conf"))
    pages = []
    for name, extra, sel, want in CASES:
        d = out / name
        cmd = [sys.executable, str(Path(args.repo) / "dev" / "render.py"), "tagesdashboard",
               "--html", "--sizes", ",".join(SIZES), "--out", str(d)] + extra
        if args.inkypi:
            cmd += ["--inkypi", args.inkypi]
        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if res.returncode:
            check(f"{name}: render.py läuft", False, res.stderr[-400:])
            continue
        for label in SIZES:
            found = list(d.glob(f"*_{label}.html"))
            check(f"{name} {label}: Seite gespeichert", len(found) == 1, str(found))
            if found:
                pages.append((name, sel, want, label, found[0]))
    print(f"{len(pages)} Seiten zu prüfen")

    with sync_playwright() as p:
        browser = p.chromium.launch(env=env)
        for name, sel, want, label, path in pages:
            w, h = SIZES[label]
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(path.as_uri())
            page.wait_for_timeout(300)
            tag = f"{name} {label}"
            m = page.evaluate(MEASURE, sel)
            if m is None:
                check(f"{tag}: Ansicht {sel} vorhanden", False)
                page.close()
                continue
            edge = list(want) if want else [m["u"]] * 4
            fmt = lambda v: "/".join(f"{x:.1f}" for x in v)  # noqa: E731
            if "has-art" in sel:  # Nachtbild mit Silhouette: body randlos, Text um den Rand eingerückt
                check(f"{tag}: body randlos", max(m["pad"] + m["margin"]) < 0.5, fmt(m["pad"] + m["margin"]))
                inner = [m["rootPad"][0] - 2.2 * m["u"], m["rootPad"][1] - 2.6 * m["u"], None, m["rootPad"][3] - 2.6 * m["u"]]
                ok = all(abs(a - b) < 0.6 for a, b in zip(inner, edge) if a is not None)
                check(f"{tag}: Text um den Rand eingerückt ({fmt([edge[0], edge[1], edge[3]])})", ok,
                      fmt([x for x in inner if x is not None]))
            else:
                got = [a + b for a, b in zip(m["pad"], m["margin"])]
                ok = all(abs(a - b) < 0.6 for a, b in zip(got, edge))
                check(f"{tag}: Rand {fmt(edge)} px", ok, f"ist {fmt(got)}")
            if sel == ".db" and name == "normal":
                bad = page.evaluate(WEAR, [texts, five])
                check(f"{tag}: Kleidung vorhanden", bad is not None)
                if bad is not None:
                    check(f"{tag}: alle Beschriftungen in ihrer Spalte und im Bild", not bad,
                          "; ".join(bad[:6]) + (f" … ({len(bad)})" if len(bad) > 6 else ""))
            page.close()
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
