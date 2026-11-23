"""Schnee-Radar (seit 1.42) ohne Rendern prüfen.

  python dev/test_schnee.py

Daten: dev/mock_brightsky.py (Szenario „winter“: heute 17–23 Uhr Schnee, Tag 3 10–18 Uhr) und
dev/mock_schnee.py (Open-Meteo, aus denselben Stundenwerten gebaut).
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "dev"), str(REPO / "tagesdashboard")]
import mock_brightsky  # noqa: E402
import mock_schnee  # noqa: E402
import nachtgrafik  # noqa: E402
import schnee  # noqa: E402
import status  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
failed = 0


def check(name, got, want):
    global failed
    ok = got == want
    failed += not ok
    print(f"  {'ok    ' if ok else 'FEHLER'}  {name}: {got!r}" + ("" if ok else f" (erwartet {want!r})"))


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def setup(now, scenario="winter", kind="normal"):
    mock_brightsky.install(now, scenario)
    mock_schnee.install(now, kind, scenario)
    schnee.reset()
    recs = [dict(r, dt=datetime.fromisoformat(r["timestamp"])) for r in mock_brightsky.hourly(now, scenario)["weather"]]
    status.begin()
    return recs, schnee.load(50.7374, 7.0982, TZ)


print("Spanne der Zentimeter (Open-Meteo-Wert bis Wert / 0,7)")
check("0,2 cm → nichts", schnee.range_text(0.2), None)
check("0,6 cm → < 1 cm", schnee.range_text(0.6), "< 1 cm")
check("0,8 cm → 1 cm", schnee.range_text(0.8), "1 cm")
check("2 cm → 2–3 cm", schnee.range_text(2.0), "2–3 cm")
check("4,8 cm → 5–7 cm", schnee.range_text(4.8), "5–7 cm")
check("ohne Daten", schnee.range_text(None), None)

print("Schneestunden nach Bright Sky")
check("Schnee mit Niederschlag", schnee.is_snow({"precipitation": 0.4, "condition": "snow"}), True)
check("Schneeregen-Symbol zählt", schnee.is_snow({"precipitation": 0.4, "condition": "rain", "icon": "sleet"}), True)
check("trocken trotz Schneesymbol", schnee.is_snow({"precipitation": 0.0, "icon": "snow"}), False)
check("Regen", schnee.is_snow({"precipitation": 2.0, "condition": "rain", "icon": "rain"}), False)

print("Karte (A)")
now = at("2026-11-10 15:07")
recs, data = setup(now)
c = schnee.card(recs, data, now)
check("Kopf: Uhrzeiten wie die Tageskurve (Zeitstempel)", c["top"], "Schnee 17–23 Uhr")
check("Menge als Spanne", c["badge"], "5–7 cm")
check("bleibt liegen, bis ins Tal", c["sub"], "bleibt liegen · bis ins Rheintal")
check("Flockenband mit Balken", c["strip"] is not None and c["strip"]["svg"].count("sn-bar"), 7)
check("Cache-Grenzen: Beginn − 1 h und Ende", schnee.boundaries(c, now), [at("2026-11-10 16:00"), at("2026-11-10 23:00")])
check("Status: Schnee ok", [e for e in status._events if e[0] == "Schnee"][-1][1], "ok")

now = at("2026-11-10 16:20")
recs, data = setup(now)
check("es schneit schon: „bis etwa“", schnee.card(recs, data, now)["top"], "Schnee bis etwa 23 Uhr")
now = at("2026-11-10 21:30")
recs, data = setup(now)
c = schnee.card(recs, data, now)
check("spät: nur noch, was ab jetzt fällt", (c["top"], c["badge"]), ("Schnee bis etwa 23 Uhr", "< 1 cm"))

now = at("2026-11-12 18:30")  # heute 17–23 Uhr Schnee (Testtage zählen ab „jetzt“), dazu morgen 10–18 Uhr
recs, data = setup(now)
both = [dict(r, precipitation=0.6, condition="snow") if at("2026-11-13 10:00") <= r["dt"] <= at("2026-11-13 18:00")
        else r for r in recs]
check("erst der laufende Schneefall", schnee.card(both, data, now)["top"], "Schnee bis etwa 23 Uhr")
recs2 = [r if r["dt"].date() != now.date() else dict(r, precipitation=0, condition="dry") for r in both]
check("morgen", schnee.card(recs2, data, now)["top"], "Schnee morgen 10–18 Uhr")
now = at("2026-11-11 23:00")
recs, data = setup(now)
nightly = [dict(r, precipitation=0.6, condition="snow", icon="snow") if at("2026-11-12 03:00") <= r["dt"] <= at("2026-11-12 08:00")
           else dict(r, precipitation=0, condition="dry") for r in recs]
check("nach 18 Uhr: „heute Nacht“", schnee.card(nightly, data, now)["top"], "Schnee heute Nacht 3–8 Uhr")
now = at("2026-11-10 09:00")
far = [dict(r, precipitation=0.6, condition="snow") if at("2026-11-11 20:00") <= r["dt"] <= at("2026-11-12 02:00")
       else dict(r, precipitation=0, condition="dry") for r in recs]
check("morgen Abend über Mitternacht", schnee.card(far, None, now)["top"], "Schnee morgen 20–2 Uhr")
far2 = [dict(r, precipitation=0.6, condition="snow") if at("2026-11-12 04:00") <= r["dt"] <= at("2026-11-12 06:00")
        else dict(r, precipitation=0, condition="dry") for r in recs]
check("in zwei Tagen: Wochentag", schnee.card(far2, None, now)["top"], "Schnee Do 4–6 Uhr")
check("ohne Open-Meteo: Temperatur statt Menge", (schnee.card(far2, None, now)["badge"],
                                                    schnee.card(far2, None, now)["sub"].startswith("bei ")), (None, True))
endless = [dict(r, precipitation=0.6, condition="snow") for r in recs]
check("bis zum Ende der 48 h: „hält an“", schnee.card(endless, None, at("2026-11-10 12:00"))["top"], "Schnee hält an")

now = at("2026-11-10 15:07")
recs, data = setup(now, kind="schneeregen")
c = schnee.card(recs, data, now)
check("Schneefallgrenze über Bonn: Schneeregen, Höhe im Abzeichen", (c["sub"], c["badge"]),
      ("in Bonn eher Schneeregen", "ab 350 m"))
recs, data = setup(now, kind="taut")
check("taut weg", schnee.card(recs, data, now)["sub"], "taut wohl gleich weg · bis ins Rheintal")
recs, data = setup(now, scenario="herbst")
check("Herbst: keine Karte, keine Abfrage nötig", (schnee.card(recs, data, now), schnee.snow_soon(recs, now)), (None, False))

print("Ausfall von Open-Meteo")
recs, data = setup(now, kind="down")
check("down → None", data, None)
check("Status: Schnee fail", [e for e in status._events if e[0] == "Schnee"][-1][1], "fail")
check("Karte trotzdem (ohne Menge)", schnee.card(recs, data, now)["top"], "Schnee 17–23 Uhr")
status.begin()
check("Zwischenspeicher hält auch den Fehlschlag", schnee.load(50.7374, 7.0982, TZ), None)
check("… und meldet nur use", [e[1] for e in status._events if e[0] == "Schnee"], ["use"])

print("Antwort einzeln (ein Ort) und mit falscher Zahl")
one = {"elevation": 60, "hourly": {"time": [1763000000], "snowfall": [0.7], "snow_depth": [0.02],
                                   "snowfall_height": [100], "temperature_2m": [-1], "precipitation": [1.0]}}
p = schnee.parse(one, ["Bonn"], TZ)
check("einzelner Ort als dict", (p["Bonn"]["hours"][0]["snow"], p["Bonn"]["hours"][0]["depth"]), (0.7, 2.0))
try:
    schnee.parse([one], ["A", "B"], TZ)
    check("falsche Zahl Orte → Fehler", False, True)
except RuntimeError:
    check("falsche Zahl Orte → Fehler", True, True)

print("Wochenvorschau (C, D)")
now = at("2026-11-15 18:30")
recs, data = setup(now, kind="umland", scenario="herbst")
check("Umland-Zeile", schnee.umland(data, now)["text"], "Winterberg 18 cm · Hohe Acht 4 cm · Ölberg – · Bonn –")
recs, data = setup(now, kind="normal", scenario="herbst")
check("nirgends Schnee → keine Zeile", schnee.umland(data, now), None)
recs, data = setup(now, kind="umland", scenario="winter")
u = schnee.umland(data, now)
check("Neuschnee in Klammern", all("(+" in p["text"] for p in u["parts"]), True)
days = [date(2026, 11, 16) + timedelta(days=i) for i in range(7)]
check("Schneetage: Mi (Tag 3)", schnee.snow_days(recs, days), {date(2026, 11, 18): "snow"})
mixed = [dict(r, condition="rain", icon="rain") if r["dt"].hour % 2 and r["dt"].date() == date(2026, 11, 18) else r
         for r in recs]
check("halb Regen, halb Schnee → snow", schnee.snow_days(mixed, days), {date(2026, 11, 18): "snow"})
mixed2 = [dict(r, condition="rain", icon="rain") if r["dt"].hour % 3 and r["dt"].date() == date(2026, 11, 18) else r
          for r in recs]
check("überwiegend Regen → mixed", schnee.snow_days(mixed2, days), {date(2026, 11, 18): "mixed"})

print("Weiße Weihnachten")
now = at("2026-12-20 18:30")
recs, data = setup(now, kind="weihnachten", scenario="herbst")
check("möglich", schnee.christmas(data, now.date(), now), "Weiße Weihnachten in Bonn: möglich · Modell 3 cm am 24.12.")
recs, data = setup(now, kind="normal", scenario="herbst")
check("eher nicht", schnee.christmas(data, now.date(), now), "Weiße Weihnachten in Bonn: eher nicht")
check("vor dem 15.12. nichts", schnee.christmas(data, date(2026, 12, 13), now), None)
check("nach Heiligabend nichts", schnee.christmas(data, date(2026, 12, 27), now), None)
now = at("2026-12-15 18:30")
recs, data = setup(now, kind="normal", scenario="herbst")
check("zu weit weg", schnee.christmas(data, now.date(), now), "Weiße Weihnachten? Noch zu weit für die Vorhersage")

print("Nachtbild (D)")
now = at("2026-11-10 23:40")
recs, data = setup(now, kind="liegt")
check("Schneekappen, wenn Schnee liegt", schnee.caps(data, now, now + timedelta(hours=7)), True)
recs, data = setup(now, kind="normal", scenario="herbst")
check("keine Kappen ohne Schnee", schnee.caps(data, now, now + timedelta(hours=7)), False)
check("Herbst ist zu warm für eine Abfrage", schnee.was_cold(recs, now), False)
check("Schneesaison Oktober bis April", [schnee.in_season(date(2026, m, 1)) for m in (5, 9, 10, 4)],
      [False, False, True, True])
caps = [c for p in nachtgrafik.CITY for c in schnee.roof_caps(p)]
check("Dächer mit Schnee (Spitzen und Türme ohne)", len(caps), 23)
check("kein Streifen über der Grundlinie", all(float(c.split()[0][1:].split(",")[1]) < 104 for c in caps), True)
spire = schnee.roof_caps("M0,104 L0,50 L10,10 L20,50 L20,104 Z")
check("steile Spitze bekommt keinen Schnee", spire, [])
check("flaches Dach: ein Streifen", len(schnee.roof_caps("M0,104 L0,80 L30,80 L30,104 Z")), 1)
svg_off = nachtgrafik.svg(now, {"cloud": 10}, width=800)
svg_on = nachtgrafik.svg(now, {"cloud": 10}, width=800, snowcaps=True)
check("ohne Kappen unverändert (kein weißer Saum)", "snowhills" in svg_off, False)
check("mit Kappen: Saum am Siebengebirge", "snowhills" in svg_on, True)
check("Sterne und Mond liegen gleich", svg_on.startswith(svg_off.split('<g transform="translate(0,104)')[0]), True)

print()
print("Alles in Ordnung." if not failed else f"{failed} Fehler.")
sys.exit(1 if failed else 0)
