"""Simulierte apt-Lage für dev/render.py --apt (Abschnitt „Updates“ im Hilfsbild, hilfsdaten.apt_lage).

Ersetzt `hilfsdaten.apt_lage` (sonst fragte der Entwicklungsrechner sein eigenes apt, Kernel und Paketlisten).
Die Ausgabe von apt wird durch dieselbe Auswertung geschickt wie auf dem Pi.

Szenarien:
  keine    nichts bekannt (kein apt, wie auf einem Rechner ohne Debian) – Standard, ändert kein Bild
  aktuell  0 Updates
  updates  12 Updates, keine Sicherheit
  sicher   12 Updates, davon 3 Sicherheit, Neustart wegen neuem Kernel (Problemfall)
  alt      4 Updates, Paketlisten 12 Tage alt
"""

_APT = {
    "aktuell": "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n",
    "updates": "".join(f"Inst pkg{i} [1.0] (1.1 Debian:12.7/stable [arm64])\n" for i in range(12))
    + "12 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n",
    "sicher": "".join(f"Inst pkg{i} [1.0] (1.1 {'Debian-Security:12/stable-security' if i < 3 else 'Debian:12.7/stable'}"
                       " [arm64])\n" for i in range(12))
    + "12 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n",
    "alt": "".join(f"Inst pkg{i} [1.0] (1.1 Debian:12.7/stable [arm64])\n" for i in range(4))
    + "4 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n",
}


def install(kind, hilfsdaten, now):
    def lage(_now, run=None, read=None):
        erg = hilfsdaten.apt_auswerten(_APT.get(kind))
        return {"n": erg[0] if erg else None, "sicher": erg[1] if erg else 0,
                "neustart": "kernel" if kind == "sicher" else None, "alter": 12.4 if kind == "alt" else 0.5 if erg else None}
    hilfsdaten.apt_lage = lage
