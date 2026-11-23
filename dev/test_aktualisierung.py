"""Signierte Updates (aktualisierung/, seit 1.44) ohne Pi und ohne GitHub testen.

  python dev/test_aktualisierung.py            (~2 min; braucht git, ssh-keygen ≥ 8.2, Chromium wie render.py)

Aufbau: zwei Test-Schlüssel („leon“ = freigegeben, „fremd“), zwei lokale Repos statt GitHub, eine Kopie von
InkyPi, die mit dev/inkypi_mit_mocks.py als Entwicklungsserver läuft (Port 8080, darf nicht belegt sein).
Geprüft wird, dass nur gültig signierte, passende und neuere Versionen installiert werden, dass kaputte
Versionen gar nicht erst live gehen bzw. zurückgenommen werden, die Selbstprüfung des Klons, install.sh des
Updaters und freigeben.sh. Als root (z. B. im Container) zusätzlich das Ausschaltbild mit seinem echten
install.sh – dann werden /usr/local/inkypi, /usr/local/inkypi-ausschaltbild und /etc/systemd/system/
inkypi-ausschaltbild*.service vorübergehend angelegt (nur, wenn es sie noch nicht gibt).
"""
import json
import re
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")).resolve()
UPDATER = Path(os.environ.get("UPDATER_TEST", ROOT / "aktualisierung" / "inkypi_update.py"))  # Gegenproben
T = Path(tempfile.mkdtemp(prefix="inkypi-update-test-"))
os.chmod(T, 0o755)
ALS_ROOT = os.geteuid() == 0
fails = 0

# Saubere Git-Umgebung: keine globalen Einstellungen (Signier-Programme, Hooks …) des Entwicklungsrechners
GITENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="Claude",
              GIT_AUTHOR_EMAIL="noreply@anthropic.com", GIT_COMMITTER_NAME="Leon", GIT_COMMITTER_EMAIL="leon@example.org")


def check(cond, msg):
    global fails
    print(("ok    " if cond else "FEHLER") + " " + msg, flush=True)
    if not cond:
        fails += 1


def sh(*cmd, cwd=None, env=None, eingabe=None, ok=True):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env or GITENV, input=eingabe, capture_output=True, text=True)
    if ok and r.returncode != 0:
        raise SystemExit(f"Befehl fehlgeschlagen: {' '.join(map(str, cmd))}\n{r.stdout}{r.stderr}")
    return r


def port_frei():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", 8080)) != 0


# ---------------------------------------------------------------------------------------------------------------
# Schlüssel, „GitHub“, InkyPi-Kopie

KEYS = T / "keys"
KEYS.mkdir()
for name in ("leon", "fremd"):
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", KEYS / name)
PUB = (KEYS / "leon.pub").read_text().strip()
BASIS = T / "basis"
BASIS.mkdir(mode=0o755)
SIGNERS = BASIS / "allowed_signers"
SIGNERS.write_text(f'leon namespaces="git" {PUB}\n')
os.chmod(SIGNERS, 0o644)

GH = T / "gh"
REPONAME = {"dashboard": "InkyPi_Dashboard", "aus": "InkyPi_Ausschaltbild"}   # wie auf GitHub (freigeben.sh prüft das)
for repo in ("dashboard", "aus"):
    sh("git", "init", "-q", "--bare", "-b", "main", GH / f"{REPONAME[repo]}.git")
    sh("git", "clone", "-q", GH / f"{REPONAME[repo]}.git", T / "arbeit" / repo)


