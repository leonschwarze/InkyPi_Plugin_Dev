"""Tests für urlaub.py (Urlaubsbild: erkennen, Reiseziel, Wetter am Ziel, Tafel) ohne Rendern."""
import re
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "tagesdashboard")
import urlaub  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


TZ = timezone(timedelta(hours=1))


def allday(title, first, last, location=""):
    """Ganztägiger Termin wie aus dem Kalender: Ende ist der Folgetag um 0 Uhr (exklusiv)."""
    return {"title": title, "all_day": True, "location": location,
            "start": datetime(first.year, first.month, first.day, tzinfo=TZ),
            "end": datetime(last.year, last.month, last.day, tzinfo=TZ) + timedelta(days=1)}


heute = date(2026, 11, 10)
words = urlaub.keywords(None)

# ---------------------------------------------------------------- Stichwörter, Mindestdauer
check("Standard-Stichwörter", words == ["urlaub", "ferien", "reise"])
check("Eigene Stichwörter, Leerraum und Großschreibung egal",
      urlaub.keywords(" Dienstreise ,  Kur ") == ["dienstreise", "kur"])
check("read_min_days: Zahl", urlaub.read_min_days("3") == 3)
check("read_min_days: Unsinn -> Standard", urlaub.read_min_days("abc") == urlaub.MIN_DAYS)
check("read_min_days: leer -> Standard", urlaub.read_min_days("") == urlaub.MIN_DAYS)
check("read_min_days: wird begrenzt", urlaub.read_min_days("0") == 1 and urlaub.read_min_days("500") == 60)

# ---------------------------------------------------------------- Reiseziel
check("„Urlaub in Lyon“ -> Lyon", urlaub.destination({"title": "Urlaub in Lyon"}, words) == "Lyon")
check("„Reise nach Wien“ -> Wien", urlaub.destination({"title": "Reise nach Wien"}, words) == "Wien")
check("„Urlaub Lyon“ -> Lyon", urlaub.destination({"title": "Urlaub Lyon"}, words) == "Lyon")
check("Ort des Termins geht vor, nur der erste Teil",
      urlaub.destination({"title": "Urlaub", "location": "Lyon, Frankreich"}, words) == "Lyon")
check("Nur „Urlaub“: kein Ziel", urlaub.destination({"title": "Urlaub"}, words) == "")

# ---------------------------------------------------------------- erkennen
v = urlaub.find([allday("Urlaub in Lyon", heute - timedelta(days=2), heute + timedelta(days=5))], heute, words)
check("Laufender Urlaub erkannt", v is not None and v["dest"] == "Lyon")
check("Resttage: letzter Tag 15.11. -> noch 5", v is not None and v["left"] == 5 and v["left_text"] == "noch 5 Tage")
check("Rückkehr als Wochentag und Datum", v is not None and v["back"] == "Sonntag, 15.11." and v["back_short"] == "SO 15.11.")
check("Ohne Ziel heißt es „Urlaub“",
      urlaub.find([allday("Urlaub", heute, heute + timedelta(days=3))], heute, words)["dest"] == "Urlaub")
check("Letzter Tag: „heute geht’s heim“",
      urlaub.find([allday("Urlaub in Lyon", heute - timedelta(days=4), heute)], heute, words)["left_text"] == "heute geht’s heim")
check("Vorletzter Tag: „morgen geht’s heim“",
      urlaub.find([allday("Urlaub in Lyon", heute - timedelta(days=4), heute + timedelta(days=1))], heute, words)["left_text"]
      == "morgen geht’s heim")
check("Zwei Tage genügen (Standard)",
      urlaub.find([allday("Ferien", heute, heute + timedelta(days=1))], heute, words) is not None)
check("Ein Tag ist kein Urlaub", urlaub.find([allday("Reise", heute, heute)], heute, words) is None)
check("Mindestdauer 3: zwei Tage zu kurz",
      urlaub.find([allday("Ferien", heute, heute + timedelta(days=1))], heute, words, min_days=3) is None)
check("Vorbei", urlaub.find([allday("Urlaub", heute - timedelta(days=9), heute - timedelta(days=1))], heute, words) is None)
check("Beginnt erst morgen",
      urlaub.find([allday("Urlaub", heute + timedelta(days=1), heute + timedelta(days=5))], heute, words) is None)
check("Ohne Stichwort", urlaub.find([allday("Klausurtagung", heute, heute + timedelta(days=3))], heute, words) is None)
timed = {"title": "Urlaub", "all_day": False, "start": datetime(2026, 11, 10, 9, tzinfo=TZ),
         "end": datetime(2026, 11, 12, 9, tzinfo=TZ)}
check("Termin mit Uhrzeit zählt nicht", urlaub.find([timed], heute, words) is None)
check("Stichwort groß/klein egal",
      urlaub.find([allday("URLAUB in Lyon", heute, heute + timedelta(days=3))], heute, words) is not None)


