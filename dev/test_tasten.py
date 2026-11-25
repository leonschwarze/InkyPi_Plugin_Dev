"""Tasten-Dienst ohne Hardware und ohne InkyPi testen.

  python dev/test_tasten.py

Geprüft wird (alles gegen Attrappen: Schein-InkyPi per `post`, Schein-LED, feste Uhr, device.json im Temp-Ordner):
  * Nachtfenster wie das Dashboard (Standard, cfgVersion, über Mitternacht, from == to, Punkt statt Doppelpunkt)
  * Aktive Instanz wie ausschaltbild.active_instance (kürzeste aktive Playlist, current_plugin_index)
  * Taste A: Zähler +1, Hilfsbild geschlossen, POST an InkyPi mit der richtigen Instanz, LED an/aus
  * Taste D: Hilfsbild auf (Zustandsdatei), zweiter Druck schließt, Ablauf stößt einmal frisch an
  * Nachts, ohne Playlist, ohne Dashboard, B/C, InkyPi lehnt ab / nicht erreichbar: nichts kaputt, LED aus
  * Zustandsdatei atomar und lesbar fürs Dashboard (hilfsbild.load), Konstanten stimmen mit hilfsbild.py überein
  * gpiod-Attrappe: drain() verwirft Ereignisse, run() zählt nur fallende Flanken und verwirft Drücke im Auftrag
"""
import json
import os
import sys
import tempfile
import types
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tasten"))
sys.path.insert(0, str(ROOT / "ausschaltbild"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))
import tasten  # noqa: E402
import ausschaltbild as aus  # noqa: E402
import hilfsbild  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
TMP = Path(tempfile.mkdtemp(prefix="tasten-"))
fails = 0


def check(cond, msg):
    global fails
    print(("ok    " if cond else "FEHLER") + " " + msg)
    if not cond:
        fails += 1


def at(h, m=0):
    return datetime(2026, 11, 17, h, m, tzinfo=TZ)


def device(playlists):
    return {"timezone": "Europe/Berlin", "playlist_config": {"playlists": playlists}}


def pl(name, start, end, plugins, idx=0):
    return {"name": name, "start_time": start, "end_time": end, "current_plugin_index": idx,
            "plugins": [{"plugin_id": pid, "name": n, "plugin_settings": s} for pid, n, s in plugins]}


DASH = ("tagesdashboard", "Tag", {})
WETTER = ("weather", "Wetter", {})
# Zuletzt von Hand gesehen: Tagesdashboard mit cfgVersion 5+ und eingeschaltetem Nachtbild
DASH_NACHT = ("tagesdashboard", "Tag", {"cfgVersion": "7", "nightEnabled": "true"})


class Welt:
    """Eine Attrappen-Welt: device.json, Zustandsdatei, Schein-InkyPi, LED-Protokoll, feste Uhr."""

    def __init__(self, playlists, now, name="w"):
        self.dir = TMP / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.device = self.dir / "device.json"
        self.device.write_text(json.dumps(device(playlists)))
        self.state = self.dir / "tasten_zustand.json"
        self.posts, self.led_log, self.fail = [], [], None
        self.t = 1_000_000.0
        self.now = now
        self.dienst = tasten.Dienst(self.device, self.state, "http://x", led=self.led_log.append,
                                    clock=lambda: self.t, post=self.post, now=lambda: self.now)

    def post(self, url, data, timeout):
        # Die LED muss im Moment des Aufrufs an sein
        self.posts.append((url, json.loads(data), timeout, bool(self.led_log and self.led_log[-1])))
        if self.fail == "http":
            raise urllib.error.HTTPError(url, 400, "Bad", {}, __import__("io").BytesIO(b"nope"))
        if self.fail == "net":
            raise ConnectionRefusedError("aus")
        return 200, "ok"

    def zustand(self):
        return tasten.read_state(self.state)


# ---------------------------------------------------------------- Nachtfenster
def night(settings, h, m=0):
    return tasten.is_night(settings, at(h, m))