def stand_schreiben(version, kaputt=None):
    """Dashboard-Repo auf Version bringen und pushen. kaputt: None, "import" oder "zeichnen"."""
    w = T / "arbeit" / "dashboard"
    for d in ("tagesdashboard", "aktualisierung"):
        shutil.rmtree(w / d, ignore_errors=True)
        shutil.copytree(ROOT / d, w / d, ignore=shutil.ignore_patterns("__pycache__"))
    info = json.loads((w / "tagesdashboard" / "plugin-info.json").read_text())
    info["version"] = version
    (w / "tagesdashboard" / "plugin-info.json").write_text(json.dumps(info, indent=4) + "\n")
    with open(w / "tagesdashboard" / "tagesdashboard.py", "a") as f:
        if kaputt == "import":
            f.write("\ndef kaputt(:\n")
        elif kaputt == "zeichnen":
            f.write("\ndef _kaputt(self, settings, device_config):\n    raise RuntimeError('Testfehler 1.45')\n"
                    "Tagesdashboard.generate_image = _kaputt\n")
    sh("git", "add", "-A", cwd=w)
    sh("git", "commit", "-q", "-m", f"{version}{' (kaputt)' if kaputt else ''}", cwd=w)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=w)


def taggen(repo, name, schluessel="leon", signiert=True, push=True):
    w = T / "arbeit" / repo
    if signiert:
        sh("git", "-c", "gpg.format=ssh", "-c", "gpg.ssh.program=ssh-keygen", "-c",
           f"user.signingkey={KEYS / schluessel}", "tag", "-s", name, "-m", f"Test {name}", cwd=w)
    else:
        sh("git", "tag", "-a", name, "-m", f"Test {name}", cwd=w)
    if push:
        sh("git", "push", "-q", "origin", f"refs/tags/{name}", cwd=w)


