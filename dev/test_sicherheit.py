"""Schutz des Nextcloud-App-Passworts und weitere Regeln aus 1.33, ohne Rendern.

  python dev/test_sicherheit.py

Geprüft:
  * Adresse und Schlüsselname aus den Einstellungen gegen einen Schein-Server, der Authorization
    mitschneidet: andere Adresse, anderer Schlüssel, http ins Internet – der Schein-Server bekommt
    nichts; Dashboard und Einzel-Plugin Kalender
  * erster erfolgreicher Abruf merkt die Nextcloud (Datei neben device.json); Umzug → klare Meldung
  * Schlüsselnamen: NEXTCLOUD_… und NC_… ja, alles andere nein
  * http und abgeschaltete Zertifikatsprüfung nur für Server im Heimnetz (privat, Loopback, link-local)
  * Serientermine mit mehr als 96 Vorkommen am Tag (FREQ=SECONDLY, DAILY mit BYHOUR×BYMINUTE×BYSECOND)
    werden nicht aufgelöst; normale Serien unverändert
  * Log „Zielort: …“ ohne Termintitel
"""
import base64
import http.server
import json
import logging
import os
import sys
import tempfile
import threading
import time as _time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(INKYPI))

import render  # noqa: E402

render.link_plugins(INKYPI)
os.chdir(INKYPI)
os.environ["DEV_PROTO"] = "ziel"  # Termine in Düsseldorf/Eschweiler für die Logzeile „Zielort“

from PIL import Image  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 12, 8, 20, tzinfo=TZ)

import mock_brightsky, mock_news, mock_radar, mock_luft, mock_pollen, mock_pegel  # noqa: E402,E401
mock_brightsky.install(NOW, "herbst")
mock_news.install(NOW, "normal")
mock_radar.install(NOW, "trocken")
mock_luft.install(NOW, "gut")
mock_pollen.install(NOW, "gut")
mock_pegel.install(NOW, "keine")
import mock_ziel  # noqa: E402  (erst jetzt: merkt sich beim Import den vorigen get)
mock_ziel.install(NOW)
import caldav_server  # noqa: E402
NC_URL, NC_USER, NC_PASSWORD = caldav_server.start(NOW.date())

db = __import__("plugins.tagesdashboard.tagesdashboard", fromlist=["x"])
nk = __import__("plugins.nextcloud_kalender.nextcloud_kalender", fromlist=["x"])
db.Tagesdashboard.current_time = lambda self, tz: NOW.astimezone(tz)
nk.NextcloudKalender.current_time = lambda self, tz: NOW.astimezone(tz)

SECRETS = {"NEXTCLOUD_APP_PASSWORD": NC_PASSWORD, "NC_ARBEIT": NC_PASSWORD, "OPEN_AI_SECRET": "sk-geheim-123"}
fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok     {name}")
    else:
        fails += 1
        print(f"FEHLER {name}" + (f"\n       {detail}" if detail else ""))


class PiConfig(render.DevConfig):
    """Wie InkyPis Config, mit config_file (neben device.json liegt die gemerkte Nextcloud)."""

    def __init__(self, folder, saved_url=None):
        super().__init__((800, 480), "horizontal", SECRETS)
        self.config_file = str(Path(folder) / "device.json")
        inst = {"plugin_id": "tagesdashboard", "name": "Dashboard",
                "plugin_settings": {"nextcloudUrl": saved_url or NC_URL, "username": NC_USER}}
        self.values["playlist_config"] = {"playlists": [{"name": "Default", "plugins": [inst]}]}


# ---------------------------------------------------------------- Schein-Server
CAPTURED = []


