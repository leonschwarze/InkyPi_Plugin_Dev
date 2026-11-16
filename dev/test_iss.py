"""Tests für iss.py (ISS-Überflug im Nachtbild): Astronomie, Überflugsuche, Bahndaten-Abruf, Texte.

Die Bahn ist ERFUNDEN, aber formal gültig (Neigung 51,64°, 15,5 Umläufe pro Tag). Geprüft wird also,
dass die Rechnung in sich stimmt (Sonnenhöhe, Sternzeit, Schatten, Geometrie, Ablauf) – nicht, ob die
Uhrzeiten mit der echten ISS übereinstimmen. Dafür einmal mit Heavens-Above vergleichen (Handbuch).
"""
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "tagesdashboard")
sys.path.insert(0, "dev")
import iss  # noqa: E402
import mock_ziel  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def near(a, b, tol):
    return abs(a - b) <= tol


UTC = timezone.utc
CET = timezone(timedelta(hours=1))
BONN = (50.7374, 7.0982)
LINES = ("1 25544U 98067A   26316.50000000  .00016717  00000-0  10270-3 0  9006",
         "2 25544  51.6400 247.4627 0006703 130.5360 325.0288 15.50000000 1000")


def jd(y, m, d, hh=0, mm=0):
    from lib.sgp4.api import jday
    a, b = jday(y, m, d, hh, mm, 0)
    return a + b


# ---------------------------------------------------------------- Sternzeit, Sonne
check("Sternzeit zum Jahr 2000 (J2000, 12 Uhr UT): 280,46°", near(math.degrees(iss.gmst(2451545.0)), 280.4606, 0.01))
check("Sonnenhöhe Bonn, Wintersonnenwende mittags ≈ 15,8°",
      near(iss.sun_elevation(jd(2026, 12, 21, 11, 30), *BONN), 15.8, 0.6))
check("Sonnenhöhe Bonn, Sommersonnenwende mittags ≈ 62,7°",
      near(iss.sun_elevation(jd(2026, 6, 21, 11, 15), *BONN), 62.7, 0.8))
check("Sonnenhöhe Bonn, Tagundnachtgleiche mittags ≈ 39,3°",
      near(iss.sun_elevation(jd(2026, 3, 20, 11, 25), *BONN), 39.3, 1.0))
check("Mitternacht: Sonne weit unter dem Horizont", iss.sun_elevation(jd(2026, 11, 10, 23, 30), *BONN) < -30)
check("Äquator, Tagundnachtgleiche, Ortsmittag: Sonne fast im Zenit",
      iss.sun_elevation(jd(2026, 3, 20, 12, 0), 0.0, 0.0) > 85)
sv, ra, dec = iss.sun_eci(jd(2026, 12, 21, 12))
check("Sonnenrichtung ist ein Einheitsvektor", near(math.sqrt(sum(c * c for c in sv)), 1.0, 1e-9))
check("Deklination zur Wintersonnenwende ≈ −23,4°", near(math.degrees(dec), -23.4, 0.1))

# ---------------------------------------------------------------- Geometrie
obs = iss.observer_ecef(*BONN)
check("Beobachter liegt auf der Erdoberfläche (6357–6378 km)", 6357 < math.sqrt(sum(c * c for c in obs)) < 6378.2)
phi, lam = (math.radians(x) for x in BONN)
up = (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))
above = tuple(obs[i] + 420 * up[i] for i in range(3))
az, el, rng = iss.look_angles(above, obs, *BONN)
check("Genau darüber: Höhe 90°, Entfernung 420 km", near(el, 90, 0.01) and near(rng, 420, 0.01))
north = (-math.sin(phi) * math.cos(lam), -math.sin(phi) * math.sin(lam), math.cos(phi))
az, el, _ = iss.look_angles(tuple(obs[i] + 100 * north[i] for i in range(3)), obs, *BONN)
check("100 km nach Norden (tangential): Azimut 0°, knapp über dem Horizont", (az < 0.1 or az > 359.9) and -0.01 < el < 1)
east = (-math.sin(lam), math.cos(lam), 0)
az, el, _ = iss.look_angles(tuple(obs[i] + 100 * east[i] for i in range(3)), obs, *BONN)
check("100 km nach Osten: Azimut 90°", near(az, 90, 0.2))

