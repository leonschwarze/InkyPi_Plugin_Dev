"""Lauf-Fenster (tagesdashboard/laufen.py) und Glätte-Hinweis (tagesdashboard/glaette.py) ohne Rendern (seit 1.37).

  python dev/test_laufen.py

Prüft Glätte: Reif nur in klarer, feuchter Frostnacht, überfrierende Nässe nach Regen, Schnee, keine Glätte bei
+3 °C oder trockener Luft, nur 5–10 Uhr, heute nur ab jetzt, DWD-Warnung „Glätte“ hat Vorrang (andere Warnungen nicht),
Texte („bis etwa 8 Uhr“, „nach 10 Uhr“), Vorrang der Gründe.
Prüft Laufen: nur hell, Regen/Regenrisiko/Böen/Kälte/Hitze sperren, Termine mit 30 min Puffer (ganztägige nicht),
Mindestdauer, beste Spanne (angenehme Temperatur), Glätte bis …, „jetzt bis …“ statt wandernder Beginn, Texte mit
Minuszeichen, Ergebnis mit last_start, Szenario „reif“ aus dev/mock_brightsky.py Ende zu Ende.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import glaette  # noqa: E402
import laufen  # noqa: E402
import mock_brightsky  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
D = date(2026, 11, 24)


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def at(h, m=0, d=D):
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ) + timedelta(hours=h, minutes=m)


def recs(temp=lambda h: 8.0, *overs):
    """Stundenwerte von gestern 0 Uhr bis morgen 23 Uhr; overs: {Stunde relativ zu D 0 Uhr: {Feld: Wert}}."""
    over = {}
    for o in overs:
        for h, v in o.items():
            over.setdefault(h, {}).update(v)
    out = []
    for h in range(-24, 48):
        r = {"dt": at(0) + timedelta(hours=h), "temperature": temp(h), "precipitation": 0, "precipitation_probability": 5,
             "condition": "dry", "icon": "clear-day", "wind_gust_speed": 20, "wind_speed": 8, "sunshine": 30,
             "relative_humidity": 70, "dew_point": temp(h) - 5, "cloud_cover": 50}
        r.update(over.get(h, {}))
        out.append(r)
    return out


SUN = (at(8, 1), at(16, 34))
frost_night = {h: {"relative_humidity": 96, "dew_point": -3, "cloud_cover": 10} for h in range(-4, 9)}
cold = lambda h: -3.0 if h <= 8 else 4.0  # noqa: E731

# ---- Glätte ------------------------------------------------------------
early = at(5, 30)
g = glaette.check(recs(cold, frost_night), early, D)
check("Reif: klare, feuchte Frostnacht", bool(g) and g["reason"] == "Reif")
check("Reif: Text „Glatt bis etwa 8 Uhr“", g and g["text"] == "Glatt bis etwa 8 Uhr" and g["until"] == at(8))
check("Reif braucht Feuchte", glaette.check(recs(cold), early, D) is None)
cloudy_night = {h: {"relative_humidity": 96, "dew_point": -3, "cloud_cover": 95} for h in range(-12, 9)}
check("Reif braucht klaren Himmel", glaette.check(recs(cold, cloudy_night), early, D) is None)
check("bei +3 °C keine Glätte", glaette.check(recs(lambda h: 3.0, frost_night), early, D) is None)
rain_eve = {h: {"precipitation": 1.2, "condition": "rain", "icon": "rain"} for h in (-3, -2)}
g = glaette.check(recs(lambda h: 0.5 if h <= 9 else 4.0, rain_eve), early, D)
check("überfrierende Nässe nach Regen am Abend (+0,5 °C)", bool(g) and g["reason"] == "überfrierende Nässe")
check("… bis 9 Uhr", g and g["until"] == at(9))
old_rain = {h: {"precipitation": 1.2, "condition": "rain"} for h in (-20,)}
check("Regen vor über 12 h zählt nicht", glaette.check(recs(lambda h: 0.5 if h <= 9 else 4.0, old_rain), early, D) is None)
snow = {-10: {"precipitation": 2, "condition": "snow", "icon": "snow"}}
check("Schnee in den letzten 24 h", (glaette.check(recs(cold, snow, frost_night), early, D) or {}).get("reason") == "Schnee")
all_day = glaette.check(recs(lambda h: -2.0, {h: {"relative_humidity": 96, "dew_point": -3, "cloud_cover": 10}
                                              for h in range(-12, 12)}), early, D)
check("Frost bis über 10 Uhr: „Glatt bis nach 10 Uhr“", all_day and all_day["text"] == "Glatt bis nach 10 Uhr")
check("nach 10 Uhr kein Hinweis mehr", glaette.check(recs(cold, frost_night), at(10, 5), D) is None)
check("heute nur ab jetzt (8:30: vorbei)", glaette.check(recs(cold, frost_night), at(8, 30), D) is None)
check("DWD warnt vor Glätte → kein eigener Hinweis",
      glaette.check(recs(cold, frost_night), early, D, alert={"event": "GLÄTTE"}) is None)
check("andere DWD-Warnung (Sturm) → Hinweis bleibt",
      glaette.check(recs(cold, frost_night), early, D, alert={"event": "STURMBÖEN"}) is not None)
check("abends für morgen (Fokustag morgen)",
      glaette.check(recs(lambda h: -3.0 if 24 <= h <= 32 else 4.0,
                         {h: {"relative_humidity": 96, "dew_point": -3, "cloud_cover": 10} for h in range(20, 33)}),
                    at(21), D + timedelta(days=1)) is not None)

# ---- Laufen --------------------------------------------------------------
noon = at(11)
r = laufen.find(recs(), [], at(7), D, SUN)
check("trockener Tag ohne Termine: Fenster gefunden", bool(r))
check("nicht vor Sonnenaufgang (8:01 → ab 8:15)", r and r["start"] == at(8, 15))
check("nicht nach Sonnenuntergang", r and r["end"] <= SUN[1])
rain = {h: {"precipitation": 0.8, "condition": "rain", "icon": "rain"} for h in range(12, 17)}
r = laufen.find(recs(lambda h: 8.0, rain), [], at(7), D, SUN)
check("Regen ab 11 Uhr (Wert um 12 gilt 11–12): Fenster 8:15–11", r and (r["start"], r["end"]) == (at(8, 15), at(11)))
prob = {h: {"precipitation_probability": 60} for h in range(9, 18)}
r = laufen.find(recs(lambda h: 8.0, prob), [], at(7), D, SUN)
check("Regenrisiko 60 % ab 8 Uhr sperrt den ganzen Tag", r is None)
check("Böen ab 50 km/h sperren", laufen.find(recs(lambda h: 8.0, {h: {"wind_gust_speed": 60} for h in range(0, 24)}), [], at(7), D, SUN) is None)
check("−5 °C sperrt", laufen.find(recs(lambda h: -5.0), [], at(7), D, SUN) is None)
check("30 °C sperrt", laufen.find(recs(lambda h: 30.0), [], at(7), D, SUN) is None)
ev = [{"start": at(10), "end": at(15), "all_day": False}]
r = laufen.find(recs(), ev, at(7), D, SUN)
check("Termin 10–15 Uhr: 8:15–9:30 (30 min Puffer)", r and (r["start"], r["end"]) == (at(8, 15), at(9, 30)))
r = laufen.find(recs(), ev, at(7), D, SUN, minutes=90)
check("90 min: morgens (75 min) und nachmittags (64 min) zu kurz → None", r is None)
check("ganztägige Termine stören nicht",
      laufen.find(recs(), [{"start": at(0), "end": at(0) + timedelta(days=1), "all_day": True}], at(7), D, SUN))
warm_afternoon = lambda h: 2.0 if h < 13 else 11.0  # noqa: E731
r = laufen.find(recs(warm_afternoon), [{"start": at(12), "end": at(13), "all_day": False}], at(7), D, SUN)
check("beste Spanne: lieber 11° am Nachmittag als 2° am Morgen", r and r["start"] >= at(13))
r = laufen.find(recs(), [], at(7), D, SUN, icy_until=at(10))
check("glatt bis 10 Uhr: Fenster ab 10", r and r["start"] >= at(10))
r = laufen.find(recs(), [], at(11, 7), D, SUN)
check("läuft schon: „jetzt bis 16:30“ statt wanderndem Beginn", r and r["span"] == "jetzt bis 16:30")
check("Text „Laufen …“", r and r["text"] == "Laufen jetzt bis 16:30")
check("last_start = Ende − Dauer", r and r["last_start"] == r["end"] - timedelta(minutes=60))
r = laufen.find(recs(lambda h: -2.0 if h < 30 else 1.0), [], at(7), D, SUN)
check("Minuszeichen in der Temperatur", r and "−2°" in r["why"])
check("zu kurzer Rest des Tages (16:00): None", laufen.find(recs(), [], at(16), D, SUN) is None)
check("ohne Sonnenzeiten: None", laufen.find(recs(), [], at(7), D, (None, None)) is None)

# ---- Szenario „reif“ Ende zu Ende ---------------------------------------
now = datetime(2026, 11, 24, 7, 10, tzinfo=TZ)
data = mock_brightsky.hourly(now, "reif")["weather"]
rr = [dict(x, dt=datetime.fromisoformat(x["timestamp"])) for x in data]
g = glaette.check(rr, now, now.date())
check("Szenario reif: Glätte durch Reif", g and g["reason"] == "Reif")
r = laufen.find(rr, [], now, now.date(), SUN, icy_until=g["until"] if g else None)
check("Szenario reif: Laufen erst nach der Glätte", r and r["start"] >= g["until"])

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
