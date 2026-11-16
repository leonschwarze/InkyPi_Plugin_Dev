"""Tests für wahlkampf.py (Wahlart, Wahltag, Countdown, Wetter am Termin) ohne Rendern."""
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "tagesdashboard")
import wahlkampf  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def cfg(**values):
    """opt/flag wie im Plugin: fehlende Werte = Standard, Schalter „true“/„false“."""
    base = {"wahlEnabled": "true", "wahlArt": "landtag", "wahlTag": "", "wahlWords": ""}
    base.update(values)
    return (lambda k: base.get(k, "")), (lambda k: base.get(k) == "true")


heute = date(2026, 11, 10)

# ---------------------------------------------------------------- Wahltag
check("Landtagswahl ohne Datum: NRW 25.04.2027", wahlkampf.read_day("") == date(2027, 4, 25))
check("Landtagswahl, Datum None", wahlkampf.read_day(None, "landtag") == date(2027, 4, 25))
check("Bundestagswahl ohne Datum: unbekannt -> None", wahlkampf.read_day("", "bundestag") is None)
check("Europawahl ohne Datum: None", wahlkampf.read_day("", "europa") is None)
check("Kommunalwahl ohne Datum: None", wahlkampf.read_day("  ", "kommunal") is None)
check("Eigenes Datum geht vor", wahlkampf.read_day("2029-06-09", "europa") == date(2029, 6, 9))
check("Eigenes Datum überschreibt auch den NRW-Termin", wahlkampf.read_day("2027-05-09", "landtag") == date(2027, 5, 9))
check("Unsinniges Datum -> None", wahlkampf.read_day("morgen", "landtag") is None)
check("Deutsches Datumsformat wird nicht geraten", wahlkampf.read_day("25.04.2027", "landtag") is None)

# ---------------------------------------------------------------- Einstellungen
c = wahlkampf.read_config(*cfg(), heute)
check("Standard: Landtagswahl NRW", c is not None and c["label"] == "Landtagswahl" and c["day"] == date(2027, 4, 25))
check("Standard-Stichwörter", c is not None and c["words"] == wahlkampf.DEFAULT_WORDS)
check("Ausgeschaltet -> None", wahlkampf.read_config(*cfg(wahlEnabled="false"), heute) is None)
for art, label in (("bundestag", "Bundestagswahl"), ("europa", "Europawahl"), ("kommunal", "Kommunalwahl")):
    c = wahlkampf.read_config(*cfg(wahlArt=art, wahlTag="2029-09-01"), heute)
    check(f"Art {art} -> {label}", c is not None and c["label"] == label)
check("Bundestagswahl ohne Datum: Modus stumm", wahlkampf.read_config(*cfg(wahlArt="bundestag"), heute) is None)
check("Unbekannte Art fällt auf Landtagswahl zurück",
      wahlkampf.read_config(*cfg(wahlArt="gemeinde"), heute)["label"] == "Landtagswahl")
check("Art egal in Groß/Klein", wahlkampf.read_config(*cfg(wahlArt="EUROPA", wahlTag="2029-06-09"), heute)["label"] == "Europawahl")
check("Eigene Stichwörter", wahlkampf.read_config(*cfg(wahlWords="Plakat"), heute)["words"] == "Plakat")
check("Am Wahltag noch aktiv", wahlkampf.read_config(*cfg(wahlTag="2026-11-10"), heute) is not None)
check("Nach dem Wahltag verschwindet der Modus", wahlkampf.read_config(*cfg(wahlTag="2026-11-09"), heute) is None)

