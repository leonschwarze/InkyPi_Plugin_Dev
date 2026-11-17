"""Ostereier (seit 1.24) ohne Rendern.

  python dev/test_ostereier.py

Prüft: Ostersonntag und Karnevalstage über viele Jahre, welche Tage welches Osterei bringen (11.11. erst
ab 11:11, Karneval vor Freitag dem 13.), Grüße, Cache-Grenzen, Vorrang bei der Katze (Geburtstag im
Wechsel, vor dem Wetter, an normalen Tagen nie eine Ostereier-Pose), Regenbogen-Regel, Sternbild Katze
(nur bei klarem Himmel, wiederholbar, ungefähre Häufigkeit, liegt im Himmel, weit weg von Mond und
ISS-Bahn) und dass Nachtbild und Template ohne Osterei unverändert bleiben.
"""
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
DEV = REPO / "dev"
inkypi_src = Path(os.environ.get("INKYPI_DIR", REPO.parent / "InkyPi")).resolve() / "src"
sys.path.insert(0, str(DEV))
from render import link_plugins  # noqa: E402

link_plugins(inkypi_src)
sys.path.insert(0, str(inkypi_src))
sys.path.insert(0, str(REPO / "tagesdashboard"))

import katze  # noqa: E402
import nachtgrafik  # noqa: E402
import ostereier as oe  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FEHLER {name}: {got!r} != {want!r}")
    else:
        print(f"  ok      {name}")


def at(y, m, d, hh=15, mm=7):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def egg_name(t):
    e = oe.today(t)
    return e["name"] if e else None


# ---- Ostern und Karneval --------------------------------------------------------------------------
known = {2000: (4, 23), 2008: (3, 23), 2011: (4, 24), 2019: (4, 21), 2024: (3, 31), 2025: (4, 20),
         2026: (4, 5), 2027: (3, 28), 2028: (4, 16), 2038: (4, 25)}
check("Ostersonntag in zehn bekannten Jahren", {y: (oe.easter(y).month, oe.easter(y).day) for y in known}, known)
check("Weiberfastnacht 2026 = 12.2.", oe.karneval(date(2026, 2, 12)), "Weiberfastnacht")
check("Rosenmontag 2026 = 16.2.", oe.karneval(date(2026, 2, 16)), "Rosenmontag")
check("Weiberfastnacht 2027 = 4.2.", oe.karneval(date(2027, 2, 4)), "Weiberfastnacht")
check("Aschermittwoch 2027 ist kein Karneval", oe.karneval(date(2027, 2, 10)), None)
wd = {oe.karneval(oe.easter(y) - timedelta(days=52)) == "Weiberfastnacht" and
      (oe.easter(y) - timedelta(days=52)).weekday() for y in range(1990, 2100)}
check("Weiberfastnacht ist immer ein Donnerstag (1990–2099)", wd, {3})
rm = {(oe.easter(y) - timedelta(days=48)).weekday() for y in range(1990, 2100)}
check("Rosenmontag ist immer ein Montag (1990–2099)", rm, {0})

# ---- Tage --------------------------------------------------------------------------------------------
check("11.11. 11:10: noch nichts", egg_name(at(2026, 11, 11, 11, 10)), None)
check("11.11. 11:11: Sessionsbeginn", egg_name(at(2026, 11, 11, 11, 11)), "sessionsbeginn")
check("11.11. abends: Sessionsbeginn", egg_name(at(2026, 11, 11, 22, 50)), "sessionsbeginn")
check("Gruß 11.11.", oe.today(at(2026, 11, 11, 12, 0))["greeting"], "Bonn Alaaf!")
check("Gruß Weiberfastnacht", oe.today(at(2027, 2, 4))["greeting"], "Beuel Alaaf!")
check("Gruß Rosenmontag", oe.today(at(2027, 2, 8))["greeting"], "Bonn Alaaf!")
check("Karnevalssonntag: Kappe ohne Gruß", (oe.today(at(2027, 2, 7))["pose"], oe.today(at(2027, 2, 7))["greeting"]),
      ("narr", None))
