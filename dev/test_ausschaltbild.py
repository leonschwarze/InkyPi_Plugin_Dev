"""Ausschaltbild ohne systemd und ohne Display testen.

  python dev/test_ausschaltbild.py

Geprüft wird: Katze wie in katze.py, Ausschalten/Neustart erkennen, Drehung wie InkyPi,
0 vom Treiber veränderte Pixel, Prüfsumme in device.json zurücksetzen, Ablauf von main()
mit einem Schein-Display (zeichnet nur beim Ausschalten, hält das Herunterfahren nie auf).
"""
import json
import os
import re
import sys
import tempfile
import time
import types
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi"))
sys.path.insert(0, str(ROOT / "ausschaltbild"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ausschaltbild as aus  # noqa: E402
import inky_sim  # noqa: E402

aus.FONT_DIRS = [INKYPI / "src" / "static" / "fonts"]
TMP = Path(tempfile.mkdtemp(prefix="ausschaltbild-"))
aus.LOG_FILE = TMP / "letzter-lauf.txt"
WHEN = datetime(2026, 11, 15, 22, 14)
fails = 0


def check(cond, msg):
    global fails
    print(("ok    " if cond else "FEHLER") + " " + msg)
    if not cond:
        fails += 1


# ---------------------------------------------------------------- Katze wie im Dashboard
sys.path.insert(0, str(ROOT / "tagesdashboard"))
import katze  # noqa: E402

_, _, inner = katze.schlaeft(zz_color=None)
dash_paths = re.findall(r' d="([^"]+)"', inner)
mine = [d for _, d in aus.CAT]
check(mine[1:] == dash_paths[1:], "Kopf, Schwanz, Augen, Nase wie katze.schlaeft()")
check(mine[0].split(" Q42")[1] == dash_paths[0].split(" Q42")[1],
      "Körper wie katze.schlaeft() (nur der Anfang liegt unter dem Kopf)")

# ---------------------------------------------------------------- Ausschalten erkennen
POWEROFF = """\
 99 poweroff.target           start waiting
101 systemd-poweroff.service  start waiting
 87 inkypi-ausschaltbild.service stop running
"""
REBOOT = """\
 95 reboot.target             start waiting
 96 systemd-reboot.service    start waiting
"""
HALT = "120 halt.target start waiting\n"
check(aus.shutdown_kind(POWEROFF) == "poweroff", "poweroff.target → ausschalten")
check(aus.shutdown_kind(HALT) == "poweroff", "halt.target → ausschalten")
check(aus.shutdown_kind(REBOOT) == "reboot", "reboot.target → Neustart (kein Bild)")
check(aus.shutdown_kind("12 kexec.target start waiting\n") == "reboot", "kexec → Neustart")
check(aus.shutdown_kind("") is None, "keine Jobs → Dienst nur gestoppt")
check(aus.shutdown_kind("33 poweroff.target stop waiting\n") is None, "poweroff.target stop zählt nicht")

# ---------------------------------------------------------------- Bild, Drehung, Treiber
sys.path.insert(0, str(INKYPI / "src"))
from utils.image_utils import change_orientation  # noqa: E402

for orient, inverted in [("horizontal", False), ("vertical", False), ("horizontal", True), ("vertical", True)]:
    cfg = {"width": 800, "height": 480, "orientation": orient, "inverted": inverted, "saturation": 0.5}
    logical = aus.build(*aus.logical_size(cfg), WHEN)
    ours = aus.for_display(logical, cfg)
    # InkyPis Weg (display_manager): change_orientation, dann ggf. 180°
    theirs = change_orientation(aus.eink.snap(logical, 0.5), orient)
    if inverted:
        theirs = theirs.rotate(180)
    same = ours.size == (800, 480) and ImageChops.difference(ours, theirs).getbbox() is None
    check(same, f"Drehung wie InkyPi: {orient}{', inverted' if inverted else ''}")

for sat in (0.5, 0.8, 1.0):
    cfg = {"width": 800, "height": 480, "orientation": "horizontal", "inverted": False, "saturation": sat}
    panel = aus.for_display(aus.build(800, 480, WHEN), cfg)
    check(inky_sim.changed_by_driver(panel, sat) == 0, f"Treiber verändert 0 Pixel (Sättigung {sat})")

img = aus.build(800, 480, WHEN)
colours = {c for _, c in img.convert("RGB").getcolors(1 << 20)}
check(len(colours) > 6, "vor dem Einrasten: geglättete Kanten (Überabtastung wirkt)")
snapped = {c for _, c in aus.eink.snap(img).getcolors(1 << 20)}
check(snapped <= {(0, 0, 0), (255, 255, 255), (255, 255, 0), (0, 0, 255)},
      f"eingerastet nur Schwarz, Weiß, Gelb, Blau ({len(snapped)} Farben)")
check(img.getpixel((0, 0)) == (255, 255, 255) and img.getpixel((799, 479)) == (255, 255, 255),
      "Rand bleibt weiß (nichts läuft aus dem Bild)")
check(aus.when_text(datetime(2026, 11, 16, 7, 5)) == "Mo 16.11. · 7:05 Uhr", "Zeitpunkt: Mo 16.11. · 7:05 Uhr")

d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
fnt = aus.font(aus.find_font(), 25.6)
lines = aus.wrap(d, "Der Stecker kann jetzt gezogen werden.", fnt, 330)
check(lines == ["Der Stecker kann jetzt", "gezogen werden."], f"ausgeglichener Umbruch: {lines}")
check(aus.wrap(d, "Ausgeschaltet", fnt, 1000) == ["Ausgeschaltet"], "kurze Zeile ohne Umbruch")

# ---------------------------------------------------------------- device.json
DEVICE = {"name": "InkyPi", "display_type": "inky", "resolution": [800, 480], "orientation": "horizontal",
          "image_settings": {"inky_saturation": 0.5}, "timezone": "Europe/Berlin",
          "refresh_info": {"refresh_time": "2026-11-15T22:00:00+01:00", "image_hash": "abc123",
                           "refresh_type": "Playlist", "plugin_id": "tagesdashboard"}}


def device_file(**changes):
    p = TMP / "device.json"
    data = json.loads(json.dumps(DEVICE))
    data.update(changes)
    p.write_text(json.dumps(data, indent=4))
    os.chmod(p, 0o640)
    return p


p = device_file()
check(aus.forget_image_hash(p) is True, "Prüfsumme wird zurückgesetzt")
after = json.loads(p.read_text())
check(after["refresh_info"]["image_hash"] is None, "image_hash = null (InkyPi zeichnet nach dem Start neu)")
check({k: v for k, v in after.items() if k != "refresh_info"} == {k: v for k, v in DEVICE.items() if k != "refresh_info"}
      and after["refresh_info"]["plugin_id"] == "tagesdashboard", "übrige Einstellungen unverändert")
check(oct(os.stat(p).st_mode & 0o777) == "0o640", "Dateirechte bleiben")
check(not list(TMP.glob(".device-*")), "keine Zwischendatei liegen geblieben")
check(aus.forget_image_hash(p) is False, "schon zurückgesetzt → nichts zu schreiben")

cfg = aus.settings_of({"resolution": [800, 480], "orientation": "vertical", "image_settings": {}})
check(aus.logical_size(cfg) == (480, 800) and cfg["saturation"] == 0.5 and not cfg["inverted"],
      "Standardwerte: Sättigung 0,5, hochkant = 480×800")

# ---------------------------------------------------------------- Ablauf mit Schein-Display


class FakeInky:
    BLACK = 0
    width, height = 800, 480
    calls = []

    def set_border(self, c):
        FakeInky.calls.append(("border", c))

    def set_image(self, image, saturation=0.5):
        FakeInky.calls.append(("image", image.size, saturation))

    def show(self):
        FakeInky.calls.append(("show",))


inky = types.ModuleType("inky")
inky_auto = types.ModuleType("inky.auto")
inky_auto.auto = lambda: FakeInky()
sys.modules["inky"], sys.modules["inky.auto"] = inky, inky_auto


def run(args, jobs="", active=False, **device):
    FakeInky.calls = []
    p = device_file(**device)
    aus.current_shutdown = lambda: aus.shutdown_kind(jobs)
    aus.inkypi_active = lambda: active
    code = aus.main(args + ["--device", str(p)])
    return code, FakeInky.calls, json.loads(p.read_text())["refresh_info"]["image_hash"]


code, calls, h = run(["--beim-ausschalten"], POWEROFF)
check(code == 0 and ("show",) in calls and ("image", (800, 480), 0.5) in calls, "Ausschalten → Bild gezeichnet")
check(h is None, "Ausschalten → Prüfsumme zurückgesetzt")
code, calls, h = run(["--beim-ausschalten"], REBOOT)
check(code == 0 and not calls and h == "abc123", "Neustart → Display und device.json unberührt")
code, calls, h = run(["--beim-ausschalten"], "")
check(code == 0 and not calls, "Dienst nur gestoppt (z. B. Deinstallation) → nichts")
code, calls, h = run(["--beim-ausschalten"], POWEROFF, display_type="mock")
check(code == 0 and not calls, "kein Inky-Display → nichts")
code, calls, h = run(["--zeigen"], active=True)
check(code == 1 and not calls, "--zeigen bei laufendem InkyPi → Hinweis statt Zeichnen")
code, calls, h = run(["--zeigen"])
check(code == 0 and ("show",) in calls and h is None, "--zeigen bei gestopptem InkyPi → Bild")

FakeInky.width = 640                 # falsches Display → Fehler, aber das Herunterfahren läuft weiter
code, calls, h = run(["--beim-ausschalten"], POWEROFF)
FakeInky.width = 800
check(code == 0 and ("show",) not in calls and h == "abc123", "Fehler beim Zeichnen hält das Herunterfahren nicht auf")
logtext = aus.LOG_FILE.read_text()
check("Fehler: ValueError" in logtext and "gezeichnet in" in logtext, "Protokoll in letzter-lauf.txt")

code, calls, h = run(["--beim-ausschalten"], POWEROFF, resolution=[800, 480], orientation="vertical",
                     image_settings={"inky_saturation": 0.7})
check(("image", (800, 480), 0.7) in calls, "hochkant: Bild für das Panel gedreht, Sättigung aus device.json")

# ---------------------------------------------------------------- nach dem Start neu zeichnen (seit 1.1)


def inst(pid, name):
    return {"plugin_id": pid, "name": name, "plugin_settings": {}, "refresh": {"interval": 900}}


PLAYLISTS = {"playlist_config": {"playlists": [
    {"name": "Nacht", "start_time": "23:00", "end_time": "06:00", "plugins": [inst("tagesdashboard", "Nachts")],
     "current_plugin_index": None},
    {"name": "Leer", "start_time": "07:00", "end_time": "08:00", "plugins": []},
    {"name": "Default", "start_time": "00:00", "end_time": "24:00",
     "plugins": [inst("tagesdashboard", "Dashboard"), inst("clock", "Uhr")], "current_plugin_index": 1}]}}


def at(hm):
    return datetime(2026, 11, 15, *map(int, hm.split(":")))


check(aus.active_instance(PLAYLISTS, at("21:25")) == ("Default", "clock", "Uhr"),
      "Instanz: aktive Playlist, zuletzt gezeigte Instanz (current_plugin_index)")
check(aus.active_instance(PLAYLISTS, at("23:30"))[0] == "Nacht" and aus.active_instance(PLAYLISTS, at("5:59"))[0] == "Nacht",
      "über Mitternacht: kürzere Playlist gewinnt (wie InkyPi), 23:30 und 5:59")
check(aus.active_instance(PLAYLISTS, at("6:00"))[0] == "Default", "6:00 gehört nicht mehr zu 23:00–06:00")
check(aus.active_instance(PLAYLISTS, at("7:30")) is None,
      "aktive Playlist ohne Plugins → nichts (wie InkyPi, kein Ausweichen auf eine andere Playlist)")
check(aus.active_instance(PLAYLISTS, at("23:30"))[2] == "Nachts", "current_plugin_index None → erste Instanz")
bad = json.loads(json.dumps(PLAYLISTS))
bad["playlist_config"]["playlists"][2]["current_plugin_index"] = 7
check(aus.active_instance(bad, at("12:00"))[2] == "Dashboard", "Index außerhalb → erste Instanz")
check(aus.active_instance({}, at("12:00")) is None, "keine Playlists → nichts")

# Gegen InkyPis eigene Auswahl (model.PlaylistManager)
from model import PlaylistManager  # noqa: E402

pm = PlaylistManager.from_dict(PLAYLISTS["playlist_config"])


def inkypi_shows(t):
    """InkyPi: aktive Playlist, aber ohne Plugins zeigt es nichts (_determine_next_plugin)."""
    p = pm.determine_active_playlist(at(t))
    return p.name if p and p.plugins else None


def ours(t):
    r = aus.active_instance(PLAYLISTS, at(t))
    return r[0] if r else None


same = all(ours(t) == inkypi_shows(t) for t in ("0:00", "5:59", "6:00", "7:30", "12:00", "22:59", "23:00", "23:59"))
check(same, "Playlist-Wahl gleich wie InkyPis determine_active_playlist (8 Uhrzeiten)")

# Ablauf gegen einen kleinen Schein-Server
import http.server  # noqa: E402
import threading  # noqa: E402


class Fake(http.server.BaseHTTPRequestHandler):
    fails_left = 0
    posts = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Fake.posts.append((self.path, json.loads(body)))
        if Fake.fails_left:
            Fake.fails_left -= 1
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "Wetter nicht erreichbar"}')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')


srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
dev_path = device_file(**PLAYLISTS)
aus.LOG_FILE.write_text("")

Fake.fails_left, Fake.posts = 1, []
ok = aus.redraw_after_start(dev_path, base=base, retries=3, pause=0)
check(ok and len(Fake.posts) == 2, "erster Versuch scheitert (Plugin ohne Netz), zweiter klappt")
path, payload = Fake.posts[-1]
check(path == "/display_plugin_instance" and set(payload) == {"playlist_name", "plugin_id", "plugin_instance"},
      f"Anfrage wie InkyPis Knopf „Display“: {payload}")
logtext = aus.LOG_FILE.read_text()
check("Versuch 1/3 fehlgeschlagen (" in logtext and "Wetter nicht erreichbar" in logtext
      and "Nach dem Start neu gezeichnet" in logtext, "Protokoll nennt Fehlschlag mit Grund und Erfolg")

Fake.fails_left, Fake.posts = 5, []
check(aus.redraw_after_start(dev_path, base=base, retries=2, pause=0) is False and len(Fake.posts) == 2,
      "nach allen Versuchen aufgeben (kein Endlos-Versuch)")
srv.shutdown()
t0 = time.monotonic()
check(aus.redraw_after_start(dev_path, base=base, server_wait=1) is False and time.monotonic() - t0 < 10,
      "InkyPi antwortet nicht → nach der Wartezeit aufgeben")