class Capture(http.server.BaseHTTPRequestHandler):
    def _any(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            auth = base64.b64decode(auth.split()[1]).decode()
        CAPTURED.append(auth)
        self.send_response(401)
        self.end_headers()

    do_GET = do_PROPFIND = do_REPORT = do_POST = _any

    def log_message(self, *args):
        pass


fake = http.server.HTTPServer(("127.0.0.1", 0), Capture)
threading.Thread(target=fake.serve_forever, daemon=True).start()
OTHER_URL = f"http://127.0.0.1:{fake.server_address[1]}"  # anderer Server im Heimnetz (http dort erlaubt)

BASE = dict(render.BASE_SETTINGS, nextcloudUrl=NC_URL, username=NC_USER, cfgVersion=str(db.CFG_VERSION))


def dashboard_calendar(settings, cfg):
    plugin = db.Tagesdashboard({"id": "tagesdashboard"})
    flag = lambda k: plugin._opt(settings, k) == "true"  # noqa: E731
    return plugin.load_calendar(settings, cfg, TZ, NOW.date(), flag)


def kalender_plugin(settings, cfg):
    plugin = nk.NextcloudKalender({"id": "nextcloud_kalender"})
    plugin.render_image = lambda dims, *a, **k: Image.new("RGB", tuple(dims), "white")
    return plugin.generate_image(settings, cfg)


def attempt(name, fn, settings, cfg, want_ok):
    """Ruft fn auf; want_ok = sollte gelingen. Der Schein-Server darf nie etwas bekommen."""
    CAPTURED.clear()
    try:
        fn(settings, cfg)
        ok, msg = True, ""
    except Exception as exc:  # RuntimeError mit Meldung für die Weboberfläche
        ok, msg = False, str(exc)
    leaked = [c for c in CAPTURED if c]
    check(f"{name}: {'gelingt' if want_ok else 'abgelehnt'}" + (f" ({msg[:70]})" if msg and not want_ok else ""),
          ok == want_ok and not leaked,
          f"gelungen={ok} Meldung={msg[:120]!r} Schein-Server bekam {leaked}")
    return msg


# ---------------------------------------------------------------- 1. Ende zu Ende
print("— Adresse und Schlüssel aus den Einstellungen")
with tempfile.TemporaryDirectory() as tmp:
    cfg = PiConfig(tmp)
    attempt("Dashboard, eigene Nextcloud", dashboard_calendar, dict(BASE), cfg, True)
    pin = Path(tmp) / "nextcloud_pin.json"
    pins = json.loads(pin.read_text()) if pin.exists() else {}
    check("erster Abruf merkt die Nextcloud", pins.get("NEXTCLOUD_APP_PASSWORD", "").startswith("http://127.0.0.1:"),
          f"{pin}: {pins}")
    attempt("Dashboard, andere Adresse im Heimnetz", dashboard_calendar, dict(BASE, nextcloudUrl=OTHER_URL), cfg, False)
    attempt("Dashboard, anderer Schlüssel OPEN_AI_SECRET", dashboard_calendar,
            dict(BASE, nextcloudUrl=OTHER_URL, passwordKey="OPEN_AI_SECRET"), cfg, False)
    attempt("Kalender-Plugin, andere Adresse", kalender_plugin, dict(BASE, nextcloudUrl=OTHER_URL), cfg, False)
    attempt("Kalender-Plugin, anderer Schlüssel", kalender_plugin,
            dict(BASE, nextcloudUrl=OTHER_URL, passwordKey="OPEN_AI_SECRET"), cfg, False)
    attempt("Kalender-Plugin, eigene Nextcloud", kalender_plugin, dict(BASE), cfg, True)
    attempt("Schlüssel NC_ARBEIT (eigener Name, erlaubt)", dashboard_calendar, dict(BASE, passwordKey="NC_ARBEIT"), cfg, True)

with tempfile.TemporaryDirectory() as tmp:
    cfg = PiConfig(tmp)
    msg = attempt("http zu einem Server im Internet", dashboard_calendar,
                  dict(BASE, nextcloudUrl="http://93.184.216.34"), cfg, False)
    check("  … Meldung nennt https", "https://" in msg, msg)
    # Noch nichts gemerkt: Adresse, die in keiner gespeicherten Instanz steht → nichts senden
    attempt("noch nichts gemerkt, Adresse nicht gespeichert", dashboard_calendar,
            dict(BASE, nextcloudUrl=OTHER_URL), cfg, False)
    check("  … nichts gemerkt", not (Path(tmp) / "nextcloud_pin.json").exists())

with tempfile.TemporaryDirectory() as tmp:  # gespeichert, aber falsches Passwort: senden ja, merken nein
    cfg = PiConfig(tmp, saved_url=OTHER_URL)
    CAPTURED.clear()
    try:
        dashboard_calendar(dict(BASE, nextcloudUrl=OTHER_URL), cfg)
    except RuntimeError:
        pass
    check("gespeicherte Adresse, Anmeldung scheitert: nichts gemerkt",
          bool(CAPTURED) and not (Path(tmp) / "nextcloud_pin.json").exists(), f"{CAPTURED}")

with tempfile.TemporaryDirectory() as tmp:  # beschädigte Datei: lieber nichts senden
    (Path(tmp) / "nextcloud_pin.json").write_text("{kaputt")
    attempt("beschädigte Datei", dashboard_calendar, dict(BASE), PiConfig(tmp), False)

# ---------------------------------------------------------------- 2. Regeln einzeln
print("— Regeln")
try:
    for key in ("NEXTCLOUD_APP_PASSWORD", "NEXTCLOUD_ARBEIT", "NC_ARBEIT"):
        check(f"Schlüssel {key} erlaubt", nk.checked_key(key) == key)
    check("leer → Standard", nk.checked_key("") == "NEXTCLOUD_APP_PASSWORD")
    for key in ("OPEN_AI_SECRET", "DB_API_KEY", "nextcloud_app_password", "NEXTCLOUD", "PATH", "NC_"):
        try:
            nk.checked_key(key)
            check(f"Schlüssel {key} abgelehnt", False)
        except RuntimeError:
            check(f"Schlüssel {key} abgelehnt", True)

    real_gai = nk.socket.getaddrinfo
    fake_dns = {"nextcloud.local": "192.168.178.40", "fritz.box": "192.168.178.1", "cloud.example.de": "93.184.216.34",
                "v6.home": "fd00::12", "gemischt.example": None}

    def gai(host, *args, **kwargs):
        if host == "gemischt.example":  # eine private und eine öffentliche Adresse → nicht Heimnetz
            return [(2, 1, 6, "", ("192.168.1.2", 0)), (2, 1, 6, "", ("93.184.216.34", 0))]
        if host in fake_dns:
            ip = fake_dns[host]
            return [(10 if ":" in ip else 2, 1, 6, "", (ip, 0))]
        raise OSError("unbekannt")

    nk.socket.getaddrinfo = gai
    for host, want in (("localhost", True), ("127.0.0.1", True), ("192.168.178.40", True), ("10.0.0.5", True),
                       ("fe80::1", True), ("nextcloud.local", True), ("fritz.box", True), ("v6.home", True),
                       ("93.184.216.34", False), ("cloud.example.de", False), ("gemischt.example", False),
                       ("unbekannt.invalid", False), ("", False)):
        check(f"Heimnetz {host or '(leer)'} → {want}", nk.is_home(host) == want)
    for url, want in (("https://cloud.example.de/remote.php/dav/", "https://cloud.example.de:443"),
                      ("http://nextcloud.local/remote.php/dav/", "http://nextcloud.local:80"),
                      ("https://Cloud.Example.de:8443/x/", "https://cloud.example.de:8443")):
        check(f"Herkunft {url}", nk.origin_of(url) == want, nk.origin_of(url))
    try:
        nk.origin_of("http://cloud.example.de/remote.php/dav/")
        check("http ins Internet abgelehnt", False)
    except RuntimeError:
        check("http ins Internet abgelehnt", True)
    check("Prüfung aus, Heimnetz → aus", nk.tls_verify("https://nextcloud.local/remote.php/dav/", False) is False)
    check("Prüfung aus, Internet → trotzdem an", nk.tls_verify("https://cloud.example.de/remote.php/dav/", False) is True)
    check("Prüfung an bleibt an", nk.tls_verify("https://nextcloud.local/remote.php/dav/", True) is True)
    nk.socket.getaddrinfo = real_gai
except AttributeError as exc:
    check("Regeln vorhanden", False, f"{exc} (Stand vor 1.33?)")

# ---------------------------------------------------------------- 3. Dichte Serientermine
print("— Serientermine")
ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//
BEGIN:VEVENT
UID:{uid}@test
DTSTAMP:20261112T080000Z
DTSTART:20261112T070000Z
DURATION:PT1S
SUMMARY:Serie
RRULE:{rule}
END:VEVENT
END:VCALENDAR"""
helper = nk.NextcloudKalender({"id": "nextcloud_kalender"})
start, end = datetime(2026, 11, 12, tzinfo=TZ), datetime(2026, 11, 21, tzinfo=TZ)  # 9 Tage wie im Dashboard
for rule, want in (("FREQ=SECONDLY", 0), ("FREQ=MINUTELY", 0), ("FREQ=MINUTELY;INTERVAL=30", None),
                   ("FREQ=DAILY;BYHOUR=" + ",".join(map(str, range(24))) + ";BYMINUTE=" + ",".join(map(str, range(60))), 0),
                   ("FREQ=HOURLY", None), ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", None), ("FREQ=DAILY;COUNT=3", 3)):
    t0 = _time.monotonic()
    if "SECONDLY" in rule and not hasattr(nk, "too_dense"):  # Stand ohne Grenze: nicht auflösen lassen (dauert)
        check(f"{rule}: übersprungen", False, "kein Schutz vorhanden")
        continue
    n = len(helper.parse_events(ICS.format(uid=abs(hash(rule)), rule=rule), {"name": "Test", "color": "#000000"}, TZ, start, end))
    took = _time.monotonic() - t0
    if want == 0:
        check(f"{rule}: übersprungen ({took:.2f} s)", n == 0 and took < 1, f"{n} Vorkommen, {took:.1f} s")
    elif want is None:
        check(f"{rule}: aufgelöst ({n} Vorkommen)", n > 0, f"{n}")
    else:
        check(f"{rule}: {want} Vorkommen", n == want, f"{n}")

# ---------------------------------------------------------------- 4. Log ohne Termintitel
print("— Log")
records = []


class Keep(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


handler = Keep(level=logging.INFO)
logging.getLogger("plugins").addHandler(handler)
logging.getLogger("plugins").setLevel(logging.INFO)
plugin = db.Tagesdashboard({"id": "tagesdashboard"})
plugin.render_image = lambda dims, *a, **k: Image.new("RGB", tuple(dims), "white")
db._IMAGE_CACHE.clear()
with tempfile.TemporaryDirectory() as tmp:
    plugin.generate_image(dict(BASE, zielEnabled="true"), PiConfig(tmp))
logging.getLogger("plugins").removeHandler(handler)
ziel = [r for r in records if r.startswith("Zielort:") and "→" in r]
check(f"Zielort-Zeilen da ({len(ziel)})", len(ziel) >= 1, "\n       ".join(records[-15:]))
titled = [r for r in records if "Ausschuss Heimat" in r or "Bürgersprechstunde" in r]
check("kein Termintitel im Log", not titled, "\n       ".join(titled))
check("Ort und Entfernung bleiben (für die Prüfung auf dem Pi)", any("Düsseldorf" in r and "km" in r for r in ziel),
      "\n       ".join(ziel))

fake.shutdown()
print("Alles in Ordnung." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