check("Veilchendienstag noch Karneval", egg_name(at(2027, 2, 9)), "karneval")
check("Aschermittwoch nicht mehr", egg_name(at(2027, 2, 10)), None)
check("17.12.: Beethoven", oe.today(at(2026, 12, 17))["pose"], "dirigent")
check("23.5.2026: 77 Jahre Grundgesetz", oe.today(at(2026, 5, 23))["greeting"], "77 Jahre Grundgesetz")
check("14.3.: π-Tag", oe.today(at(2027, 3, 14))["pose"], "himbeerkuchen")
check("31.10.: Halloween", oe.today(at(2027, 10, 31))["pose"], "kürbis")
check("Fr 13.11.2026: schwarze Katze", oe.today(at(2026, 11, 13))["pose"], "schwarz")
check("Sa 13.3.2027 ist kein Freitag", egg_name(at(2027, 3, 13)), None)
check("Fr 13.2.2026 ist Karneval (Rußiger Freitag) – Kappe geht vor", egg_name(at(2026, 2, 13)), "karneval")
check("normaler Tag 10.11.", egg_name(at(2026, 11, 10)), None)
days = [date(2026, 1, 1) + timedelta(days=k) for k in range(366 * 4)]
per_year = sum(1 for d in days if oe.today(at(d.year, d.month, d.day))) / 4
check("etwa 13–16 Ostereier-Tage im Jahr (selten genug)", 12 <= per_year <= 17, True)
check("alle Posen gibt es", all(oe.today(at(d.year, d.month, d.day))["pose"] in katze.POSES
                                for d in days if oe.today(at(d.year, d.month, d.day))), True)

# ---- Cache-Grenzen -----------------------------------------------------------------------------------
b = oe.boundaries(at(2026, 11, 11, 7, 40))
check("Grenze 11.11. 11:11 und Mitternacht", [t.strftime("%d. %H:%M") for t in b[:2]], ["11. 11:11", "12. 00:00"])
check("nach 11:11 keine vergangene Grenze", all(t > at(2026, 11, 11, 12, 0) for t in oe.boundaries(at(2026, 11, 11, 12, 0))), True)
check("am Vortag schon die Grenze 11:11", any(t == at(2026, 11, 11, 11, 11) for t in oe.boundaries(at(2026, 11, 10, 22, 0))), True)

# ---- Katze ----------------------------------------------------------------------------------------------
check("Ostereier-Posen nie im Alltag", set(katze.EVERYDAY) & set(katze.EGG_POSES), set())
check("Ostereier-Posen = alle Posen aus ostereier.today",
      {oe.today(at(d.year, d.month, d.day))["pose"] for d in days if oe.today(at(d.year, d.month, d.day))},
      set(katze.EGG_POSES))
bogen = (DEV / "katze_bogen.py").read_text(encoding="utf-8")
check("Posen-Bogen (README) ohne Ostereier", "name in katze.EGG_POSES and not eggs" in bogen, True)
c = katze.choose(at(2026, 12, 17), egg="dirigent")
check("Osterei wird Hauptpose", (c["main"]["name"], c["reason"]), ("dirigent", "osterei"))
check("hohe Ostereier-Pose sucht zuerst die Kopfzeile", c["spots"][0], "kopf")
rain = [{"dt": at(2026, 12, 17, 15, 0), "precipitation": 2.0, "icon": "rain", "wind_gust_speed": 20,
         "temperature": 8, "sunshine": 0}]
c = katze.choose(at(2026, 12, 17), records=rain, egg="dirigent")
check("Osterei geht dem Wetter vor (kein Schirm)", c["main"]["name"], "dirigent")
names = {katze.choose(at(2026, 12, 17) + timedelta(minutes=15 * k), egg="dirigent",
                      occasions=["geburtstag"])["main"]["name"] for k in range(16)}
check("Geburtstag am Ostereier-Tag: beide im Wechsel", names, {"dirigent", "partyhut"})
seen = set()
for k in range(0, 366 * 96, 7):  # ein Jahr in 15-Minuten-Schritten (jeder 7. Takt), ohne Osterei
    seen.add(katze.choose(at(2026, 1, 1, 0, 0) + timedelta(minutes=15 * k))["main"]["name"])
check("ohne Osterei nie eine Ostereier-Pose", seen & set(katze.EGG_POSES), set())
check("schwarze Katze ist flach (passt auf jede Linie)", katze.is_flat("schwarz"), True)
svg = katze.pose("schwarz")["svg"]
check("schwarze Katze: keine weiße Fläche mehr", 'fill="var(--bg)"' in svg, False)

# ---- Regenbogen -------------------------------------------------------------------------------------------
def rec(hour, sun, mm, icon="rain"):
    return [{"dt": at(2026, 11, 10, hour, 0), "sunshine": sun, "precipitation": mm, "icon": icon, "condition": "rain"}]


