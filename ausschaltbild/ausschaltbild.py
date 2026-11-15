"""Ausschaltbild für InkyPi: „Ausgeschaltet – der Stecker kann gezogen werden“.

Ein E-Ink-Display braucht nur Strom, während es das Bild wechselt; danach bleibt das Bild
ohne Strom stehen. Dieses Skript zeichnet beim Ausschalten des Raspberry Pi ein letztes
Bild: die schlafende Katze aus dem Tagesdashboard auf einem Kissen, dazu der Hinweis,
dass der Stecker gezogen werden kann, und wann heruntergefahren wurde.

Aufgerufen wird es vom systemd-Dienst `inkypi-ausschaltbild.service` (ExecStop). Beim
Herunterfahren stoppt systemd die Dienste in umgekehrter Startreihenfolge; der Dienst ist
`Before=inkypi.service`, läuft also erst, wenn InkyPi schon beendet ist (sonst würden zwei
Programme gleichzeitig auf das Display schreiben) und solange die Speicherkarte noch
beschreibbar ist.

Aufrufe:
  ausschaltbild.py --beim-ausschalten   vom Dienst: nur zeichnen, wenn der Pi ausgeschaltet wird
                                        (nicht beim Neustart – dann wäre der Hinweis falsch)
  ausschaltbild.py --zeigen             sofort aufs Display (Test; InkyPi vorher stoppen)
  ausschaltbild.py --png datei.png      nur als Bild speichern (ohne Display)
      [--size 800x480] [--vertical] [--time "2026-11-15 22:14"]
  ausschaltbild.py --probe              Prüfung bei der Installation: Einstellungen, Schrift,
                                        Treiber vorhanden? Bild nach /tmp

Dieses Skript darf das Herunterfahren nie aufhalten: Jeder Fehler wird nur protokolliert
(journalctl -u inkypi-ausschaltbild, dazu die Datei letzter-lauf.txt neben dem Skript).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eink  # noqa: E402  (Kopie von shared/eink.py, siehe dev/sync_lib.py)

VERSION = "1.0"
INKYPI = Path("/usr/local/inkypi")
DEVICE_JSON = INKYPI / "src" / "config" / "device.json"
FONT_DIRS = [INKYPI / "src" / "static" / "fonts", HERE]
FONT_NAME = "Jost-SemiBold.ttf"          # Jost 600 wie im Dashboard
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LOG_FILE = HERE / "letzter-lauf.txt"

# Gestaltungsfarben (wie im Dashboard); eink.py rastet sie auf die Displayfarben ein
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 196, 0)
BLUE = (0, 130, 201)

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
SS = 4                                   # Überabtastung für die Katze (glatte Kurven)

# ---------------------------------------------------------------- die Katze

# Pfade der Pose „schläft“ aus tagesdashboard/katze.py (schlaeft()), dazu ein Kissen.
# dev/test_ausschaltbild.py prüft, dass sie mit katze.py übereinstimmen – bis auf den
# Anfang des Körpers: Im Dashboard (Katze ~40 px) verschmelzen Körper- und Kopflinie links;
# hier, 6-mal so groß, liefen sie als Doppellinie nebeneinander. Der Körper beginnt deshalb
# unter dem Kopf (M12 29 Q8 13 statt M5 29 Q3 13) und verschwindet dort hinter dessen Fläche.
# Art: F = Fläche (weiß) mit Kontur, L = nur Linie, D = schwarz gefüllt.
CAT_W, CAT_H = 54, 30
CAT = [
    ("F", "M12 29 Q8 13 22 11 Q42 10 47 23 Q48.5 29 44 29 Z"),                      # Körper
    ("L", "M46.5 26 Q42 29.5 33 28 Q28.5 27.2 29.5 24.8"),                         # Schwanz
    ("F", "M7 29 Q5 21 9.5 17.5 L10 10.5 L15 14.5 Q18 13.8 21 15 L26 12 L25.5 18.5"
          " Q28.5 23.5 25 29 Z"),                                                  # Kopf
    ("L", "M11.5 21.8 Q13.3 23.4 15.1 21.8 M18 21.8 Q19.8 23.4 21.6 21.8"),        # Augen zu
    ("D", "M15.5 24.6 L18 24.6 L16.75 25.9 Z"),                                    # Nase
]
# Kissen unter der Katze (gelb): Kanten nach außen gewölbt, Ecken als Zipfel; die Oberkante
# wölbt sich über die Unterkante der Katze (y = 29) – sie sinkt ein wenig ein.
CUSHION = "M-6 27.5 Q27 23.5 60 27.5 Q63 33.5 60 39.5 Q27 42.5 -6 39.5 Q-9 33.5 -6 27.5 Z"
CUSHION_TUFTS = ["M-3.5 30.5 L-1.5 31.5", "M57.5 30.5 L55.5 31.5",       # Falten an den Zipfeln
                 "M-3.5 36.5 L-1.5 35.5", "M57.5 36.5 L55.5 35.5"]
# „Z Z“ in Blau (größer als im Dashboard, wo es nur ~3 px wären)
ZZ = ["M40 3 h6 l-6 6 h6", "M49 -4.5 h4.5 l-4.5 4.5 h4.5"]   # mit Abstand über dem Rücken
ART_X0, ART_Y0, ART_X1, ART_Y1 = -9.5, -6, 63.5, 42.5   # Begrenzung aller Formen (Einheiten)

_TOKEN = re.compile(r"[MLQZhlz]|-?\d*\.?\d+")


def path_points(d, steps=14):
    """SVG-Pfad (nur M, L, Q, Z, h, l) -> Liste von (Punkte, geschlossen)."""
    tokens = _TOKEN.findall(d)
    shapes, pts, x, y, cmd, i = [], [], 0.0, 0.0, None, 0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if re.fullmatch(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
        if cmd == "M":
            if pts:
                shapes.append((pts, False))
            x, y = num(), num()
            pts = [(x, y)]
            cmd = "L"                    # weitere Zahlenpaare nach M sind Linien
        elif cmd == "L":
            x, y = num(), num()
            pts.append((x, y))
        elif cmd == "l":
            x, y = x + num(), y + num()
            pts.append((x, y))
        elif cmd == "h":
            x += num()
            pts.append((x, y))
        elif cmd == "Q":
            cx, cy, ex, ey = num(), num(), num(), num()
            for s in range(1, steps + 1):
                t = s / steps
                pts.append(((1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t * t * ex,
                            (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t * t * ey))
            x, y = ex, ey
        elif cmd in ("Z", "z"):
            shapes.append((pts, True))
            pts = []
            cmd = None
        else:
            raise ValueError(f"Pfadbefehl nicht unterstützt: {cmd!r} in {d!r}")
    if pts:
        shapes.append((pts, False))
    return shapes


def _stroke(draw, pts, closed, width, colour):
    if closed:
        pts = pts + [pts[0], pts[1] if len(pts) > 1 else pts[0]]
    draw.line(pts, fill=colour, width=width, joint="curve")
    r = width / 2                        # runde Enden (PIL kennt nur eckige)
    for px, py in (pts[0], pts[-1]):
        draw.ellipse([px - r, py - r, px + r, py + r], fill=colour)


def art_size(scale):
    """Breite und Höhe der Zeichnung in Pixeln bei scale Pixeln je Einheit."""
    return (ART_X1 - ART_X0) * scale, (ART_Y1 - ART_Y0) * scale


def draw_art(dr, x0, y0, scale, stroke):
    """Katze auf dem Kissen zeichnen; (x0, y0) = linke obere Ecke, scale = Pixel je Einheit,
    stroke = Strich in Pixeln (alles schon in der überabgetasteten Größe)."""
    sw = max(1, round(stroke))

    def tr(points):
        return [(x0 + (px - ART_X0) * scale, y0 + (py - ART_Y0) * scale) for px, py in points]

    def shape(kind, d, fill=WHITE, line=BLACK):
        for pts, closed in path_points(d):
            p = tr(pts)
            if kind in ("F", "D") and closed:
                dr.polygon(p, fill=BLACK if kind == "D" else fill)
            if kind != "D":
                _stroke(dr, p, closed, sw, line)

    shape("F", CUSHION, fill=YELLOW)
    for d in CUSHION_TUFTS:
        shape("L", d)
    for kind, d in CAT:
        shape(kind, d)
    for d in ZZ:
        shape("L", d, line=BLUE)


# ---------------------------------------------------------------- Text und Layout

def find_font():
    for d in FONT_DIRS:
        if (d / FONT_NAME).exists():
            return str(d / FONT_NAME)
    return FONT_FALLBACK if os.path.exists(FONT_FALLBACK) else None


def font(path, size):
    if path:
        return ImageFont.truetype(path, max(8, round(size)))
    return ImageFont.load_default(size=max(8, round(size)))


def wrap(draw, text, fnt, width):
    """Zeilenumbruch nach Wörtern, damit nichts über den Rand läuft. Bei zwei Zeilen werden
    sie ausgeglichen („Der Stecker kann jetzt / gezogen werden.“ statt eines einzelnen
    „werden.“ in der zweiten Zeile)."""
    lines, line = [], ""
    words = text.split()
    for word in words:
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=fnt) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    lines += [line] if line else []
    if len(lines) == 2:
        splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
        fits = [s for s in splits if max(draw.textlength(x, font=fnt) for x in s) <= width]
        if fits:
            lines = list(min(fits, key=lambda s: max(draw.textlength(x, font=fnt) for x in s)))
    return lines


def when_text(when):
    return f"{WEEKDAYS[when.weekday()]} {when.day}.{when.month}. · {when.hour}:{when.minute:02d} Uhr"


def unit(width, height):
    """--u wie im Dashboard (quer min(1vw, 1,667vh), hochkant min(1,45vw, 0,98vh))."""
    if width >= height:
        return min(width / 100, height / 60)
    return min(width * 1.45 / 100, height * 0.98 / 100)


def build(width, height, when, font_path=None):
    """Bild in Leserichtung (hochkant schon gedreht), Gestaltungsfarben, noch nicht eingerastet.

    Gezeichnet wird ss-mal so groß und am Ende verkleinert: Kurven werden glatt, und die
    Schrift bekommt gleichmäßige Abstände (bei Originalgröße rundet FreeType jeden Buchstaben
    einzeln, dann stand da „gef ahren“). eink.py macht die grauen Kanten danach wieder hart.
    """
    font_path = font_path or find_font()
    ss = SS if width * height <= 900_000 else 2       # 1600×1200 wäre ×4 zu viel für einen Pi Zero
    u = unit(width, height) * ss
    W, H = width * ss, height * ss
    portrait = height > width
    img = Image.new("RGB", (W, H), WHITE)
    dr = ImageDraw.Draw(img)

    # Texte: Titel groß, Hinweis mittel, Zeitpunkt und LED-Hinweis klein (≥ 1,7 u)
    sizes = {"title": 7 * u, "main": 3.2 * u, "small": 2.3 * u}
    f = {k: font(font_path, v) for k, v in sizes.items()}
    blocks = [
        ("Ausgeschaltet", "title", 1.4 * u),
        ("Der Stecker kann jetzt gezogen werden.", "main", 2.4 * u),
        (f"Heruntergefahren {when_text(when)}", "small", 0.7 * u),
        ("Grüne LED am Pi aus? Dann ist er fertig.", "small", 0),
    ]

    # Zeichnung (Kissen samt Katze) 38 u breit quer, 46 u hochkant
    art_scale = (46 if portrait else 38) * u / (ART_X1 - ART_X0)
    art_w, art_h = art_size(art_scale)
    margin, gap = 4 * u, (3 if portrait else 4) * u
    text_w = W - 2 * margin if portrait else W - 2 * margin - art_w - gap

    # Text setzen: Zeilen umbrechen und messen. Zeilenhöhe = Schriftgröße (Oberkante der
    # Großbuchstaben bis Unterlänge passt hinein), dazu Abstände je Block.
    lines = []
    for text, key, after in blocks:
        parts = wrap(dr, text, f[key], text_w)
        for n, part in enumerate(parts):
            lead = after if n == len(parts) - 1 else 0.25 * sizes[key]
            lines.append((part, f[key], sizes[key], lead))
    text_h = sum(h + a for _, _, h, a in lines)
    longest = max(dr.textlength(t, font=fn) for t, fn, _, _ in lines)

    def put(x, y, text, fn, size):
        # anchor "ls" = linke Grundlinie; die Grundlinie liegt bei ~0,8 der Schriftgröße
        dr.text((x, y + 0.8 * size), text, font=fn, fill=BLACK, anchor="ls")

    if portrait:
        total = art_h + gap + text_h
        y0 = (H - total) / 2
        draw_art(dr, (W - art_w) / 2, y0, art_scale, 0.6 * u)
        y = y0 + art_h + gap
        for text, fn, h, after in lines:
            put((W - dr.textlength(text, font=fn)) / 2, y, text, fn, h)
            y += h + after
    else:
        x0 = (W - (art_w + gap + longest)) / 2
        draw_art(dr, x0, (H - art_h) / 2, art_scale, 0.6 * u)
        x, y = x0 + art_w + gap, (H - text_h) / 2
        for text, fn, h, after in lines:
            put(x, y, text, fn, h)
            y += h + after
    return img.resize((width, height), Image.BOX) if ss > 1 else img


# ---------------------------------------------------------------- InkyPi-Einstellungen

def load_device(path=DEVICE_JSON):
    with open(path) as f:
        return json.load(f)


def settings_of(device):
    """Auflösung, Drehung und Treiber-Sättigung so, wie InkyPi sie verwendet."""
    res = device.get("resolution") or [800, 480]
    width, height = int(res[0]), int(res[1])
    orientation = device.get("orientation", "horizontal")
    inverted = bool(device.get("inverted_image", False))
    try:
        saturation = float((device.get("image_settings") or {}).get("inky_saturation", 0.5))
    except (TypeError, ValueError):
        saturation = 0.5
    tz = device.get("timezone") or "Europe/Berlin"
    return {"width": width, "height": height, "orientation": orientation, "inverted": inverted,
            "saturation": saturation, "timezone": tz, "display_type": device.get("display_type", "inky")}


def local_now(tz):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now()


def for_display(img, cfg):
    """Einrasten und drehen wie InkyPis display_manager (hochkant 90°, „inverted“ +180°)."""
    out = eink.snap(img, cfg["saturation"])
    if cfg["orientation"] == "vertical":
        out = out.rotate(90, expand=1)
    if cfg["inverted"]:
        out = out.rotate(180)
    return out


def logical_size(cfg):
    w, h = cfg["width"], cfg["height"]
    return (h, w) if cfg["orientation"] == "vertical" else (w, h)


def forget_image_hash(path=DEVICE_JSON):
    """InkyPi überspringt ein Bild, das gleich dem zuletzt gezeigten ist (Prüfsumme in
    device.json). Das Nachtbild ist die ganze Nacht gleich – nach dem Einschalten bliebe
    sonst das Ausschaltbild stehen. Deshalb die Prüfsumme vergessen (atomar schreiben:
    erst eine neue Datei, dann umbenennen)."""
    device = load_device(path)
    info = device.get("refresh_info") or {}
    if info.get("image_hash") is None:
        return False
    info["image_hash"] = None
    device["refresh_info"] = info
    fd, tmp = tempfile.mkstemp(dir=str(Path(path).parent), prefix=".device-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(device, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    st = os.stat(path)
    os.chmod(tmp, st.st_mode & 0o777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, path)
    return True


# ---------------------------------------------------------------- Ausschalten erkennen

_POWEROFF = re.compile(r"^\s*\d+\s+(poweroff|halt)\.target\s+start\b", re.M)


def shutdown_kind(jobs_text):
    """Aus `systemctl list-jobs`: 'poweroff' (auch halt), 'reboot' bzw. None."""
    if _POWEROFF.search(jobs_text):
        return "poweroff"
    if re.search(r"^\s*\d+\s+(reboot|kexec|soft-reboot)\.target\s+start\b", jobs_text, re.M):
        return "reboot"
    return None


def current_shutdown():
    try:
        out = subprocess.run(["systemctl", "list-jobs", "--no-legend", "--no-pager"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception as e:
        log(f"systemctl list-jobs fehlgeschlagen: {e}")
        return None
    return shutdown_kind(out)


# ---------------------------------------------------------------- Display

def show(img):
    from inky.auto import auto   # erst hier: --png läuft auch ohne Display-Treiber
    display = auto()
    display.set_border(display.BLACK)    # wie InkyPi
    if img.size != (display.width, display.height):
        raise ValueError(f"Bild {img.size} passt nicht zum Display {display.width}x{display.height}")
    return display


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def draw_now(cfg, when):
    t0 = time.monotonic()
    img = for_display(build(*logical_size(cfg), when), cfg)
    display = show(img)
    display.set_image(img, saturation=cfg["saturation"])
    display.show()                       # wartet, bis das Display fertig ist (bis ~30 s)
    log(f"Ausschaltbild gezeichnet in {time.monotonic() - t0:.1f} s")


def inkypi_active():
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", "inkypi.service"], timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ausschaltbild für InkyPi")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--beim-ausschalten", action="store_true", help="vom systemd-Dienst (ExecStop)")
    mode.add_argument("--zeigen", action="store_true", help="sofort aufs Display (InkyPi vorher stoppen)")
    mode.add_argument("--png", metavar="DATEI", help="nur als PNG speichern")
    mode.add_argument("--probe", action="store_true", help="Prüfung bei der Installation")
    ap.add_argument("--size", help="z. B. 800x480 (nur mit --png; sonst aus device.json)")
    ap.add_argument("--vertical", action="store_true", help="hochkant (nur mit --png)")
    ap.add_argument("--time", help='Zeitpunkt, z. B. "2026-11-15 22:14" (nur mit --png)')
    ap.add_argument("--device", default=str(DEVICE_JSON), help="Pfad zu InkyPis device.json")
    a = ap.parse_args(argv)

    if a.png:
        if a.size:
            w, h = (int(v) for v in a.size.lower().split("x"))
            cfg = {"width": w, "height": h, "orientation": "vertical" if a.vertical else "horizontal",
                   "inverted": False, "saturation": 0.5, "timezone": "Europe/Berlin"}
        else:
            cfg = settings_of(load_device(a.device))
        when = datetime.strptime(a.time, "%Y-%m-%d %H:%M") if a.time else local_now(cfg["timezone"])
        img = build(*logical_size(cfg), when)
        eink.snap(img, 0.5).save(a.png)     # in Leserichtung, reine Farben
        print(f"gespeichert: {a.png} {img.size}")
        return 0

    if a.probe:
        cfg = settings_of(load_device(a.device))
        print(f"device.json: {cfg['width']}x{cfg['height']}, {cfg['orientation']}, "
              f"inverted={cfg['inverted']}, Sättigung {cfg['saturation']}, {cfg['display_type']}")
        print(f"Schrift: {find_font() or 'Standardschrift von Pillow (Jost nicht gefunden)'}")
        try:
            import inky.auto  # noqa: F401
            print("Display-Treiber (inky): vorhanden")
        except ImportError as e:
            print(f"Display-Treiber (inky) fehlt: {e}")
            return 1
        out = "/tmp/ausschaltbild-probe.png"
        build(*logical_size(cfg), local_now(cfg["timezone"])).save(out)
        print(f"Vorschau: {out}")
        return 0

    try:
        cfg = settings_of(load_device(a.device))
        if cfg["display_type"] != "inky":
            log(f"display_type = {cfg['display_type']!r}, nichts zu tun (nur Inky-Displays)")
            return 0
        if a.beim_ausschalten:
            kind = current_shutdown()
            if kind != "poweroff":
                log(f"kein Ausschalten ({kind or 'Dienst nur gestoppt'}) – Display bleibt, wie es ist")
                return 0
        elif inkypi_active():
            print("InkyPi läuft noch und belegt das Display. Erst: sudo systemctl stop inkypi.service")
            return 1
        draw_now(cfg, local_now(cfg["timezone"]))
        if forget_image_hash(a.device):
            log("Prüfsumme in device.json zurückgesetzt – InkyPi zeichnet nach dem Start neu")
    except Exception as e:  # nie das Herunterfahren aufhalten
        log(f"Fehler: {type(e).__name__}: {e}")
        return 0 if a.beim_ausschalten else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
