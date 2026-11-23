"""Katze (seit 1.14) ohne Rendern prüfen: Wetterregeln, Abwechslung, Wiederholbarkeit, SVG.

    python dev/test_katze.py

Wo die Katze im Bild landet, entscheidet erst der Browser (placeCat im Template) –
das prüft man mit dev/render.py und Hinsehen.
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tagesdashboard"))
import katze  # noqa: E402
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("INKYPI_DIR", REPO.parent / "InkyPi")) / "src"))  # für BasePlugin
sys.path.insert(0, str(REPO / "dwd_wetter"))
from dwd_wetter import feels_like  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
FAILS = []


def check(ok, what):
    print(("  ok      " if ok else "  FEHLER  ") + what)
    if not ok:
        FAILS.append(what)


def hour(dt, **kw):
    r = {"dt": dt, "temperature": 11, "precipitation": 0, "wind_gust_speed": 30, "wind_speed": 12,
         "relative_humidity": 70, "sunshine": 0, "icon": "cloudy", "condition": "dry"}
    r.update(kw)
    return r


def reason(now, nowcast=None, **kw):
    base = now.replace(minute=0)
    records = [hour(base - timedelta(hours=1)), hour(base, **kw), hour(base + timedelta(hours=1))]
    return katze.weather_reason(records, now, nowcast, feels_like)


BBOX_JS = """() => [...document.querySelectorAll('svg')].map(s => {
  const inv = s.getScreenCTM().inverse(); let y0 = 1e9, y1 = -1e9, x0 = 1e9, x1 = -1e9;
  for (const el of s.querySelectorAll('path,circle,ellipse,rect,line,polyline,polygon')) {
    const bb = el.getBBox(), t = inv.multiply(el.getScreenCTM());
    for (const [px, py] of [[bb.x, bb.y], [bb.x + bb.width, bb.y], [bb.x, bb.y + bb.height],
                            [bb.x + bb.width, bb.y + bb.height]]) {
      const q = new DOMPoint(px, py).matrixTransform(t);
      x0 = Math.min(x0, q.x); y0 = Math.min(y0, q.y); x1 = Math.max(x1, q.x); y1 = Math.max(y1, q.y);
    }
  }
  return [s.dataset.name, x0, y0, x1, y1];
})"""


def outside_viewbox():
    """Posen, deren Zeichnung (ohne Strichbreite) über ihre viewBox hinausragt. placeCat rechnet nur mit
    der viewBox – ein Hütchen darüber könnte sonst Text überdecken (ist in 1.20 beim Partyhut passiert).
    Braucht Playwright (wie test_settings.py); ohne → None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    poses = {n: katze.pose(n) for n in katze.POSES}
    html = "".join(p["svg"].replace("<svg ", f'<svg data-name="{n}" width="{p["w"] * 4}" ')
                   for n, p in poses.items())
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(f"<body>{html}</body>")
        boxes = page.evaluate(BBOX_JS)
        browser.close()
    # 0,6 Einheiten Spielraum: Pfoten stehen bei y = 43,5, Rundungen dürfen leicht über den Rand
    return [(n, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)) for n, x0, y0, x1, y1 in boxes
            if x0 < -0.6 or y0 < -0.6 or x1 > poses[n]["w"] + 0.6 or y1 > poses[n]["h"] + 0.6]


