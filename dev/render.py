"""Rendert ein Plugin mit Testdaten zu PNG-Dateien – ohne Display, Internet oder Nextcloud.

Beispiele:
  python dev/render.py tagesdashboard
  python dev/render.py dwd_wetter --scenario winter --sizes 800x480,480x800v
  python dev/render.py tagesdashboard --time "2026-11-10 21:12" --set sensitivity=sehr
  python dev/render.py tagesdashboard --fail kalender
  python dev/render.py tagesdashboard --time "2026-11-10 07:42" --train spaet   # Zug im Zeitfenster
  python dev/render.py tagesdashboard --time "2026-11-10 07:12" --train ok --strecke stoerung   # Streckenmeldung (VRR)
  python dev/render.py tagesdashboard --time "2026-11-11 07:20" --news ohnega   # Nachrichten, GA-Feed fehlt
  python dev/render.py tagesdashboard --air schlecht --scenario trocken          # Luftqualität (Bürgersensoren)
  python dev/render.py tagesdashboard --fail kalender --radar down --seit 9:10   # Statusanzeige: Ausfall seit 9:10
  python dev/render.py tagesdashboard --gestern -4                              # „4° kälter als gestern“

Ablauf:
  * verlinkt die Plugin-Ordner dieses Repos nach <InkyPi>/src/plugins/ (falls noch nicht vorhanden)
  * ersetzt die Bright-Sky-API durch simulierte Daten (dev/mock_brightsky.py)
  * startet einen CalDAV-Testserver mit Testterminen (dev/caldav_server.py)
  * friert die Uhrzeit ein (Methode current_time() der Plugins)
  * rendert über InkyPis eigene Pipeline (Jinja + Chromium-Screenshot)

Größen: "800x480" = Querformat, "480x800v" = Display hochkant gedreht (orientation vertical).

Display-Nachbildung (Standard: wie ein Inky Impression mit Schrift ohne Kantenglättung):
  --display inky|mock   inky = Plugins rasten die Farben ein (wie auf dem Pi), mock = unverändert
  --font eink|mono|aa   eink = Autohinter, Kanten von eink.py eingerastet (dev/fonts-eink.conf, wie auf dem Pi empfohlen)
                        mono = ganz ohne Kantenglättung (dev/fonts-mono.conf, nur zum Vergleich), aa = Systemstandard
  --simulate            zusätzlich *_display.png: so sieht es nach dem Pimoroni-Treiber aus
InkyPi-Pfad: --inkypi oder Umgebungsvariable INKYPI_DIR, sonst ../InkyPi neben diesem Repo.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
DEV = REPO / "dev"
PLUGINS = {
    "dwd_wetter": "DwdWetter",
    "nextcloud_kalender": "NextcloudKalender",
    "tagesdashboard": "Tagesdashboard",
}
TZ = ZoneInfo("Europe/Berlin")

BASE_SETTINGS = {
    "latitude": "50.7374", "longitude": "7.0982",
    "textColor": "#000000", "backgroundOption": "color", "backgroundColor": "#ffffff",
}


class DevConfig:
    """Minimaler Ersatz für InkyPis Config-Objekt."""

    def __init__(self, resolution, orientation, env, display_type="inky", saturation=0.5):
        self.resolution, self.orientation, self.env = resolution, orientation, env
        self.values = {"timezone": "Europe/Berlin", "orientation": orientation, "time_format": "24h",
                       "display_type": display_type, "image_settings": {"inky_saturation": saturation}}

    def get_config(self, key, default=None):
        return self.values.get(key, default)

    def get_resolution(self):
        return self.resolution

    def load_env_key(self, key):
        return self.env.get(key)


def parse_sizes(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        vertical = part.endswith("v")
        w, h = (int(x) for x in part.rstrip("v").split("x"))
        # InkyPi kennt die physische Auflösung (quer) und dreht per orientation
        res = (h, w) if vertical else (w, h)
        out.append((part, res, "vertical" if vertical else "horizontal"))
    return out


def link_plugins(inkypi_src):
    target = inkypi_src / "plugins"
    for name in PLUGINS:
        dst = target / name
        if dst.is_symlink() or dst.exists():
            if dst.resolve() != (REPO / name).resolve():
                print(f"Hinweis: {dst} zeigt nicht auf dieses Repo – es wird die dortige Version verwendet.")
            continue
        dst.symlink_to(REPO / name, target_is_directory=True)
        print(f"verlinkt: {dst} -> {REPO / name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin", choices=PLUGINS)
    ap.add_argument("--inkypi", default=os.environ.get("INKYPI_DIR", str(REPO.parent / "InkyPi")))
    ap.add_argument("--time", default="2026-11-10 15:07", help='feste Uhrzeit, z. B. "2026-11-10 21:12"')
    ap.add_argument("--scenario", default="herbst", choices=["herbst", "winter", "sommer", "ruhig", "klar", "trocken", "nebel", "bedeckt", "regenbogen"])
    ap.add_argument("--sizes", default="800x480,480x800v,1600x1200")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Plugin-Einstellung setzen")
    ap.add_argument("--fail", choices=["wetter", "kalender", "uv"], help="Ausfall einer Datenquelle simulieren")
    ap.add_argument("--seit", metavar="HH:MM", help="Statusanzeige: simulierte Ausfälle laufen schon seit dieser "
                    "Uhrzeit (am Tag von --time, oder \"gestern 22:40\"). Ohne: Ausfall beginnt jetzt")
    ap.add_argument("--train", choices=["ok", "leicht", "spaet", "ausfall", "gleis", "kurz", "stoerung", "sev", "ohnelive", "down"],
                    help="Tagesdashboard: Zuganzeige einschalten und Bahn-Daten simulieren (Zeit im Zugfenster wählen)")
    ap.add_argument("--strecke", default="ruhig", choices=["ruhig", "stoerung", "gesperrt", "baustelle", "behoben",
                                                          "beides", "down"],
                    help="Tagesdashboard mit --train: simulierte Streckenmeldungen der VRR-Auskunft (dev/mock_vrr.py)")
    ap.add_argument("--news", choices=["normal", "ohnega", "keine"], default="normal",
                    help="Tagesdashboard: simulierte Nachrichten-Feeds (sichtbar werktags 6–9:30, Sa/So 8–10:30)")
    ap.add_argument("--radar", choices=["schauer", "jetzt", "dauer", "trocken", "down"], default="trocken",
                    help="Tagesdashboard: simuliertes Regenradar (nächste zwei Stunden)")
    ap.add_argument("--air", default="gut", choices=["gut", "maessig", "schlecht", "sehrschlecht", "nebel", "ozon",
                                                     "ohnestation", "ausfall", "wenige"],
                    help="Luftqualität simulieren (dev/mock_luft.py); die Feuchte kommt aus --scenario (herbst 82 %%, trocken 62 %%)")
    ap.add_argument("--pollen", default="gut", choices=["gut", "gering", "mittel", "hoch", "uebergang", "ausfall"],
                    help="Tagesdashboard: Pollenflug simulieren (dev/mock_pollen.py)")
    ap.add_argument("--gestern", type=float, metavar="GRAD",
                    help="Tagesdashboard: Vergleich mit dem Vortag simulieren, z. B. -4 = Luft heute 4° kälter als gestern "
                         "(abends ab switchHour: morgen gegenüber heute). Angezeigt wird der Unterschied der gefühlten "
                         "Temperatur – mit Windchill unter 10 °C oft größer")
    ap.add_argument("--iss", choices=["abend", "morgen", "keine", "echt"],
                    help="Tagesdashboard: ISS-Überflug festlegen (abend/morgen/keine) oder mit erfundener Bahn "
                         "wirklich rechnen (echt, dev/mock_ziel.py)")
    ap.add_argument("--display", default="inky", choices=["inky", "mock"])
    ap.add_argument("--font", default="eink", choices=["eink", "mono", "aa"])
    ap.add_argument("--inky-saturation", type=float, default=0.5)
    ap.add_argument("--simulate", action="store_true", help="Ergebnis des Inky-Treibers zusätzlich speichern")
    ap.add_argument("--out", default=str(DEV / "out"))
    args = ap.parse_args()

    inkypi_src = Path(args.inkypi).resolve() / "src"
    if not (inkypi_src / "plugins" / "base_plugin").exists():
        sys.exit(f"InkyPi nicht gefunden unter {inkypi_src} – mit --inkypi angeben.")
    link_plugins(inkypi_src)

    sys.path.insert(0, str(DEV))
    sys.path.insert(0, str(inkypi_src))
    os.chdir(inkypi_src)  # InkyPi löst Pfade relativ zu src/ auf
    if args.font in ("eink", "mono"):  # Chromium übernimmt das für alle Schriften, auch Webfonts
        os.environ["FONTCONFIG_FILE"] = str(DEV / f"fonts-{args.font}.conf")

    now = datetime.strptime(args.time, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)

    import mock_brightsky
    shift = None
    if args.gestern:
        # Tagsüber wird der Vortag verschoben (heute bleibt wie immer), abends der morgige Tag
        switch = next((kv.split("=", 1)[1] for kv in args.set if kv.startswith("switchHour=")), "20")
        evening = switch.isdigit() and now.hour >= int(switch)
        shift = {1: args.gestern} if evening else {-1: -args.gestern}
    mock_brightsky.install(now, args.scenario, fail=args.fail == "wetter", fail_uv=args.fail == "uv", shift=shift)
    if args.train:
        import mock_bahn
        mock_bahn.install(now, args.train)
        import mock_vrr  # Streckenmeldungen immer simulieren (Standard: nur unpassende, Bild bleibt wie bisher)
        mock_vrr.install(now, args.strecke)
    import mock_news  # Feeds immer simulieren: Renders sollen nicht vom echten Nachrichtenstand abhängen
    mock_news.install(now, args.news)
    import mock_radar  # Radar immer simulieren (Standard: trocken, dann bleibt das Bild wie bisher)
    mock_radar.install(now, args.radar)
    import mock_luft  # Luft immer simulieren (Standard: gut, dann bleibt das Bild wie bisher)
    mock_luft.install(now, args.air)
    import mock_pollen  # Pollen immer simulieren (Standard: gut, dann bleibt das Bild wie bisher)
    mock_pollen.install(now, args.pollen)

    settings = dict(BASE_SETTINGS)
    env = {}
    if args.plugin in ("nextcloud_kalender", "tagesdashboard"):
        import caldav_server
        url, user, password = caldav_server.start(now.date())
        settings.update({"nextcloudUrl": url, "username": user})
        env["NEXTCLOUD_APP_PASSWORD"] = "falsch" if args.fail == "kalender" else password
    if args.train:
        settings.update({"trainEnabled": "true", "trainDi": "true"})
        settings.update({f"train{d}": "true" for d in ("Mo", "Mi", "Do", "Fr", "Sa", "So")})  # jeder Testtag
    for item in args.set:
        key, _, value = item.partition("=")
        settings[key] = value

    module = __import__(f"plugins.{args.plugin}.{args.plugin}", fromlist=["x"])
    if args.plugin == "tagesdashboard":
        import mock_ziel  # Reiseziel-Wetter und Celestrak immer simulieren (nie echtes Netz)
        mock_ziel.install(now)
    if args.iss and args.iss != "echt" and args.plugin == "tagesdashboard":
        import mock_iss
        mock_iss.install(now, args.iss)
    cls = getattr(module, PLUGINS[args.plugin])
    cls.current_time = lambda self, tz: now.astimezone(tz)
    plugin = cls({"id": args.plugin})
    if args.seit and args.plugin == "tagesdashboard":
        # Statusanzeige: Ausfälle, die in dieser Runde beginnen, auf die gewünschte Uhrzeit zurückdatieren
        status = __import__("plugins.tagesdashboard.status", fromlist=["x"])
        yesterday = args.seit.startswith("gestern")
        hh, mm = args.seit.replace("gestern", "").strip().split(":")
        since = now.replace(hour=int(hh), minute=int(mm)) - timedelta(days=1 if yesterday else 0)
        real_commit = status.commit

        def commit(when):
            real_commit(when)
            for st in status._state.values():
                if st["since"] == when:
                    st["since"] = since
        status.commit = commit

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{args.plugin}_{args.scenario}_{now:%H%M}" + (f"_ohne-{args.fail}" if args.fail else "")
    if args.train:
        tag += f"_zug-{args.train}" + (f"_strecke-{args.strecke}" if args.strecke != "ruhig" else "")
    if args.news != "normal":
        tag += f"_news-{args.news}"
    if args.radar != "trocken":
        tag += f"_radar-{args.radar}"
    if args.air != "gut":
        tag += f"_luft-{args.air}"
    if args.pollen != "gut":
        tag += f"_pollen-{args.pollen}"
    if args.iss:
        tag += f"_iss-{args.iss}"
    if args.seit:
        tag += f"_seit-{args.seit.replace(':', '').replace('gestern ', 'g')}"
    if args.display == "mock" or args.font != "eink":
        tag += f"_{args.display}-{args.font}"
    for label, res, orientation in parse_sizes(args.sizes):
        cfg = DevConfig(res, orientation, env, args.display, args.inky_saturation)
        image = plugin.generate_image(dict(settings), cfg)
        path = out / f"{tag}_{label}.png"
        image.save(path)
        print(f"gespeichert: {path} {image.size}")
        if args.simulate:
            import inky_sim
            # wie InkyPi: erst für das hochkant montierte Display drehen, dann an den Treiber
            panel = image.rotate(90, expand=1) if orientation == "vertical" else image
            idx = inky_sim.emulate_driver(panel, args.inky_saturation)
            shown = inky_sim.show(idx)
            shown = shown.rotate(-90, expand=1) if orientation == "vertical" else shown
            sim_path = out / f"{tag}_{label}_display.png"
            shown.save(sim_path)
            print(f"  Displaysimulation: {sim_path} · vom Treiber verändert: "
                  f"{inky_sim.changed_by_driver(panel, args.inky_saturation)} Pixel")


if __name__ == "__main__":
    main()
