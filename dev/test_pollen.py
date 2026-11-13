"""Logik der Pollen-Kachel (tagesdashboard/pollen.py) ohne Rendern.

  python dev/test_pollen.py

Prüft: Einstufung von "0".."3" und Übergängen wie "1-2"/"2-3" (classify), Lesen der Einstellungen
(Haupt- und Art-Schalter, Stufe, Teilregion), die Teilregion-Suche (find_region, Rückfall über die
Region), die Schwelle "ab eingestellter Stufe" und das Zählfeld "more" für "+N weitere" in der Kachel.
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import mock_pollen  # noqa: E402
import pollen  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 13, 15, 7, tzinfo=TZ)
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(("ok   " if ok else "FEHLER ") + name + ("" if ok else f": {got!r} statt {want!r}"))


class FakeSession:
    def __init__(self, kind):
        self.kind = kind

    def get(self, url, timeout=None):
        data = mock_pollen.payload(self.kind)
        if data is None:
            raise ConnectionError("simulierter Ausfall")
        return mock_pollen._Resp(data)


def run(kind, **cfg_overrides):
    pollen._cache.clear()
    cfg = {"level": 1, "types": list(pollen.TYPES), "partregion": "41"}
    cfg.update(cfg_overrides)
    return pollen.load(cfg, NOW, session=FakeSession(kind))


# ---- classify(): Skala 0–3, Übergänge, fehlende Angabe ----
check("classify 0", pollen.classify("0"), 0)
check("classify 1", pollen.classify("1"), 1)
check("classify 2", pollen.classify("2"), 2)
check("classify 3", pollen.classify("3"), 3)
check("classify Übergang 1-2 → 2 (höherer Wert)", pollen.classify("1-2"), 2)
check("classify Übergang 2-3 → 3", pollen.classify("2-3"), 3)
check("classify -1 → keine Angabe", pollen.classify("-1"), None)
check("classify leer → keine Angabe", pollen.classify(""), None)
check("classify None → keine Angabe", pollen.classify(None), None)
check("classify unlesbar → keine Angabe", pollen.classify("abc"), None)
check("classify über der Skala wird gekappt", pollen.classify("5"), 3)

# ---- read_config(): Haupt-/Art-Schalter, Stufe, Teilregion ----
flags_all_on = {f"pollen{t}": "true" for t in pollen.TYPES}


def opt_flag(extra_opt=None, extra_flag=None):
    opt_vals = dict(extra_opt or {})
    flag_vals = dict(flags_all_on)
    flag_vals["pollenEnabled"] = "true"
    flag_vals.update(extra_flag or {})
    return (lambda k: opt_vals.get(k, "")), (lambda k: flag_vals.get(k, False))


opt, flag = opt_flag()
check("read_config: Standard, alle Arten", pollen.read_config(opt, flag)["types"], list(pollen.TYPES))
check("read_config: Standard-Stufe 1", pollen.read_config(opt, flag)["level"], 1)
check("read_config: Standard-Teilregion 41", pollen.read_config(opt, flag)["partregion"], pollen.DEFAULT_PARTREGION)

opt, flag = opt_flag(extra_flag={"pollenEnabled": False})
check("read_config: Hauptschalter aus → None", pollen.read_config(opt, flag), None)

opt, flag = opt_flag(extra_flag={f"pollen{t}": False for t in pollen.TYPES})
check("read_config: alle Arten abgewählt → None", pollen.read_config(opt, flag), None)

opt, flag = opt_flag(extra_opt={"pollenLevel": "3"})
check("read_config: Stufe 3 übernommen", pollen.read_config(opt, flag)["level"], 3)

opt, flag = opt_flag(extra_opt={"pollenLevel": "9"})  # ungültig → Rückfall auf 1
check("read_config: ungültige Stufe → Rückfall 1", pollen.read_config(opt, flag)["level"], 1)

opt, flag = opt_flag(extra_opt={"pollenRegion": "32"})
check("read_config: eigene Teilregion übernommen", pollen.read_config(opt, flag)["partregion"], "32")

opt, flag = opt_flag(extra_flag={"pollenBirke": False})
check("read_config: einzelne Art abgewählt",
      "Birke" not in pollen.read_config(opt, flag)["types"] and "Graeser" in pollen.read_config(opt, flag)["types"],
      True)

# ---- load(): Schwelle, Teilregion-Suche, "more"-Zählung ----
check("load: keine Belastung → None", run("gut"), None)
check("load: Ausfall der Quelle → None", run("ausfall"), None)

data = run("gering")
check("load: Gräser gering → word", data["word"], "gering")
check("load: Gräser gering → lead", data["lead"], "Gräser")
check("load: Gräser gering → keine weiteren", data["more"], 0)

data = run("mittel")
check("load: Birke mittel + Erle gering → word (stärkste Art zählt)", data["word"], "mittel")
check("load: Birke mittel + Erle gering → lead", data["lead"], "Birke")
check("load: Birke mittel + Erle gering → eine weitere", data["more"], 1)

data = run("hoch")
check("load: Gräser hoch + Birke mittel + Esche gering → lead", data["lead"], "Gräser")
check("load: Gräser hoch + Birke mittel + Esche gering → zwei weitere", data["more"], 2)

data = run("uebergang")
check("load: Übergang 2-3 (Ambrosia) → word hoch (höherer Wert zählt)", data["word"], "hoch")

# Schwelle "ab Stufe x": bei "mittel" (Stufe 2) ist die Erle (gering) unter der Schwelle für die
# Zählung "more" – Birke (mittel) bleibt die einzige gemeldete Art.
data = run("mittel", level=2)
check("load: Stufe 2 → Erle (gering) zählt nicht mehr mit", data["more"], 0)
check("load: Stufe 2 → Birke bleibt über der Schwelle", data is not None, True)

check("load: Stufe 3 bei nur geringer Belastung → None (unter der Schwelle)", run("gering", level=3), None)

# Eine abgewählte Art wird nicht berücksichtigt, auch wenn sie am stärksten betroffen ist.
data = run("hoch", types=[t for t in pollen.TYPES if t != "Graeser"])
check("load: Gräser abgewählt → Birke führt stattdessen", data["lead"], "Birke")

# Teilregion nicht gefunden (z. B. Berlin/Brandenburg ohne eigene Teilregion) → Rückfall über
# die Region scheitert hier ebenfalls (Mock kennt nur Region 40/Teilregion 41 und eine andere
# Teilregion ohne Belastung) → None statt Absturz.
check("load: unbekannte Teilregion → None", run("hoch", partregion="99"), None)

print(f"\n{'ALLE TESTS OK' if not fails else f'{fails} FEHLER'}")
sys.exit(1 if fails else 0)
