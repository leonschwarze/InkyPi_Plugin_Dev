"""Verteilt gemeinsam genutzte Module auf die Plugins.

shared/eink.py      -> in alle drei Plugins und ins Ausschaltbild
shared/zeichensatz.py -> in alle drei Plugins
dwd_wetter/...      -> tagesdashboard/lib/
nextcloud_kalender/ -> tagesdashboard/lib/


Das Tagesdashboard ist ein eigenständiges Plugin und bringt Kopien der Module
aus dwd_wetter/ und nextcloud_kalender/ mit. Bearbeitet werden immer nur die
Originale; danach dieses Skript ausführen.

  python dev/sync_lib.py          # kopieren
  python dev/sync_lib.py --check  # nur prüfen (Exit-Code 1, wenn veraltet)
"""
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ("shared/eink.py", "dwd_wetter/eink.py"),
    ("shared/eink.py", "nextcloud_kalender/eink.py"),
    ("shared/eink.py", "tagesdashboard/lib/eink.py"),
    ("shared/eink.py", "ausschaltbild/eink.py"),          # Zusatz Ausschaltbild (kein Plugin)
    ("shared/zeichensatz.py", "dwd_wetter/zeichensatz.py"),
    ("shared/zeichensatz.py", "nextcloud_kalender/zeichensatz.py"),
    ("shared/zeichensatz.py", "tagesdashboard/lib/zeichensatz.py"),
    ("dwd_wetter/dwd_wetter.py", "tagesdashboard/lib/dwd_wetter.py"),
    ("dwd_wetter/dwd_icons.py", "tagesdashboard/lib/dwd_icons.py"),
    ("nextcloud_kalender/nextcloud_kalender.py", "tagesdashboard/lib/nextcloud_kalender.py"),
]


def main():
    check = "--check" in sys.argv
    stale = []
    for src, dst in FILES:
        s, d = ROOT / src, ROOT / dst
        if d.exists() and filecmp.cmp(s, d, shallow=False):
            continue
        stale.append(dst)
        if not check:
            shutil.copy2(s, d)
            print(f"aktualisiert: {dst}")
    if check:
        if stale:
            print("Veraltet (python dev/sync_lib.py ausführen):", *stale, sep="\n  ")
            sys.exit(1)
        print("lib/ ist aktuell.")
    elif not stale:
        print("lib/ war schon aktuell.")


if __name__ == "__main__":
    main()
