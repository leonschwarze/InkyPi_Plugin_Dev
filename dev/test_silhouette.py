"""Lebende Stadt und weiße Gipfel im Nachtbild (seit 1.43) – ohne Rendern.

    python dev/test_silhouette.py

Geprüft:
  * ohne live/snow ist das SVG genau das von 1.41 (gleiche Aufrufe → gleicher Text)
  * Fenster: um 22 Uhr alle, danach weniger, 2–4 Uhr gleich wenige, ab 5 Uhr wieder mehr
  * Stunden ohne Änderung ergeben dasselbe SVG (dann zeichnet InkyPi nicht neu) – in einer Novembernacht
    23–5 Uhr genau fünf verschiedene Bilder
  * Stadtbahn nur zu Betriebszeiten, nie auf der Pegellatte (alle Breiten)
  * Morgendämmerung nur in der Stunde vor Sonnenaufgang
  * Dachkatze nur mit live, Katzen-Funktion und verdecktem Mond
  * Gipfel: weiße Kappen nur mit peaks; schnee.peaks (Ölberg ≥ 1 cm) gegen mock_schnee „berg“; mit Schnee in
    Bonn kommen Dachkappen (1.42) und Gipfel zusammen
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tagesdashboard"))
sys.path.insert(0, str(ROOT / "dev"))
import katze  # noqa: E402
import nachtgrafik as ng  # noqa: E402
import schnee  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
FAILS = []
WINDOW = re.compile(r'<rect x="\d+" y="\d+" width="3" height="3" fill="#FFE500"/>')


def check(ok, text):
    print(("  ok      " if ok else "  FEHLER  ") + text)
    if not ok:
        FAILS.append(text)


NIGHT = datetime(2026, 11, 23, 23, 5, tzinfo=TZ)
WX = {"cloud": 20, "wet": False, "snowy": False, "fog": False}


def live_svg(hour_dt, width=756, sunrise=None, **kw):
    return ng.svg(NIGHT, WX, width=width, live={"now": hour_dt, "sunrise": sunrise}, **kw)


def windows(svg):
    return len(WINDOW.findall(svg))


print("Ohne Lebende Stadt und Schnee wie bisher")
base = ng.svg(NIGHT, WX, width=756, cat=katze.on_moon)
check(base == ng.svg(NIGHT, WX, width=756, cat=katze.on_moon, live=None, peaks=False, roof_cat=katze.on_roof),
      "live=None, peaks=False → dasselbe SVG")
total = sum(k for *_, k in ng.WINDOWS)
check(windows(base) == total, f"alle {total} Fenster erleuchtet")

print("Fenster")
night = [NIGHT.replace(hour=22, minute=0) + timedelta(hours=k) for k in range(9)]  # 22 … 6 Uhr
counts = [windows(live_svg(t)) for t in night]
check(counts[0] == total, f"22 Uhr alle an ({counts[0]})")
check(counts[0] >= counts[1] >= counts[2] >= counts[3] >= counts[4], f"bis 2 Uhr gehen Fenster aus {counts[:5]}")
check(counts[4] == counts[5] == counts[6] > 0, f"2–4 Uhr gleich viele Nachteulen {counts[4:7]}")
check(counts[7] > counts[6] and counts[8] > counts[7], f"ab 5 Uhr wieder mehr {counts[6:]}")
lit_at = {t.hour: set(m.start() for m in WINDOW.finditer(live_svg(t))) for t in night}
check(len(lit_at[1]) < len(lit_at[0]) and lit_at[5] != lit_at[1], "Frühaufsteher sind andere Fenster als um 1 Uhr")
check(live_svg(NIGHT.replace(hour=1, minute=0)) == live_svg(NIGHT.replace(hour=1, minute=59)),
      "innerhalb einer Stunde unverändert")

print("Stunden ohne Änderung → gleiches Bild")
hours = [NIGHT.replace(hour=23, minute=0) + timedelta(hours=k) for k in range(7)]  # 23 … 5 Uhr
svgs = [live_svg(t) for t in hours]
check(svgs[3] == svgs[4] == svgs[5], "2, 3 und 4 Uhr gleich (InkyPi zeichnet nicht neu)")
check(len(set(svgs)) == 5, f"Novembernacht 23–5 Uhr: 5 verschiedene Bilder ({len(set(svgs))})")
for h in range(24):
    t = NIGHT.replace(hour=h, minute=0)
    check(ng.next_change(t.replace(minute=40)) == t + timedelta(hours=1), f"nächster Wechsel {h}:40 → volle Stunde") if h in (0, 23) else None

print("Stadtbahn")
check([h for h in range(24) if ng.tram_at(h) is not None and h in (23, 0, 1, 2, 3, 4, 5)] == [0, 5, 23],
      "nachts nur 23, 0 und 5 Uhr")
check("stroke-width=\"1.4\"" in live_svg(NIGHT.replace(hour=23, minute=0)) and
      "stroke-width=\"1.4\"" not in live_svg(NIGHT.replace(hour=2, minute=0)), "23 Uhr Bahn, 2 Uhr keine")
for W in (800, 756, 516, 480, 467):
    s = ng.scale(W)
    bx0, bx1 = 400 * s + 4, W - 300 * s + 30 * s
    latte = bx0 + (bx1 - bx0) * 3 / 8
    ok = all(0 <= p <= 1 for p in ng.TRAM_POS)
    for pos in ng.TRAM_POS_PEGEL:
        x0 = bx0 + (bx1 - bx0 - ng.TRAM_LEN * s) * pos
        x1 = x0 + ng.TRAM_LEN * s
        ok &= not (x0 - 2 < latte + ng.LATTE_W / 2 and x1 + 2 > latte - ng.LATTE_W / 2)
        ok &= bx0 - 0.5 <= x0 and x1 <= bx1 + 0.5
    check(ok, f"Breite {W}: Bahn auf der Brücke, mit Pegel nie an der Latte")

print("Morgendämmerung")
june = datetime(2027, 6, 21, 5, 0, tzinfo=TZ)
sunrise = june.replace(minute=17)
check(ng.dawn(june, sunrise) and not ng.dawn(june.replace(hour=4), sunrise), "21.6.: 5 Uhr ja, 4 Uhr nein (5:17)")
check(not ng.dawn(NIGHT.replace(hour=5, minute=0), NIGHT.replace(day=24, hour=8, minute=0)) and not ng.dawn(june, None),
      "November (Aufgang 8 Uhr) und ohne Sonnenaufgang: keine Dämmerung")
check(ng.BLOOD in live_svg(june, sunrise=sunrise).split("<circle")[0], "roter Streifen vor den Sternen gezeichnet")

print("Dachkatze")
rain = {"cloud": 95, "wet": True, "snowy": False, "fog": False}
roof = ng.svg(NIGHT, rain, width=756, cat=katze.on_moon, roof_cat=katze.on_roof,
              live={"now": NIGHT, "sunrise": None})
check("scale(1.7)" in roof, "Regen, Mond verdeckt → Katze auf dem Dach")
check("scale(1.7)" not in ng.svg(NIGHT, WX, width=756, cat=katze.on_moon, roof_cat=katze.on_roof,
                                 live={"now": NIGHT, "sunrise": None}), "Mond sichtbar → keine Dachkatze")
check("scale(1.7)" not in ng.svg(NIGHT, rain, width=756, cat=katze.on_moon, roof_cat=katze.on_roof),
      "ohne Lebende Stadt → keine Dachkatze")
check("scale(2.6)" in ng.svg(NIGHT, rain, width=467, roof_cat=katze.on_roof, live={"now": NIGHT, "sunrise": None}),
      "hochkant größer (gleich groß auf dem Display)")

print("Weiße Gipfel (Ölberg)")
check("clipPath id=\"snow" in ng.svg(NIGHT, WX, width=756, peaks=True) and "clipPath" not in base, "Kappen nur mit peaks")
both = ng.svg(NIGHT, WX, width=756, peaks=True, snowcaps=True)
check("snowhills" in both and "clipPath id=\"snow756" in both, "mit Schnee in Bonn: Kamm-Saum (1.42) und Gipfel zusammen")

import mock_brightsky  # noqa: E402
import mock_schnee  # noqa: E402
now = datetime(2026, 12, 15, 23, 30, tzinfo=TZ)
end = now.replace(hour=6, minute=0) + timedelta(days=1)


class Sess:
    def __init__(self, kind):
        self.kind = kind

    def get(self, url, params=None, headers=None, timeout=None):
        payload = mock_schnee.payload(now, self.kind, "klar", params)

        class R:
            status_code = 200
            text = ""

            def json(self):
                return payload
        return R()


for kind, peak, caps in (("berg", True, False), ("liegt", True, True), ("normal", False, False),
                         ("umland", False, False)):
    schnee.reset()
    data = schnee.load(50.73, 7.10, TZ, session=Sess(kind))
    check(data is not None and schnee.peaks(data, now, end) == peak and schnee.caps(data, now, end) == caps,
          f"{kind}: Gipfel {'weiß' if peak else 'schwarz'}, Dächer {'weiß' if caps else 'schwarz'}")
check(not schnee.peaks(None, now, end) and not schnee.peaks({}, now, end), "ohne Daten keine Gipfel")
schnee.reset()

print()
print("Alles in Ordnung." if not FAILS else f"{len(FAILS)} Fehler.")
sys.exit(1 if FAILS else 0)
