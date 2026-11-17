"""Tests für planeten.py (helle Planeten im Nachtbild) ohne Rendern."""
import sys
from datetime import date, timedelta

sys.path.insert(0, "tagesdashboard")
import planeten  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


# ----------------------------------------------------------------------
# Nichts los: vor jedem Fensterbeginn bzw. weit vor jedem Vorlauf
# ----------------------------------------------------------------------
nichts = planeten.active(date(2026, 7, 1))  # Saturn-Vorlauf (Peak 4.10.) noch zu weit entfernt
check("Weit vor jedem Höhepunkt -> None", nichts is None)

# ----------------------------------------------------------------------
# Saturn-Opposition am 4.10.2026: Vorlauf, Höhepunkt, Ambiguität, danach vorbei
# ----------------------------------------------------------------------
knapp_davor = planeten.active(date(2026, 9, 20))  # 14 Tage vor dem 4.10. -- an der Grenze
check("Genau an der 14-Tage-Grenze -> gefunden", knapp_davor is not None)
check("Grenze: at_peak ist False", knapp_davor is not None and knapp_davor["at_peak"] is False)

zu_frueh = planeten.active(date(2026, 9, 19))  # 15 Tage vor dem 4.10.
check("15 Tage entfernt -> None", zu_frueh is None)

vorlauf = planeten.active(date(2026, 9, 25))  # 9 Tage vor dem 4.10.
check("Vorlauf-Text nennt Tage und 'Opposition'",
      vorlauf is not None and vorlauf["text"] == "Planeten: Saturn in 9 Tagen in Opposition (0,3 mag)")
check("Kind ist 'Opposition' (äußerer Planet)", vorlauf is not None and vorlauf["kind"] == "Opposition")

ein_tag = planeten.active(date(2026, 10, 3))
check("Einzahl 'Tag' statt 'Tagen'", ein_tag is not None and "in 1 Tag in Opposition" in ein_tag["text"])

heute = planeten.active(date(2026, 10, 4))
check("Am Oppositionstag selbst: at_peak", heute is not None and heute["at_peak"] is True)
check("Text 'heute Nacht' statt Countdown",
      heute is not None and heute["text"] == "Planeten: Saturn heute Nacht in Opposition · die ganze Nacht sichtbar (0,3 mag)")

# Dieselbe physische Nacht lässt sich auf zwei Arten lesen (wie bei meteore._at_peak und
# finsternisse._at_peak): je nach Uhrzeit von "jetzt" trägt sie das Datum des Höhepunkts oder den
# Folgetag.
tag_danach = planeten.active(date(2026, 10, 5))
check("Folgetag zählt noch als dieselbe Nacht (Ambiguität wie bei Meteoren/Finsternissen)",
      tag_danach is not None and tag_danach["name"] == "Saturn" and tag_danach["at_peak"])

zwei_tage_danach = planeten.active(date(2026, 10, 6))
check("Zwei Tage danach: Saturn vorbei, nichts anderes nah -> None", zwei_tage_danach is None)

# ----------------------------------------------------------------------
# Venus als Morgenstern, größte Helligkeit am 25.11.2026
# ----------------------------------------------------------------------
venus_vorlauf = planeten.active(date(2026, 11, 20))
check("Venus-Vorlauf: Kind 'Morgenstern', Text mit 'größte Helligkeit'",
      venus_vorlauf is not None and venus_vorlauf["kind"] == "Morgenstern"
      and venus_vorlauf["text"] == "Planeten: Venus Morgenstern · größte Helligkeit in 5 Tagen (-4,9 mag)")

venus_heute = planeten.active(date(2026, 11, 25))
check("Venus am Tag der größten Helligkeit: at_peak, Text 'am hellsten'",
      venus_heute is not None and venus_heute["at_peak"]
      and venus_heute["text"] == "Planeten: Venus heute Nacht am hellsten · Morgenstern (-4,9 mag)")

venus_tag_danach = planeten.active(date(2026, 11, 26))
check("Venus: Folgetag zählt noch als dieselbe Nacht", venus_tag_danach is not None and venus_tag_danach["at_peak"])