# ---------------------------------------------------------------- Erdschatten
sun = (1.0, 0.0, 0.0)
check("Hinter der Erde (−7000 km): im Schatten", iss.in_shadow((-7000, 0, 0), sun))
check("Hinter der Erde, aber seitlich außerhalb (Abstand 7000 km): Licht", not iss.in_shadow((-7000, 7000, 0), sun))
check("Sonnenseite: Licht", not iss.in_shadow((7000, 0, 0), sun))
check("Seitlich über dem Rand (Abstand 6400 km): Licht", not iss.in_shadow((-100, 6400, 0), sun))
check("Seitlich knapp innerhalb (Abstand 6300 km, hinter der Erde): Schatten", iss.in_shadow((-100, 6300, 0), sun))

# ---------------------------------------------------------------- Helligkeit
# Dämmerung: Sonne knapp unter dem Horizont des Beobachters (Beobachter im Zenit-Punkt (0,0,6380))
dusk = (1 / math.sqrt(1.01), 0.0, -0.1 / math.sqrt(1.01))
obs_pt = (0.0, 0.0, 6380.0)
nah = iss.magnitude(420, (0.0, 0.0, 6800.0), dusk, obs_pt)
check("Überflug im Zenit in der Dämmerung: Größenordnung −2 bis −5 mag", -5.5 < nah < -2.0)
fern = iss.magnitude(1500, (0.0, 0.0, 7880.0), dusk, obs_pt)
check("Weiter weg ist schwächer", fern > nah)
voll = iss.magnitude(1000, (0.0, 0.0, 6800.0), (0.0, 0.0, -1.0), (0.0, 0.0, 5800.0))
check("Sonne genau hinter dem Beobachter (Vollphase, 1000 km): ≈ −3,0 mag", near(voll, -3.04, 0.05))
neu = iss.magnitude(420, (0.0, 0.0, 6800.0), (0.0, 0.0, 1.0), obs_pt)
check("Beleuchtete Seite abgewandt (Neuphase): so schwach, dass worth() sie aussortiert", neu > 2)

# ---------------------------------------------------------------- Bahndaten (TLE)
check("TLE ohne Namenszeile", iss.parse_tle("\n".join(LINES)) == LINES)
check("TLE mit Namenszeile und Leerzeilen", iss.parse_tle("ISS (ZARYA)\n\n" + "\n".join(LINES) + "\n") == LINES)
check("Andere Satelliten werden nicht genommen", iss.parse_tle("1 99999U 98067A   26316.5 x\n2 99999  51.6 x") is None)
check("Unsinn -> None", iss.parse_tle("<html>403 Forbidden</html>") is None and iss.parse_tle("") is None)
check("Epoche: Tag 316,5 des Jahres 2026 = 12.11.2026 12:00 UTC", iss.tle_epoch(LINES[0]) == datetime(2026, 11, 12, 12, tzinfo=UTC))

# ---------------------------------------------------------------- Überflüge (reine Rechnung)
start = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
ps = iss.compute_passes(LINES, start, 30, *BONN)
check("Im Winter gibt es in 30 Stunden mehrere sichtbare Überflüge", len(ps) >= 2)
check("Alle zeitlich geordnet", all(ps[i]["start"] < ps[i + 1]["start"] for i in range(len(ps) - 1)))
check("Alle Überflüge höchstens 8 Minuten sichtbar", all((p["end"] - p["start"]) <= timedelta(minutes=8) for p in ps))
check("start ≤ peak ≤ end", all(p["start"] <= p["peak"] <= p["end"] for p in ps))
check("Höchststand zwischen 10° und 90°", all(10 <= p["peak_el"] <= 90 for p in ps))
check("Azimute 0–360°", all(0 <= p[k] < 360 for p in ps for k in ("start_az", "peak_az", "end_az")))
check("Helligkeit plausibel (−6 bis +3 mag)", all(-6 < p["mag"] < 3 for p in ps))
check("Dunkel genug: Sonne bei Beginn ≤ −6°",
      all(iss.sun_elevation(jd(p["start"].year, p["start"].month, p["start"].day, p["start"].hour, p["start"].minute),
                            *BONN) <= -5.5 for p in ps))