# ---------------------------------------------------------------- Countdown
d = wahlkampf.countdown(heute, date(2027, 4, 25))
check("166 Tage bis zum 25.4.2027", d["n"] == 166 and d["text"] == "Landtagswahl in 166 Tagen" and d["badge"] == ("166", "Tage"))
check("Bezeichnung folgt der Wahlart", wahlkampf.countdown(heute, date(2027, 4, 25), "Europawahl")["text"] == "Europawahl in 166 Tagen")
check("Morgen", wahlkampf.countdown(date(2027, 4, 24), date(2027, 4, 25))["text"] == "Morgen ist Landtagswahl")
check("Morgen: Badge", wahlkampf.countdown(date(2027, 4, 24), date(2027, 4, 25))["badge"] == ("Morgen", ""))
check("Heute", wahlkampf.countdown(date(2027, 4, 25), date(2027, 4, 25))["text"] == "Heute ist Landtagswahl")
check("Danach: None", wahlkampf.countdown(date(2027, 4, 26), date(2027, 4, 25)) is None)
check("Kein Wahltag: None", wahlkampf.countdown(heute, None) is None)
check("Übermorgen zählt noch in Tagen", wahlkampf.countdown(date(2027, 4, 23), date(2027, 4, 25))["n"] == 2)

# ---------------------------------------------------------------- Wahlkampftermine
w = wahlkampf.DEFAULT_WORDS
check("Haustürwahlkampf erkannt", wahlkampf.is_campaign("Haustürwahlkampf Beuel", w))
check("Infostand erkannt, Groß/Klein egal", wahlkampf.is_campaign("INFOSTAND Marktplatz", w))
check("Fremder Termin nicht", not wahlkampf.is_campaign("Jour fixe Team", w))
check("Leere Stichwörter erkennen nichts", not wahlkampf.is_campaign("Infostand", " , "))
check("Eigene Stichwörter", wahlkampf.is_campaign("Plakate hängen", "plakat"))

# ---------------------------------------------------------------- Wetter am Termin
TZ = timezone(timedelta(hours=1))
day0 = datetime(2026, 11, 10, 0, 0, tzinfo=TZ)


def records(rain_hours=(), temp=8.0):
    return [{"dt": day0 + timedelta(hours=h), "precipitation": 1.2 if h in rain_hours else 0.0,
             "temperature": temp, "wind_speed": 10, "relative_humidity": 80} for h in range(24)]


feels = lambda t, wind, hum: t - 2 if t is not None else None  # noqa: E731
src = {"start": day0 + timedelta(hours=15), "end": day0 + timedelta(hours=18)}
sunset = day0 + timedelta(hours=16, minutes=51)

r = wahlkampf.weather_at(src, records(), sunset, feels)
check("Trocken", r["rain"] == "trocken" and r["level"] == "ok")
check("Dämmerung nach Terminbeginn", r["dark"] == "dunkel ab 16:51")
check("Gefühlte Temperatur (Minimum)", r["felt"] == "gefühlt 6°")
check("Zeitraum", r["time"] == "15–18 Uhr")
check("Reihenfolge Regen · dunkel · gefühlt", r["short"] == "trocken · dunkel ab 16:51 · gefühlt 6°")

r = wahlkampf.weather_at(src, records(rain_hours=range(15, 20)), sunset, feels)
check("Regen die ganze Zeit", r["rain"] == "Regen" and r["level"] == "achtung")
r = wahlkampf.weather_at(src, records(rain_hours=(17, 18)), sunset, feels)
check("Regen ab 17 Uhr", r["rain"] == "Regen ab 17 Uhr" and r["level"] == "achtung")
r = wahlkampf.weather_at(src, records(rain_hours=(16,)), sunset, feels)
check("Regen nur zu Beginn: „bis“", r["rain"] == "Regen bis 16 Uhr")
r = wahlkampf.weather_at(src, records(), day0 + timedelta(hours=19), feels)
check("Sonnenuntergang nach dem Termin: keine Dämmerungsangabe", r["dark"] is None)
r = wahlkampf.weather_at(src, records(), None, feels)
check("Ohne Sonnenzeiten: keine Dämmerungsangabe", r["dark"] is None)
r = wahlkampf.weather_at({"start": day0 + timedelta(hours=10, minutes=30), "end": day0 + timedelta(hours=13)},
                         records(), sunset, feels)
check("Zeitraum mit halben Stunden", r["time"] == "10:30–13:00")
check("Keine Wetterdaten -> None",
      wahlkampf.weather_at({"start": day0 + timedelta(days=9), "end": day0 + timedelta(days=9, hours=2)},
                           records(), sunset, feels) is None)

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
