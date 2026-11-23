"""Feierabend-Schwelle (tagesdashboard/feierabend.py, seit 1.47) ohne Rendern.

  python dev/test_feierabend.py

Prüft: Regeln (nur Termine mit Uhrzeit, die heute beginnen; ganztägige zählen nie; Ende nach Mitternacht →
kein Feierabend; Überschneidungen; Einzahl/Mehrzahl), Cache-Grenze zum Ende des letzten Termins; die Katze
(Sessel vor dem Wetter, im Wechsel mit den übrigen Anlässen, nie auf Takten ohne Anlass) und mit dem echten
generate_image: Zeile ab dem Ende des letzten Termins, abends weiter, nicht im Nachtbild, Schalter,
abgelehnte Einladungen zählen nicht, Bild-Cache endet genau zum Feierabend.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(ROOT / "tagesdashboard"))
sys.path.insert(0, str(ROOT / "dwd_wetter"))
sys.path.insert(0, str(INKYPI))  # für BasePlugin

import feierabend  # noqa: E402
import katze  # noqa: E402
from dwd_wetter import feels_like  # noqa: E402
from PIL import Image  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
DAY = datetime(2026, 11, 24, tzinfo=TZ)  # Dienstag
TODAY = DAY.date()


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def at(h, m=0, days=0):
    return DAY + timedelta(days=days, hours=h, minutes=m)


def ev(start, end, all_day=False, title="T"):
    return {"start": start, "end": end, "all_day": all_day, "title": title}


# ---------------------------------------------------------------- Regeln
day3 = [ev(at(8), at(9)), ev(at(13), at(13, 45)), ev(at(15), at(17, 30)),
        ev(at(0), at(0, days=1), all_day=True, title="Müll"), ev(at(10, days=1), at(11, days=1))]
check("vor dem Ende des letzten Termins: nichts", feierabend.check(day3, at(17, 29), TODAY) is None)
fb = feierabend.check(day3, at(17, 30), TODAY)
check("genau zum Ende: Feierabend", fb is not None)
check("Text „seit 17:30 · 3 Termine“", fb and (fb["since_text"], fb["count_text"]) == ("17:30", "3 Termine"))
check("abends weiter da (22:40)", feierabend.check(day3, at(22, 40), TODAY) is not None)
check("ein Termin: Einzahl", feierabend.check([ev(at(9), at(10))], at(11), TODAY)["count_text"] == "1 Termin")
check("nur ganztägig: kein Feierabend",
      feierabend.check([ev(at(0), at(0, days=1), all_day=True)], at(20), TODAY) is None)
check("ohne Termine: kein Feierabend", feierabend.check([], at(20), TODAY) is None)
check("nur morgen Termine: kein Feierabend", feierabend.check([ev(at(10, days=1), at(11, days=1))], at(20), TODAY) is None)
night = day3 + [ev(at(22, 15), at(7, 30, days=1), title="Nachtzug")]
check("letzter Termin endet nach Mitternacht: kein Feierabend", feierabend.check(night, at(23, 0), TODAY) is None)
check("… und keine Cache-Grenze", feierabend.boundaries(night, at(17), TODAY) == [])
yesterday = [ev(at(22, 15, days=-1), at(7, 30), title="Nachtzug gestern"), ev(at(9), at(10))]
check("Termin von gestern zählt nicht mit", feierabend.check(yesterday, at(11), TODAY)["count"] == 1)
overlap = [ev(at(14), at(18)), ev(at(15), at(16))]
check("Überschneidung: das spätere Ende zählt", feierabend.check(overlap, at(17), TODAY) is None
      and feierabend.check(overlap, at(18), TODAY)["since_text"] == "18:00")
check("Termin ohne Dauer zählt nicht", feierabend.check([ev(at(9), at(9))], at(10), TODAY) is None)
check("Cache-Grenze vorher = Ende des letzten Termins", feierabend.boundaries(day3, at(16), TODAY) == [at(17, 30)])
check("Cache-Grenze danach: keine", feierabend.boundaries(day3, at(17, 30), TODAY) == [])
check("Häkchen ist gültiges SVG mit Klasse", feierabend.CHECK_ICON.format(cls="fb-ck").startswith('<svg class="fb-ck"'))

# ---------------------------------------------------------------- Katze


def hour(dt, **kw):
    r = {"dt": dt, "temperature": 11, "precipitation": 0, "wind_gust_speed": 30, "wind_speed": 12,
         "relative_humidity": 70, "sunshine": 0, "icon": "cloudy", "condition": "dry"}
    r.update(kw)
    return r


def records(now, **kw):
    base = now.replace(minute=0)
    return [hour(base + timedelta(hours=i), **kw) for i in (-1, 0, 1)]


evening = [at(17, 30) + timedelta(minutes=15 * i) for i in range(22)]   # 17:30 … 22:45
anl = [t for t in evening if katze.occasion_slot(t)]
plain = [t for t in evening if not katze.occasion_slot(t)]
dry = {t: katze.choose(t, records(t), occasions=["feierabend"], feels_like=feels_like) for t in evening}
check("nur Feierabend: jeder Anlass-Takt im Sessel", all(dry[t]["main"]["name"] == "sessel" for t in anl))
check("nie auf Takten ohne Anlass", all(dry[t]["main"]["name"] != "sessel" for t in plain))
check("Grund „feierabend“", all(dry[t]["reason"] == "feierabend" for t in anl))
rain = {t: katze.choose(t, records(t, precipitation=1.2, condition="rain"), occasions=["feierabend"],
                        feels_like=feels_like) for t in anl}
check("vor dem Wetter: auch bei Regen im Sessel", all(rain[t]["main"]["name"] == "sessel" for t in anl))
check("Regen ohne Feierabend: Wetterkatze", katze.choose(anl[0], records(anl[0], precipitation=1.2, condition="rain"),
                                                         occasions=[], feels_like=feels_like)["reason"] == "regen")
mixed = [katze.choose(t, records(t), occasions=["waesche", "feierabend"], feels_like=feels_like)["main"]["name"]
         for t in anl]
check("im Wechsel mit der Wäsche: beide kommen vor", "sessel" in mixed and "socke" in mixed)
check("… und etwa gleich oft", abs(mixed.count("sessel") - mixed.count("socke")) <= 1)
wet = [katze.choose(t, records(t, precipitation=1.2, condition="rain"), occasions=["waesche", "feierabend"],
                    feels_like=feels_like)["reason"] for t in anl]
check("Regen + Wäsche + Feierabend: Sessel oder Wetter, nie die Socke", set(wet) == {"feierabend", "regen"})
bday = katze.choose(anl[0], records(anl[0]), occasions=["geburtstag", "feierabend"], feels_like=feels_like)
check("Geburtstag geht vor", bday["reason"] == "geburtstag")
check("Sessel nie zufällig im Alltag", "sessel" not in katze.EVERYDAY)
check("Sessel ist hoch (Kopfzeile zuerst)", not katze.is_flat("sessel") and dry[anl[0]]["spots"][0] == "kopf")

# ---------------------------------------------------------------- mit dem echten generate_image
os.chdir(INKYPI)
sys.path.insert(0, str(INKYPI))
os.environ["DEV_PROTO"] = "feierabend"
import caldav_server  # noqa: E402
import mock_brightsky  # noqa: E402
import mock_news  # noqa: E402
import mock_radar  # noqa: E402
import mock_luft  # noqa: E402
import mock_pollen  # noqa: E402
import mock_nina  # noqa: E402
import mock_xkcd  # noqa: E402

link = INKYPI / "plugins" / "tagesdashboard"
if not link.exists():
    link.symlink_to(ROOT / "tagesdashboard")
from plugins.tagesdashboard import tagesdashboard as td  # noqa: E402

seen = {}


class Cfg:
    def get_resolution(self):
        return (800, 480)

    def get_config(self, key, default=None):
        return {"timezone": "Europe/Berlin", "orientation": "horizontal"}.get(key, default)

    def load_env_key(self, key):
        return seen.get("pw") if key == "NEXTCLOUD_APP_PASSWORD" else None


def run(t, keep_cache=False, **extra):
    """Parameter, die ans Template gingen (render_image abgefangen), und der Eintrag im Bild-Cache."""
    mock_brightsky.install(t, "trocken")
    mock_news.install(t, "normal")
    mock_radar.install(t, "trocken")
    for mod in (mock_luft, mock_pollen, mock_nina):
        mod.install(t)
    mock_xkcd.install(t, "normal")
    import mock_ziel  # merkt sich den vorigen get, deshalb zuletzt
    mock_ziel.install(t)
    url, user, pw = caldav_server.start(t.date())
    seen["pw"] = pw
    if not keep_cache:
        td._IMAGE_CACHE.clear()
    td._NIGHT_CACHE.clear()
    p = td.Tagesdashboard({"id": "tagesdashboard"})
    p.current_time = lambda tz: t.astimezone(tz)
    got = {}
    p.render_image = lambda dims, html, css, params: got.update(params) or Image.new("RGB", dims, "white")
    settings = {"nextcloudUrl": url, "username": user, "latitude": "50.73", "longitude": "7.10", "einkSnap": "false",
                "verifySSL": "false", **extra}
    p.generate_image(settings, Cfg())
    hit = next(iter(td._IMAGE_CACHE.values()), None)
    return got, hit


got, hit = run(at(17, 10))
check("17:10 (Ausschuss läuft): keine Zeile", not got.get("fb"))
check("17:10: Bild-Cache endet um 17:30 (nicht erst 17:25)", hit and hit["edge"] == at(17, 30))
got, _ = run(at(17, 30))
check("17:30: Feierabend seit 17:30 · 3 Termine",
      got.get("fb") and (got["fb"]["since_text"], got["fb"]["count_text"]) == ("17:30", "3 Termine"))
check("… mit Häkchen", "fb-ck" in (got.get("fb_icon") or ""))
got, _ = run(at(21, 15))
check("21:15 Abendansicht: weiter da", bool(got.get("fb")))
check("abgelehnte Einladung 19–21 Uhr zählt nicht (sonst „seit 21:00“)", got["fb"]["since_text"] == "17:30")
got, _ = run(at(23, 30))
check("23:30 Nachtbild: keine Zeile", not got.get("fb"))
got, _ = run(at(17, 45), cfgVersion="30")
check("Schalter aus: keine Zeile", not got.get("fb"))
got, _ = run(at(17, 45), cfgVersion="29")
check("alte Einstellungen (v29): Standard an", bool(got.get("fb")))

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
