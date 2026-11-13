"""
Simulierte RSS-Feeds für die Nachrichten des Tagesdashboards (erfundene Beispieltexte).

Szenarien (render.py --news ...):
  normal   alle drei Feeds da
  ohnega   General-Anzeiger nicht erreichbar -> Bonn aus WDR-Meldungen mit "Bonn"
  keine    alle Feeds nicht erreichbar -> Nachrichtenblock fehlt, Termine wie sonst

Absichtlich enthalten, damit die Filter geprüft werden: ein Liveblog, ein Ticker mit "++",
ein Video, ein GA-Artikel außerhalb von /bonn/, ein Artikel älter als 24 Stunden und
dasselbe Thema in zwei Feeds.
"""

from datetime import timedelta
from email.utils import format_datetime

import requests

SCENARIOS = ["normal", "ohnega", "keine"]


class _Resp:
    def __init__(self, text, status=200):
        self.content = text.encode("utf-8")
        self.status_code = status


def _rss(title, items, now):
    out = [f"<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel><title>{title}</title>"]
    for t, link, hours, desc in items:
        out.append(f"<item><title><![CDATA[{t}]]></title><link>{link}</link>"
                   f"<description><![CDATA[<p>{desc}</p>]]></description>"
                   f"<pubDate>{format_datetime(now - timedelta(hours=hours))}</pubDate></item>")
    out.append("</channel></rss>")
    return "".join(out)


def ga(now):
    return _rss("GA", [
        ("Liveblog: Alle Entwicklungen zum Sturm in der Region", "https://ga.de/bonn/liveblog-sturm_aid-1.html", 0.5, ""),
        ("Weihnachtsmarkt in der Innenstadt öffnet mit längeren Öffnungszeiten",
         "https://ga.de/bonn/stadt-bonn/weihnachtsmarkt_aid-2.html", 1.2, "Bonner Weihnachtsmarkt"),
        ("Siegburg plant neuen Busbahnhof", "https://ga.de/region/sieg-und-rhein/siegburg/busbahnhof_aid-3.html", 1.5, ""),
        ("Neue Taktung für mehrere Buslinien ab Dezember", "https://ga.de/bonn/stadt-bonn/buslinien_aid-4.html", 2.0, ""),
        ("Beethovenhalle: Termin für die Wiedereröffnung steht", "https://ga.de/bonn/kultur/beethovenhalle_aid-5.html", 30, "zu alt"),
    ], now)


def wdr(now):
    return _rss("WDR", [
        ("Landtag debattiert über mehr Lehrkräfte an Grundschulen", "https://www1.wdr.de/nachrichten/landespolitik/lehrkraefte-100.html", 0.8, ""),
        ("Video: So sieht es nach dem Sturm am Niederrhein aus", "https://www1.wdr.de/video/sturm-100.html", 1.0, ""),
        ("Bonner Polizei warnt vor falschen Handwerkern", "https://www1.wdr.de/nachrichten/rheinland/bonn-polizei-100.html", 1.3,
         "In Bonn sind mehrere Fälle bekannt geworden."),
        ("Bundestag berät über den Haushalt 2027 – was er für NRW bedeutet",
         "https://www1.wdr.de/nachrichten/haushalt-nrw-100.html", 1.6, ""),
        ("Bahnstrecke Köln–Bonn: Bauarbeiten am Wochenende", "https://www1.wdr.de/nachrichten/rheinland/bahn-koeln-bonn-100.html", 2.2,
         "Zwischen Köln und Bonn fallen Züge aus."),
    ], now)


def tagesschau(now):
    return _rss("tagesschau", [
        ("++ Sturmtief: Bahn stellt Fernverkehr teilweise ein ++", "https://www.tagesschau.de/newsticker/liveblog-sturm-100.html", 0.3, ""),
        ("Bundestag berät in erster Lesung über den Haushalt 2027", "https://www.tagesschau.de/inland/haushalt-2027-100.html", 0.9, ""),
        ("Inflationsrate im Oktober leicht gesunken", "https://www.tagesschau.de/wirtschaft/inflation-oktober-100.html", 1.8, ""),
        ("EU-Gipfel berät über gemeinsame Verteidigung", "https://www.tagesschau.de/ausland/eu-gipfel-100.html", 2.5, ""),
    ], now)


def franceinfo(now):
    """Erfundene französische Schlagzeilen (Beispieldaten) – mit Fällen für die Filter:
    DIRECT (Liveticker), VIDEO, Gattungsetikett „ENQUÊTE.“ und „INFO FRANCEINFO.“, ein zu alter Eintrag."""
    return _rss("franceinfo", [
        ("DIRECT. Tempête : 40 000 foyers privés d'électricité dans le Nord", "https://www.francetvinfo.fr/meteo/direct-tempete_1.html", 0.2, ""),
        ("Budget 2027 : l'Assemblée nationale adopte la première partie du projet de loi de finances",
         "https://www.francetvinfo.fr/politique/budget-2027_2.html", 0.7, ""),
        ("VIDEO. Les images de la crue de la Seine à Paris", "https://www.francetvinfo.fr/meteo/video-crue_3.html", 0.9, ""),
        ("INFO FRANCEINFO. Les communes rurales réclament davantage de médecins généralistes",
         "https://www.francetvinfo.fr/sante/communes-medecins_4.html", 1.4, ""),
        ("ENQUÊTE. Comment les villes moyennes se réinventent après la fermeture des usines",
         "https://www.francetvinfo.fr/economie/villes-moyennes_5.html", 2.1, ""),
        ("Coupe de France : le tirage au sort des 32es de finale", "https://www.francetvinfo.fr/sports/coupe_6.html", 30, "zu alt"),
    ], now)


def install(now, scenario):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "ga.de/" in url:
            if scenario in ("ohnega", "keine"):
                raise requests.ConnectionError("simulierter Ausfall GA")
            return _Resp(ga(now))
        if "wdr.de/" in url:
            if scenario == "keine":
                return _Resp("", 503)
            return _Resp(wdr(now))
        if "francetvinfo.fr/" in url or "franceinfo.fr/" in url:
            if scenario == "keine":
                raise requests.Timeout("simulierter Ausfall franceinfo")
            return _Resp(franceinfo(now))
        if "tagesschau.de/" in url:
            if scenario == "keine":
                raise requests.Timeout("simulierter Ausfall tagesschau")
            return _Resp(tagesschau(now))
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
