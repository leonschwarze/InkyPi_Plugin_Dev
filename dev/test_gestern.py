"""Vergleich mit dem Vortag in der Kleidungsempfehlung („4° kälter als gestern“, seit 1.22) ohne Rendern.

  python dev/test_gestern.py

Prüft: Schwelle (3°) und Rundung, wärmer/kälter, Abdeckung des Vortags (75 %), gleiche Kennzahl wie die
Empfehlung (kältester gefühlter Wert im Fenster), Empfindlichkeit ändert den Unterschied nicht,
abends „als heute“, Zuordnung nach Uhrzeit an beiden Tagen der Zeitumstellung, Begründung in Teilen
(why_head, why_rest) und unveränderte Zeile ohne Vergleich; dazu den Abrufzeitraum bei Bright Sky
(Einzel-Plugin wie bisher 3 h zurück, Dashboard ab gestern 0 Uhr).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
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

import requests  # noqa: E402

import kleidung  # noqa: E402
from plugins.tagesdashboard import tagesdashboard as td  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FEHLER {name}: {got!r} != {want!r}")
    else:
        print(f"ok     {name}")


# ---- reine Funktion ----------------------------------------------------------
v = kleidung.vergleich
check("4 Grad kälter", v([(5, 9), (6, 10), (7, 11)]), -4)
check("3 Grad wärmer", v([(12, 9), (13, 10)]), 3)
check("2 Grad: unter der Schwelle", v([(7, 9), (8, 10)]), None)
check("2,6 Grad gerundet = 3", v([(6.4, 9)]), -3)
check("2,4 Grad gerundet = 2", v([(6.6, 9)]), None)
check("kältester Wert zählt, nicht der Mittelwert", v([(2, 6), (14, 14)]), -4)
check("Vortag zu 75 % da: reicht", v([(5, 9), (5, 9), (5, 9), (5, None)]), -4)
check("Vortag nur zur Hälfte da: kein Vergleich", v([(5, 9), (5, 9), (5, None), (5, None)]), None)
check("leeres Fenster", v([]), None)
check("Text kälter", kleidung.vergleich_text(-4), "4° kälter als gestern")
check("Text wärmer, abends", kleidung.vergleich_text(5, "heute"), "5° wärmer als heute")


# ---- echter Weg durch Tagesdashboard.wear() ----------------------------------
def records(day_temps, start, hours, wind=3, step_utc=False):
    """Stundenwerte ab `start`; day_temps = {Datum: Temperatur} (gilt für alle Stunden dieses Tages).
    step_utc=True: Schritte in UTC wie bei Bright Sky (wichtig an den Tagen der Zeitumstellung)."""
    out = []
    t = start.astimezone(timezone.utc) if step_utc else start
    for _ in range(hours):
        dt = t.astimezone(TZ)
        if dt.date() in day_temps:
            out.append({"dt": dt, "temperature": day_temps[dt.date()], "wind_speed": wind, "relative_humidity": 80,
                        "precipitation": 0, "precipitation_probability": 10, "wind_gust_speed": 20,
                        "sunshine": 0, "icon": "cloudy", "condition": "dry"})
        t += timedelta(hours=1)
    return out


def wear(recs, d, now, sens="empfindlich"):
    return td.Tagesdashboard.wear(None, recs, [], d, now, TZ, sens)


now = datetime(2026, 11, 11, 14, 0, tzinfo=TZ)
gestern, heute = now.date() - timedelta(days=1), now.date()
start = datetime(2026, 11, 10, 0, 0, tzinfo=TZ)
w = wear(records({gestern: 9, heute: 5}, start, 72), heute, now)
check("tagsüber: Vergleich", w["compare"], "4° kälter als gestern")
check("tagsüber: Kopf der Begründung", w["why_head"], "Bis 18:00: gefühlt bis 5°")
check("Zeile ohne Vergleich unverändert", w["why"], "Bis 18:00: gefühlt bis 5°")
check("Empfindlichkeit ändert nichts", wear(records({gestern: 9, heute: 5}, start, 72), heute, now, "sehr")["compare"],
      "4° kälter als gestern")
check("wärmer", wear(records({gestern: 9, heute: 13}, start, 72), heute, now)["compare"], "4° wärmer als gestern")
check("ähnlich: nichts", wear(records({gestern: 7, heute: 5}, start, 72), heute, now)["compare"], None)
check("Vortag fehlt ganz: nichts", wear(records({heute: 5}, start, 72), heute, now)["compare"], None)

# Windchill: gefühlt, nicht Lufttemperatur – gleiche Luft, aber heute stürmisch
calm = records({gestern: 4}, start, 24, wind=3)
storm = records({heute: 4}, start + timedelta(days=1), 24, wind=40)
felt = td.dwd.feels_like(4, 40, 80)  # Windchill: etwa -1,6 °C
check("gefühlte Temperatur (Wind), Luft gleich", wear(calm + storm, heute, now)["compare"],
      f"{round(4 - felt)}° kälter als gestern")

# Mehrere Gründe: Kopf + Rest, damit fitWhy hintere Gründe weglassen kann
rain = records({gestern: 9, heute: 5}, start, 72)
for r in rain:
    if r["dt"].date() == heute:
        r.update(precipitation=1.2, precipitation_probability=90, wind_gust_speed=45, icon="rain", condition="rain")
w = wear(rain, heute, now)
check("Gründe in Teilen", (w["why_head"], w["why_rest"]), ("Bis 18:00: gefühlt bis 5°", ["Regen, zu windig für Schirm"]))
check("ganze Zeile wie bisher", w["why"], "Bis 18:00: gefühlt bis 5° · Regen, zu windig für Schirm")

# Abends (Fokus morgen): morgen gegenüber heute
eve = datetime(2026, 11, 11, 21, 0, tzinfo=TZ)
morgen = eve.date() + timedelta(days=1)
w = wear(records({heute: 10, morgen: 5}, start, 96), morgen, eve)
check("abends: als heute", w["compare"], "5° kälter als heute")

# Zeitumstellung: Zuordnung nach Uhrzeit, nicht „minus 24 h“.
# 25.10.2026: 3 Uhr -> 2 Uhr (2 Uhr doppelt); 29.3.2026: 2 Uhr -> 3 Uhr (2 Uhr fehlt).
# Am Tag danach, Fenster 0–4 Uhr, heute überall 5°, sonst 9°, und genau eine kalte Stunde (1°), die
# nur einer der beiden Wege trifft:
#   Herbst: Vortag 0 Uhr kalt – nach Uhrzeit dabei (4° wärmer), „minus 24 h“ fängt erst um 1 Uhr an.
#   Frühjahr: Vorvortag 23 Uhr kalt – nach Uhrzeit nie dabei (4° kälter), „minus 24 h“ landet dort.
cases = (("Herbst", datetime(2026, 10, 25, tzinfo=TZ), (datetime(2026, 10, 25, 0, tzinfo=TZ)), "4° wärmer als gestern"),
         ("Frühjahr", datetime(2026, 3, 29, tzinfo=TZ), (datetime(2026, 3, 28, 23, tzinfo=TZ)), "4° kälter als gestern"))
for label, d0, cold, want in cases:
    d1 = (d0 + timedelta(days=1)).date()
    first = d0 - timedelta(days=1)
    recs = records({first.date(): 9, d0.date(): 9, d1: 5}, first, 84, step_utc=True)
    for r in recs:
        if r["dt"] == cold:
            r["temperature"] = 1
    w = wear(recs, d1, datetime.combine(d1, datetime.min.time(), TZ))
    check(f"Zeitumstellung {label}: Tag danach nach Uhrzeit", w["compare"], want)
    # Gegenprobe: „minus 24 h“ hätte die kalte Stunde genau andersherum erwischt
    window = [r for r in recs if r["dt"].date() == d1 and r["dt"].hour <= 4]
    by_t = {r["dt"]: r for r in recs}
    shifted = [by_t[(r["dt"].astimezone(timezone.utc) - timedelta(hours=24)).astimezone(TZ)] for r in window]
    check(f"Gegenprobe {label}: minus 24 h trifft die kalte Stunde {'nicht' if 'wärmer' in want else ''}".rstrip(),
          any(x["dt"] == cold for x in shifted), "kälter" in want)
w = wear(records({datetime(2026, 10, 25).date(): 5}, datetime(2026, 10, 25, tzinfo=TZ), 30, step_utc=True),
         datetime(2026, 10, 25).date(), datetime(2026, 10, 25, 0, tzinfo=TZ))
check("Tag der Umstellung ohne Vortag: nichts", w["compare"], None)


# ---- Abrufzeitraum bei Bright Sky --------------------------------------------
sys.path.insert(0, str(REPO / "dwd_wetter"))
import dwd_wetter  # noqa: E402

seen = []


class _R:
    status_code = 200

    def json(self):
        return {}


real = requests.Session.get
requests.Session.get = lambda s, url, params=None, **kw: (seen.append((url, params)), _R())[1]
try:
    t = datetime(2026, 11, 11, 14, 0, tzinfo=TZ)
    plugin = dwd_wetter.DwdWetter({"id": "dwd_wetter"})
    plugin.fetch_data(50.7, 7.1, TZ, t, {"days": 2, "hours": 24})
    check("Einzel-Plugin: ab 3 h vor Mitternacht wie bisher", seen[0][1]["date"], "2026-11-10T21:00+01:00")
    seen.clear()
    plugin.fetch_data(50.7, 7.1, TZ, t, {"days": 2, "hours": 24, "history_hours": 24})
    check("Dashboard: ab gestern 0 Uhr", seen[0][1]["date"], "2026-11-10T00:00+01:00")
finally:
    requests.Session.get = real
src = (REPO / "tagesdashboard" / "tagesdashboard.py").read_text(encoding="utf-8")
check("Dashboard fragt 24 h zurück", '"history_hours": 24' in src, True)

print()
print("Alles ok." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
