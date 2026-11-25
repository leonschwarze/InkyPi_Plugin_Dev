"""apt-Updates des Pi im Hilfsbild (tagesdashboard/hilfsdaten.py, seit 1.53) ohne Rendern.

  python dev/test_pi_updates.py

Prüft: Ausgabe von `apt-get -s dist-upgrade` (Anzahl aus der Schlusszeile, Sicherheit aus den Quellen, neu
installierte Pakete zählen nicht, unbrauchbare Ausgabe = unbekannt statt „0“), Kernel-Vergleich für den
Neustart (gleiche Art, neuere Version, ABI-Nummer, fremde Kernelarten, Hinweisdatei), Alter der Paketlisten,
Zeilen (Einzahl, rot nur bei Sicherheit/Neustart/alten Listen), Merken des Ergebnisses und frühere Wiederholung
nach einem Fehlschlag, Zusammenbau im Abschnitt „Updates“, Fehler werfen nie.
"""
import sys
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
        key = cmd[2] if cmd[0] == "env" else cmd[0]
        val = answers.get(key)
        return val() if callable(val) else val
    run.calls = calls
    return run


def reset():
    hd._apt_gemerkt.clear()


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

# ------------------------------------------------------------------------------------------ Merken
reset()
run = fake({"apt-get": APT, "uname": RPI, "ls": RPI, "find": vor(1)})
l1 = hd.apt_lage(NOW, run, lambda p: None)
l2 = hd.apt_lage(NOW, run, lambda p: None)
check("Lage vollständig", l1 == {"n": 4, "sicher": 3, "neustart": None, "alter": l1["alter"]} and abs(l1["alter"] - 1) < 0.01)
check("apt läuft nur einmal (zweiter Aufruf aus dem Gedächtnis), mit LC_ALL=C und Zeitgrenze",
      sum(1 for c, _ in run.calls if "apt-get" in c) == 1
      and run.calls[0] == (["env", "LC_ALL=C", "apt-get", "-s", "dist-upgrade"], hd.APT_TIMEOUT))
hd._apt_gemerkt["bis"] = time.time() - 1
hd.apt_lage(NOW, run, lambda p: None)
check("nach Ablauf wieder", sum(1 for c, _ in run.calls if "apt-get" in c) == 2)

reset()
bad = fake({"apt-get": None})
hd.apt_lage(NOW, bad, lambda p: None)
frist = hd._apt_gemerkt["bis"] - time.time()
check("Fehlschlag wird früher wiederholt als ein Erfolg (10 statt 60 min)", 8 * 60 < frist <= 10 * 60 + 1)
check("Fehlschlag lässt die Zahl unbekannt", hd.apt_lage(NOW, bad, lambda p: None)["n"] is None)

# ------------------------------------------------------------------------------------------ Zusammenbau
reset()
run = fake({"apt-get": APT, "uname": RPI, "ls": f"{RPI}\n6.6.62+rpt-rpi-v8", "find": vor(1), "systemctl": None})
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], run=run, read=lambda p: None)}
check("Abschnitt „Updates“ enthält die Pi-Zeilen auch ohne signierte Updates",
      [x["text"] for x in sec["updates"]["lines"]] == ["Pi: 4 Updates (3 Sicherheit)", "Neustart nötig (neuer Kernel)"])
reset()
info = {"eingerichtet": True, "installiert": {"version": "1.52", "wann": "Mi 3:40"}, "bereit": None, "fremd": False}
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], update_info=info, run=fake({"apt-get": APT_NULL}), read=lambda p: None)}
check("Pi-Zeilen stehen vor den Zeilen der signierten Updates",
      [x["text"] for x in sec["updates"]["lines"]][:2] == ["Pi: aktuell", "Installiert v1.52 · Mi 3:40"])
reset()
sec = {s["key"]: s for s in hd.abschnitte(NOW, [], run=fake({}), read=lambda p: None)}
check("ohne apt und ohne Updates-Info fehlt der Abschnitt (wie in 1.52)", "updates" not in sec)


def boom(cmd, timeout=3):
    raise RuntimeError("kaputt")


reset()
check("Fehler in run werfen nie", hd.pi_updates(NOW, boom, lambda p: None) == [])
reset()
check("Programm ohne timeout-Argument (alte Attrappe) wirft nie", hd.pi_updates(NOW, lambda cmd: None, lambda p: None) == [])

print()
print("ALLES OK" if not FAILED else f"{len(FAILED)} FEHLER: {FAILED}")
sys.exit(1 if FAILED else 0)
