"""Bildet den Pimoroni-Treiber für Spectra 6 (inky_e673.set_image) nach.

So lässt sich ohne Display prüfen, was am Ende wirklich angezeigt wird:

  idx = emulate_driver(image, saturation=0.5)   # Farbindex je Pixel, wie ihn das Display bekommt
  show(idx).save("display.png")                 # sichtbar machen (reine Farben)

Der Treiber quantisiert mit Floyd-Steinberg-Dithering auf eine Mischpalette aus
DESATURATED_PALETTE und SATURATED_PALETTE (Gewicht = "Inky Driver Saturation").
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import eink  # noqa: E402


def driver_palette(saturation):
    return (eink.SATURATED * saturation + eink.PURE * (1 - saturation)).astype(np.uint8)


def emulate_driver(image, saturation=0.5):
    pal = Image.new("P", (1, 1))
    pal.putpalette(driver_palette(saturation).flatten().tobytes())
    out = image.convert("RGB").quantize(6, palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
    return np.asarray(out)


def show(idx):
    return Image.fromarray(eink.PURE[idx].astype(np.uint8), "RGB")


def changed_by_driver(image, saturation=0.5):
    """Wie viele Pixel verändert der Treiber noch? 0 = Bild kommt pixelgenau an."""
    idx = emulate_driver(image, saturation)
    pal = eink.palette_for(saturation)
    want = np.full(idx.shape, -1)
    rgb = np.asarray(image.convert("RGB"))
    for i, c in enumerate(pal):
        want[(rgb == c).all(-1)] = i
    return int((idx != want).sum())