check(night({}, 23, 30) and night({}, 3) and not night({}, 6) and not night({}, 12), "Standard 23:00–6:00, 6:00 ist schon Tag")
check(not night({"cfgVersion": "7"}, 3), "cfgVersion ≥ 5 ohne nightEnabled = aus")
check(night({"cfgVersion": "4"}, 3), "cfgVersion < 5: Standard (an) gilt")
check(not night({"nightEnabled": "false"}, 3), "nightEnabled=false → kein Nachtbild")
check(night({"nightFrom": "22.30", "nightTo": "5.45", "nightEnabled": "true"}, 22, 45), "Punkt statt Doppelpunkt, über Mitternacht")
check(not night({"nightFrom": "22:00", "nightTo": "22:00"}, 23), "from == to → kein Nachtfenster")
check(night({"nightFrom": "01:00", "nightTo": "05:00"}, 2) and not night({"nightFrom": "01:00", "nightTo": "05:00"}, 5),
      "Fenster ohne Mitternacht: Ende ausgeschlossen")
check(not night({"nightFrom": "xx", "nightTo": "06:00"}, 3), "Unsinn in der Uhrzeit → kein Nachtfenster")

# ---------------------------------------------------------------- aktive Instanz wie Ausschaltbild
lists = [pl("Tag", "00:00", "24:00", [WETTER, DASH], idx=1),
         pl("Abend", "18:00", "22:00", [DASH, WETTER], idx=0),
         pl("Nacht", "22:00", "06:00", [WETTER], idx=5)]
dev = device(lists)
for h in (3, 7, 12, 19, 21, 22, 23):
    mine = tasten.active_instance(dev, at(h))
    theirs = aus.active_instance(dev, at(h))
    check((mine[:3] if mine else None) == (theirs if theirs else None), f"{h}:00 gleiche Instanz wie Ausschaltbild: {mine and mine[2]}")
check(tasten.active_instance(device([pl("Leer", "00:00", "24:00", [])]), at(12)) is None, "aktive Playlist ohne Plugins → nichts")

# ---------------------------------------------------------------- Taste A
w = Welt([pl("Tag", "00:00", "24:00", [WETTER, DASH], idx=1)], at(10), "a")
check(w.dienst.press("A") == "neu", "A: Ergebnis „neu“")
url, body, timeout, led_an = w.posts[0]
check(url == "http://x/display_plugin_instance", "A: POST an /display_plugin_instance")
check(body == {"playlist_name": "Tag", "plugin_id": "tagesdashboard", "plugin_instance": "Tag"},
      "A: gezeigte Instanz (current_plugin_index) wird angestoßen")
check(timeout == tasten.REQUEST_TIMEOUT, "A: Timeout wie für die lange Antwort von InkyPi")
check(led_an and w.led_log == [True, False], "A: LED an während des POST, danach aus")
check(w.zustand().get("neu") == 1 and w.zustand().get("v") == 1, "A: Zähler 1, Version 1")
w.dienst.press("A")
check(w.zustand().get("neu") == 2, "A: zweiter Druck → Zähler 2")
check(not (w.state.parent / (w.state.name + ".tmp")).exists() and [p.name for p in w.dir.iterdir() if p.name.startswith(w.state.name + ".")] == [],
      "Zustandsdatei: keine Zwischendateien übrig (atomar)")
check(hilfsbild.load(str(w.state)).get("neu") == 2, "Zustandsdatei: das Dashboard (hilfsbild.load) liest sie")
check(oct(w.state.stat().st_mode & 0o777) == "0o644", "Zustandsdatei: 0644 (InkyPi läuft als anderer Benutzer)")

# A ohne Dashboard, nur Wetter
w = Welt([pl("Tag", "00:00", "24:00", [WETTER])], at(10), "a2")
check(w.dienst.press("A") == "neu" and w.posts[0][1]["plugin_id"] == "weather", "A: ohne Dashboard zeichnet die gezeigte Instanz neu")
check(w.zustand().get("neu") == 1, "A: Zähler wird auch ohne Dashboard erhöht (harmlos)")
w = Welt([pl("Leer", "00:00", "24:00", [])], at(10), "a3")
check(w.dienst.press("A") == "keine-playlist" and not w.posts, "A: keine aktive Instanz → kein POST")