# InkyPi-Kopie wie auf dem Pi: /usr/local/inkypi/src -> Klon/src, venv-Python
IK = T / "InkyPi"
shutil.copytree(INKYPI / "src", IK / "src", symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
for p in (IK / "src" / "plugins").iterdir():
    if p.is_symlink():
        p.unlink()
shutil.copytree(ROOT / "tagesdashboard", IK / "src" / "plugins" / "tagesdashboard",
                ignore=shutil.ignore_patterns("__pycache__"))
alt_info = IK / "src" / "plugins" / "tagesdashboard" / "plugin-info.json"
alt_info.write_text(re.sub(r'"version": "[0-9.]+"', '"version": "1.42"', alt_info.read_text()))
dev_json = IK / "src" / "config" / "device_dev.json"
d = json.loads(dev_json.read_text())
d["playlist_config"]["playlists"][0]["plugins"] = [{
    "plugin_id": "tagesdashboard", "name": "Dashboard", "refresh": {"interval": 900},
    "plugin_settings": {"latitude": "50.7374", "longitude": "7.0982"}}]
dev_json.write_text(json.dumps(d, indent=1))
dev_geraet = dict(d, display_type="inky")
(IK / "src" / "config" / "device.json").write_text(json.dumps(dev_geraet, indent=1))

PI = T / "inkypi"
(PI / "venv_inkypi" / "bin").mkdir(parents=True)
(PI / "src").symlink_to(IK / "src")
FAKE = T / "fake"
(FAKE / "inky").mkdir(parents=True)
(FAKE / "inky" / "__init__.py").write_text("")
(FAKE / "inky" / "auto.py").write_text("def auto(**kw):\n    raise RuntimeError('kein Display im Test')\n")
py = PI / "venv_inkypi" / "bin" / "python"
py.write_text(f'#!/bin/bash\nexport PYTHONPATH="{FAKE}${{PYTHONPATH:+:$PYTHONPATH}}"\nexec "{sys.executable}" "$@"\n')
py.chmod(0o755)

# systemctl-Attrappe (protokolliert), Neustart = Entwicklungsserver neu starten
(T / "systemd").mkdir()
BIN = T / "bin"
BIN.mkdir()
(BIN / "systemctl").write_text(f'#!/bin/bash\necho "$*" >> "{T}/systemctl.log"\n'
                               'if [ "$1" = is-active ]; then echo inactive; exit 3; fi\nexit 0\n')
(BIN / "systemctl").chmod(0o755)
NEUSTART = T / "neustart.sh"
NEUSTART.write_text(f'''#!/bin/bash
if [ -f "{T}/inkypi.pid" ]; then kill "$(cat "{T}/inkypi.pid")" 2>/dev/null; sleep 1; fi
for i in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8080) 2>/dev/null || break; sleep 0.5; done
cd "{DEV}"
nohup "{sys.executable}" "{DEV / 'inkypi_mit_mocks.py'}" "{IK / 'src'}" >> "{T}/inkypi.log" 2>&1 &
echo $! > "{T}/inkypi.pid"
''')
ENV = dict(GITENV, PATH=f"{BIN}:{os.environ['PATH']}")

KONFIG = T / "konfig.json"
KONFIG.write_text(json.dumps({
    "basis": str(BASIS), "daten": str(T / "daten"), "inkypi": str(PI),
    "ausschaltbild_ziel": "/usr/local/inkypi-ausschaltbild" if ALS_ROOT else str(T / "aus_ziel"),
    "web": "http://127.0.0.1:8080", "device_json": str(dev_json),
    "systemd": str(T / "systemd"),
    "repos": {"tagesdashboard": f"file://{GH / 'InkyPi_Dashboard.git'}", "ausschaltbild": f"file://{GH / 'InkyPi_Ausschaltbild.git'}"},
    "neustart": ["bash", str(NEUSTART)], "warte_web_s": 90, "zeichnen_versuche": 1, "zeichnen_pause_s": 1,
}))


def update(*args):
    r = subprocess.run([sys.executable, UPDATER, "--konfig", KONFIG, *args], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout + r.stderr


def installierte_version():
    return json.loads((IK / "src" / "plugins" / "tagesdashboard" / "plugin-info.json").read_text()).get("version")


def stand():
    p = T / "daten" / "stand.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------------------------------------------------------------------------------------------------------
if not port_frei():
    sys.exit("Port 8080 ist belegt – läuft schon ein InkyPi? Bitte beenden.")
print(f"Testordner: {T}\n")
try:
    sh("bash", NEUSTART)
    print("— Prüfen, was als Freigabe zählt (--pruefen, nur Dashboard)")
    stand_schreiben("1.43")
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check(rc == 0 and "keine neuere freigegebene Version" in out, "ohne Tags: nichts zu tun")

    taggen("dashboard", "v1.43", signiert=False)
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check("v1.43 abgelehnt: nicht signiert" in out, "unsigniertes Tag abgelehnt")
    sh("git", "push", "-q", "origin", ":refs/tags/v1.43", cwd=T / "arbeit" / "dashboard")
    sh("git", "tag", "-d", "v1.43", cwd=T / "arbeit" / "dashboard")

    taggen("dashboard", "v1.43", schluessel="fremd")
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check("v1.43 abgelehnt: Signatur von einem unbekannten Schlüssel" in out, "Tag mit fremdem Schlüssel abgelehnt")
    sh("git", "push", "-q", "origin", ":refs/tags/v1.43", cwd=T / "arbeit" / "dashboard")
    sh("git", "tag", "-d", "v1.43", cwd=T / "arbeit" / "dashboard")

    sh("git", "tag", "v1.43", cwd=T / "arbeit" / "dashboard")       # leichtgewichtiges Tag
    sh("git", "push", "-q", "origin", "refs/tags/v1.43", cwd=T / "arbeit" / "dashboard")
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check("v1.43 abgelehnt" in out and "freigegeben v1.43" not in out, "Tag ohne Tag-Objekt abgelehnt")
    sh("git", "push", "-q", "origin", ":refs/tags/v1.43", cwd=T / "arbeit" / "dashboard")
    sh("git", "tag", "-d", "v1.43", cwd=T / "arbeit" / "dashboard")

    taggen("dashboard", "v1.43")
    taggen("dashboard", "v1.44")                                       # Code sagt 1.43
    sh("git", "push", "-q", "origin", "refs/tags/v1.43:refs/tags/v1.50", cwd=T / "arbeit" / "dashboard")  # umbenannt
    taggen("dashboard", "v9.9", signiert=False)
    # Signatur von v1.43, aber auf einen anderen Commit umgebogen
    w = T / "arbeit" / "dashboard"
    roh = sh("git", "cat-file", "tag", "v1.43", cwd=w).stdout
    erster = sh("git", "rev-list", "--max-parents=0", "HEAD", cwd=w).stdout.strip()
    zeilen = roh.split("\n")
    zeilen[0] = f"object {erster}" if erster else zeilen[0]
    gefaelscht = "\n".join(z.replace("tag v1.43", "tag v1.45") if z.startswith("tag ") else z for z in zeilen)
    obj = sh("git", "hash-object", "-t", "tag", "-w", "--stdin", "--literally", cwd=w, eingabe=gefaelscht).stdout.strip()
    sh("git", "push", "-q", "origin", f"{obj}:refs/tags/v1.45", cwd=w)
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check("v9.9 abgelehnt: nicht signiert" in out, "unsigniertes v9.9 abgelehnt …")
    check("v1.50 abgelehnt: heißt innen „v1.43“" in out, "umbenanntes Tag (v1.43 als v1.50) abgelehnt")
    check("v1.45 abgelehnt: Signatur ungültig" in out, "umgebogenes Tag (fremder Commit, alte Signatur) abgelehnt")
    check("v1.44 abgelehnt: im Code steht Version 1.43" in out, "Tag mit falscher Version im Code abgelehnt")
    check("freigegeben v1.43" in out and "signiert von leon" in out, "… und trotzdem wird v1.43 gefunden")
    check(installierte_version() == "1.42" and "version" not in stand().get("tagesdashboard", {}),
          "--pruefen installiert nichts")
    ll = stand().get("letzter_lauf", {})
    check(stand()["tagesdashboard"].get("bereit") == "v1.43" and ll.get("art") == "prüfen"
          and "v1.43 liegt bereit" in ll.get("text", ""), "… merkt sich aber „v1.43 liegt bereit“ für die Einstellungsseite")
    for t in ("v1.44", "v1.50", "v9.9", "v1.45"):
        sh("git", "push", "-q", "origin", f":refs/tags/{t}", cwd=w)
        sh("git", "tag", "-d", t, cwd=w, ok=False)

    os.chmod(SIGNERS, 0o664)
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check(rc == 1 and "nur von root beschreibbar" in out, "allowed_signers für andere beschreibbar → verweigert")
    os.chmod(SIGNERS, 0o644)

    print("\n— Installieren (Ende zu Ende gegen InkyPi --dev)")
    rc, out = update("--nur", "tagesdashboard")
    check(rc == 0 and "Vortest ok" in out and "Dashboard gezeichnet" in out and "v1.43 installiert" in out,
          "v1.43: Vortest, Tausch, Neustart, Dashboard gezeichnet")
    check(installierte_version() == "1.43" and stand().get("tagesdashboard", {}).get("version") == "1.43",
          "Plugin-Ordner und stand.json auf 1.43")
    check((T / "daten" / "sicherung" / "tagesdashboard" / "plugin-info.json").exists(), "alter Stand (1.42) gesichert")
    check((BASIS / "inkypi_update.py").exists() and "Updater erneuert" in out, "Updater aus demselben Stand erneuert")
    check(not (IK / "src" / "plugins" / "tagesdashboard" / ".git").exists()
          and not (IK / "src" / "plugins" / "tagesdashboard" / "aktualisierung").exists(), "nur der Plugin-Ordner")
    rc, out = update("--nur", "tagesdashboard")
    check(rc == 0 and "keine neuere freigegebene Version" in out, "zweiter Lauf: nichts zu tun")
    ll = stand().get("letzter_lauf", {})
    check(ll.get("text") == "Dashboard aktuell" and not ll.get("fehler") and ll.get("art") == "von Hand"
          and "bereit" not in stand()["tagesdashboard"], "… letzter Lauf „Dashboard aktuell“, „bereit“ gelöscht")

    stand_schreiben("1.44", kaputt="import")
    taggen("dashboard", "v1.44")
    rc, out = update("--nachts", "--nur", "tagesdashboard")
    check(rc == 1 and "Vortest" in out and "Dashboard gezeichnet" not in out, "v1.44 (lädt nicht): Vortest hält sie auf")
    check(installierte_version() == "1.43", "… Plugin bleibt 1.43")
    check(stand()["fehlversuche"]["tagesdashboard"].get("v1.44") == 1, "… Fehlversuch gezählt")
    ll = stand().get("letzter_lauf", {})
    check(ll.get("fehler") == 1 and ll.get("art") == "nachts" and ll.get("text", "").startswith("Dashboard: Fehler – "),
          "… letzter Lauf zeigt den Fehler")

    stand_schreiben("1.45", kaputt="zeichnen")
    taggen("dashboard", "v1.45")
    rc, out = update("--nur", "tagesdashboard")
    check(rc == 1 and "FEHLER mit der neuen Version" in out and "Testfehler 1.45" in out,
          "v1.45 (Fehler beim Zeichnen): nach dem Neustart erkannt")
    check("Rückfall auf den alten Stand: Dashboard gezeichnet" in out and installierte_version() == "1.43",
          "… zurück auf 1.43, InkyPi zeichnet wieder")
    check((T / "daten" / "fehlgeschlagen" / "tagesdashboard" / "plugin-info.json").exists(), "… 1.45 zum Ansehen aufbewahrt")

    s = stand()
    s["fehlversuche"]["tagesdashboard"] = {"v1.44": 3, "v1.45": 3}
    (T / "daten" / "stand.json").write_text(json.dumps(s))
    rc, out = update("--nachts", "--nur", "tagesdashboard")
    check(rc == 0 and "nachts ausgelassen nach 3 Fehlversuchen" in out, "nachts: nach drei Fehlversuchen ausgelassen")

    stand_schreiben("1.46")
    taggen("dashboard", "v1.46")
    rc, out = update("--nachts", "--nur", "tagesdashboard")
    check(rc == 0 and installierte_version() == "1.46", "v1.46 repariert: nachts installiert")
    rc, out = update("--nur", "tagesdashboard", "--version", "v1.43")
    check(rc == 0 and "ACHTUNG" in out and installierte_version() == "1.43", "--version v1.43: bewusst zurück auf ältere Freigabe")
    rc, out = update("--nachts", "--nur", "tagesdashboard")
    check(installierte_version() == "1.46", "nächste Nacht wieder 1.46 (höchste Freigabe)")

    print("\n— Selbstprüfung des Klons (für install.sh)")
    k = T / "klon"
    sh("git", "clone", "-q", "--branch", "v1.46", f"file://{GH / 'InkyPi_Dashboard.git'}", k)
    r = subprocess.run([sys.executable, UPDATER, "--konfig", KONFIG, "--klon-pruefen", k], capture_output=True, text=True, env=ENV)
    check(r.returncode == 0 and "Klon geprüft: v1.46" in r.stdout, "Klon auf v1.46: geprüft")
    (k / "tagesdashboard" / "kleidung.py").write_text("# verändert\n")
    r = subprocess.run([sys.executable, UPDATER, "--konfig", KONFIG, "--klon-pruefen", k], capture_output=True, text=True, env=ENV)
    check(r.returncode == 1 and "verändert" in r.stderr, "veränderte Datei im Klon: abgelehnt")
    sh("git", "checkout", "-q", "--", ".", cwd=k)
    (k / "tagesdashboard" / "extra.py").write_text("print('hallo')\n")
    r = subprocess.run([sys.executable, UPDATER, "--konfig", KONFIG, "--klon-pruefen", k], capture_output=True, text=True, env=ENV)
    check(r.returncode == 1, "zusätzliche Datei im Klon: abgelehnt")
    (k / "tagesdashboard" / "extra.py").unlink()
    sh("git", "checkout", "-q", "main", cwd=k)
    sh("git", "reset", "-q", "--hard", "v1.45", cwd=k)
    sh("git", "tag", "-d", "v1.45", cwd=k)
    r = subprocess.run([sys.executable, UPDATER, "--konfig", KONFIG, "--klon-pruefen", k], capture_output=True, text=True, env=ENV)
    check(r.returncode == 1 and "nicht auf einem Versions-Tag" in r.stderr, "Klon ohne Tag: abgelehnt")

    print("\n— freigeben.sh (auf Leons Rechner)")
    home = T / "home"
    (home / ".ssh").mkdir(parents=True)
    shutil.copy(KEYS / "leon", home / ".ssh" / "inkypi_freigabe")
    shutil.copy(KEYS / "leon.pub", home / ".ssh" / "inkypi_freigabe.pub")
    os.chmod(home / ".ssh" / "inkypi_freigabe", 0o600)
    stand_schreiben("1.47")
    fk = T / "freigabe-klon"
    sh("git", "clone", "-q", f"file://{GH / 'InkyPi_Dashboard.git'}", fk)
    fenv = dict(GITENV, HOME=str(home))
    r = sh("bash", ROOT / "aktualisierung" / "freigeben.sh", fk, env=fenv, eingabe="n\n", ok=False)
    check(r.returncode == 0 and "Tagesdashboard 1.47" in r.stdout and "Abgebrochen" in r.stdout
          and not sh("git", "ls-remote", "--tags", GH / "InkyPi_Dashboard.git", "v1.47").stdout, "„n“: nichts freigegeben")
    r = subprocess.run(["bash", str(ROOT / "aktualisierung" / "freigeben.sh")], cwd=fk / "tagesdashboard",
                       env=fenv, input="n\n", capture_output=True, text=True)
    check(r.returncode == 0 and "Tagesdashboard 1.47" in r.stdout, "aus einem Unterordner gestartet: findet den Klon")
    r = subprocess.run(["bash", str(ROOT / "aktualisierung" / "freigeben.sh")], cwd=T, env=fenv, input="n\n",
                       capture_output=True, text=True)
    check(r.returncode == 1 and "InkyPi_Dashboard" not in r.stdout, "außerhalb eines Klons, Skript nicht im Klon: verweigert")
    r = sh("bash", ROOT / "aktualisierung" / "freigeben.sh", fk, env=fenv, eingabe="j\n", ok=False)
    check(r.returncode == 0 and "Freigegeben: v1.47" in r.stdout, "„j“: v1.47 signiert und gepusht")
    rc, out = update("--pruefen", "--nur", "tagesdashboard")
    check("freigegeben v1.47" in out and "signiert von leon" in out, "… der Pi erkennt v1.47 als freigegeben")
    r = sh("bash", ROOT / "aktualisierung" / "freigeben.sh", fk, env=fenv, eingabe="j\n", ok=False)
    check(r.returncode == 1 and "gibt es schon" in r.stderr, "zweimal dieselbe Version: verweigert")
    (fk / "README.md").write_text("geändert\n")
    r = sh("bash", ROOT / "aktualisierung" / "freigeben.sh", fk, env=fenv, eingabe="j\n", ok=False)
    check(r.returncode == 1 and "Änderungen" in r.stderr, "Klon mit lokalen Änderungen: verweigert")
    (fk / "README.md").unlink()
    stand_schreiben("1.48")
    r = sh("bash", ROOT / "aktualisierung" / "freigeben.sh", fk, env=fenv, eingabe="j\n", ok=False)
    check(r.returncode == 1 and "git pull" in r.stderr, "Klon nicht auf dem Stand von GitHub: verweigert")

    print("\n— Ausschaltbild")
    aw = T / "arbeit" / "aus"
    shutil.copytree(ROOT / "ausschaltbild", aw / "ausschaltbild", ignore=shutil.ignore_patterns("__pycache__"))
    sh("git", "add", "-A", cwd=aw)
    sh("git", "commit", "-q", "-m", "Ausschaltbild 1.1", cwd=aw)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=aw)
    taggen("aus", "v1.1")
    if not ALS_ROOT:
        rc, out = update("--nur", "ausschaltbild")
        check(rc == 0 and "nicht installiert – übersprungen" in out, "nicht installiert: übersprungen")
        print("(Installation des Ausschaltbilds nur als root getestet)")
    else:
        angelegt = []
        ziel = Path("/usr/local/inkypi-ausschaltbild")
        if Path("/usr/local/inkypi").exists() or ziel.exists():
            print("(/usr/local/inkypi oder das Ausschaltbild gibt es schon – Installation übersprungen)")
        else:
            try:
                rc, out = update("--nur", "ausschaltbild")
                check(rc == 0 and "nicht installiert – übersprungen" in out, "nicht installiert: übersprungen")
                Path("/usr/local/inkypi").symlink_to(PI)
                angelegt.append(Path("/usr/local/inkypi"))
                ziel.mkdir()
                angelegt.append(ziel)
                (ziel / "ausschaltbild.py").write_text('VERSION = "1.0"\n# alter Stand\n')
                rc, out = update("--nur", "ausschaltbild")
                check(rc == 0 and "Vortest ok (Probebild erzeugt)" in out and "install.sh ok" in out
                      and "v1.1 installiert" in out, "v1.1: Probebild, echtes install.sh")
                check((ziel / "ausschaltbild.py").read_bytes() == (ROOT / "ausschaltbild" / "ausschaltbild.py").read_bytes()
                      and (ziel / "eink.py").exists(), "… Dateien in /usr/local/inkypi-ausschaltbild")
                log = (T / "systemctl.log").read_text()
                check("enable --now inkypi-ausschaltbild.service" in log and "enable inkypi-ausschaltbild-start.service" in log,
                      "… beide Dienste eingeschaltet")
                # Kaputte Version: install.sh scheitert an der Probe → alter Stand zurück
                (aw / "ausschaltbild" / "ausschaltbild.py").write_text(
                    (aw / "ausschaltbild" / "ausschaltbild.py").read_text().replace('VERSION = "1.1"', 'VERSION = "1.2"')
                    .replace("    if a.probe:\n", "    if a.probe:\n        raise SystemExit('Testfehler Probe')\n"))
                sh("git", "commit", "-q", "-am", "1.2 kaputt", cwd=aw)
                sh("git", "push", "-q", "origin", "HEAD:main", cwd=aw)
                taggen("aus", "v1.2")
                rc, out = update("--nur", "ausschaltbild")
                check(rc == 1 and "FEHLER in install.sh" in out and "Rückfall" in out, "v1.2 (Probe scheitert): Rückfall")
                check((ziel / "ausschaltbild.py").read_bytes() == (ROOT / "ausschaltbild" / "ausschaltbild.py").read_bytes(),
                      "… wieder 1.1 installiert")
            finally:
                for p in (Path("/etc/systemd/system/inkypi-ausschaltbild.service"),
                          Path("/etc/systemd/system/inkypi-ausschaltbild-start.service")):
                    if ziel in angelegt and p.exists():
                        p.unlink()
                for p in reversed(angelegt):
                    if p.is_symlink():
                        p.unlink()
                    elif p.exists():
                        shutil.rmtree(p)

    print("\n— install.sh des Updaters")
    inst = ROOT / "aktualisierung" / "install.sh"
    text = inst.read_text()
    check("--klon-pruefen" in text and "allowed_signers" in text and "/usr/local/bin/inkypi-update" in text,
          "install.sh prüft den Klon und richtet Befehl und Schlüssel ein")
    timer = (ROOT / "aktualisierung" / "inkypi-update.timer").read_text()
    check("OnCalendar=*-*-* 03:30:00" in timer and "Persistent=false" in timer, "Timer 3:30 Uhr, nicht nachholen")
    for n in ("inkypi_update.py", "install.sh", "uninstall.sh", "freigeben.sh"):
        bad = [z for z in (ROOT / "aktualisierung" / n).read_text().splitlines() if "\t" in z]
        check(not bad, f"{n}: keine Tabulatoren")
    r = sh("bash", "-n", inst, ok=False)
    check(r.returncode == 0, "install.sh: Syntax ok")
finally:
    if (T / "inkypi.pid").exists():
        subprocess.run(["kill", (T / "inkypi.pid").read_text().strip()], capture_output=True)

print(f"\n{'Alles ok.' if not fails else f'{fails} Fehler.'}  (Testordner {T})")
sys.exit(1 if fails else 0)
