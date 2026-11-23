"""InkyPis Entwicklungsserver (`inkypi.py --dev`, Port 8080) mit den Netz-Attrappen aus dev/ starten.

Für Ende-zu-Ende-Tests, in denen InkyPi das Dashboard selbst zeichnet (dev/test_aktualisierung.py):
Wetter, Nachrichten, Radar usw. kommen aus den Mocks, die Uhr läuft echt. Kalender nur, wenn die Instanz
einen hat (die Tests lassen ihn weg).

    python dev/inkypi_mit_mocks.py /pfad/zu/InkyPi/src
"""

import contextlib
import os
import runpy
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEV = Path(__file__).resolve().parent


def main():
    src = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(DEV))
    sys.path.insert(0, str(src))
    os.chdir(src)
    os.environ.setdefault("FONTCONFIG_FILE", str(DEV / "fonts-eink.conf"))
    now = datetime.now(ZoneInfo("Europe/Berlin"))

    import mock_brightsky
    mock_brightsky.install(now, "herbst")
    for name, kind in [("mock_news", "normal"), ("mock_radar", "trocken"), ("mock_luft", "gut"),
                       ("mock_pollen", "gut"), ("mock_pegel", "keine"), ("mock_polar", "keine"),
                       ("mock_nina", "keine"), ("mock_xkcd", "normal")]:
        __import__(name).install(now, kind)
    __import__("mock_schnee").install(now, "normal", "herbst")
    # Diese Mocks brauchen Module des Plugins; ist das Plugin kaputt, startet InkyPi trotzdem
    with contextlib.suppress(Exception):
        __import__("mock_klima").install(now, "normal", __import__("plugins.tagesdashboard.klima", fromlist=["x"]))
    with contextlib.suppress(Exception):
        __import__("mock_pi").install(now, "ok", __import__("plugins.tagesdashboard.pizustand", fromlist=["x"]))
    with contextlib.suppress(Exception):
        __import__("mock_ziel").install(now)

    sys.argv = ["inkypi.py", "--dev"]
    runpy.run_path(str(src / "inkypi.py"), run_name="__main__")


if __name__ == "__main__":
    main()