check("Abstand aufeinanderfolgender Überflüge ≥ 80 Minuten (eine Bahn dauert ~93 Minuten)",
      all((ps[i + 1]["start"] - ps[i]["start"]) >= timedelta(minutes=80) for i in range(len(ps) - 1)))
check("Schatten: Ende der Sichtbarkeit = Eintritt in den Schatten",
      all(p["shadow"] == p["end"] for p in ps if p["shadow"]))
check("Weg (Himmelsscheibe) nicht leer", all(len(p["path"]) >= 2 for p in ps))
check("Mittags im Sommer: nichts zu sehen (zu hell)",
      iss.compute_passes(LINES, datetime(2026, 6, 21, 10, 0, tzinfo=UTC), 4, *BONN) == [])
check("Eine Minute weit gerechnet: höchstens ein Überflug", len(iss.compute_passes(LINES, start, 0.02, *BONN)) <= 1)
# gleiche Rechnung, feinerer Schritt: gleiche Anzahl, Startzeiten auf wenige Sekunden gleich
fein = iss.compute_passes(LINES, start, 30, *BONN, step_s=5)
check("Feinerer Zeitschritt: gleiche Überflüge", len(fein) == len(ps))
check("Feinerer Zeitschritt: Startzeiten auf 10 s genau",
      all(abs((a["start"] - b["start"]).total_seconds()) <= 10 for a, b in zip(ps, fein)))
# Bahnhöhe
from lib.sgp4.api import Satrec, WGS72  # noqa: E402
sat = Satrec.twoline2rv(*LINES, WGS72)
e, r, v = sat.sgp4(*(lambda a, b: (a, b))(*__import__("lib.sgp4.api", fromlist=["jday"]).jday(2026, 11, 12, 12, 0, 0)))
check("Bahnhöhe 350–450 km", e == 0 and 350 < math.sqrt(sum(c * c for c in r)) - 6371 < 450)
check("Bahngeschwindigkeit ≈ 7,66 km/s", near(math.sqrt(sum(c * c for c in v)), 7.66, 0.1))

# ---------------------------------------------------------------- Abruf mit Zwischenspeicher
iss.CACHE_FILE = os.path.join(tempfile.mkdtemp(), "tle.txt")
now = datetime(2026, 11, 16, 12, 0, tzinfo=CET)
text = mock_ziel.tle_text(now)


class Resp:
    def __init__(self, text="", code=200):
        self.text, self.status_code = text, code


class Session:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def get(self, url, **kw):
        self.calls += 1
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


def reset():
    iss._tle.update(lines=None, epoch=None, tried=None)
    iss._passes_cache.clear()


reset()
s = Session(Resp(text))
l = iss.get_tle(now, s)
check("Erster Abruf: Bahndaten", l is not None and l[0].startswith("1 25544") and s.calls == 1)
iss.get_tle(now, s)
iss.get_tle(now, s)
check("Weitere Aufrufe innerhalb von 2 Stunden: kein neuer Abruf (Celestrak sperrt sonst)", s.calls == 1)
check("Antwort liegt in der Datei", os.path.exists(iss.CACHE_FILE))
iss._tle["tried"] -= 3 * 3600
iss.get_tle(now, s)
check("Nach 2 Stunden wird neu geladen", s.calls == 2)

reset()
s2 = Session(Resp("", 500))
check("Neustart mit frischer Datei: Bahndaten aus der Datei, kein Abruf",
      iss.get_tle(now, s2) is not None and s2.calls == 0)

reset()
os.utime(iss.CACHE_FILE, (0, 0))  # Datei uralt -> Abruf fällig
s3 = Session(Resp("", 403))
l = iss.get_tle(now, s3)
check("Gesperrt (403): es wird gefragt, alte Bahndaten bleiben nutzbar", s3.calls == 1 and l is not None)
iss.get_tle(now, s3)
check("Nach Fehlschlag nicht sofort wieder fragen", s3.calls == 1)

