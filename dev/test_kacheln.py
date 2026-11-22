"""Wetterkacheln des Dashboards (seit 1.36, „entschlackt“) ohne Rendern.

  python dev/test_kacheln.py

Prüft: Wind und Böen in einer Kachel (heute „Wind · Bft 3“/„Böen“, abends „Wind tagsüber“/„Böen bis“),
Richtungspfeil bleibt, UV erst ab 3 und dann als letzte Kachel, ohne UV-Daten keine Ersatzkachel
Bewölkung, fehlende Werte („–“), Pollen-Kachel bleibt unberührt, Reihenfolge der übrigen Kacheln.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEV = REPO / "dev"
inkypi_src = Path(os.environ.get("INKYPI_DIR", REPO.parent / "InkyPi")).resolve() / "src"
sys.path.insert(0, str(DEV))
from render import link_plugins  # noqa: E402

link_plugins(inkypi_src)
sys.path.insert(0, str(inkypi_src))

from plugins.tagesdashboard import tagesdashboard as td  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FEHLER {name}: {got!r} != {want!r}")


slim = td.Tagesdashboard.slim_tiles


def today(uv=None, cloud=True):
    tiles = [
        {"label": "Wind · Bft 3", "value": "17", "unit": "km/h", "extra": "<svg/><span>SW</span>"},
        {"label": "Böen", "value": "39", "unit": "km/h"},
        {"label": "Regen heute", "value": "6,8", "unit": "mm"},
        {"label": "Luftfeuchte", "value": "78", "unit": "%"},
    ]
    if uv is not None:
        tiles.append({"label": "UV heute", "value": str(uv), "unit": "niedrig", "key": "uv"})
    elif cloud:
        tiles.append({"label": "Bewölkung", "value": "80", "unit": "%", "key": "cloudcover"})
    tiles.append({"label": "Tageslicht", "value": "7:42–16:48", "unit": "", "raw": True})
    return tiles


labels = lambda ts: [t["label"] for t in ts]  # noqa: E731

# Wind + Böen
out = slim(today(uv=1))
check("vier Kacheln bei UV 1", labels(out), ["Wind · Böen", "Regen heute", "Luftfeuchte", "Tageslicht"])
check("Wert Wind/Böen", out[0]["value"], '17<span class="sep">/</span>39')
check("Wert ist Rohtext", out[0]["raw"], True)
check("Richtung bleibt", out[0]["extra"], "<svg/><span>SW</span>")
check("Einheit", out[0]["unit"], "km/h")

# UV-Grenze
for v, shown in ((0, False), (2, False), (3, True), (7, True), (11, True)):
    out = slim(today(uv=v))
    check(f"UV {v} sichtbar", any(t.get("key") == "uv" for t in out), shown)
    if shown:
        check(f"UV {v} zuletzt", out[-1].get("key"), "uv")
        check(f"UV {v} übrige Reihenfolge", labels(out[:-1]),
              ["Wind · Böen", "Regen heute", "Luftfeuchte", "Tageslicht"])

# ohne UV-Daten: keine Ersatzkachel Bewölkung
check("ohne UV keine Bewölkung", labels(slim(today(uv=None))),
      ["Wind · Böen", "Regen heute", "Luftfeuchte", "Tageslicht"])

# abends (Fokus morgen): Beschriftungen aus focus_day
eve = [
    {"label": "Wind tagsüber", "value": "16", "unit": "km/h", "extra": ""},
    {"label": "Böen bis", "value": "38", "unit": "km/h"},
    {"label": "Regen morgen", "value": "0,0", "unit": "mm"},
    {"label": "Luftfeuchte", "value": "82", "unit": "%"},
    {"label": "Bewölkung", "value": "30", "unit": "%", "key": "cloudcover"},
    {"label": "Sonne", "value": "7:43–16:47", "unit": "", "raw": True},
]
out = slim(eve)
check("abends", labels(out), ["Wind · Böen", "Regen morgen", "Luftfeuchte", "Sonne"])
check("abends Wert", out[0]["value"], '16<span class="sep">/</span>38')

# fehlende Werte
t = today(uv=1)
t[1]["value"] = "–"
check("Böen fehlen", slim(t)[0]["value"], '17<span class="sep">/</span>–')

# ohne Böen-Kachel bleibt Wind, wie er ist
t = [x for x in today(uv=1) if x["label"] != "Böen"]
check("ohne Böen", slim(t)[0]["label"], "Wind · Bft 3")

# Pollen wird erst danach angehängt und hier nicht angefasst
pol = {"label": "Pollen", "value": "Gräser", "unit": "hoch", "extra_class": "tile-wide lvl-hoch"}
check("Pollen bleibt", slim(today(uv=1) + [pol])[-1], pol)

# Eingabe nicht verändert (Kacheln kommen aus dem Zwischenspeicher des Wetters)
orig = today(uv=1)
before = [dict(x) for x in orig]
slim(orig)
check("Eingabe unverändert", orig, before)

print("Alles in Ordnung." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
