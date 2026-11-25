"""apt-Updates des Pi im Hilfsbild (tagesdashboard/hilfsdaten.py, seit 1.53) ohne Rendern.

  python dev/test_pi_updates.py

Prüft: Ausgabe von `apt-get -s dist-upgrade` (Anzahl aus der Schlusszeile, Sicherheit aus den Quellen, neu
installierte Pakete zählen nicht, unbrauchbare Ausgabe = unbekannt statt „0“), Kernel-Vergleich für den
Neustart (gleiche Art, neuere Version, ABI-Nummer, fremde Kernelarten, Hinweisdatei), Alter der Paketlisten,
Zeilen (Einzahl, rot nur bei Sicherheit/Neustart/alten Listen), Ergebnisdatei (seit 1.55: dreimal am Tag, atomar
geschrieben, Lesen während des Schreibens, Rückfall auf den letzten Stand), Abfrage im Hintergrund, Zusammenbau
im Abschnitt „Updates“, Fehler werfen nie.
"""
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tagesdashboard import hilfsdaten as hd  # noqa: E402

FAILED = []
NOW = datetime(2026, 11, 25, 15, 41, tzinfo=ZoneInfo("Europe/Berlin"))

APT = """Reading package lists...
Building dependency tree...
The following packages will be upgraded:
  libssl3 openssh-server raspi-firmware bash
Inst libssl3 [3.0.11-1~deb12u1] (3.0.11-1~deb12u2 Debian-Security:12/stable-security [arm64])
Inst openssh-server [1:9.2p1-2+deb12u2] (1:9.2p1-2+deb12u3 Debian-Security:12/stable-security [arm64]) []
Inst raspi-firmware [1:1.20230405] (1:1.20240924 Raspberry Pi Foundation:stable [all])
Inst bash [5.2.15-2+b2] (5.2.15-2+b7 Debian:12.7/stable, Debian-Security:12/stable-security [arm64])
Inst linux-image-6.6.62+rpt-rpi-v8 (1:6.6.62-1+rpt1 Raspberry Pi Foundation:stable [arm64])
Conf libssl3 (3.0.11-1~deb12u2 Debian-Security:12/stable-security [arm64])
4 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.
"""
APT_NULL = "Reading package lists...\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def fake(answers):
    """run-Attrappe: Programmname (erstes Wort, `env` übersprungen) → Antwort; merkt sich die Aufrufe."""
    calls = []

    def run(cmd, timeout=3):
        calls.append((list(cmd), timeout))
        key = "apt-get" if "apt-get" in cmd else cmd[2] if cmd[0] == "env" else cmd[0]
        val = answers.get(key)
        return val() if callable(val) else val
    run.calls = calls
    return run


hd.APT_HINTERGRUND = False     # die meisten Prüfungen laufen der Reihe nach; der Hintergrund hat einen eigenen Abschnitt unten


TMP = tempfile.mkdtemp(prefix="pi_updates_")
PFAD = os.path.join(TMP, hd.APT_DATEI)


def reset():
    hd._apt_zuletzt.clear()
    if hd._apt_sperre.locked():
        hd._apt_sperre.release()
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))


def warte_auf_ende():
    for _ in range(200):
        if not hd._apt_sperre.locked():
            return
        time.sleep(0.05)


