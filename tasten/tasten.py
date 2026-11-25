"""Tasten für InkyPi: Die vier Tasten A bis D des Inky Impression 7,3″ (seit 1.0).

InkyPi kennt keine Tasten. Dieser kleine Dienst läuft deshalb neben InkyPi (systemd-Dienst
`inkypi-tasten.service`), liest die Tasten und spricht InkyPi über dessen Weboberfläche an – genau wie der
Knopf „Display“ dort. Das Display selbst gehört weiter InkyPi; der Dienst fasst es nie an.

Belegung (Druck, kein langer Druck):
  A  Jetzt neu zeichnen   – das Dashboard zeichnet mit frischen Daten, ohne seinen Bild-Cache
  B  (frei)
  C  (frei)
  D  Hilfsbild            – Belegung, Version, Zustand des Pi; noch einmal D schließt es, sonst nach 3 Minuten
Nachts (im Nachtbild des Dashboards) tun die Tasten nichts.

Die Antwort von InkyPi kommt erst, wenn das Display fertig ist (Zeichnen plus Bildwechsel, grob 30–60 s).
Die LED des Boards (GPIO 13) leuchtet in dieser Zeit. Tasten, die währenddessen gedrückt werden, zählen
nicht – sonst stauten sich Aufträge, und das Display zeichnete minutenlang weiter.

Wie das Dashboard erfährt, was es tun soll: über die kleine Datei `tasten_zustand.json` neben InkyPis
device.json (siehe tagesdashboard/hilfsbild.py). Der Dienst schreibt sie, das Dashboard liest sie.

Aufrufe:
  tasten.py                 der Dienst (systemd): Tasten lesen, Aufträge ausführen
  tasten.py --druck A|D     die Aktion einer Taste ausführen, ohne die Taste zu drücken (Test des Weges bis
                            zum Display; der Dienst darf dabei laufen)
  tasten.py --probe         Prüfung bei der Installation: Einstellungen, Dashboard in der Playlist, GPIO-Chip
  tasten.py --version

Fehler halten den Dienst nie an: Jeder wird protokolliert (journalctl -u inkypi-tasten -f).
"""
import argparse
import glob
import json
import os
import re
import signal
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

VERSION = "1.0"
INKYPI = Path("/usr/local/inkypi")
DEVICE_JSON = INKYPI / "src" / "config" / "device.json"
STATE_FILE = DEVICE_JSON.with_name("tasten_zustand.json")   # muss zu hilfsbild.STATE_FILE im Dashboard passen
INKYPI_URL = "http://127.0.0.1:80"
REQUEST_TIMEOUT = 240      # s, InkyPi antwortet erst, wenn das Display fertig ist
DASHBOARD_ID = "tagesdashboard"

PINS = {"A": 5, "B": 6, "C": 16, "D": 24}   # BCM-Nummern, von oben nach unten (beim 13,3″ liegt C auf 25)
LED_PIN = 13                                # LED des Boards (Pimoroni-Beispiel: an, solange das Display arbeitet)
DEBOUNCE_MS = 20                            # Kontaktprellen
HILFE_SEKUNDEN = 180                        # muss zu hilfsbild.HILFE_SEKUNDEN im Dashboard passen
POLL = 1.0                                  # s, höchstens so lange wartet die Schleife auf eine Taste

# Nachtfenster so lesen wie das Dashboard (Standardwerte und Regeln aus tagesdashboard.py: DEFAULTS, SINCE_VERSION, _opt)
NIGHT_DEFAULTS = {"nightEnabled": "true", "nightFrom": "23:00", "nightTo": "06:00"}
NIGHT_SINCE = 5            # cfgVersion, ab der es den Schalter nightEnabled gibt


def log(msg):
    print(msg, flush=True)   # landet im Journal (journalctl -u inkypi-tasten)


# ------------------------------------------------------------------ device.json und Playlists
def load_device(path=DEVICE_JSON):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def local_now(device):
    tz = (device or {}).get("timezone") or "Europe/Berlin"
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now()


def _playlists(device):
    return ((device.get("playlist_config") or {}).get("playlists")) or []