check("Sonne und Regen in der Stunde", oe.rainbow(rec(15, 25, 0.4), at(2026, 11, 10, 15, 7)), True)
check("nur Regen", oe.rainbow(rec(15, 0, 0.4), at(2026, 11, 10, 15, 7)), False)
check("nur Sonne", oe.rainbow(rec(15, 40, 0.0), at(2026, 11, 10, 15, 7)), False)
check("zu wenig Sonne (10 min)", oe.rainbow(rec(15, 10, 0.4), at(2026, 11, 10, 15, 7)), False)
check("Schnee: kein Regenbogen", oe.rainbow(rec(15, 25, 0.4, icon="snow"), at(2026, 11, 10, 15, 7)), False)
check("andere Stunde zählt nicht", oe.rainbow(rec(13, 25, 0.4), at(2026, 11, 10, 15, 7)), False)
check("ohne Daten", oe.rainbow([], at(2026, 11, 10, 15, 7)), False)
check("Regenbogen: nur Displayfarben", set(re.findall(r'stroke="(#\w+)"', oe.RAINBOW_SVG)),
      {"#E3001B", "#FFC400", "#2E9E3F", "#0082C9"})

# ---- Sternbild Katze ----------------------------------------------------------------------------------------
clear = {"cloud": 20, "wet": False, "fog": False}
nights = [date(2026, 1, 1) + timedelta(days=k) for k in range(3650)]
share = sum(oe.felis_night(d, clear) for d in nights) / len(nights)
check("in etwa 6 % der klaren Nächte (4–8 %)", 0.04 <= share <= 0.08, True)
some = next(d for d in nights if oe.felis_night(d, clear))
check("wiederholbar (gleiche Nacht, gleiche Antwort)", oe.felis_night(some, clear), True)
check("bewölkt (30 %): nicht", oe.felis_night(some, {"cloud": 30}), False)
check("Regen: nicht", oe.felis_night(some, {"cloud": 10, "wet": True}), False)
check("Nebel: nicht", oe.felis_night(some, {"cloud": 10, "fog": True}), False)
check("ohne Wetter: nicht", oe.felis_night(some, None), False)
check("Bewölkung 0 zählt als klar", oe.felis_night(some, {"cloud": 0}), True)

for W in (800, 480, 756, 467, 516):  # seit 1.31 zeichnet das Dashboard die Szene in der Breite von nachtgrafik.band_width (756, 467, 516)
    s = nachtgrafik.scale(W)
    hills_x = W - 300 * s
    g = nachtgrafik.svg(at(2026, 11, 12, 0, 30), clear, width=W, felis=oe.felis_svg)
    xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)" cy="[\d.]+" r="[\d.]+" fill="#FFE500"/>', g)]
    pts = [(float(x), float(y)) for x, y in re.findall(r'<line x1="([\d.]+)" y1="([\d.]+)"', g)]
    felis_pts = pts[-len(oe.FELIS_LINES):]
    fx = [x for x, _ in felis_pts]
    fy = [y for _, y in felis_pts]
    check(f"{W}: Sternbild im Bild und im Himmel (über y 46)", min(fx) > 0 and max(fx) + 6 < W and min(fy) >= 0
          and max(fy) <= 46, True)
    moon_right = hills_x + 40 + 18 + 2  # höchster Mond-Platz + größter Radius + Ring
    check(f"{W}: rechts vom Mond", min(fx) - 3 > moon_right, True)
    check(f"{W}: rechts vom Ende der ISS-Bahn (0,88 W)", min(fx) - 3 > W * 0.88, True)
    check(f"{W}: ohne felis unverändert (kein Zufall verbraucht)",
          nachtgrafik.svg(at(2026, 11, 12, 0, 30), clear, width=W) ==
          g.replace(oe.felis_svg(nachtgrafik.felis_x(W), 4, nachtgrafik.FELIS_K), ""), True)
    g2 = nachtgrafik.svg(at(2026, 11, 12, 0, 30), clear, width=W, planet="Opposition", felis=oe.felis_svg)
    check(f"{W}: bei einer Opposition kein Sternbild", g2 == nachtgrafik.svg(at(2026, 11, 12, 0, 30), clear, width=W,
                                                                           planet="Opposition"), True)

# ---- Template: ohne Regenbogen unverändert ---------------------------------------------------------------------
tpl = (REPO / "tagesdashboard" / "render" / "tagesdashboard.html").read_text(encoding="utf-8")
check("Template: Regenbogen nur mit params.rainbow",
      '<div class="wx-icon{% if rainbow %} has-rainbow{% endif %}">{% if rainbow %}{{ rainbow | safe }}{% endif %}'
      '{{ weather.icon | safe }}</div>' in tpl, True)
src = (REPO / "tagesdashboard" / "tagesdashboard.py").read_text(encoding="utf-8")
check("Dashboard: Regenbogen nicht im Schwarz-Weiß-Modus", "use_colors and ostereier.rainbow" in src, True)
check("Dashboard: Ostereier-Grenzen im Bild-Cache", "ostereier.boundaries(now)" in src, True)

print()
print("Alles ok." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
