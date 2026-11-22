"""Simulierte xkcd-Schnittstelle für dev/render.py --xkcd (Sonntagscomic, seit 1.40).

Die Comics sind erfundene Beispiele im Stil von xkcd (Strichmännchen, Handschrift), mit Pillow gezeichnet –
keine echten xkcd, damit die Screenshots in docs/ nichts fremdes zeigen. Größen wie bei echten Comics:
normale Fassung 1x (Schrift etwa 13 px), dazu „…_2x.png“ in doppelter Größe.

Handschrift: Liegt die Schrift „xkcd Script“ (ipython/xkcd-font, CC BY-NC 3.0) unter
dev/out/xkcd-script.ttf oder in XKCD_FONT, wird sie genommen, sonst DejaVu Sans. Herunterladen von
  https://raw.githubusercontent.com/ipython/xkcd-font/master/xkcd-script/font/xkcd-script.ttf

Szenarien (neuester Comic hat immer die Nummer 3327):
  normal   ein Feld, 440 × 400 – passt (Standard; erscheint nur sonntags ohne Termine, DEV_PROTO=frei)
  breit    3327 ist ein Streifen aus vier Feldern (740 × 230) → passt nicht, 3326 (ein Feld) wird genommen
  hoch     3327 sehr hoch (360 × 900) mit langem Mouseover-Text → Text fällt weg bzw. Bild wird kleiner
  farbig   ein Feld mit roter und blauer Fläche
  lang     ein Feld mit sehr langem Mouseover-Text (passt quer nicht dazu)
  keiner   alle acht letzten Comics sind breite Streifen → kein Comic, die Terminliste bleibt
  nur1x    keine doppelt großen Bilder (…_2x.png gibt 404)
  down     HTTP 503 → kein Comic, „● xkcd“ im Kopf
"""
import io
import json
import os
from pathlib import Path

import requests

NEWEST = 3327
DEV = Path(__file__).resolve().parent

ALT_SHORT = "The trick is to schedule nothing on Sunday, then claim the empty calendar was the plan all along."
ALT_LONG = ("Every weekend I promise myself I will finally sort the cables behind the desk, and every weekend "
            "the cables win. At this point I think they have formed a union, elected a speaker, and filed a "
            "formal complaint about the vacuum cleaner.")

_font_cache = {}