def active_playlist(device, now):
    """Die Playlist, die InkyPi gerade abspielt (wie PlaylistManager.determine_active_playlist und
    ausschaltbild.active_instance): aktive Playlists (start ≤ jetzt < end, auch über Mitternacht), die kürzeste
    gewinnt. Auch eine aktive Playlist ohne Plugins gilt – InkyPi zeigt dann nichts, wir dann auch nicht."""
    hm = now.strftime("%H:%M")

    def active(p):
        start, end = p.get("start_time", "00:00"), p.get("end_time", "24:00")
        return start <= hm < end if start <= end else (hm >= start or hm < end)

    def minutes(p):
        h1, m1 = map(int, p.get("start_time", "00:00").split(":"))
        h2, m2 = map(int, p.get("end_time", "24:00").split(":"))
        d = (h2 * 60 + m2) - (h1 * 60 + m1)
        return d if d > 0 else d + 24 * 60

    candidates = sorted((p for p in _playlists(device) if active(p)), key=minutes)
    return candidates[0] if candidates else None


def active_instance(device, now):
    """Die Instanz, die InkyPi gerade zeigt: (Playlist, Plugin-ID, Name, Einstellungen) oder None."""
    p = active_playlist(device, now)
    if not p or not p.get("plugins"):
        return None
    idx = p.get("current_plugin_index")
    inst = p["plugins"][idx] if isinstance(idx, int) and 0 <= idx < len(p["plugins"]) else p["plugins"][0]
    return p["name"], inst["plugin_id"], inst["name"], inst.get("plugin_settings") or {}


def dashboard_instance(device, now):
    """Die Dashboard-Instanz: die gerade gezeigte, wenn sie das Dashboard ist, sonst die erste in der aktiven
    Playlist, zuletzt die erste in irgendeiner Playlist (dann kennt man wenigstens seine Einstellungen).
    -> (Playlist, Plugin-ID, Name, Einstellungen, in_aktiver_Playlist) oder None."""
    current = active_instance(device, now)
    if current and current[1] == DASHBOARD_ID:
        return current + (True,)
    p = active_playlist(device, now)
    for pl, in_active in ((p, True),) + tuple((q, False) for q in _playlists(device) if q is not p):
        for inst in (pl or {}).get("plugins") or []:
            if inst.get("plugin_id") == DASHBOARD_ID:
                return pl["name"], inst["plugin_id"], inst["name"], inst.get("plugin_settings") or {}, in_active
    return None


# ------------------------------------------------------------------ Nacht
def parse_hhmm(text):
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return dtime(int(m.group(1)), int(m.group(2)))


def night_opt(settings, key):
    """Einstellung wie Tagesdashboard._opt: Mit cfgVersion bedeutet ein fehlender Schalter „aus“ (ab der Version,
    die ihn kennt), sonst gilt der Standard."""
    default = NIGHT_DEFAULTS[key]
    if key == "nightEnabled" and "cfgVersion" in settings:
        saved = int(settings["cfgVersion"]) if str(settings["cfgVersion"]).isdigit() else 1
        if saved < NIGHT_SINCE:
            return settings.get(key) or default
        return settings.get(key, "false")
    return settings.get(key) or default


def is_night(settings, now):
    """Liegt `now` im Nachtfenster des Dashboards (wie ansichten.in_window)? Ohne Dashboard-Einstellungen
    (leeres Wörterbuch) gelten die Standardwerte des Dashboards."""
    if night_opt(settings, "nightEnabled") != "true":
        return False
    start, end = parse_hhmm(night_opt(settings, "nightFrom")), parse_hhmm(night_opt(settings, "nightTo"))
    if not start or not end or start == end:
        return False
    t = now.time().replace(second=0, microsecond=0)
    return (start <= t < end) if start <= end else (t >= start or t < end)


