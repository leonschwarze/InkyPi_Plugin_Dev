#!/usr/bin/env python3
"""Sternschnuppenströme ohne Rendern: Aktivitätsfenster, Maximum, Auswahl bei Überschneidung,
SVG-Schwelle (stark + Maximum + klarer Himmel). Aufruf: python dev/test_meteore.py"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import meteore  # noqa: E402

failures = []


def check(label, cond):
    status = "ok" if cond else "FEHLER"
    print(f"[{status}] {label}")
    if not cond:
        failures.append(label)


# ---------------------------------------------------------------- Aktivitätsfenster
check("3. Januar (Quadrantiden-Maximum) aktiv", meteore.active(date(2026, 1, 3))["name"] == "Quadrantiden")
check("Quadrantiden über den Jahreswechsel: 30.12. aktiv",
      meteore.active(date(2026, 12, 30))["name"] == "Quadrantiden")
check("Quadrantiden über den Jahreswechsel: 5.1. aktiv",
      meteore.active(date(2026, 1, 5))["name"] == "Quadrantiden")
check("13. Februar: kein Strom aktiv (Lücke)", meteore.active(date(2026, 2, 13)) is None)
check("1. März: kein Strom aktiv (Lücke)", meteore.active(date(2026, 3, 1)) is None)
check("12. August (Perseiden-Maximum) aktiv", meteore.active(date(2026, 8, 12))["name"] == "Perseiden")
check("14. Dezember (Geminiden-Maximum) aktiv", meteore.active(date(2026, 12, 14))["name"] == "Geminiden")

# ---------------------------------------------------------------- Auswahl bei Überschneidung
# 25. Juli: Südliche Delta-Aquariiden (Maximum 30.7., 5 Tage entfernt) und beginnende Perseiden
# (Maximum 12.8., 18 Tage entfernt) sind beide aktiv -> das nähere Maximum gewinnt.
info = meteore.active(date(2026, 7, 25))
check("Überschneidung Ende Juli: Südliche Delta-Aquariiden (näheres Maximum) gewinnt",
      info and info["name"] == "Südliche Delta-Aquariiden")

# 20. Dezember: Geminiden (Ende 17.12., nicht mehr aktiv) vs. Ursiden (17.-26.12., Maximum 22.12.)
info = meteore.active(date(2026, 12, 20))
check("20. Dezember: nur noch Ursiden aktiv", info and info["name"] == "Ursiden")

# ---------------------------------------------------------------- Maximumnacht (at_peak)
check("11. August: noch nicht im Maximum", meteore.active(date(2026, 8, 11))["at_peak"] is False)
check("12. August: im Maximum", meteore.active(date(2026, 8, 12))["at_peak"] is True)
check("13. August: noch im Maximum (Folgenacht)", meteore.active(date(2026, 8, 13))["at_peak"] is True)
check("14. August: nicht mehr im Maximum", meteore.active(date(2026, 8, 14))["at_peak"] is False)

# ---------------------------------------------------------------- Texte
info = meteore.active(date(2026, 8, 18))
check("Text außerhalb des Maximums nennt Strom und Maximumsdatum",
      info and info["text"] == "Sternschnuppen: Perseiden aktiv · Maximum 12./13.8.")
info = meteore.active(date(2026, 8, 12))
check("Text im Maximum nennt ZHR",
      info and info["text"] == "Sternschnuppen: Perseiden-Maximum heute Nacht · ZHR 100")
info = meteore.active(date(2026, 4, 22))
check("Schwacher Strom (Lyriden) im Maximum: Text ohne 'SVG'-Hinweis, aber mit ZHR",
      info and info["text"] == "Sternschnuppen: Lyriden-Maximum heute Nacht · ZHR 18")

# ---------------------------------------------------------------- stark-Kennzeichnung
for name in ("Quadrantiden", "Perseiden", "Geminiden"):
    d = {"Quadrantiden": date(2026, 1, 3), "Perseiden": date(2026, 8, 12), "Geminiden": date(2026, 12, 14)}[name]
    check(f"{name} als 'stark' markiert", meteore.active(d)["stark"] is True)
for name, d in (("Lyriden", date(2026, 4, 22)), ("Orioniden", date(2026, 10, 21)), ("Ursiden", date(2026, 12, 22))):
    check(f"{name} nicht als 'stark' markiert", meteore.active(d)["stark"] is False)

# ---------------------------------------------------------------- SVG-Schwelle (show_streaks)
peak_perseiden = meteore.active(date(2026, 8, 12))
peak_lyriden = meteore.active(date(2026, 4, 22))
vorher_perseiden = meteore.active(date(2026, 8, 1))
check("Starker Strom, Maximum, klarer Himmel -> Sternschnuppen zeichnen",
      meteore.show_streaks(peak_perseiden, {"cloud": 15}) is True)
check("Starker Strom, Maximum, bedeckt -> keine Sternschnuppen",
      meteore.show_streaks(peak_perseiden, {"cloud": 80}) is False)
check("Starker Strom, Maximum, klar aber nass -> keine Sternschnuppen (Regen verdeckt den Himmel)",
      meteore.show_streaks(peak_perseiden, {"cloud": 10, "wet": True}) is False)
check("Starker Strom, Maximum, klar aber neblig -> keine Sternschnuppen",
      meteore.show_streaks(peak_perseiden, {"cloud": 10, "fog": True}) is False)
check("Starker Strom, aber nicht im Maximum, klarer Himmel -> keine Sternschnuppen",
      meteore.show_streaks(vorher_perseiden, {"cloud": 10}) is False)
check("Schwacher Strom im Maximum, klarer Himmel -> keine Sternschnuppen (nicht 'stark')",
      meteore.show_streaks(peak_lyriden, {"cloud": 10}) is False)
check("Kein Strom aktiv -> keine Sternschnuppen", meteore.show_streaks(None, {"cloud": 10}) is False)
check("Strom aktiv, aber keine Wetterdaten -> keine Sternschnuppen (vorsichtig ohne Daten)",
      meteore.show_streaks(peak_perseiden, None) is False)

if failures:
    print(f"\n{len(failures)} Fehler:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("\nALLE TESTS OK")