def _font(size):
    if size not in _font_cache:
        from PIL import ImageFont
        for cand in (os.environ.get("XKCD_FONT"), DEV / "out" / "xkcd-script.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if cand and Path(cand).exists():
                _font_cache[size] = ImageFont.truetype(str(cand), size)
                break
        else:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _figure(d, x, y, f, arm="down", color=(0, 0, 0)):
    """Strichmännchen, Füße bei (x, y)."""
    w = round(2 * f)
    head_r = 9 * f
    hy = y - 62 * f
    d.ellipse((x - head_r, hy - head_r, x + head_r, hy + head_r), outline=color, width=w)
    d.line((x, hy + head_r, x, y - 22 * f), fill=color, width=w)
    d.line((x, y - 22 * f, x - 10 * f, y), fill=color, width=w)
    d.line((x, y - 22 * f, x + 10 * f, y), fill=color, width=w)
    if arm == "up":
        d.line((x, y - 44 * f, x + 16 * f, y - 62 * f), fill=color, width=w)
    else:
        d.line((x, y - 44 * f, x + 14 * f, y - 30 * f), fill=color, width=w)
    d.line((x, y - 44 * f, x - 14 * f, y - 30 * f), fill=color, width=w)


def _panel(d, box, f, lines, color_fill=None, figures=2):
    x0, y0, x1, y1 = box
    if color_fill:
        d.rectangle((x0 + 30 * f, y1 - 70 * f, x0 + 110 * f, y1 - 12 * f), fill=color_fill[0])
        d.ellipse((x1 - 90 * f, y0 + 20 * f, x1 - 40 * f, y0 + 70 * f), fill=color_fill[1])
    d.rectangle(box, outline=(0, 0, 0), width=round(2 * f))
    font = _font(round(13 * f))
    ty = y0 + 12 * f
    for ln in lines:
        d.text((x0 + 14 * f, ty), ln, fill=(0, 0, 0), font=font)
        ty += 17 * f
    ground = y1 - 14 * f
    xs = [x0 + (x1 - x0) * (i + 1) / (figures + 1) for i in range(figures)]
    for i, x in enumerate(xs):
        _figure(d, x, ground, f, arm="up" if i == 0 else "down")
        d.line((x - 4 * f, ty + 2 * f, x, ground - 76 * f), fill=(0, 0, 0), width=max(1, round(f)))


def draw(kind, f):
    """Comic als PNG-Bytes in Faktor f (1 = normale Größe, 2 = doppelt)."""
    from PIL import Image, ImageDraw
    if kind == "breit":
        W, H = 740, 230
    elif kind == "hoch":
        W, H = 360, 900
    else:
        W, H = 440, 400
    img = Image.new("RGB", (round(W * f), round(H * f)), "white")
    d = ImageDraw.Draw(img)
    m = 4 * f
    if kind == "breit":
        texts = [["SO WHAT ARE YOU", "DOING TODAY?"], ["NOTHING. IT'S", "SUNDAY."], ["LIKE, NOTHING", "NOTHING?"],
                 ["I SCHEDULED IT", "IN MY CALENDAR."]]
        pw = (W * f - 2 * m) / 4
        for i, t in enumerate(texts):
            _panel(d, (m + i * pw + 3 * f, m, m + (i + 1) * pw - 3 * f, H * f - m), f, t, figures=1 if i % 2 else 2)
    elif kind == "hoch":
        ph = (H * f - 2 * m) / 3
        for i, t in enumerate([["STEP 1: CLEAR THE", "WHOLE SUNDAY."], ["STEP 2: TELL NO ONE."],
                               ["STEP 3: REFRESH THE", "E-INK DISPLAY", "EVERY FIVE MINUTES."]]):
            _panel(d, (m, m + i * ph + 3 * f, W * f - m, m + (i + 1) * ph - 3 * f), f, t)
    else:
        lines = ["MY E-INK DASHBOARD", "SAYS I'M FREE TODAY.", "", "      HOW DOES IT KNOW?", "",
                 "IT READ MY CALENDAR", "AND FOUND NOTHING.", "      THAT'S THE SADDEST", "      THING A COMPUTER",
                 "      HAS EVER SAID."]
        _panel(d, (m, m, W * f - m, H * f - m), f, lines,
               color_fill=((227, 0, 27), (0, 130, 201)) if kind == "farbig" else None)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _comic(num, kind):
    if kind == "keiner" or (kind == "breit" and num == NEWEST):
        shape = "breit"
    elif kind in ("hoch", "farbig") and num == NEWEST:
        shape = kind
    else:
        shape = "normal"
    titles = {NEWEST: "Empty Calendar", NEWEST - 1: "Sunday Plans", NEWEST - 2: "Cable Union"}
    alt = ALT_LONG if (kind in ("lang", "hoch") and num == NEWEST) else ALT_SHORT
    return {"num": num, "title": titles.get(num, f"Example {num}"), "safe_title": titles.get(num, f"Example {num}"),
            "alt": alt, "img": f"https://imgs.xkcd.com/comics/example_{num}_{shape}.png",
            "year": "2026", "month": "11", "day": "20", "link": "", "news": "", "transcript": ""}, shape


class _Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content = status, data, content
        self.text = json.dumps(data) if data is not None else ""

    def json(self):
        return self._data


calls = []  # zum Prüfen in Tests: welche Adressen wurden gefragt


def install(now=None, kind="normal"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "xkcd.com" not in url:
            return previous(session, url, params=params, timeout=timeout, **kw)
        calls.append(url)
        if kind == "down":
            return _Resp(503)
        if url.endswith("xkcd.com/info.0.json"):
            return _Resp(200, _comic(NEWEST, kind)[0])
        if url.endswith("/info.0.json"):
            num = int(url.rstrip("/").split("/")[-2])
            if num > NEWEST or num == 404:
                return _Resp(404)
            return _Resp(200, _comic(num, kind)[0])
        if "imgs.xkcd.com/comics/example_" in url:
            name = url.rsplit("/", 1)[1][:-4]
            double = name.endswith("_2x")
            if double and kind == "nur1x":
                return _Resp(404)
            shape = name.removesuffix("_2x").split("_")[-1]
            return _Resp(200, content=draw(shape, 2 if double else 1))
        return _Resp(404)

    requests.Session.get = fake_get
