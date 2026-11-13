"""Katze (seit 1.14) ohne Rendern prüfen: Wetterregeln, Abwechslung, Wiederholbarkeit, SVG.

    python dev/test_katze.py

Wo die Katze im Bild landet, entscheidet erst der Browser (placeCat im Template) –
das prüft man mit dev/render.py und Hinsehen.
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tagesdashboard"))
import katze  # noqa: E402
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("INKYPI_DIR", REPO.parent / "InkyPi")) / "src"))  # für BasePlugin
sys.path.insert(0, str(REPO / "dwd_wetter"))
from dwd_wetter import feels_like  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
FAILS = []


def check(ok, what):
    print(("  ok      " if ok else "  FEHLER  ") + what)
    if not ok:
        FAILS.append(what)


def hour(dt, **kw):
    r = {"dt": dt, "temperature": 11, "precipitation": 0, "wind_gust_speed": 30, "wind_speed": 12,
         "relative_humidity": 70, "sunshine": 0, "icon": "cloudy", "condition": "dry"}
    r.update(kw)
    return r


def reason(now, nowcast=None, **kw):
    base = now.replace(minute=0)
    records = [hour(base - timedelta(hours=1)), hour(base, **kw), hour(base + timedelta(hours=1))]
    return katze.weather_reason(records, now, nowcast, feels_like)


def main():
    now = datetime(2026, 11, 10, 15, 7, tzinfo=TZ)
    print("Wetterregeln (C)")
    check(reason(now) is None, "ruhiges Wetter → keine Wetter-Pose")
    check(reason(now, wind_gust_speed=65, precipitation=2) == "sturm", "Sturm geht Regen vor")
    check(reason(now, precipitation=0.4) == "regen", "Regen in der laufenden Stunde → Schirm")
    check(reason(now, icon="snow", condition="snow", temperature=-1) == "schnee", "Schnee → Schal")
    check(reason(now, temperature=1, wind_speed=20) == "frost", "gefühlt unter 0 °C (Windchill) → Schal")
    check(reason(now, temperature=18, sunshine=50) == "sonne", "sonnig und mild → Sonnenbad")
    check(reason(now, temperature=10, sunshine=60) is None, "sonnig, aber kalt → keine Wetter-Pose")
    check(reason(now, nowcast={"state": "jetzt"}) == "regen", "Radar: es regnet gerade → Schirm")
    # Bright Sky: Datensatz 16:00 = Regen von 15–16 Uhr; das Dashboard schreibt dann „Regen 16 Uhr“
    base = datetime(2026, 11, 10, 16, 15, tzinfo=TZ)
    records = [hour(base.replace(minute=0)), hour(base.replace(minute=0) + timedelta(hours=1), precipitation=3)]
    check(katze.weather_reason(records, base, None, feels_like) is None,
          "16:15, Regen erst im Datensatz 17:00 → noch kein Schirm (wie „Regen ab 17 Uhr“)")
    check(katze.weather_reason([], now) is None, "ohne Wetterdaten → keine Wetter-Pose")

    print("Auswahl (B)")
    day = datetime(2026, 11, 10, 6, 0, tzinfo=TZ)
    slots = [katze.choose(day + timedelta(minutes=15 * i)) for i in range(4 * 17)]  # 6–23 Uhr
    names = [c["main"]["name"] for c in slots]
    check(all(a != b for a, b in zip(names, names[1:])), "nie zweimal dieselbe Pose hintereinander")
    check(set(names) == set(katze.EVERYDAY), "über den Tag kommen alle Alltags-Posen vor")
    firsts = [c["spots"][0] for c in slots]
    check(all(a != b for a, b in zip(firsts, firsts[1:])), "der erste Platz wechselt mit jedem Takt")
    check(all(katze.is_flat(c["flat"]["name"]) for c in slots), "Ersatzpose ist immer flach")
    check(katze.choose(now) == katze.choose(now.replace(minute=14)), "gleicher 15-Minuten-Takt → gleiche Katze")
    other = [katze.choose(now.replace(day=11) + timedelta(minutes=15 * i))["main"]["name"] for i in range(8)]
    check(other != names[36:44], "anderer Tag → andere Reihenfolge")
    rainy = [hour(now.replace(minute=0), precipitation=1)]
    c = katze.choose(now, rainy)
    check(c["main"]["name"] == "schirm" and c["spots"][0] == "kopf", "Schirm braucht Höhe → zuerst die Kopfzeile")
    check(katze.choose(now, rainy, weather=False)["main"]["name"] in katze.EVERYDAY,
          "„passt sich dem Wetter an“ aus → nur Alltags-Posen")
    stormy = [hour(now.replace(minute=0), wind_gust_speed=70)]
    c = katze.choose(now, stormy)
    check(c["main"]["name"] == c["flat"]["name"] == "sturm", "Sturm-Pose ist flach und gilt für alle Plätze")

    print("Zeichnungen")
    for name in katze.POSES:
        p = katze.pose(name)
        try:
            ET.fromstring(p["svg"].replace("&", "&amp;"))
            ok = True
        except ET.ParseError as exc:
            ok = False
            print("   ", exc)
        check(ok and p["w"] > 0 and p["h"] > 0, f"{name}: gültiges SVG ({p['w']}×{p['h']})")
        check("#" not in p["svg"], f"{name}: Farben nur über CSS-Variablen (Schwarz-Weiß-Modus)")

    print("Nachtbild (Katze auf dem Mond)")
    sys.path.insert(0, str(REPO / "tagesdashboard"))
    import nachtgrafik
    g = katze.on_moon(400, 30)
    try:
        ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{g}</svg>')
        ok = True
    except ET.ParseError:
        ok = False
    check(ok and "#FFE500" in g, "on_moon: gültiges SVG mit gelbem Z")
    night = datetime(2026, 11, 10, 23, 40, tzinfo=TZ)
    wx = {"cloud": 20}
    with_cat = nachtgrafik.svg(night, wx, cat=katze.on_moon)
    def cat_part(svg_):
        i = svg_.index('stroke-linecap="round"')
        return svg_[svg_.rindex("<g", 0, i):svg_.index("</g>", i)]
    check(cat_part(with_cat) == cat_part(nachtgrafik.svg(night.replace(minute=55), wx, cat=katze.on_moon)),
          "gleiche Nacht → Katze an derselben Stelle (kein Zufall, nightFreeze bleibt wirksam)")
    check(nachtgrafik.svg(night, wx) != with_cat and "stroke-width" in with_cat, "mit Katze anders als ohne")
    check(nachtgrafik.svg(night, {"cloud": 95, "wet": True}, cat=katze.on_moon).count("#FFE500\" fill=\"none\" d=\"M38") == 0,
          "kein Mond (Regen, ganz bedeckt) → keine Katze")
    # Mond mit Katze nie über Münster oder Langem Eugen (sitzt tiefer und würde dahinter verschwinden)
    import re
    bad = []
    for width in (800, 480):
        s_ = min(1.0, (width - 230) / 400)
        for i in range(60):
            svg_ = nachtgrafik.svg(night + timedelta(days=i), wx, width=width, cat=katze.on_moon)
            mx = float(re.search(r'<path d="M([0-9.]+),', svg_).group(1))
            if 60 * s_ < mx < 250 * s_ + 20:
                bad.append((width, i, mx))
    check(not bad, f"Mond mit Katze nie hinter Münster/Langem Eugen (60 Nächte, quer und hochkant){bad[:3]}")

    print()
    print("Alles in Ordnung." if not FAILS else f"{len(FAILS)} Fehler.")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
