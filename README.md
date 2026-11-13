# InkyPi-Plugins: DWD Wetter, Nextcloud Kalender, Tagesdashboard

Drei Plugins für [InkyPi](https://github.com/fatihak/InkyPi):

| Ordner | Anzeigename | Inhalt |
|---|---|---|
| `dwd_wetter` | DWD Wetter | Wetter vom Deutschen Wetterdienst (Bright Sky), mit Warnungen, Stundenverlauf und Vorhersage |
| `nextcloud_kalender` | Nextcloud Kalender | Termine per CalDAV, als Terminliste oder Wochenansicht |
| `tagesdashboard` | Wetter & Kalender | beides auf einem Bild, mit Kleidungsempfehlung; eigenständig installierbar |

Installation eines Plugins:

```bash
inkypi plugin install tagesdashboard https://github.com/<dein-name>/inkypi-plugins
```

## Schärfer auf dem Inky Impression

Das Inky Impression 7,3″ kann nur sechs Farben darstellen. Alles andere setzt der Treiber aus farbigen Pünktchen zusammen, dabei fransen Schrift und Linien aus. Zwei Maßnahmen machen das Bild deutlich schärfer:

**1. Farben einrasten (im Plugin, standardmäßig an).** Das Plugin legt jedes Pixel selbst auf eine der sechs Displayfarben fest, bevor das Bild zum Treiber geht. Kanten bleiben dadurch glatt, kräftige Farben werden einfarbig. Nur Graustufen und helle Töne (zum Beispiel die Nachtstunden im Graphen) erscheinen als feines, gleichmäßiges Punktmuster. Abschalten lässt es sich in den Plugin-Einstellungen: „Schärfer auf Inky-Displays“.

Damit das wirkt, in InkyPi unter den Bildeinstellungen (Image Settings) Sättigung, Kontrast, Schärfe und Helligkeit auf **1,0** lassen. Die Inky-Sättigung (`inky_saturation`) bei **0,5 oder weniger** einstellen. Andere Werte verfälschen die Farben wieder; das Plugin schreibt dann eine Warnung ins Log.

**2. Schrift am Pixelraster ausrichten (einmalig auf dem Pi).** Diese Einstellung schaltet den Autohinter von FreeType ein. Er richtet alle Striche einer Schriftgröße auf dieselbe Pixelbreite aus. Die grauen Kantenpixel der geglätteten Schrift macht danach das Einrasten (Punkt 1) hart schwarz oder weiß. So entstehen gleichmäßige Buchstaben ohne graue Ränder:

```bash
sudo tee /etc/fonts/local.conf > /dev/null <<'XML'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="antialias" mode="assign"><bool>true</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="autohint" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintfull</const></edit>
    <edit name="rgba" mode="assign"><const>none</const></edit>
    <edit name="lcdfilter" mode="assign"><const>lcdnone</const></edit>
  </match>
</fontconfig>
XML
fc-cache -f
sudo systemctl restart inkypi.service
```

Der Befehl überschreibt eine vorhandene `/etc/fonts/local.conf`. Er gilt für alle Programme auf dem Pi, die fontconfig nutzen, also auch für andere InkyPi-Plugins. Rückgängig machen: `sudo rm /etc/fonts/local.conf` und InkyPi neu starten.

Bitte nicht Schrift ganz ohne Kantenglättung (`antialias=false`) verwenden. Dann rundet FreeType jeden Buchstaben einzeln auf ganze Pixel, und die Striche werden ungleich dick: „n“ und „m“ wirken dünn, „H“ und Ziffern fett.

**Vorschau:** Die Vorschau in der InkyPi-Weboberfläche zeigt das eingerastete Bild. So sieht es auf dem Display aus, nur leuchtender.

Entwicklung und Tests: siehe `CLAUDE.md` und den Ordner `dev/`.

Lizenz: GPL-3.0 (wie InkyPi).