# ---------------------------------------------------------------- Taste D
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "d")
check(w.dienst.press("D") == "hilfe-auf", "D: Hilfsbild auf")
check(w.zustand().get("hilfe_bis") == w.t + tasten.HILFE_SEKUNDEN, f"D: hilfe_bis = jetzt + {tasten.HILFE_SEKUNDEN} s")
check(len(w.posts) == 1 and w.led_log == [True, False], "D: ein POST, LED an/aus")
check(hilfsbild.check(str(w.state), datetime.fromtimestamp(w.t + 5, TZ))[0], "D: das Dashboard sieht das Hilfsbild (check → an)")
w.t += 30
check(w.dienst.press("D") == "hilfe-zu", "D zum zweiten Mal: schließt")
check(w.zustand().get("hilfe_bis") == 0 and w.zustand().get("neu") == 1, "D schließt: hilfe_bis 0, Zähler +1 (frisch zeichnen)")
check(w.dienst.help_end is None and w.dienst.due() is None and w.dienst.next_deadline() is None, "nach dem Schließen nichts mehr fällig")

# Ablauf
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "d2")
w.dienst.press("D")
n = len(w.posts)
w.t += tasten.HILFE_SEKUNDEN - 1
check(w.dienst.due() is None and 0 < w.dienst.next_deadline() <= 1.0 + 1e-6, "vor dem Ablauf: nichts fällig, Frist läuft")
w.t += 2
check(w.dienst.due() == "hilfe-ende" and len(w.posts) == n + 1, "Ablauf: einmal frisch angestoßen")
check(w.zustand().get("hilfe_bis") == 0 and w.zustand().get("neu") == 1, "Ablauf: hilfe_bis 0, Zähler +1")
check(w.dienst.due() is None, "Ablauf passiert nur einmal")

# A schließt das Hilfsbild ebenfalls
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "d3")
w.dienst.press("D")
w.dienst.press("A")
check(w.zustand().get("hilfe_bis") == 0 and w.dienst.help_end is None, "A schließt ein offenes Hilfsbild")

# Neustart des Dienstes mitten im Hilfsbild
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "d4")
w.dienst.press("D")
neu = tasten.Dienst(w.device, w.state, "http://x", clock=lambda: w.t + 10, post=w.post, now=lambda: w.now)
check(neu.help_end == w.zustand()["hilfe_bis"], "Neustart des Dienstes: Ende des Hilfsbilds bleibt bekannt")
alt = tasten.Dienst(w.device, w.state, "http://x", clock=lambda: w.t + 10_000, post=w.post, now=lambda: w.now)
check(alt.help_end is None, "Neustart nach dem Ende: nichts mehr offen")

# D ohne Dashboard / Dashboard nur in anderer Playlist
w = Welt([pl("Tag", "00:00", "24:00", [WETTER])], at(10), "d5")
check(w.dienst.press("D") == "kein-dashboard" and not w.posts and not w.state.exists(), "D ohne Dashboard: nichts getan, nichts geschrieben")
w = Welt([pl("Tag", "00:00", "18:00", [WETTER]), pl("Abend", "18:00", "24:00", [DASH])], at(10), "d6")
check(w.dienst.press("D") == "kein-dashboard" and not w.posts, "D: Dashboard nur in inaktiver Playlist → nichts")

# ---------------------------------------------------------------- Nachts nichts
w = Welt([pl("Tag", "00:00", "24:00", [DASH_NACHT])], at(2), "n")
for letter in "ABCD":
    check(w.dienst.press(letter) in ("nacht", "frei"), f"Nacht, Taste {letter}: keine Funktion")
check(not w.posts and not w.state.exists() and w.led_log == [], "Nacht: kein POST, keine Zustandsdatei, LED bleibt aus")
w.now = at(6, 0)
check(w.dienst.press("A") == "neu", "um 6:00 ist es Tag: A geht wieder")
w = Welt([pl("Tag", "00:00", "24:00", [WETTER])], at(2), "n2")
check(w.dienst.press("A") == "neu", "Nacht, aber ohne Dashboard (kein Nachtbild): A geht (Fehler bis zur Prüfung vermieden)")

# ---------------------------------------------------------------- B und C
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "bc")
check(w.dienst.press("B") == "frei" and w.dienst.press("C") == "frei" and not w.posts and not w.state.exists(), "B und C: nicht belegt, nichts passiert")