# ------------------------------------------------------------------ Zustandsdatei
def read_state(path=STATE_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(state, path=STATE_FILE):
    """Atomar schreiben (Zwischendatei + os.replace): Das Dashboard liest sie mitten im Zeichnen, nie halb."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ InkyPi ansprechen
def _http(url, data=None, timeout=10):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


class Dienst:
    """Die Aktionen der Tasten, ohne GPIO (so lässt sich alles ohne Hardware prüfen).

    led(an: bool) schaltet die LED; clock() liefert die Unix-Zeit; post(url, daten, timeout) ruft InkyPi."""

    def __init__(self, device_path=DEVICE_JSON, state_path=STATE_FILE, base=INKYPI_URL, led=None, clock=time.time,
                 post=_http, now=None):
        self.device_path, self.state_path, self.base = device_path, state_path, base
        self.led = led or (lambda on: None)
        self.clock, self.post = clock, post
        self.now = now or None           # Tests: feste Ortszeit; sonst aus der Zeitzone in device.json
        self.help_end = None             # Unix-Zeit, zu der das Hilfsbild abläuft (dann noch einmal zeichnen)
        until = read_state(state_path).get("hilfe_bis")
        if isinstance(until, (int, float)) and until > self.clock():
            self.help_end = float(until)  # nach einem Neustart des Dienstes das Ende des laufenden Hilfsbilds nicht verlieren

    # -- Hilfen
    def _local_now(self, device):
        return self.now() if callable(self.now) else (self.now or local_now(device))

    def _set_state(self, **changes):
        state = read_state(self.state_path)
        state["v"] = 1
        state.update(changes)
        write_state(state, self.state_path)
        return state

    def _bump(self, **changes):
        """Zähler `neu` um eins erhöhen (das Dashboard zeichnet dann ohne Bild-Cache)."""
        n = read_state(self.state_path).get("neu")
        return self._set_state(neu=(n if isinstance(n, int) and not isinstance(n, bool) else 0) + 1, **changes)

    def _display(self, playlist, plugin_id, name):
        """InkyPis Knopf „Display“: zeigt die Instanz, antwortet erst nach dem Bildwechsel. LED an, solange das läuft."""
        body = json.dumps({"playlist_name": playlist, "plugin_id": plugin_id, "plugin_instance": name}).encode()
        t0 = time.monotonic()
        self.led(True)
        try:
            self.post(self.base + "/display_plugin_instance", body, REQUEST_TIMEOUT)
        except urllib.error.HTTPError as e:
            reason = e.read().decode("utf-8", "replace")[:200].strip()
            log(f"InkyPi hat abgelehnt ({e.code}): {reason}")
            return False
        except Exception as e:
            log(f"InkyPi nicht erreichbar: {type(e).__name__}: {e}")
            return False
        finally:
            self.led(False)
        log(f"Display fertig: {name} ({plugin_id}, Playlist {playlist}) nach {time.monotonic() - t0:.1f} s")
        return True

    # -- Tasten
    def press(self, letter):
        """Aktion einer Taste. Gibt ein Stichwort zurück (fürs Protokoll und die Tests):
        „neu“, „hilfe-auf“, „hilfe-zu“, „nacht“, „frei“, „keine-playlist“, „kein-dashboard“, „fehler“."""
        if letter not in ("A", "D"):
            log(f"Taste {letter}: nicht belegt")
            return "frei"
        try:
            device = load_device(self.device_path)
        except (OSError, ValueError) as e:
            log(f"Taste {letter}: device.json nicht lesbar ({e})")
            return "fehler"
        now = self._local_now(device)
        dash = dashboard_instance(device, now)
        if dash and is_night(dash[3], now):   # ohne Dashboard gibt es kein Nachtbild, an dem man sich richten könnte
            log(f"Taste {letter}: Nachtbild – nichts getan")
            return "nacht"
        if letter == "A":
            return self._neu(device, now)
        return self._hilfe(dash)

    def _neu(self, device, now):
        target = active_instance(device, now)
        if not target:
            log("Taste A: keine aktive Playlist mit Plugins – nichts zu zeichnen")
            return "keine-playlist"
        playlist, plugin_id, name, _ = target
        self.help_end = None
        self._bump(hilfe_bis=0)   # auch ein laufendes Hilfsbild schließt A
        log(f"Taste A: neu zeichnen ({name})")
        return "neu" if self._display(playlist, plugin_id, name) else "fehler"

    def _hilfe(self, dash):
        if not dash or not dash[4]:
            log("Taste D: kein Dashboard in der aktiven Playlist – kein Hilfsbild")
            return "kein-dashboard"
        playlist, plugin_id, name = dash[:3]
        now_ts = self.clock()
        if self.help_end and self.help_end > now_ts:   # läuft schon → schließen
            self.help_end = None
            self._bump(hilfe_bis=0)
            log("Taste D: Hilfsbild schließen")
            return "hilfe-zu" if self._display(playlist, plugin_id, name) else "fehler"
        self.help_end = now_ts + HILFE_SEKUNDEN
        self._set_state(hilfe_bis=self.help_end)
        log(f"Taste D: Hilfsbild für {HILFE_SEKUNDEN} s")
        ok = self._display(playlist, plugin_id, name)
        if not ok:
            self.help_end = None
            self._set_state(hilfe_bis=0)
        return "hilfe-auf" if ok else "fehler"

    # -- Zeit
    def due(self):
        """Fällige Arbeit ohne Tastendruck: Das Hilfsbild ist abgelaufen → das Dashboard einmal frisch zeichnen.
        Der Zeitpunkt des Hilfsbilds sitzt in der Zustandsdatei; hier muss nur noch jemand InkyPi anstoßen."""
        if self.help_end is None or self.clock() < self.help_end:
            return None
        self.help_end = None
        try:
            device = load_device(self.device_path)
        except (OSError, ValueError) as e:
            log(f"Hilfsbild abgelaufen, device.json nicht lesbar ({e})")
            return "fehler"
        now = self._local_now(device)
        dash = dashboard_instance(device, now)
        if not dash or not dash[4]:
            return "kein-dashboard"
        self._bump(hilfe_bis=0)
        log("Hilfsbild abgelaufen: Dashboard zeichnet neu")
        return "hilfe-ende" if self._display(*dash[:3]) else "fehler"

    def next_deadline(self):
        """Sekunden bis zur nächsten Aufgabe ohne Taste (None = keine)."""
        return None if self.help_end is None else max(0.0, self.help_end - self.clock())


# ------------------------------------------------------------------ GPIO
HINT_PYTHON = "Mit InkyPis Python starten: sudo /usr/local/inkypi/venv_inkypi/bin/python tasten.py"


def import_gpiod():
    try:
        import gpiod
    except ImportError as e:
        raise SystemExit(f"Das Paket gpiod fehlt ({e}).\n{HINT_PYTHON}")
    try:
        from gpiod.line import Bias, Direction, Edge, Value  # noqa: F401
    except ImportError:
        raise SystemExit(f"Dieses gpiod ist zu alt (Version 1.x, es fehlt gpiod.line).\n{HINT_PYTHON}")
    return gpiod


def find_chip(gpiod):
    """Den GPIO-Chip der 40-poligen Leiste suchen (Label „pinctrl-…“ bei Pi 3, 4 und 5)."""
    problems = []
    for path in sorted(glob.glob("/dev/gpiochip*")):
        try:
            if not gpiod.is_gpiochip_device(path):
                continue
            chip = gpiod.Chip(path)
            label = chip.get_info().label
        except PermissionError:
            raise SystemExit(f"{path}: keine Berechtigung. Mit sudo starten.")
        except OSError as e:
            problems.append(f"{path}: {e}")
            continue
        if re.match(r"pinctrl-", label):
            return chip
        chip.close()
    raise SystemExit("Kein GPIO-Chip „pinctrl-…“ gefunden. " + " ".join(problems))


def request_buttons(gpiod, chip, pins):
    from gpiod.line import Bias, Direction, Edge
    settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.BOTH,
                                  debounce_period=timedelta(milliseconds=DEBOUNCE_MS))
    try:
        return chip.request_lines(consumer="inkypi-tasten", config=dict.fromkeys(pins.values(), settings))
    except OSError as e:
        raise SystemExit(f"Tasten-Leitungen konnten nicht angefordert werden: {e}\n"
                         "Läuft schon ein Tasten-Dienst oder ein Tastentest?")


def request_led(gpiod, chip):
    """LED des Boards als Ausgang (aus). Ohne LED (Leitung belegt) läuft der Dienst trotzdem; led() tut dann nichts."""
    from gpiod.line import Direction, Value
    try:
        req = chip.request_lines(consumer="inkypi-tasten-led",
                                 config={LED_PIN: gpiod.LineSettings(direction=Direction.OUTPUT,
                                                                     output_value=Value.INACTIVE)})
    except OSError as e:
        log(f"LED (GPIO {LED_PIN}) nicht verfügbar, weiter ohne: {e}")
        return lambda on: None

    def led(on):
        try:
            req.set_value(LED_PIN, Value.ACTIVE if on else Value.INACTIVE)
        except OSError as e:
            log(f"LED: {e}")
    return led


def drain(req):
    """Alles verwerfen, was sich in der Warteschlange angesammelt hat (Tasten, die während eines Auftrags gedrückt
    wurden – sonst liefe jeder davon hinterher noch einmal ab). Gibt die verworfenen Ereignisse zurück."""
    events = []
    while req.wait_edge_events(timedelta(0)):
        events += req.read_edge_events()
    return events


def run(dienst_factory=Dienst):
    gpiod = import_gpiod()
    chip = find_chip(gpiod)
    by_pin = {pin: letter for letter, pin in PINS.items()}
    req = request_buttons(gpiod, chip, PINS)
    led = request_led(gpiod, chip)
    dienst = dienst_factory(led=led)
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    log(f"Tasten {VERSION}: A=GPIO {PINS['A']} neu zeichnen, D=GPIO {PINS['D']} Hilfsbild – bereit")
    try:
        while not stop:
            wait = dienst.next_deadline()
            timeout = POLL if wait is None else max(0.05, min(POLL, wait))
            if req.wait_edge_events(timedelta(seconds=timeout)):
                presses = [ev for ev in req.read_edge_events() if ev.event_type == gpiod.EdgeEvent.Type.FALLING_EDGE]
                if presses:   # nur der Druck zählt, nicht das Loslassen; bei mehreren zugleich gilt der erste
                    letter = by_pin.get(presses[0].line_offset)
                    try:
                        dienst.press(letter)
                    except Exception as e:  # Zusatz: der Dienst läuft weiter, was auch passiert
                        log(f"Taste {letter}: unerwarteter Fehler {type(e).__name__}: {e}")
                    skipped = [e for e in drain(req) if e.event_type == gpiod.EdgeEvent.Type.FALLING_EDGE]
                    if skipped:   # Loslassen zählt nicht mit, nur Drücke
                        log(f"{len(skipped)} Tastendrücke während des Auftrags verworfen")
            try:
                if dienst.due() is not None:
                    drain(req)   # während des Neuzeichnens Gedrücktes zählt nicht
            except Exception as e:
                log(f"Hilfsbild-Ende: unerwarteter Fehler {type(e).__name__}: {e}")
    finally:
        led(False)
        req.release()
        chip.close()
    log("Tasten: beendet")
    return 0


# ------------------------------------------------------------------ Aufrufe
def probe():
    """Installationsprüfung: gelingt alles, was der Dienst braucht? (ohne etwas zu zeichnen)"""
    ok = True
    try:
        device = load_device()
        now = local_now(device)
        print(f"device.json: gelesen, Zeitzone {device.get('timezone') or 'Europe/Berlin'}, Ortszeit {now:%H:%M}")
    except (OSError, ValueError) as e:
        print(f"device.json: NICHT lesbar ({e}) – ist InkyPi unter {INKYPI} installiert?")
        return 1
    dash = dashboard_instance(device, now)
    if dash:
        where = "in der aktiven Playlist" if dash[4] else "nur in einer inaktiven Playlist (D braucht die aktive)"
        print(f"Dashboard: Instanz „{dash[2]}“ {where}")
        print(f"Nachtbild jetzt: {'ja – die Tasten ruhen' if is_night(dash[3], now) else 'nein'}")
        ok &= bool(dash[4])
    else:
        print("Dashboard: keine Instanz in den Playlists – A funktioniert, D nicht")
    cur = active_instance(device, now)
    print("Aktive Instanz: " + (f"{cur[2]} ({cur[1]}, Playlist {cur[0]})" if cur else "keine – A hätte nichts zu zeichnen"))
    if os.access(STATE_FILE.parent, os.W_OK):
        print(f"Zustandsdatei: {STATE_FILE} kann geschrieben werden")
    else:
        print(f"Zustandsdatei: {STATE_FILE.parent} ist NICHT beschreibbar (mit sudo starten)")
        ok = False
    try:
        _http(INKYPI_URL + "/", timeout=5)
        print("InkyPi-Weboberfläche: antwortet")
    except Exception as e:
        print(f"InkyPi-Weboberfläche: antwortet nicht ({e}) – läuft inkypi.service? (A und D brauchen sie)")
    gpiod = import_gpiod()
    chip = find_chip(gpiod)
    req = request_buttons(gpiod, chip, PINS)
    req.release()
    chip.close()
    print("GPIO: Chip gefunden, Tasten-Leitungen frei")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tasten A–D des Inky Impression für InkyPi",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--druck", choices=["A", "B", "C", "D"], help="Aktion dieser Taste ausführen, ohne die Taste zu drücken")
    ap.add_argument("--probe", action="store_true", help="Installationsprüfung")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    if args.probe:
        return probe()
    if args.druck:
        print(Dienst().press(args.druck))
        return 0
    return run()


if __name__ == "__main__":
    sys.exit(main())
