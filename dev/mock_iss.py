"""Simulierte ISS-Überflüge (render.py --iss abend|morgen|keine; mit --iss echt wird stattdessen gerechnet).

Die Bahn auf der Himmelsscheibe wird hier nur grob angenähert (Azimut gleichmäßig, Höhe als
Sinusbogen); die echte Rechnung liefert später sgp4 in Schritten von einigen Sekunden.
"""
import math
from datetime import datetime, timedelta


def _pass(start, rise_az, peak_az, set_az, peak_el, minutes, mag, shadow_after=None):
    peak = start + timedelta(minutes=minutes / 2)
    end = start + timedelta(minutes=minutes)
    # Azimut ohne Sprung über 0°/360°
    a0, a1, a2 = rise_az, peak_az, set_az
    if a1 - a0 > 180:
        a1 -= 360
    if a1 - a0 < -180:
        a1 += 360
    if a2 - a1 > 180:
        a2 -= 360
    if a2 - a1 < -180:
        a2 += 360
    stop = shadow_after / minutes if shadow_after else 1.0
    path = []
    for i in range(31):
        t = i / 30 * stop
        az = a0 + (a1 - a0) * (t / 0.5) if t <= 0.5 else a1 + (a2 - a1) * ((t - 0.5) / 0.5)
        el = 10 + (peak_el - 10) * math.sin(math.pi * t)
        path.append((az % 360, el))
    shadow = start + timedelta(minutes=shadow_after) if shadow_after else None
    return {"start": start, "peak": peak, "end": end, "start_az": rise_az, "peak_az": peak_az, "end_az": set_az,
            "peak_el": peak_el, "mag": mag, "shadow": shadow, "shadow_az": path[-1][0], "path": path}


def install(now, scenario):
    import importlib
    iss = importlib.import_module("plugins.tagesdashboard.iss")
    d = now.date()
    tz = now.tzinfo
    if scenario == "abend":
        # Abends: aus Westsüdwest, hoch im Süden, verschwindet im Osten im Erdschatten
        p = _pass(datetime(d.year, d.month, d.day, 18, 42, tzinfo=tz), 248, 178, 78, 63, 6.2, -3.4, shadow_after=4.6)
    elif scenario == "morgen":
        # Morgens (Nachtbild): aus Südwest, halbhoch im Südosten, nach Nordost
        n = d + timedelta(days=1 if now.hour >= 12 else 0)
        p = _pass(datetime(n.year, n.month, n.day, 5, 51, tzinfo=tz), 228, 150, 60, 48, 5.6, -2.6)
    else:
        p = None
    iss.passes = lambda now_, lat, lon: [p] if p else []