venus_vorbei = planeten.active(date(2026, 11, 27))
check("Venus: zwei Tage danach vorbei, nichts anderes nah -> None", venus_vorbei is None)

# ----------------------------------------------------------------------
# Überlappende Vorläufe: Jupiter-Opposition 11.2.2027, Mars-Opposition 19.2.2027 -- der nähere
# Höhepunkt gewinnt, und nach Jupiters Höhepunkt übernimmt Mars allein.
# ----------------------------------------------------------------------
beide_nah = planeten.active(date(2027, 2, 8))  # Jupiter 3 Tage, Mars 11 Tage entfernt
check("Bei zwei nahen Höhepunkten gewinnt der nähere (Jupiter vor Mars)",
      beide_nah is not None and beide_nah["name"] == "Jupiter")

nur_mars = planeten.active(date(2027, 2, 17))  # Jupiter-Höhepunkt (11.2.) ist vorbei, Mars (19.2.) nah
check("Nach Jupiters Höhepunkt übernimmt Mars allein", nur_mars is not None and nur_mars["name"] == "Mars")

# ----------------------------------------------------------------------
# show_dot: nur am Höhepunkt und bei klarem Himmel
# ----------------------------------------------------------------------
klar = {"cloud": 10, "wet": False, "fog": False}
bewoelkt = {"cloud": 60, "wet": False, "fog": False}
regen = {"cloud": 10, "wet": True, "fog": False}

check("Punkt am Höhepunkt bei klarem Himmel", planeten.show_dot(heute, klar))
check("Kein Punkt am Höhepunkt bei bewölktem Himmel", not planeten.show_dot(heute, bewoelkt))
check("Kein Punkt am Höhepunkt bei Regen", not planeten.show_dot(heute, regen))
check("Kein Punkt vor dem Höhepunkt (nur Countdown), auch bei klarem Himmel", not planeten.show_dot(vorlauf, klar))
check("Kein Punkt ohne Planet (None)", not planeten.show_dot(None, klar))

# ----------------------------------------------------------------------
# Tabelle in sich konsistent
# ----------------------------------------------------------------------
check("PLANETS hat keine doppelten Namen", len({p[0] for p in planeten.PLANETS}) == len(planeten.PLANETS))
check("Jedes Fenster: Beginn < Höhepunkt < Ende",
      all(p[1] < p[3] < p[2] for p in planeten.PLANETS))
check("Alle Fensterenden liegen in der Zukunft ab dem Recherchestand (November 2026)",
      all(p[2] > date(2026, 11, 13) for p in planeten.PLANETS))

# ----------------------------------------------------------------------
# Zeichnung (seit 1.31): Morgen-/Abendstern nie hinter dem Mond – in allen Szenenbreiten
# (800/480 bis 1.29, 756/467/516 = nachtgrafik.band_width), mit und ohne Katze, 120 Nächte
# ----------------------------------------------------------------------
import re  # noqa: E402
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402
import katze  # noqa: E402
import nachtgrafik  # noqa: E402

hidden = []
start = datetime(2026, 11, 1, 23, 30, tzinfo=ZoneInfo("Europe/Berlin"))
for W in (800, 480, 756, 467, 516):
    for cat in (None, katze.on_moon):
        for kind in ("Morgenstern", "Abendstern"):
            for i in range(120):
                g = nachtgrafik.svg(start + timedelta(days=i), {"cloud": 10}, width=W, cat=cat, planet=kind)
                mx = float(re.search(r'<path d="M([0-9.]+),', g).group(1))
                px = float(re.search(r'<circle cx="([\d.]+)" cy="[\d.]+" r="3.2"', g).group(1))
                if abs(px - mx) <= (18 if cat else 14) + 7:  # Mondradius + Strahlenlänge
                    hidden.append((W, bool(cat), kind, i))
check(f"Morgen-/Abendstern nie hinter dem Mond (5 Breiten, mit/ohne Katze, 120 Nächte){hidden[:3]}", not hidden)

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