def datei():
    with open(PFAD, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------------------ apt auswerten
check("Anzahl aus der Schlusszeile, Sicherheit aus den Quellen (3 von 4; ein neues Paket zählt nicht)",
      hd.apt_auswerten(APT) == (4, 3))
check("Quelle mit mehreren Einträgen: eine Sicherheitsquelle genügt", hd.apt_auswerten(APT)[1] == 3)
check("0 Updates ist 0, nicht unbekannt", hd.apt_auswerten(APT_NULL) == (0, 0))
check("leere Ausgabe = unbekannt", hd.apt_auswerten(None) is None and hd.apt_auswerten("") is None)
check("Fehlermeldung statt Schlusszeile = unbekannt (nicht „0 Updates“)",
      hd.apt_auswerten("E: Could not open file /var/lib/apt/lists/x\n") is None)
check("übersetzte Schlusszeile (ohne LC_ALL=C) = unbekannt", hd.apt_auswerten("4 aktualisiert, 1 neu installiert\n") is None)

# ------------------------------------------------------------------------------------------ Neustart
RPI = "6.6.51+rpt-rpi-v8"
check("neuerer Kernel derselben Art → kernel",
      hd.neustart_grund(fake({"uname": RPI + "\n", "ls": f"{RPI}\n6.6.62+rpt-rpi-v8\n"}), lambda p: None) == "kernel")
check("derselbe Kernel → nichts",
      hd.neustart_grund(fake({"uname": RPI, "ls": RPI + "\n"}), lambda p: None) is None)
check("neuerer Kernel anderer Art (rpi-2712 auf einem Pi mit v8) zählt nicht",
      hd.neustart_grund(fake({"uname": RPI, "ls": f"{RPI}\n6.6.62+rpt-rpi-2712\n"}), lambda p: None) is None)
check("älterer Kernel zählt nicht (Zehnerstelle: 6.6.9 < 6.6.51)",
      hd.neustart_grund(fake({"uname": RPI, "ls": f"{RPI}\n6.6.9+rpt-rpi-v8\n"}), lambda p: None) is None)
check("Debian-ABI: -13 nach -12 → kernel",
      hd.neustart_grund(fake({"uname": "6.1.0-12-arm64", "ls": "6.1.0-12-arm64\n6.1.0-13-arm64\n"}), lambda p: None) == "kernel")
check("Hinweisdatei /run/reboot-required → hinweis",
      hd.neustart_grund(fake({"uname": RPI, "ls": RPI}), lambda p: "*** restart ***" if p == "/run/reboot-required" else None) == "hinweis")
check("leere Hinweisdatei zählt auch", hd.neustart_grund(fake({}), lambda p: "") == "hinweis")
check("nichts lesbar → nichts behaupten", hd.neustart_grund(fake({}), lambda p: None) is None)

# ------------------------------------------------------------------------------------------ Alter der Listen
vor = lambda tage: f"{NOW.timestamp() - tage * 86400:.1f}\n"
check("Alter = neuester Zeitstempel (2 und 9 Tage → 2)",
      abs(hd.listen_alter_tage(NOW, fake({"find": vor(2) + vor(9)})) - 2) < 0.01)
check("keine Dateien → unbekannt", hd.listen_alter_tage(NOW, fake({"find": None})) is None)
check("Müll in der Ausgabe stört nicht", abs(hd.listen_alter_tage(NOW, fake({"find": "x\n" + vor(1)})) - 1) < 0.01)

# ------------------------------------------------------------------------------------------ Zeilen
z = hd.apt_zeilen({"n": 12, "sicher": 3, "neustart": "kernel", "alter": 1})
check("Zeilen: Updates mit Sicherheit (rot) und Neustart (rot)",
      [(x["text"], x["bad"]) for x in z] == [("Pi: 12 Updates (3 Sicherheit)", True),
                                              ("Neustart nötig (neuer Kernel)", True)])
check("ohne Sicherheit nicht rot", hd.apt_zeilen({"n": 5, "sicher": 0, "neustart": None, "alter": 0})[0]
      == {"text": "Pi: 5 Updates", "bad": False})
check("Einzahl", hd.apt_zeilen({"n": 1, "sicher": 0})[0]["text"] == "Pi: 1 Update")
check("0 → aktuell", hd.apt_zeilen({"n": 0, "sicher": 0})[0] == {"text": "Pi: aktuell", "bad": False})
check("alte Listen: Hinweis rot", hd.apt_zeilen({"n": 0, "alter": 12.4})[1] == {"text": "Paketlisten 12 Tage alt, Zahl unsicher", "bad": True})
check("7 Tage alt noch ohne Hinweis", len(hd.apt_zeilen({"n": 0, "alter": 7.0})) == 1)
check("Neustart auch ohne bekannte Zahl", [x["text"] for x in hd.apt_zeilen({"n": None, "neustart": "hinweis"})] == ["Neustart nötig"])
check("nichts bekannt → keine Zeilen", hd.apt_zeilen({"n": None, "neustart": None, "alter": None}) == [])
check("alte Listen ohne bekannte Zahl: kein Hinweis", hd.apt_zeilen({"n": None, "alter": 30}) == [])

# ------------------------------------------------------------------------------------------ Datei, Intervall
reset()
run = fake({"apt-get": APT, "uname": RPI, "ls": RPI, "find": vor(1)})
check("ohne Pfad (Entwicklungsrechner) nichts angestoßen", hd.apt_anstossen(None, run) is False and not run.calls)
check("Pfad nur mit InkyPi-Konfiguration", hd.apt_pfad(object()) is None
      and hd.apt_pfad(type("C", (), {"config_file": "/x/y/device.json"})()) == f"/x/y/{hd.APT_DATEI}")
check("erste Abfrage: gestartet", hd.apt_anstossen(PFAD, run) is True)
d = datei()
check("Datei hat Zahl, Sicherheit, Zeit, ok", (d["n"], d["sicher"], d["ok"], d["v"]) == (4, 3, True, 1) and abs(d["t"] - time.time()) < 5)
check("apt läuft mit nice, LC_ALL=C und 180 s",
      run.calls[0] == (hd.APT_BEFEHL, 180) and hd.APT_BEFEHL[:3] == ["nice", "-n", "19"] and "LC_ALL=C" in hd.APT_BEFEHL)
check("kein Rest der Nebendatei", [f for f in os.listdir(TMP) if f.endswith(".tmp")] == [])
n0 = len(run.calls)
check("zweiter Aufruf kurz danach: nichts", hd.apt_anstossen(PFAD, run) is False and len(run.calls) == n0)
l = hd.apt_lage(NOW, run, lambda p: None, PFAD)
check("apt_lage liest nur die Datei, startet kein apt",
      (l["n"], l["sicher"], l["laeuft"]) == (4, 3, False) and sum(1 for c, _ in run.calls if "apt-get" in c) == 1)
vor7 = time.time() - 7 * 3600
d["versuch"] = vor7; hd.apt_speichern(PFAD, d)
check("nach 7 Stunden noch nicht fällig", hd.apt_anstossen(PFAD, run) is False)
d["versuch"] = time.time() - 8 * 3600 - 5; hd.apt_speichern(PFAD, d)
check("nach 8 Stunden fällig → dreimal am Tag", hd.apt_anstossen(PFAD, run) is True and datei()["versuch"] > time.time() - 5)
check("Zeit des Ergebnisses wird erneuert", abs(datei()["t"] - time.time()) < 5)

# Fehlschlag: alte Zahl bleibt, früher wiederholen
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": time.time() - 9 * 3600, "versuch": time.time() - 9 * 3600, "ok": True, "n": 7, "sicher": 1})
bad = fake({"apt-get": None})
hd.apt_anstossen(PFAD, bad)
d = datei()
check("Fehlschlag behält die alte Zahl und vermerkt den Versuch", (d["n"], d["sicher"], d["ok"]) == (7, 1, False) and d["versuch"] > time.time() - 5)
check("nach einem Fehlschlag in 1 Stunde wieder dran, vorher nicht",
      hd.apt_faellig(d, d["versuch"] + 3500) is False and hd.apt_faellig(d, d["versuch"] + 3700) is True)
check("alte Zahl wird weiter angezeigt (kein „nicht ermittelt“)",
      [x["text"] for x in hd.apt_zeilen(hd.apt_lage(NOW, bad, lambda p: None, PFAD))][0] == "Pi: 7 Updates (1 Sicherheit)")
reset()
hd.apt_anstossen(PFAD, bad)
l = hd.apt_lage(NOW, bad, lambda p: None, PFAD)
check("nie eine Zahl und Fehlschlag: „nicht ermittelt“ statt Schweigen",
      l["n"] is None and l["fehler"] and [x["text"] for x in hd.apt_zeilen(l)] == ["Pi: Updates nicht ermittelt"])
reset()
check("Ausnahme in apt: Versuch trotzdem vermerkt, Sperre frei",
      hd.apt_anstossen(PFAD, lambda cmd, timeout=3: (_ for _ in ()).throw(RuntimeError("x"))) is True
      and not hd._apt_sperre.locked() and datei()["ok"] is False)

# Zahl älter als 30 h → rote Zeile mit Datum
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": time.time() - 40 * 3600, "versuch": time.time(), "ok": False, "n": 5, "sicher": 0})
zl = [(x["text"], x["bad"]) for x in hd.apt_zeilen(hd.apt_lage(NOW, bad, lambda p: None, PFAD))]
check("Zahl über 30 Stunden alt: Datum und Warnung", zl[0] == ("Pi: 5 Updates", False) and zl[-1][1] and zl[-1][0].startswith("Zahl vom "))

# ------------------------------------------------------------------------------------------ Lesen beim Schreiben
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": time.time(), "versuch": time.time(), "ok": True, "n": 4, "sicher": 3})
check("gut gelesener Stand wird gemerkt", hd.apt_lesen(PFAD)["n"] == 4 and hd._apt_zuletzt["d"]["n"] == 4)

with open(PFAD, "w") as f:                      # Datei „mitten im Schreiben“: abgeschnittenes JSON
    f.write('{"v": 1, "n": 9, "sic')
t0 = time.time()
l = hd.apt_lesen(PFAD)
check("halb geschriebene Datei: Rückfall auf den letzten guten Stand (nicht 9, kein Absturz)",
      l is not None and l["n"] == 4)
check("… nach kurzem Warten (Versuche × Pause), nicht endlos", 0.3 < time.time() - t0 < 2.5)

with open(PFAD, "w") as f:                      # leere Datei (Moment nach dem Öffnen zum Schreiben)
    pass
check("leere Datei: ebenfalls letzter Stand", hd.apt_lesen(PFAD)["n"] == 4)

with open(PFAD, "w") as f:
    f.write('{"v": 1, "n": 9, "sic')
def spaeter_fertig():
    time.sleep(0.2)
    hd.apt_speichern(PFAD, {"v": 1, "t": time.time(), "versuch": time.time(), "ok": True, "n": 11, "sicher": 2})
th = threading.Thread(target=spaeter_fertig); th.start()
l = hd.apt_lesen(PFAD)
th.join()
check("Leser wartet kurz und bekommt dann den neuen, vollständigen Stand (11)", l["n"] == 11)

reset()
with open(PFAD, "w") as f:
    f.write("kein json")
check("beschädigt und nie etwas gelesen: None, kein Absturz", hd.apt_lesen(PFAD) is None)
check("… und die Zeile fehlt einfach (Hilfsbild bleibt brauchbar)", hd.pi_updates(NOW, fake({}), lambda p: None, PFAD) == [])
reset()
check("Datei fehlt: None", hd.apt_lesen(PFAD) is None)

# Dauerprobe: Schreiber und Leser gleichzeitig – nie ein Fehler, nie eine halbe Datei
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": 1.0, "versuch": 1.0, "ok": True, "n": 0, "sicher": 0})
fertig = threading.Event()
gelesen, kaputt_gesehen = [], []
je_leser = []


def schreiber():
    for i in range(1, 300):
        hd.apt_speichern(PFAD, {"v": 1, "t": float(i), "versuch": float(i), "ok": True, "n": i, "sicher": 0})
    fertig.set()


def leser():
    eigene = []
    je_leser.append(eigene)
    while not fertig.is_set():
        try:
            with open(PFAD, encoding="utf-8") as f:
                eigene.append(json.load(f)["n"])
                gelesen.append(eigene[-1])
        except Exception as e:  # noqa: BLE001
            kaputt_gesehen.append(repr(e))


ts = [threading.Thread(target=schreiber)] + [threading.Thread(target=leser) for _ in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]
check(f"300 Schreibvorgänge gegen 3 Leser: {len(gelesen)} Lesungen ohne Fehler und halbe Datei",
      not kaputt_gesehen and len(gelesen) > 50)
check("gelesene Zahlen gehen je Leser nie rückwärts (nie ein älterer Stand nach einem neueren)",
      all(a <= b for e in je_leser for a, b in zip(e, e[1:])))

# ------------------------------------------------------------------------------------------ Hintergrund
reset()
hd.APT_HINTERGRUND = True
tor, begonnen = threading.Event(), threading.Event()
grundlauf = fake({"apt-get": APT, "uname": RPI, "ls": RPI, "find": vor(1)})


def langsam(cmd, timeout=None):
    if "apt-get" in cmd:
        begonnen.set()
        tor.wait(5)
    return grundlauf(cmd, timeout)


t0 = time.time()
check("anstoßen kehrt sofort zurück", hd.apt_anstossen(PFAD, langsam) is True and time.time() - t0 < 1)
begonnen.wait(2)
l1 = hd.apt_lage(NOW, langsam, lambda p: None, PFAD)
check("während der ersten Abfrage: „werden geprüft“, Zahl unbekannt",
      l1["n"] is None and l1["laeuft"] is True and [x["text"] for x in hd.apt_zeilen(l1)] == ["Pi: Updates werden geprüft …"])
check("zweites Anstoßen startet keine zweite Abfrage", hd.apt_anstossen(PFAD, langsam) is False)
tor.set()
warte_auf_ende()
l3 = hd.apt_lage(NOW, langsam, lambda p: None, PFAD)
check("danach steht die Zahl in der Datei und im Bild",
      l3["n"] == 4 and not l3["laeuft"] and [x["text"] for x in hd.apt_zeilen(l3)][0] == "Pi: 4 Updates (3 Sicherheit)")

d = datei(); d["versuch"] = time.time() - 9 * 3600; hd.apt_speichern(PFAD, d)
tor.clear(); begonnen.clear()
hd.apt_anstossen(PFAD, langsam)
begonnen.wait(2)
l4 = hd.apt_lage(NOW, langsam, lambda p: None, PFAD)
check("beim Erneuern bleibt der alte Stand sichtbar", l4["n"] == 4 and l4["laeuft"] is True
      and [x["text"] for x in hd.apt_zeilen(l4)][0] == "Pi: 4 Updates (3 Sicherheit)")
tor.set()
warte_auf_ende()

check("Zeitgrenze 180 s, Intervall 8 h (dreimal am Tag)", hd.APT_TIMEOUT == 180 and hd.APT_INTERVALL_STD == 8 and 24 / hd.APT_INTERVALL_STD == 3)
hd.APT_HINTERGRUND = False
reset()

# ------------------------------------------------------------------------------------------ Zusammenbau
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": time.time(), "versuch": time.time(), "ok": True, "n": 4, "sicher": 3})
run = fake({"apt-get": APT, "uname": RPI, "ls": f"{RPI}\n6.6.62+rpt-rpi-v8", "find": vor(1), "systemctl": None})
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], run=run, read=lambda p: None, apt_datei=PFAD)}
check("Abschnitt „Updates“ enthält die Pi-Zeilen auch ohne signierte Updates",
      [x["text"] for x in sec["updates"]["lines"]] == ["Pi: 4 Updates (3 Sicherheit)", "Neustart nötig (neuer Kernel)"])