def main():
    # Die Prüfungen bis „Saisonale Gäste“ stammen aus der Zeit vor 1.46 und laufen oft im November (Igel-Saison):
    # dort ohne Gäste, damit sie weiter genau das prüfen, wofür sie geschrieben wurden.
    season = katze.GUEST_SEASON
    katze.GUEST_SEASON = {}
    now = datetime(2026, 11, 10, 15, 7, tzinfo=TZ)
    print("Wetterregeln (C)")
    check(reason(now) is None, "ruhiges Wetter → keine Wetter-Pose")
    check(reason(now, wind_gust_speed=65, precipitation=2) == "sturm", "Sturm geht Regen vor")
    check(reason(now, precipitation=0.4) == "regen", "Regen in der laufenden Stunde → Schirm")
    check(reason(now, icon="snow", condition="snow", temperature=-1) == "schnee", "Schnee → Schal")
    check(reason(now, temperature=1, wind_speed=20) == "frost", "gefühlt unter 0 °C (Windchill) → Schal")
    check(reason(now, temperature=18, sunshine=50) == "sonne", "sonnig und mild → Sonnenbad")
    check(reason(now, temperature=10, sunshine=60) is None, "sonnig, aber kalt → keine Wetter-Pose")
    check(reason(now, nowcast={"state": "jetzt"}) == "regen", "Radar: es regnet gerade → Schirm")
    # Bright Sky: Datensatz 16:00 = Regen von 15–16 Uhr; das Dashboard schreibt dann „Regen 16 Uhr“
    base = datetime(2026, 11, 10, 16, 15, tzinfo=TZ)
    records = [hour(base.replace(minute=0)), hour(base.replace(minute=0) + timedelta(hours=1), precipitation=3)]
    check(katze.weather_reason(records, base, None, feels_like) is None,
          "16:15, Regen erst im Datensatz 17:00 → noch kein Schirm (wie „Regen ab 17 Uhr“)")
    check(katze.weather_reason([], now) is None, "ohne Wetterdaten → keine Wetter-Pose")

    print("Auswahl (B)")
    day = datetime(2026, 11, 10, 6, 0, tzinfo=TZ)
    slots = [katze.choose(day + timedelta(minutes=15 * i)) for i in range(4 * 17)]  # 6–23 Uhr
    names = [c["main"]["name"] for c in slots]
    check(all(a != b for a, b in zip(names, names[1:])), "nie zweimal dieselbe Pose hintereinander")
    check(set(names) == set(katze.EVERYDAY), "über den Tag kommen alle Alltags-Posen vor")
    firsts = [c["spots"][0] for c in slots]
    check(all(a != b for a, b in zip(firsts, firsts[1:])), "der erste Platz wechselt mit jedem Takt")
    check(all(katze.is_flat(c["flat"]["name"]) for c in slots), "Ersatzpose ist immer flach")
    check(katze.choose(now) == katze.choose(now.replace(minute=14)), "gleicher 15-Minuten-Takt → gleiche Katze")
    other = [katze.choose(now.replace(day=11) + timedelta(minutes=15 * i))["main"]["name"] for i in range(8)]
    check(other != names[36:44], "anderer Tag → andere Reihenfolge")
    rainy = [hour(now.replace(minute=0), precipitation=1)]
    c = katze.choose(now, rainy)
    check(c["main"]["name"] in katze.WEATHER_POSES["regen"] and c["reason"] == "regen", "Regen → eine Regen-Pose")
    tall = next(t for t in (now + timedelta(minutes=15 * i) for i in range(6))
                if not katze.is_flat(katze.choose(t, [hour(t.replace(minute=0), precipitation=1)])["main"]["name"]))
    c = katze.choose(tall, [hour(tall.replace(minute=0), precipitation=1)])
    check(c["spots"][0] == "kopf", "hohe Regen-Pose braucht Höhe → zuerst die Kopfzeile")
    check(katze.choose(now, rainy, weather=False)["main"]["name"] in katze.EVERYDAY,
          "„passt sich dem Wetter an“ aus → nur Alltags-Posen")
    stormy = [hour(now.replace(minute=0), wind_gust_speed=70)]
    c = katze.choose(now, stormy)
    check(c["main"]["name"] in katze.WEATHER_POSES["sturm"] and c["flat"]["name"] == "sturm",
          "Sturm: Variante, flach weiter die geduckte Sturm-Katze")

    print("Wetter-Varianten (seit 1.34)")
    for why, kw in (("regen", {"precipitation": 1}), ("sturm", {"wind_gust_speed": 70}),
                    ("schnee", {"icon": "snow", "precipitation": 1}), ("frost", {"temperature": -4}),
                    ("sonne", {"sunshine": 55, "temperature": 22}),
                    ("gewitter", {"icon": "thunderstorm", "precipitation": 3}), ("nebel", {"icon": "fog"})):
        ts = [day + timedelta(minutes=15 * i) for i in range(24)]
        got = [katze.choose(t, [hour(t.replace(minute=0), **kw)], feels_like=feels_like) for t in ts]
        names = [c["main"]["name"] for c in got]
        check(all(c["reason"] == why for c in got), f"{why}: reason stimmt")
        check(set(names) == set(katze.WEATHER_POSES[why]), f"{why}: alle drei Varianten kommen vor ({sorted(set(names))})")
        if len(katze.WEATHER_POSES[why]) > 1:
            check(all(a != b for a, b in zip(names, names[1:])), f"{why}: nie zweimal dieselbe hintereinander")
        flats = {c["flat"]["name"] for c in got}
        same = [p for p in katze.WEATHER_POSES[why] if katze.is_flat(p)]
        check(flats <= set(same) if same else all(f in katze.EVERYDAY for f in flats),
              f"{why}: flache Ersatzpose {sorted(flats)}")
    seq = lambda d: [katze.weather_pose("regen", d, s) for s in range(3)]  # noqa: E731
    check(len({tuple(seq(day.date() + timedelta(days=i))) for i in range(10)}) > 1, "Reihenfolge wechselt von Tag zu Tag")
    check(not {p for v in katze.WEATHER_POSES.values() for p in v} & set(katze.EVERYDAY),
          "Wetter-Posen kommen nie im Alltag")

    print("Anlässe (seit 1.20)")
    morning = datetime(2026, 11, 11, 6, 0, tzinfo=TZ)
    window = [morning + timedelta(minutes=15 * i) for i in range(14)]          # Nachrichtenfenster 6–9:30
    picks = [katze.choose(t, occasions=["nachrichten"]) for t in window]
    papers = [c["main"]["name"] == "zeitung" for c in picks]
    check(sum(papers) == 7, f"Nachrichtenfenster: Zeitung genau jedes zweite Mal ({sum(papers)} von 14)")
    check(all(a != b for a, b in zip(papers, papers[1:])), "Zeitung und Alltag wechseln sich ab")
    check(all(c["reason"] == "nachrichten" for c in picks if c["main"]["name"] == "zeitung"), "reason = nachrichten")
    occ = next(t for t in window if katze.occasion_slot(t))
    plain = next(t for t in window if not katze.occasion_slot(t))
    rain = lambda t: [hour(t.replace(minute=0), precipitation=1)]  # noqa: E731
    c = katze.choose(occ, rain(occ), occasions=["geburtstag", "nachrichten"], feels_like=feels_like)
    check(c["main"]["name"] == "partyhut", "Geburtstag geht dem Wetter vor (Anlass-Takt, Regen)")
    c = katze.choose(plain, rain(plain), occasions=["geburtstag"], feels_like=feels_like)
    check(c["reason"] == "regen", "im anderen Takt gilt am Geburtstag das Wetter")
    c = katze.choose(occ, rain(occ), occasions=["nachrichten", "zug"], feels_like=feels_like)
    check(c["reason"] == "regen", "Wetter geht Nachrichten und Zug vor")
    c = katze.choose(occ, occasions=["geburtstag"])
    check(c["main"]["name"] == "partyhut" and c["spots"][0] == "kopf", "Partyhut braucht Höhe → zuerst die Kopfzeile")
    both = {katze.choose(t, occasions=["nachrichten", "zug"])["main"]["name"]
            for t in window if katze.occasion_slot(t)}
    check(both == {"zeitung", "koffer"}, "Zug-Dienstag im Nachrichtenfenster: Zeitung und Koffer abwechselnd")
    evening = datetime(2026, 11, 10, 18, 0, tzinfo=TZ)
    socks = [katze.choose(evening + timedelta(minutes=15 * i), occasions=["waesche"])["main"]["name"]
             for i in range(8)]
    check(socks.count("socke") == 4 and katze.is_flat("socke"), "Wäsche-Karte: Socke jedes zweite Mal (flach)")
    check(katze.choose(occ)["reason"] is None, "ohne Anlass und Wetter: Alltag")
    check(not set(katze.OCCASION_POSE.values()) & set(katze.EVERYDAY), "Anlass-Posen kommen nie im Alltag")
    starts = {katze.occasion_slot(datetime(2026, 11, d, 6, 0, tzinfo=TZ)) for d in range(1, 15)}
    check(starts == {True, False}, "welcher Takt beginnt, wechselt von Tag zu Tag")

    print("Nebel, Gewitter, neue Anlässe (seit 1.35)")
    t0 = now.replace(minute=0)
    check(katze.weather_reason([hour(t0, icon="thunderstorm", wind_gust_speed=70)], now) == "sturm", "Sturm vor Gewitter")
    check(katze.weather_reason([hour(t0, icon="thunderstorm", precipitation=5)], now) == "gewitter",
          "Gewitter vor Regen (vorher Regen)")
    check(katze.weather_reason([hour(t0, icon="fog", precipitation=1)], now) == "regen", "Regen vor Nebel")
    check(katze.weather_reason([hour(t0, icon="fog", temperature=-5)], now) == "nebel", "Nebel vor Frost")
    check(katze.weather_reason([hour(t0, condition="fog")], now) == "nebel", "Nebel auch über condition")
    check(katze.is_flat("gewitter") and katze.is_flat("hängematte"), "Gewitter und Hängematte sind flach")
    for occ_name, pose_name in (("radar", "fernglas"), ("rad", "helm"), ("oepnv", "haltestelle"), ("pollen", "niest"),
                                ("wahlkampf", "plakat"), ("zielort", "karte"), ("abend", "zipfelmütze")):
        got = [katze.choose(day + timedelta(minutes=15 * i), occasions=[occ_name])["main"]["name"] for i in range(8)]
        check(got.count(pose_name) == 4, f"{occ_name} → {pose_name} jedes zweite Mal ({got.count(pose_name)} von 8)")
    sat = datetime(2026, 11, 14, 9, 0, tzinfo=TZ)
    got = [katze.choose(sat + timedelta(minutes=15 * i), occasions=["wochenende"])["main"]["name"] for i in range(16)]
    check(got.count("hängematte") == 4, f"Wochenende: Hängematte nur jedes vierte Mal ({got.count('hängematte')} von 16)")
    got = [katze.choose(sat + timedelta(minutes=15 * i), occasions=["wochenende", "radar"])["main"]["name"]
           for i in range(16)]
    check(got.count("fernglas") >= 4 and got.count("hängematte") >= 2, "Wochenende wechselt sich mit anderen Anlässen ab")
    check(not set(katze.OCCASION_POSE.values()) & set(katze.EVERYDAY), "Anlass-Posen nie im Alltag")
    check(len(katze.EVERYDAY) == 24, "24 Alltags-Posen")

    print("Advent (seit 1.34)")
    adv = datetime(2026, 12, 3, 9, 0, tzinfo=TZ)
    picks = [katze.choose(adv + timedelta(minutes=15 * i), occasions=["advent"]) for i in range(8)]
    names = [c["main"]["name"] for c in picks]
    check(sum(n in ("lichterkette", "plätzchen") for n in names) == 4, "Advent-Pose jedes zweite Mal")
    check({"lichterkette", "plätzchen"} <= set(names), f"Lichterkette und Plätzchen wechseln sich ab (seit 1.43) {names}")
    o = next(adv + timedelta(minutes=15 * i) for i in range(4) if katze.occasion_slot(adv + timedelta(minutes=15 * i)))
    check(katze.choose(o, rain(o), occasions=["advent"], feels_like=feels_like)["reason"] == "regen",
          "Wetter geht der Lichterkette vor")
    check(katze.choose(o, occasions=["advent", "geburtstag"])["main"]["name"] == "partyhut", "Geburtstag vor Advent")

    print("Neue Anlässe (seit 1.43)")
    day = datetime(2026, 11, 24, 10, 0, tzinfo=TZ)
    for occ, want in (("schneekarte", "schlitten"), ("glaette", "glatteis"), ("laufen", "stirnband"),
                      ("klima", "thermometer"), ("comic", "comic"), ("laterne", "laterne")):
        got = [katze.choose(day + timedelta(minutes=15 * i), occasions=[occ])["main"]["name"] for i in range(8)]
        check(got.count(want) == 4, f"{occ} → {want} jedes zweite Mal ({got.count(want)} von 8)")
    check("schlitten" in katze.WEATHER_POSES["schnee"], "Schlitten auch bei Schneefall (Wetterkatze)")
    frosty = [{"dt": day.replace(minute=0) + timedelta(hours=h), "temperature": -3, "wind_speed": 5,
               "relative_humidity": 90, "icon": "clear-day"} for h in range(-1, 4)]
    got = [katze.choose(day + timedelta(minutes=15 * i), frosty, occasions=["glaette"], feels_like=feels_like)
           for i in range(8)]
    check(sum(c["main"]["name"] == "glatteis" for c in got) == 4 and sum(c["reason"] == "frost" for c in got) == 4,
          "Glätte bei Frost: Glatteis und Frost-Posen im Wechsel (Winter-Anlass schlägt Frost)")
    got = [katze.choose(t, rain(t), occasions=["glaette"], feels_like=feels_like)
           for t in (day + timedelta(minutes=15 * i) for i in range(8))]
    check(all(c["reason"] == "regen" for c in got), "bei Regen bleibt die Regenkatze (nur Frost/Schnee werden geschlagen)")
    check(katze.is_lantern("Laternenumzug Kita") and katze.is_lantern("St. Martin am Münster")
          and katze.is_lantern("Martinszug Beuel") and not katze.is_lantern("Martin Schulz") and not katze.is_lantern(None),
          "Laternen-Termine erkannt (Laterne, St. Martin, Martinszug; nicht „Martin Schulz“)")
    check(len(katze.POSES) == 72, f"72 Posen ({len(katze.POSES)}, seit 1.46 mit vier Gästen)")
    roof = katze.on_roof(37, 88)
    check("#FFE500" in roof and "#000000" in roof and "currentColor" not in roof,
          "Dachkatze nur Schwarz und Gelb (keine CSS-Farben im Nachtbild)")

    print("Ratssitzung (seit 1.27)")
    session = datetime(2026, 11, 12, 17, 0, tzinfo=TZ)
    slots = [session + timedelta(minutes=15 * i) for i in range(20)]           # 17–22 Uhr
    picks = [katze.choose(t, occasions=["rat"]) for t in slots]
    rat = [c for c in picks if c["reason"] == "rat"]
    check(len(rat) == 10, f"Ratssitzung jedes zweite Mal ({len(rat)} von 20)")
    check(all((c["main"]["name"] == "akten") == (t.hour >= katze.RAT_LATE_HOUR)
              for t, c in zip(slots, picks) if c["reason"] == "rat"), "vor 21 Uhr Rednerpult, ab 21 Uhr nur Akten")
    check({c["main"]["name"] for c in rat} == {"rednerpult", "akten"}, "beide Posen kommen vor")
    occ = next(t for t in slots if katze.occasion_slot(t))
    plain = next(t for t in slots if not katze.occasion_slot(t))
    c = katze.choose(occ, rain(occ), occasions=["rat"], feels_like=feels_like)
    check(c["main"]["name"] == "rednerpult", "Ratssitzung geht dem Wetter vor (Anlass-Takt, Regen)")
    check(c["spots"][0] == "kopf", "Rednerpult braucht Höhe → zuerst die Kopfzeile")
    c = katze.choose(plain, rain(plain), occasions=["rat"], feels_like=feels_like)
    check(c["reason"] == "regen", "im anderen Takt gilt das Wetter")
    c = katze.choose(occ, occasions=["rat"], egg="narr")
    check(c["main"]["name"] == "rednerpult", "Ratssitzung geht dem Osterei vor (Anlass-Takt)")
    check(katze.choose(plain, occasions=["rat"], egg="narr")["main"]["name"] == "narr", "… im anderen Takt das Osterei")
    c = katze.choose(occ, occasions=["rat", "geburtstag", "waesche"])
    check(c["main"]["name"] == "partyhut", "Geburtstag geht der Ratssitzung vor")
    c = katze.choose(occ, occasions=["rat", "waesche"])
    check(c["main"]["name"] == "rednerpult", "Ratssitzung geht der Wäsche-Karte vor")
    check(not {"rednerpult", "akten"} & set(katze.EVERYDAY), "Ratssitzungs-Posen kommen nie im Alltag")

    print("Saisonale Gäste (seit 1.46)")
    katze.GUEST_SEASON = season
    months = {m: katze.guest_of(date(2026, m, 15)) for m in range(1, 13)}
    check(months == {1: "rotkehlchen", 2: "rotkehlchen", 3: "kröte", 4: "kröte", 5: None, 6: None, 7: None, 8: None,
                     9: "eichhörnchen", 10: "igel", 11: "igel", 12: "rotkehlchen"}, f"Saison je Monat {months}")
    day0 = datetime(2026, 11, 24, 0, 0, tzinfo=TZ)
    ticks = [day0 + timedelta(minutes=15 * i) for i in range(96)]
    picks = [katze.choose(t) for t in ticks]
    guests = [t for t, c in zip(ticks, picks) if c["reason"] == "gast"]
    check(len(guests) == 24, f"selten: jedes vierte Bild ({len(guests)} von 96)")
    check(sorted(t.hour for t in guests) == list(range(24)), "genau einmal pro Stunde")
    check(all(c["main"]["name"] == "igel" for c in picks if c["reason"] == "gast"), "im November kommt der Igel")
    check(not any(katze.occasion_slot(t) for t in guests), "nie auf einem Anlass-Takt (Zeitung, Geburtstag … bleiben)")
    shifts = {tuple(t.minute for t in ticks[:8] if katze.guest_slot(t.replace(day=d))) for d in range(1, 15)}
    check(len(shifts) > 1, "welcher Takt den Gast bringt, wechselt von Tag zu Tag")
    g = guests[0]
    check(katze.choose(g, rain(g), feels_like=feels_like)["reason"] == "gast", "Gast kommt auch bei Regen (Leons Wahl)")
    check(katze.choose(g, egg="narr")["main"]["name"] == "narr", "Osterei geht dem Gast vor")
    check(katze.choose(g, guests=False)["reason"] is None, "guests=False → kein Gast")
    news = [day0.replace(hour=6) + timedelta(minutes=15 * i) for i in range(14)]
    with_g = [katze.choose(t, occasions=["nachrichten"])["main"]["name"] for t in news]
    without = [katze.choose(t, occasions=["nachrichten"], guests=False)["main"]["name"] for t in news]
    check(with_g.count("zeitung") == without.count("zeitung") == 7, "Anlass-Posen kommen genauso oft wie ohne Gäste")
    bday = [katze.choose(t, occasions=["geburtstag"])["main"]["name"] for t in news]
    check(bday.count("partyhut") == 7 and bday.count("igel") in (3, 4), f"Geburtstag unberührt, Gast dazwischen {bday}")
    july = datetime(2027, 7, 14, 0, 0, tzinfo=TZ)
    check(not any(katze.choose(july + timedelta(minutes=15 * i))["reason"] == "gast" for i in range(96)),
          "im Sommer (Mai–August) kein Gast")
    for month, name in ((1, "rotkehlchen"), (3, "kröte"), (9, "eichhörnchen")):
        d = datetime(2027, month, 12, 0, 0, tzinfo=TZ)
        t = next(d + timedelta(minutes=15 * i) for i in range(96) if katze.guest_slot(d + timedelta(minutes=15 * i)))
        c = katze.choose(t)
        check(c["main"]["name"] == name, f"{month}. Monat: {name}")
        check(c["spots"][0] == "kopf" or katze.is_flat(name), f"{name}: hohe Pose zuerst auf die Kopfzeile")
    check(not set(katze.GUEST_POSES) & set(katze.EVERYDAY), "Gäste kommen nie im Alltag")
    check(katze.is_flat("igel") and katze.is_flat("kröte"), "Igel und Kröte sind flach (passen auf jede Linie)")

    print("Zeichnungen")
    for name in katze.POSES:
        p = katze.pose(name)
        try:
            ET.fromstring(p["svg"].replace("&", "&amp;"))
            ok = True
        except ET.ParseError as exc:
            ok = False
            print("   ", exc)
        check(ok and p["w"] > 0 and p["h"] > 0, f"{name}: gültiges SVG ({p['w']}×{p['h']})")
        check("#" not in p["svg"], f"{name}: Farben nur über CSS-Variablen (Schwarz-Weiß-Modus)")

    print("Nachtbild (Katze auf dem Mond)")
    sys.path.insert(0, str(REPO / "tagesdashboard"))
    import nachtgrafik
    g = katze.on_moon(400, 30)
    try:
        ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{g}</svg>')
        ok = True
    except ET.ParseError:
        ok = False
    check(ok and "#FFE500" in g, "on_moon: gültiges SVG mit gelbem Z")
    night = datetime(2026, 11, 10, 23, 40, tzinfo=TZ)
    wx = {"cloud": 20}
    with_cat = nachtgrafik.svg(night, wx, cat=katze.on_moon)
    def cat_part(svg_):
        i = svg_.index('stroke-linecap="round"')
        return svg_[svg_.rindex("<g", 0, i):svg_.index("</g>", i)]
    check(cat_part(with_cat) == cat_part(nachtgrafik.svg(night.replace(minute=55), wx, cat=katze.on_moon)),
          "gleiche Nacht → Katze an derselben Stelle (kein Zufall, nightFreeze bleibt wirksam)")
    check(nachtgrafik.svg(night, wx) != with_cat and "stroke-width" in with_cat, "mit Katze anders als ohne")
    check(nachtgrafik.svg(night, {"cloud": 95, "wet": True}, cat=katze.on_moon).count("#FFE500\" fill=\"none\" d=\"M38") == 0,
          "kein Mond (Regen, ganz bedeckt) → keine Katze")
    # Mond mit Katze nie über Münster oder Langem Eugen (sitzt tiefer und würde dahinter verschwinden)
    import re
    bad = []
    for width in (800, 480, 756, 467, 516):  # seit 1.31 zeichnet das Dashboard die Szene in der Breite von nachtgrafik.band_width (756, 467, 516)
        s_ = nachtgrafik.scale(width)
        for i in range(60):
            svg_ = nachtgrafik.svg(night + timedelta(days=i), wx, width=width, cat=katze.on_moon)
            mx = float(re.search(r'<path d="M([0-9.]+),', svg_).group(1))
            if 60 * s_ < mx < 250 * s_ + 20:
                bad.append((width, i, mx))
    check(not bad, f"Mond mit Katze nie hinter Münster/Langem Eugen (60 Nächte, quer und hochkant){bad[:3]}")

    out = outside_viewbox()
    if out is None:
        print("  --      Posen in ihrer viewBox: übersprungen (Playwright fehlt)")
    else:
        check(not out, f"alle Posen liegen in ihrer viewBox (placeCat rechnet damit){out}")

    print()
    print("Alles in Ordnung." if not FAILS else f"{len(FAILS)} Fehler.")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