# ---------------------------------------------------------------- Fehler
for how, label in (("http", "InkyPi lehnt ab (400)"), ("net", "InkyPi nicht erreichbar")):
    w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "f" + how)
    w.fail = how
    check(w.dienst.press("A") == "fehler" and w.led_log == [True, False], f"A, {label}: „fehler“, LED wieder aus")
    check(w.dienst.press("D") == "fehler" and w.zustand().get("hilfe_bis") == 0 and w.dienst.help_end is None,
          f"D, {label}: Hilfsbild nicht als offen gemerkt")
w = Welt([pl("Tag", "00:00", "24:00", [DASH])], at(10), "f3")
w.device.write_text("{kaputt")
check(w.dienst.press("A") == "fehler" and not w.posts, "device.json kaputt: Fehler, kein Absturz")
w.state.write_text("[1,2]")
check(tasten.read_state(w.state) == {}, "Zustandsdatei ohne Wörterbuch → leer")

# ---------------------------------------------------------------- Konstanten wie im Dashboard
check(tasten.HILFE_SEKUNDEN == hilfsbild.HILFE_SEKUNDEN, "HILFE_SEKUNDEN gleich im Dienst und im Dashboard")
check(tasten.STATE_FILE.name == hilfsbild.STATE_FILE, "Dateiname der Zustandsdatei gleich")
check(tasten.PINS == {"A": 5, "B": 6, "C": 16, "D": 24} and tasten.LED_PIN == 13, "Pins wie im erfolgreichen Tastentest")

# ---------------------------------------------------------------- gpiod-Attrappe: drain und run
FALL, RISE = "fall", "rise"


class Ev:
    def __init__(self, pin, kind):
        self.line_offset, self.event_type = pin, kind


class Req:
    def __init__(self, batches):
        self.batches = list(batches)   # Liste von Ereignislisten; jede kommt auf einmal an
        self.waits = 0
        self.released = False

    def wait_edge_events(self, timeout):
        self.waits += 1
        return bool(self.batches)

    def read_edge_events(self):
        return self.batches.pop(0)

    def release(self):
        self.released = True


check([e.line_offset for e in tasten.drain(Req([[Ev(5, FALL)], [Ev(5, RISE), Ev(24, FALL)]]))] == [5, 5, 24],
      "drain: leert die ganze Warteschlange")
check(tasten.drain(Req([])) == [], "drain: leer bleibt leer")

fake_gpiod = types.SimpleNamespace(EdgeEvent=types.SimpleNamespace(Type=types.SimpleNamespace(FALLING_EDGE=FALL, RISING_EDGE=RISE)))
chip_closed = []
fake_chip = types.SimpleNamespace(close=lambda: chip_closed.append(1))


class Skript:
    """Spielt der Schleife eine Folge von Ereignissen vor; beendet sie danach per SIGTERM-Ersatz."""

    def __init__(self, req):
        self.req, self.pressed, self.due_calls = req, [], 0
        self.stop_after = None

    def __call__(self, led=None):
        self.led = led
        return self

    def next_deadline(self):
        return None

    def press(self, letter):
        self.pressed.append(letter)
        # Während des „Auftrags“ kommen zwei weitere Drücke und ein Loslassen an
        self.req.batches.append([Ev(24, FALL), Ev(5, FALL), Ev(5, RISE)])
        return "neu"

    def due(self):
        self.due_calls += 1
        if not self.req.batches:
            os.kill(os.getpid(), __import__("signal").SIGTERM)
        return None


req = Req([[Ev(5, RISE)],                      # nur Loslassen → nichts
           [Ev(5, FALL), Ev(24, FALL)],        # zwei Drücke zugleich → nur der erste (A)
           ])
skript = Skript(req)
orig = (tasten.import_gpiod, tasten.find_chip, tasten.request_buttons, tasten.request_led)
tasten.import_gpiod = lambda: fake_gpiod
tasten.find_chip = lambda g: fake_chip
tasten.request_buttons = lambda g, c, p: req
tasten.request_led = lambda g, c: (lambda on: None)
try:
    code = tasten.run(skript)
finally:
    tasten.import_gpiod, tasten.find_chip, tasten.request_buttons, tasten.request_led = orig
check(code == 0 and skript.pressed == ["A"], f"run: nur der erste Druck zählt, Loslassen nicht ({skript.pressed})")
check(not req.batches, "run: während des Auftrags Gedrücktes wurde verworfen (Warteschlange leer)")
check(req.released and chip_closed, "run: Leitungen und Chip am Ende freigegeben")

print()
print("Alles ok." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
