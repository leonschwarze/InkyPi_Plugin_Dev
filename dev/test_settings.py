"""Prüft die Einstellungsseiten von DWD Wetter, Nextcloud Kalender und Tagesdashboard:
Gehen beim Update Einstellungen verloren?

Für jeden Fall (gespeicherte Einstellungen einer älteren Version) läuft ein Rundlauf wie in echt:
  1. InkyPi zeigt die Einstellungsseite mit den gespeicherten Werten (pluginSettings),
  2. der Nutzer drückt sofort „Speichern“: InkyPis handleAction('update_instance') läuft samt den Prüfungen
     des Plugins, das Skript fängt den fetch ab und liest die Formulardaten, die gesendet würden
     (blockiert eine Prüfung, ist das ein Fehler),
  3. das Plugin liest die neuen Daten.
Verglichen wird, was das Plugin daraus macht („wirksame Einstellungen“): vorher (alte Daten, mit Migration) und
nachher (Formulardaten) müssen gleich sein. Ein zweiter Rundlauf muss dieselben Formulardaten ergeben.

Benötigt: InkyPi daneben (../InkyPi oder INKYPI_DIR), Chromium (wie dev/render.py) und Playwright:
  pip install playwright        # Browser-Download nicht nötig, das Skript nimmt die vorhandene Headless-Shell

  python dev/test_settings.py
  python dev/test_settings.py --shots   # zusätzlich Screenshots der Seiten nach dev/out/settings/
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEV = REPO / "dev"
PORT = 8080

# --------------------------------------------------------------------------
# Testfälle: so lagen Einstellungen früherer Versionen in InkyPis device.json
# --------------------------------------------------------------------------
STYLE = {"backgroundOption": "color", "backgroundColor": "#ffffff", "textColor": "#000000"}
DWD_BASE = {"latitude": "50.7374", "longitude": "7.0982", "showAlerts": "true", "showMetrics": "true",
            "showGraph": "true", "hourlyHours": "24", "graphIcons": "true", "nightShading": "true",
            "showForecast": "true", "forecastDays": "5", "einkSnap": "true", "showFooter": "true",
            "tile_wind": "true", "tile_gust": "true", "tile_humidity": "true", "tile_precip": "true",
            "tile_sunshine": "true", "tile_sun": "true", **STYLE}

DWD_CASES = {
    # Ortssuche hatte "Bonn" ins Titelfeld geschrieben, aktiv war aber der DWD-Name
    "v1 Titel auto, Feld gefüllt": {**DWD_BASE, "cfgVersion": "1", "titleSelection": "auto", "customTitle": "Bonn"},
    "v1 eigener Titel": {**DWD_BASE, "cfgVersion": "1", "titleSelection": "custom", "customTitle": "Zuhause"},
    "v1 eigener Titel, aber leer": {**DWD_BASE, "cfgVersion": "1", "titleSelection": "custom", "customTitle": "  "},
    "v1 vieles aus": {"cfgVersion": "1", "latitude": "52.52", "longitude": "13.405", "titleSelection": "auto",
                      "customTitle": "", "showGraph": "true", "hourlyHours": "48", "showForecast": "true",
                      "forecastDays": "7", "tile_pressure": "true", "tile_dewpoint": "true", "tile_cloudcover": "true",
                      **STYLE},
    "v1 Graph aus, Stunden gemerkt": {**DWD_BASE, "cfgVersion": "1", "titleSelection": "auto", "customTitle": "",
                                      "showGraph": None, "hourlyHours": "36", "einkSnap": None},
    # sehr alte Einstellungen ohne cfgVersion: fehlender Schlüssel = Standardwert
    "v0 ohne cfgVersion": {"latitude": "50.7374", "longitude": "7.0982", "customTitle": "Garten",
                           "showFooter": "false", "tile_visibility": "true", **STYLE},
    "v0 eigener Titel": {"latitude": "50.7374", "longitude": "7.0982", "titleSelection": "custom",
                         "customTitle": "Garten", **STYLE},
    "v2 neues Format": {**DWD_BASE, "cfgVersion": "2", "customTitle": "Balkon", "nightShading": None},
}

NC_BASE = {"nextcloudUrl": "https://cloud.example.de", "username": "leon", "passwordKey": "",
           "calendars": "Persönlich, SPD", "layout": "agenda", "days": "14", "weekStart": "today",
           "customTitle": "", "verifySSL": "true", "useColors": "true", "showLocation": "true", "showMonth": "true",
           "showEmptyToday": "true", "einkSnap": "true", "showFooter": "true", **STYLE}

NC_CASES = {
    "v1 Standard": {**NC_BASE, "cfgVersion": "1"},
    "v1 Woche, Montag, Titel": {**NC_BASE, "cfgVersion": "1", "layout": "week", "weekStart": "monday",
                                "days": "30", "customTitle": "Familie", "showMonth": None},
    "v1 Technik geändert": {**NC_BASE, "cfgVersion": "1", "passwordKey": "NC_ARBEIT", "verifySSL": None,
                            "einkSnap": None, "showPast": "true", "useColors": None},
    "v0 ohne cfgVersion": {"nextcloudUrl": "https://cloud.example.de", "username": "leon", "days": "7",
                           "showLocation": "false", **STYLE},
}

DB_BASE = {"latitude": "50.7374", "longitude": "7.0982", "nextcloudUrl": "https://cloud.example.de",
           "username": "leon", "calendars": "", "switchHour": "20", "sensitivity": "empfindlich",
           "calendarDays": "7", "showAlerts": "true", "showWear": "true", "showGraph": "true",
           "rainOnEvents": "true", "useColors": "true", "showLocation": "true", "verifySSL": "true",
           "einkSnap": "true", **STYLE}
DB_TRAIN = {"trainEnabled": "true", "trainStation": "Bonn Hbf", "trainLine": "RE 5", "trainTime": "08:04",
            "trainFrom": "06:30", "trainTo": "08:15", "trainDi": "true", "quietMinutes": "15"}
DB_NEWS = {"newsEnabled": "true", "newsFrom": "06:00", "newsTo": "09:30", "newsWeekendFrom": "08:00",
           "newsWeekendTo": "10:30", "newsBonnUrl": "https://ga.de/feed.rss", "newsBonnFilter": "/bonn/",
           "newsNrwUrl": "https://www1.wdr.de/uebersicht-100.feed",
           "newsBundUrl": "https://www.tagesschau.de/index~rss2.xml"}
DB_LATER = {"laundryEnabled": "true", "laundryFrom": "17:00", "laundryTo": "23:00",
            "nightEnabled": "true", "nightFrom": "23:00", "nightTo": "06:00", "nightFreeze": "true",
            "weekEnabled": "true", "weekFrom": "18:00", "weekTo": "23:00", "nightArt": "true",
            "trainTarget": "Düsseldorf Hbf", "trainAlerts": "true"}
DB_9 = {**DB_BASE, **DB_TRAIN, **DB_NEWS, **DB_LATER, "tripEnabled": "true", "tripBuffer": "5",
        "tripRainProb": "30", "tripMaxGap": "90", "tripLead": "120", "tripStart": "", "tripPlaces": "",
        "festXmas": "true", "festNye": "true", "festBday": "true",
        "birthdays": '[{"name":"Mia","day":12,"month":11,"year":1992}]'}

DB_CASES = {
    "v9 wie bei Leon (vor 1.11)": {**DB_9, "cfgVersion": "9"},
    "v9 Nachrichten aus, Wäsche überdacht": {**DB_9, "cfgVersion": "9", "newsEnabled": None, "laundryCovered": "true"},
    "v7 vor Anfahrt und Festtagen": {**DB_BASE, **DB_TRAIN, **DB_NEWS, **DB_LATER, "cfgVersion": "7"},
    "v4 vor Nachtbild": {**DB_BASE, **DB_TRAIN, **DB_NEWS, "cfgVersion": "4", "laundryEnabled": "true",
                         "laundryFrom": "17:00", "laundryTo": "23:00"},
    "v1 nur Wetter und Kalender": {**DB_BASE, "cfgVersion": "1", "showPast": "true", "useColors": None},
    "v0 ohne cfgVersion": {"latitude": "50.7374", "longitude": "7.0982", "nextcloudUrl": "https://cloud.example.de",
                           "username": "leon", "showGraph": "false", "useColors": "false", **STYLE},
    "v10 Radar aus, Frankreich an": {**DB_9, "cfgVersion": "10", "radarEnabled": None, "newsFrEnabled": "true",
                                     "newsFrUrl": "https://www.lemonde.fr/rss/une.xml"},
    # 1.12: Luftqualität aus, Unteroptionen gemerkt (müssen erhalten bleiben)
    "v11 Luft aus, Unteroptionen gemerkt": {**DB_9, "cfgVersion": "11", "radarEnabled": "true", "airEnabled": None,
                                            "airLevel": "4", "airRadius": "5", "airGases": "true",
                                            "airStation": "DENW175"},
    "v11 Luft an, Standard": {**DB_9, "cfgVersion": "11", "radarEnabled": "true", "airEnabled": "true",
                              "airLevel": "3", "airRadius": "3", "airStation": "DENW062"},
    # 1.13: Streckenmeldungen (VRR) – aus bzw. bei abgeschaltetem Störungsmonitor gemerkt
    "v12 Strecke aus": {**DB_9, "cfgVersion": "12", "radarEnabled": "true", "airEnabled": "true",
                        "trainAlerts": "true", "trainRoute": None},
    "v12 Störungsmonitor aus, Strecke gemerkt": {**DB_9, "cfgVersion": "12", "radarEnabled": "true",
                                                 "airEnabled": "true", "trainAlerts": None, "trainRoute": "true"},
    # 1.14: Katze – aus mit gemerkter Wetter-Option bzw. an ohne Wetter
    "v13 Katze aus, Wetter gemerkt": {**DB_9, "cfgVersion": "13", "radarEnabled": "true", "airEnabled": "true",
                                      "trainRoute": "true", "catEnabled": None, "catWeather": "true"},
    "v13 Katze an, ohne Wetter": {**DB_9, "cfgVersion": "13", "radarEnabled": "true", "airEnabled": "true",
                                  "trainRoute": "true", "catEnabled": "true", "catWeather": None},
    # 1.15: Katze im Nachtbild – aus, bzw. Katze ganz aus mit gemerktem Nachtbild-Schalter
    "v14 Katze nicht im Nachtbild": {**DB_9, "cfgVersion": "14", "radarEnabled": "true", "airEnabled": "true",
                                     "trainRoute": "true", "catEnabled": "true", "catWeather": "true",
                                     "catNight": None},
    "v14 Katze aus, Nachtbild gemerkt": {**DB_9, "cfgVersion": "14", "radarEnabled": "true", "airEnabled": "true",
                                         "trainRoute": "true", "catEnabled": None, "catWeather": "true",
                                         "catNight": "true"},
    # 1.16: Pollenflug – aus mit gemerkter Stufe/Arten bzw. an mit eigener Auswahl
    "v15 Pollen aus, Stufe und Arten gemerkt": {**DB_9, "cfgVersion": "15", "radarEnabled": "true",
                                                "airEnabled": "true", "trainRoute": "true", "catEnabled": "true",
                                                "catWeather": "true", "catNight": "true", "pollenEnabled": None,
                                                "pollenLevel": "3", "pollenHasel": "true", "pollenErle": "true",
                                                "pollenEsche": "true", "pollenBirke": None, "pollenGraeser": "true",
                                                "pollenRoggen": "true", "pollenBeifuss": "true",
                                                "pollenAmbrosia": None},
    "v15 Pollen an, nur Gräser und Birke": {**DB_9, "cfgVersion": "15", "radarEnabled": "true", "airEnabled": "true",
                                            "trainRoute": "true", "catEnabled": "true", "catWeather": "true",
                                            "catNight": "true", "pollenEnabled": "true", "pollenLevel": "2",
                                            "pollenHasel": None, "pollenErle": None, "pollenEsche": None,
                                            "pollenBirke": "true", "pollenGraeser": "true", "pollenRoggen": None,
                                            "pollenBeifuss": None, "pollenAmbrosia": None,
                                            "pollenRegion": "32"},
    # 1.17: Sternschnuppenströme – aus bzw. an (gemeinsam mit nightArt, da verschachtelt)
    "v15 Sternschnuppen noch unbekannt (nightArt aus)": {**DB_9, "cfgVersion": "15", "radarEnabled": "true",
                                                         "airEnabled": "true", "trainRoute": "true",
                                                         "catEnabled": "true", "catWeather": "true",
                                                         "catNight": "true", "pollenEnabled": "true",
                                                         "nightArt": None},
    "v16 Sternschnuppen aus, Rest wie gehabt": {**DB_9, "cfgVersion": "16", "radarEnabled": "true",
                                                "airEnabled": "true", "trainRoute": "true", "catEnabled": "true",
                                                "catWeather": "true", "catNight": "true", "pollenEnabled": "true",
                                                "nightArt": "true", "meteorEnabled": None},
    # 1.18: Mondfinsternisse – aus bzw. an (gemeinsam mit nightArt, da verschachtelt)
    "v16 Finsternisse noch unbekannt (nightArt aus)": {**DB_9, "cfgVersion": "16", "radarEnabled": "true",
                                                       "airEnabled": "true", "trainRoute": "true",
                                                       "catEnabled": "true", "catWeather": "true",
                                                       "catNight": "true", "pollenEnabled": "true",
                                                       "meteorEnabled": "true", "nightArt": None},
    "v17 Finsternisse aus, Rest wie gehabt": {**DB_9, "cfgVersion": "17", "radarEnabled": "true",
                                              "airEnabled": "true", "trainRoute": "true", "catEnabled": "true",
                                              "catWeather": "true", "catNight": "true", "pollenEnabled": "true",
                                              "nightArt": "true", "meteorEnabled": "true", "eclipseEnabled": None},
    # 1.19: Helle Planeten – aus bzw. an (gemeinsam mit nightArt, da verschachtelt)
    "v17 Planeten noch unbekannt (nightArt aus)": {**DB_9, "cfgVersion": "17", "radarEnabled": "true",
                                                   "airEnabled": "true", "trainRoute": "true", "catEnabled": "true",
                                                   "catWeather": "true", "catNight": "true", "pollenEnabled": "true",
                                                   "meteorEnabled": "true", "eclipseEnabled": "true", "nightArt": None},
    "v18 Planeten aus, Rest wie gehabt": {**DB_9, "cfgVersion": "18", "radarEnabled": "true",
                                          "airEnabled": "true", "trainRoute": "true", "catEnabled": "true",
                                          "catWeather": "true", "catNight": "true", "pollenEnabled": "true",
                                          "nightArt": "true", "meteorEnabled": "true", "eclipseEnabled": "true",
                                          "planetEnabled": None},
}


def clean(d):
    """None = Checkbox war nicht angehakt, d. h. der Schlüssel fehlt in den gespeicherten Daten."""
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------
# Was das Plugin aus den Einstellungen macht
# --------------------------------------------------------------------------
def effective_dwd(mod, settings):
    s = mod.migrate_settings(settings)
    plugin = mod.DwdWetter.__new__(mod.DwdWetter)
    eff = dict(plugin._options(s))
    eff["title"] = (s.get("customTitle") or "").strip() or "<DWD-Name>"
    eff["latitude"], eff["longitude"] = s.get("latitude"), s.get("longitude")
    eff["style"] = {k: s.get(k) for k in STYLE}
    return eff


def effective_nc(mod, settings):
    plugin = mod.NextcloudKalender.__new__(mod.NextcloudKalender)
    eff = {k: plugin._opt(settings, k) for k in mod.DEFAULTS}
    for k in ("nextcloudUrl", "username", "calendars", "customTitle"):
        eff[k] = (settings.get(k) or "").strip()
    eff["passwordKey"] = (settings.get("passwordKey") or mod.DEFAULT_PASSWORD_KEY).strip()
    eff["style"] = {k: settings.get(k) for k in STYLE}
    return eff


def effective_db(mod, settings):
    plugin = mod.Tagesdashboard.__new__(mod.Tagesdashboard)
    eff = {k: plugin._opt(settings, k) for k in mod.DEFAULTS}
    try:  # gleiche Liste, egal wie die Seite das JSON formatiert
        eff["birthdays"] = json.loads(eff["birthdays"] or "[]")
    except ValueError:
        pass
    for k in ("latitude", "longitude", "nextcloudUrl", "username", "calendars"):
        eff[k] = (settings.get(k) or "").strip()
    eff["style"] = {k: settings.get(k) for k in STYLE}
    return eff


# --------------------------------------------------------------------------
# InkyPi-Entwicklungsserver und Browser
# --------------------------------------------------------------------------
def find_chromium():
    for name in ("chromium-headless-shell", "chromium", "chrome", "google-chrome"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("Chromium nicht gefunden (siehe Handbuch „Testen“).")


def port_open():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_inkypi(inkypi_src):
    if port_open():
        sys.exit(f"Port {PORT} ist belegt – läuft schon ein InkyPi? Bitte beenden (Templates werden sonst nicht neu geladen).")
    proc = subprocess.Popen([sys.executable, "inkypi.py", "--dev"], cwd=inkypi_src,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    for _ in range(60):
        if port_open():
            return proc
        time.sleep(0.5)
    proc.kill()
    sys.exit("InkyPi-Entwicklungsserver startet nicht.")


# Echter Speicherweg: InkyPis handleAction (mit den Prüfungen des Plugins), fetch wird abgefangen
SAVE_JS = """async () => {
    let sent = null;
    window.fetch = async (url, opts) => {
        if (opts && opts.body instanceof FormData) {
            sent = {};
            for (const [k, v] of opts.body.entries()) { if (typeof v === 'string') sent[k] = v; }
        }
        return new Response(JSON.stringify({success: true, message: 'ok'}),
                            {headers: {'Content-Type': 'application/json'}});
    };
    await window.handleAction('update_instance');
    return sent;
}"""


def form_after_save(browser, plugin, saved, shot=None):
    """Seite mit gespeicherten Einstellungen öffnen und die Formulardaten zurückgeben (= was gespeichert würde)."""
    page = browser.new_page(viewport={"width": 420, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/unpkg.com/**", lambda r: r.abort())      # Leaflet/Karte wird hier nicht gebraucht

    def patch(route):
        resp = route.fetch()
        html = resp.text()
        a = "const pluginSettings = {};"
        b = "const loadPluginSettings = pluginInstanceName != '';"
        assert a in html and b in html, "InkyPis plugin.html hat sich geändert – test_settings.py anpassen"
        html = html.replace(a, "const pluginSettings = " + json.dumps(saved) + ";", 1)
        html = html.replace(b, "const loadPluginSettings = true;", 1)
        route.fulfill(response=resp, body=html)

    page.route(f"**/plugin/{plugin}", patch)
    page.goto(f"http://127.0.0.1:{PORT}/plugin/{plugin}", wait_until="load")
    if shot:
        page.query_selector("#settingsForm").screenshot(path=str(shot))
    data = page.evaluate(SAVE_JS)
    page.close()
    if errors:
        raise AssertionError(f"JavaScript-Fehler: {errors}")
    if data is None:
        raise AssertionError("Speichern blockiert (Prüfung der Seite schlug fehl)")
    return data


def diff(a, b):
    keys = sorted(set(a) | set(b))
    return [f"    {k}: vorher {a.get(k)!r} → nachher {b.get(k)!r}" for k in keys if a.get(k) != b.get(k)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inkypi", default=os.environ.get("INKYPI_DIR", str(REPO.parent / "InkyPi")))
    ap.add_argument("--shots", action="store_true", help="Screenshots nach dev/out/settings/")
    args = ap.parse_args()

    inkypi_src = Path(args.inkypi).resolve() / "src"
    if not (inkypi_src / "plugins" / "base_plugin").exists():
        sys.exit(f"InkyPi nicht gefunden unter {inkypi_src} – mit --inkypi angeben.")
    sys.path.insert(0, str(DEV))
    from render import link_plugins
    link_plugins(inkypi_src)
    sys.path.insert(0, str(inkypi_src))
    sys.path.insert(0, str(REPO / "dwd_wetter"))
    sys.path.insert(0, str(REPO / "nextcloud_kalender"))
    import dwd_wetter
    import nextcloud_kalender
    import re
    from plugins.tagesdashboard import tagesdashboard
    html = (REPO / "tagesdashboard" / "settings.html").read_text(encoding="utf-8")
    tagesdashboard.CFG_VERSION = int(re.search(r'name="cfgVersion" value="(\d+)"', html).group(1))

    from playwright.sync_api import sync_playwright
    shots = DEV / "out" / "settings"
    if args.shots:
        shots.mkdir(parents=True, exist_ok=True)

    suites = [("dwd_wetter", DWD_CASES, dwd_wetter, effective_dwd),
              ("nextcloud_kalender", NC_CASES, nextcloud_kalender, effective_nc),
              ("tagesdashboard", DB_CASES, tagesdashboard, effective_db)]
    failed = 0
    server = start_inkypi(inkypi_src)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=find_chromium())
            for plugin, cases, mod, effective in suites:
                print(f"\n{plugin} (cfgVersion {mod.CFG_VERSION})")
                for i, (name, raw) in enumerate(cases.items()):
                    saved = clean(raw)
                    shot = shots / f"{plugin}_{i}.png" if args.shots else None
                    problems = []
                    try:
                        form1 = form_after_save(browser, plugin, saved, shot)
                        form2 = form_after_save(browser, plugin, form1)
                        before, after = effective(mod, saved), effective(mod, form1)
                        problems += diff(before, after)
                        if form2 != form1:
                            problems.append("  zweiter Rundlauf ändert die Daten:")
                            problems += diff(form1, form2)
                        if form1.get("cfgVersion") != str(mod.CFG_VERSION):
                            problems.append(f"    cfgVersion im Formular: {form1.get('cfgVersion')!r}")
                        # Kein gespeicherter Wert darf einfach verschwinden (außer bewusst migrierten Schlüsseln)
                        gone = set(saved) - set(form1) - {"titleSelection"}
                        gone = {k for k in gone if saved[k] != "false"}   # v0: "false" fehlt jetzt, wirkt gleich
                        if gone:
                            problems.append(f"    nicht mehr gespeichert: {sorted(gone)}")
                    except AssertionError as exc:
                        problems.append(f"    {exc}")
                    if problems:
                        failed += 1
                        print(f"  FEHLER  {name}")
                        print("\n".join(problems))
                    else:
                        print(f"  ok      {name}")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    # Migration ohne Browser: konkrete Erwartungen an den Titel
    m = dwd_wetter.migrate_settings
    title = lambda s: (m(s).get("customTitle") or "").strip()  # noqa: E731
    checks = [
        (title({"cfgVersion": "1", "titleSelection": "auto", "customTitle": "Bonn"}), ""),
        (title({"cfgVersion": "1", "titleSelection": "custom", "customTitle": "Zuhause"}), "Zuhause"),
        (title({"customTitle": "Garten"}), ""),                      # v0: Standard war "auto"
        (title({"cfgVersion": "2", "customTitle": "Balkon"}), "Balkon"),
        ("titleSelection" in m({"cfgVersion": "1", "titleSelection": "auto"}), False),
    ]
    orig = {"cfgVersion": "1", "titleSelection": "auto", "customTitle": "Bonn"}
    m(orig)
    checks.append((orig.get("customTitle"), "Bonn"))                  # Original bleibt unverändert
    bad = [(i, got, want) for i, (got, want) in enumerate(checks) if got != want]
    print(f"\nmigrate_settings: {len(checks) - len(bad)}/{len(checks)} ok")
    for i, got, want in bad:
        print(f"  Prüfung {i}: {got!r} statt {want!r}")
    failed += len(bad)

    print("\nAlles in Ordnung." if not failed else f"\n{failed} Fehler.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