code = aus.main(["--nach-dem-start", "--device", str(TMP / "fehlt.json")])
check(code == 0, "--nach-dem-start endet nie mit Fehler (sonst „failed“ in systemd)")

aus.LOG_FILE.write_text("".join(f"Zeile {i}\n" for i in range(300)))
aus.log("neu")
lines = aus.LOG_FILE.read_text().splitlines()
check(len(lines) == aus.LOG_KEEP and lines[-1].endswith("neu") and lines[0] == "Zeile 101",
      f"Protokoll behält die letzten {aus.LOG_KEEP} Zeilen")

# Dienst-Dateien und Installation
unit = (ROOT / "ausschaltbild" / "inkypi-ausschaltbild-start.service").read_text()
check("WantedBy=inkypi.service" in unit and "After=inkypi.service" in unit and "Type=exec" in unit
      and "--nach-dem-start" in unit, "Start-Dienst: mit InkyPi, danach, ohne das Terminal zu blockieren")
inst_sh = (ROOT / "ausschaltbild" / "install.sh").read_text()
check('"$DIENST" "$START" /etc/systemd/system/' in inst_sh and 'systemctl enable "$START"' in inst_sh
      and "enable --now \"$START\"" not in inst_sh, "install.sh kopiert und aktiviert beide Dienste (Start-Dienst ohne --now)")
check("inkypi-ausschaltbild-start.service" in (ROOT / "ausschaltbild" / "uninstall.sh").read_text(),
      "uninstall.sh entfernt beide Dienste")

print(f"\n{'Alles ok.' if not fails else f'{fails} Fehler.'}")
sys.exit(1 if fails else 0)