reset()
os.remove(iss.CACHE_FILE)
s4 = Session(requests_error := ConnectionError("kein Netz"))
check("Kein Netz, keine Datei: None statt Absturz", iss.get_tle(now, s4) is None)
reset()
s5 = Session(Resp("<html>Rate limit</html>"))
check("Antwort ohne Bahndaten: None", iss.get_tle(now, s5) is None)

reset()
iss.get_tle(now, Session(Resp(text)))
check("Bahndaten älter als 7 Tage werden nicht benutzt", iss.get_tle(now + timedelta(days=9), Session(Resp(text))) is None)

# ---------------------------------------------------------------- passes(): Zeitzone, Zwischenspeicher, Fehler
reset()
s = Session(Resp(text))
res = iss.passes(now, *BONN, session=s)
check("passes: Liste mit Zeitzone des Aufrufers", len(res) >= 1 and res[0]["start"].utcoffset() == timedelta(hours=1))
check("passes: beginnt nicht vor dem Aufruf (minus laufender Überflug)", res[0]["end"] >= now - timedelta(minutes=10))
again = iss.passes(now + timedelta(minutes=5), *BONN, session=s)
check("passes: innerhalb von 30 Minuten aus dem Speicher", again is res)
check("passes: ohne Ort -> []", iss.passes(now, None, None, session=s) == [])
reset()
if os.path.exists(iss.CACHE_FILE):
    os.remove(iss.CACHE_FILE)
check("passes: ohne Bahndaten -> []", iss.passes(now, *BONN, session=Session(Resp("", 403))) == [])

# ---------------------------------------------------------------- Texte
def mk(**kw):
    t0 = datetime(2026, 11, 16, 18, 42, tzinfo=CET)
    p = {"start": t0, "peak": t0 + timedelta(minutes=3), "end": t0 + timedelta(minutes=6), "start_az": 248,
         "peak_az": 178, "end_az": 78, "peak_el": 63, "mag": -3.4, "shadow": None, "shadow_az": 78, "path": []}
    p.update(kw)
    return p


check("Richtungen: 0 Nord, 350 Nord, 45 Nordost, 225 Südwest, 270 West",
      [iss.direction(a) for a in (0, 350, 45, 225, 270)] == ["Nord", "Nord", "Nordost", "Südwest", "West"])
check("Richtungen kurz", [iss.direction(a, True) for a in (0, 90, 180, 315)] == ["N", "O", "S", "NW"])
d = iss.describe(mk())
check("Text: Zeit, Route, Höhe, Dauer, Helligkeit",
      d["time"] == "18:42" and d["route"] == "von Westsüdwest".replace("Westsüdwest", "West") + " nach Ost"
      and d["peak"] == "hoch im Süden" and d["mins"] == "6 Min" and d["bright"] == "sehr hell")
check("Text ohne Schatten: kein Schattenhinweis", d["shadow"] == "")
t1 = mk()["start"]
d = iss.describe(mk(shadow=t1 + timedelta(minutes=4, seconds=36), shadow_az=100))
check("Text mit Schatten: Dauer bis zum Schatten und Uhrzeit",
      d["mins"] == "5 Min" and d["shadow"] == "ab 18:46 im Erdschatten" and d["route_short"] == "W → O")
check("Fast senkrecht", iss.describe(mk(peak_el=80))["peak"] == "fast senkrecht über uns")
check("Halbhoch", iss.describe(mk(peak_el=30))["peak"].startswith("halbhoch"))
check("Helligkeitsworte", [iss.brightness(m) for m in (-3.5, -2.5, -1.6)] == ["sehr hell", "hell", "gut sichtbar"])
check("worth: hoch und hell genug", iss.worth(mk()))
check("worth: zu flach", not iss.worth(mk(peak_el=24)))
check("worth: zu schwach", not iss.worth(mk(mag=-1.4)))
check("worth: genau an der Grenze zählt", iss.worth(mk(peak_el=25, mag=-1.5)))
arc = iss.night_arc(800)
check("Bahn im Nachtbild: nur Gelb und Weiß, SVG-Teile", "#FFE500" in arc and "<path" in arc and "<g " in arc
      and all(c not in arc for c in ("#0082C9", "#000")))

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