# ---------------------------------------------------------------- Geocoding und Zielwetter (ohne Netz)
class Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class Session:
    def __init__(self, handler):
        self.calls, self.handler = [], handler

    def get(self, url, params=None, timeout=None, **kw):
        self.calls.append((url, params))
        return self.handler(url, params)


urlaub._geo.clear()
s = Session(lambda url, p: Resp({"results": [{"latitude": 45.76, "longitude": 4.84, "country": "Frankreich"}]}))
check("geocode: Koordinaten", urlaub.geocode("Lyon", s) == (45.76, 4.84))
check("geocode: Name wird übergeben", s.calls[0][1]["name"] == "Lyon" and s.calls[0][1]["count"] == 1)
urlaub.geocode("lyon", s)
check("geocode: zweiter Aufruf aus dem Speicher (auch andere Schreibweise)", len(s.calls) == 1)

urlaub._geo.clear()
s = Session(lambda url, p: Resp({"generationtime_ms": 0.2}))
check("geocode: unbekannter Ort -> None", urlaub.geocode("Gibtesnicht", s) is None)
urlaub.geocode("Gibtesnicht", s)
check("geocode: Fehlschlag wird nicht sofort wiederholt", len(s.calls) == 1)
key = "gibtesnicht"
urlaub._geo[key] = (urlaub._geo[key][0] - 2 * 3600, None)
urlaub.geocode("Gibtesnicht", s)
check("geocode: nach einer Stunde wird es erneut versucht", len(s.calls) == 2)

urlaub._geo.clear()
s = Session(lambda url, p: Resp({}, 503))
check("geocode: HTTP-Fehler -> None, kein Absturz", urlaub.geocode("Lyon", s) is None)
check("geocode: leerer Name -> None ohne Abruf", urlaub.geocode("  ", s) is None and len(s.calls) == 1)

urlaub._wx.clear()
now = datetime(2026, 11, 10, 10, 20, tzinfo=TZ)
rows = {"weather": [{"timestamp": "2026-11-10T09:00:00+01:00", "temperature": 14.0},
                    {"timestamp": "2026-11-10T08:00:00+01:00", "temperature": 12.0},
                    {"kaputt": True}]}
s = Session(lambda url, p: Resp(rows))
parse = lambda ts, tz: datetime.fromisoformat(ts)  # noqa: E731
recs = urlaub.fetch_records((45.76, 4.84), TZ, now, parse, s)
check("fetch_records: sortiert, kaputte Zeilen übersprungen", [r["temperature"] for r in recs] == [12.0, 14.0])
check("fetch_records: Koordinaten an Bright Sky", s.calls[0][1]["lat"] == 45.76 and s.calls[0][1]["lon"] == 4.84)
urlaub.fetch_records((45.76, 4.84), TZ, now, parse, s)
check("fetch_records: Zwischenspeicher", len(s.calls) == 1)
urlaub._wx.clear()
s = Session(lambda url, p: Resp({}, 500))
check("fetch_records: Fehler -> leere Liste", urlaub.fetch_records((1.0, 2.0), TZ, now, parse, s) == [])

# ---------------------------------------------------------------- Tafel
wx = lambda tmax, tmin, text: {"icon": '<svg viewBox="0 0 10 10"></svg>', "tmax": tmax, "tmin": tmin,  # noqa: E731
                                "text": text, "prob": 5}
info = v
quer = urlaub.scene(800, 480, info, heute, wx("16", "8", "Heiter"), wx("12", "4", "Regenschauer"))
hoch = urlaub.scene(480, 800, info, heute, wx("16", "8", "Heiter"), wx("12", "4", "Regenschauer"))
check("Tafel quer: ist ein SVG mit viewBox 800x480", quer.startswith("<svg") and 'viewBox="0 0 800 480"' in quer)
check("Tafel hoch: viewBox 480x800", 'viewBox="0 0 480 800"' in hoch)
lesbar = "".join(re.findall(r">([^<]+)</text>", quer))   # je Kärtchen ein Zeichen, Leerzeichen = leeres Kärtchen
check("Tafel zeigt Ziel, Rückkehr und Resttage", "ReisezielLYONZurückSO15.11.Noch5TAGE" in lesbar)
check("Beide Wetterspalten", "Lyon heute" in quer and "Zuhause in Bonn" in quer and "16° / 8°" in quer)
ohne = urlaub.scene(800, 480, info, heute, None, wx("12", "4", "Regenschauer"))
check("Ohne Zielwetter: nur Zuhause, Tafel bleibt", "Lyon heute" not in ohne and "Zuhause in Bonn" in ohne)
check("Ohne Zielwetter: Zuhause rückt nach links (x < 100)", 'x="26' in ohne)
nichts = urlaub.scene(800, 480, info, heute, None, None)
check("Ganz ohne Wetter: Tafel bleibt", nichts.startswith("<svg") and "Zuhause" not in nichts)
lang = dict(info, dest="Sankt Petersburg am Meer")
check("Langer Ortsname sprengt die Tafel nicht (kleinere Kärtchen)",
      urlaub.scene(800, 480, lang, heute, None, None).count("<rect") > 20)

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