reset()
hd.apt_speichern(PFAD, {"v": 1, "t": time.time(), "versuch": time.time(), "ok": True, "n": 0, "sicher": 0})
info = {"eingerichtet": True, "installiert": {"version": "1.52", "wann": "Mi 3:40"}, "bereit": None, "fremd": False}
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], update_info=info, run=fake({}), read=lambda p: None, apt_datei=PFAD)}
check("Pi-Zeilen stehen vor den Zeilen der signierten Updates",
      [x["text"] for x in sec["updates"]["lines"]][:2] == ["Pi: aktuell", "Installiert v1.52 · Mi 3:40"])
reset()
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], run=fake({}), read=lambda p: None)}
check("ohne apt und ohne Updates-Info fehlt der Abschnitt (wie in 1.52)", "updates" not in sec)


def boom(cmd, timeout=3):
    raise RuntimeError("kaputt")


reset()
check("Fehler in run werfen nie", hd.pi_updates(NOW, boom, lambda p: None, PFAD) == [])
reset()
check("Programm ohne timeout-Argument (alte Attrappe) wirft nie", hd.pi_updates(NOW, lambda cmd: None, lambda p: None, PFAD) == [])
check("anstoßen mit alter Attrappe wirft nie", hd.apt_anstossen(PFAD, lambda cmd: None) in (True, False))
warte_auf_ende()

print()
print("ALLES OK" if not FAILED else f"{len(FAILED)} FEHLER: {FAILED}")
sys.exit(1 if FAILED else 0)
