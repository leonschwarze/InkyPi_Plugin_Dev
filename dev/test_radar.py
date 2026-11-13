"""Regenradar und französische Schlagzeilen ohne Rendern prüfen.

  python dev/test_radar.py

Radar: simulierte Antworten von Bright Sky /radar (dev/mock_radar.py) → Texte der Karte.
Frankreich: Filter für Liveticker/Videos, Gattungsetiketten, geschützte Leerzeichen.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "dev"), str(REPO / "tagesdashboard")]
import mock_news  # noqa: E402
import mock_radar  # noqa: E402
import nachrichten  # noqa: E402
import radar  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 12, 16, 20, tzinfo=TZ)
failed = 0


def check(name, got, want):
    global failed
    ok = got == want
    failed += not ok
    print(f"  {'ok    ' if ok else 'FEHLER'}  {name}: {got!r}" + ("" if ok else f" (erwartet {want!r})"))


def summary(scenario, word="Regen", now=NOW):
    mock_radar.install(now, scenario)
    radar._cache.clear()
    return radar.summary(radar.fetch(50.7374, 7.0982, now), now, word=word)


print("Regenradar")
s = summary("schauer")
check("Schauer: Kopf", s["top"], "Regen 16:35–17:05")
check("Schauer: danach", s["after"], "ab 17:45 wieder")
check("Schauer: Stärke", s["level_text"], "mäßig")
check("Schauer: 25 Balken (jetzt bis +2 Std.)", len(s["points"]), 25)
check("Schauer: Ticks 17 und 18 Uhr", [t["text"] for t in s["strip"]["ticks"]], ["17", "18"])
s = summary("jetzt")
check("Regnet gerade", (s["state"], s["top"], s["after"]), ("jetzt", "Regen bis etwa 16:55", "danach trocken bis 18:20"))
s = summary("dauer")
check("Landregen", (s["top"], s["after"]), ("Regen hält an", ""))
check("Trocken → keine Karte", summary("trocken"), None)
check("Schnee statt Regen", summary("schauer", word="Schnee")["top"], "Schnee 16:35–17:05")

# Episoden direkt: kurze Pause (10 min) gehört dazu, 15 min trennt
t0 = NOW
pts = [(t0 + timedelta(minutes=5 * i), v) for i, v in enumerate([0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1])]
eps = radar.episodes(pts)
check("Pause 10 min überbrückt, 15 min trennt", [(a.strftime("%H:%M"), b and b.strftime("%H:%M")) for a, b, _ in eps],
      [("16:25", "16:55"), ("17:10", None)])
check("Stufen", [radar.level(v) for v in (0.5, 1.0, 3.9, 4.0)], ["leicht", "maessig", "maessig", "stark"])
check("Rohwert 45 = 5,4 mm/Std.", round(radar.mmh(45), 2), 5.4)

print("\nFrankreich")
mock_news.install(datetime(2026, 11, 12, 7, 20, tzinfo=TZ), "normal")
nachrichten._cache.clear()
flag = lambda k: k in ("newsEnabled", "newsFrEnabled")  # noqa: E731
opt = lambda k: {"newsFrom": "06:00", "newsTo": "09:30", "newsWeekendFrom": "08:00",  # noqa: E731
                 "newsWeekendTo": "10:30"}.get(k, "")
cfg = nachrichten.read_config(opt, flag, lambda v: datetime.strptime(v, "%H:%M").time() if v else None)
groups = nachrichten.load(cfg, datetime(2026, 11, 12, 7, 20, tzinfo=TZ))
fr = next((g for g in groups if g.get("lang") == "fr"), None)
titles = [it["title"] for it in fr["items"]] if fr else []
check("Ebene France vorhanden, als letzte", (groups[-1].get("lang"), groups[-1]["label"]), ("fr", "France"))
check("ohne DIRECT, VIDEO und zu alte", titles, [
    "Budget 2027 : l'Assemblée nationale adopte la première partie du projet de loi de finances",
    "Les communes rurales réclament davantage de médecins généralistes",
    "Comment les villes moyennes se réinventent après la fermeture des usines"])
check("Etikett nur aus der Liste", nachrichten.LABEL_FR.sub("", "SNCF. Grève jeudi"), "SNCF. Grève jeudi")
check("Typografie", nachrichten.fr_typo("« Non » : pourquoi ?"), "« Non » : pourquoi ?")
cfg_off = nachrichten.read_config(opt, lambda k: k == "newsEnabled", lambda v: datetime.strptime(v, "%H:%M").time())
check("ausgeschaltet → kein Feed", "fr" in cfg_off["feeds"], False)

print("\nAlles in Ordnung." if not failed else f"\n{failed} Fehler.")
sys.exit(1 if failed else 0)
