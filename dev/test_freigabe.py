"""Updates in den Einstellungen des Dashboards (seit 1.45), ohne Rendern und ohne systemd.

  python dev/test_freigabe.py

Geprüft:
  * status(): ohne stand.json, mit Installation, „bereit“, letzter Lauf, fremder Stand (Plugin Manager)
  * starten(): Befehl fehlt, systemd-run klappt, Lauf läuft schon, anderer Fehler
  * generate_image mit dem Knopf-Feld: Meldung statt Bild, startet nichts ohne das Feld
  * Einstellungsseite: Abschnitt „Updates“ mit Knopf; ohne Einrichtung ohne Knopf
  * plugin-info.json ohne „repository“ (sonst bietet der Plugin Manager ein ungeprüftes Update an)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(INKYPI))

import render  # noqa: E402

render.link_plugins(INKYPI)
os.chdir(INKYPI)

from plugins.tagesdashboard import freigabe  # noqa: E402
from plugins.tagesdashboard.tagesdashboard import Tagesdashboard  # noqa: E402

FEHLER = 0


def check(bed, text):
    global FEHLER
    print(("ok    " if bed else "FEHLER") + " " + text)
    FEHLER += not bed


T = Path(tempfile.mkdtemp(prefix="freigabe-"))
befehl = T / "inkypi-update"
befehl.write_text("#!/bin/sh\n")
stand = T / "stand.json"

print("— status()")
s = freigabe.status("1.45", stand, befehl)
check(s["eingerichtet"] and s["installiert"] is None and not s["fremd"], "ohne stand.json: eingerichtet, nichts installiert")
check(not freigabe.status("1.45", stand, T / "fehlt")["eingerichtet"], "ohne Befehl: nicht eingerichtet")
stand.write_text("{kaputt")
check(freigabe.status("1.45", stand, befehl)["installiert"] is None, "kaputte stand.json: kein Absturz")
stand.write_text(json.dumps({
    "tagesdashboard": {"version": "1.45", "tag": "v1.45", "signiert_von": "leon", "installiert": "2026-11-24T03:41:12",
                       "bereit": "v1.46"},
    "letzter_lauf": {"zeit": "2026-11-24T03:41:30", "art": "nachts", "fehler": 0, "text": "Dashboard: v1.45 installiert"}}))
s = freigabe.status("1.45", stand, befehl)
check(s["installiert"] == {"version": "1.45", "von": "leon", "wann": "24.11. 3:41"}, "installiert 1.45, „24.11. 3:41“")
check(s["bereit"] == "v1.46" and not s["fremd"], "„v1.46 liegt bereit“, kein fremder Stand")
check(s["lauf"] == {"wann": "24.11. 3:41", "art": "nachts", "ok": True, "text": "Dashboard: v1.45 installiert"},
      "letzter Lauf")
check(freigabe.status("1.46-dev", stand, befehl)["fremd"], "anderer Stand im Ordner → Hinweis")

print("\n— starten()")
attrappe = T / "systemd-run"


def antwort(code, err=""):
    attrappe.write_text(f"#!/bin/sh\necho \"$@\" > {T}/aufruf\necho '{err}' >&2\nexit {code}\n")
    attrappe.chmod(0o755)


antwort(0)
ok, text = freigabe.starten(befehl, str(attrappe))
aufruf = (T / "aufruf").read_text()
check(ok and text.startswith("Update gestartet"), "systemd-run klappt → „Update gestartet …“")
check("--unit=inkypi-update-jetzt" in aufruf and str(befehl) in aufruf and "--nachts" not in aufruf,
      "eigene Einheit, Lauf wie von Hand (ohne --nachts)")
antwort(1, "Failed to start transient service unit: Unit inkypi-update-jetzt.service was already loaded")
check(freigabe.starten(befehl, str(attrappe)) == (False, "Es läuft schon ein Update."), "läuft schon")
antwort(1, "Interactive authentication required.")
ok, text = freigabe.starten(befehl, str(attrappe))
check(not ok and "Interactive authentication" in text, "anderer Fehler wird genannt")
check(not freigabe.starten(T / "fehlt", str(attrappe))[0], "ohne Befehl: nicht gestartet")

print("\n— generate_image")
gerufen = []
alt = freigabe.starten
freigabe.starten = lambda: (gerufen.append(1), (True, "Update gestartet. Test"))[1]
plugin = Tagesdashboard({"id": "tagesdashboard", "version": "1.45"})
try:
    plugin.generate_image({"inkypiUpdate": "jetzt"}, None)
    check(False, "Knopf: Meldung erwartet")
except RuntimeError as exc:
    check(str(exc) == "Update gestartet. Test" and gerufen == [1], "Knopf: Meldung statt Bild, Update angestoßen")
check(not freigabe.angefordert({"inkypiUpdate": "später"}) and not freigabe.angefordert({}),
      "ohne genau dieses Feld wird nichts gestartet")
freigabe.starten = alt

print("\n— Einstellungsseite")
from jinja2 import Environment, FileSystemLoader  # noqa: E402

env = Environment(loader=FileSystemLoader(str(ROOT / "tagesdashboard")))
with_btn = env.get_template("settings.html").render(updates=freigabe.status("1.45", stand, befehl))
check('id="updSec"' in with_btn and 'id="updStart"' in with_btn and "v1.46 liegt bereit" in with_btn,
      "Abschnitt „Updates“ mit Knopf und Freigabe")
ohne = env.get_template("settings.html").render(updates=freigabe.status("1.45", stand, T / "fehlt"))
check('id="updSec"' in ohne and 'id="updStart"' not in ohne and "nicht eingerichtet" in ohne,
      "nicht eingerichtet: Hinweis statt Knopf")
check('name="inkypiUpdate"' not in with_btn, "kein Formularfeld – landet nie in den gespeicherten Einstellungen")
params = Tagesdashboard({"id": "tagesdashboard", "version": "1.45"}).generate_settings_template()
check("updates" in params and params["updates"]["plugin"] == "1.45", "generate_settings_template liefert „updates“")

info = json.loads((ROOT / "tagesdashboard" / "plugin-info.json").read_text())
check("repository" not in info, "plugin-info.json ohne „repository“ (Plugin Manager zeigt kein Update an)")

print("\nAlles ok." if not FEHLER else f"\n{FEHLER} Fehler.")
sys.exit(1 if FEHLER else 0)
