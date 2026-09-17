# artwall

[Español](README.md) · [English](README.en.md) · [Deutsch](README.de.md)

`artwall` wechselt das KDE-Hintergrundbild mit Kunstwerken aus Museen und zeigt in der unteren linken Ecke eine dezente Beschriftung mit Titel, Künstler, Datum und Museum an.

## Aktueller Status

- Zielumgebung: KDE Plasma unter Linux
- Befehl zum Ändern des Hintergrundbilds: `plasma-apply-wallpaperimage`
- Zeitplanung: `systemd --user`

Die Projektstruktur ist für weitere Quellen vorbereitet.

## Abhängigkeiten

```bash
sudo apt install -y \
  python3 python3-requests python3-pil plasma-workspace \
  python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

## Infobereich-Modus

```bash
./run.sh tray
```

Auch `./run.sh` ohne Argumente startet den Infobereich-Modus.

Über das Symbol im Infobereich kannst du:

- das Wechselintervall ändern
- `The Met` auswählen
- `Cleveland Museum of Art` auswählen
- `Art Institute of Chicago` auswählen
- `Harvard Art Museums` auswählen
- `National Gallery London` auswählen
- `Rijksmuseum` auswählen
- `Zufällig zwischen Museen` auswählen
- pausieren oder einen sofortigen Wechsel erzwingen

Verfügbare Intervalle:

- `2` Minuten
- `5` Minuten
- `10` Minuten

## Manuelle Verwendung in der Befehlszeile

```bash
./run.sh init --minutes 2 --source random
./run.sh once
```

## Timer installieren

```bash
./install_systemd.sh 2
```

Dadurch werden diese Dateien erstellt und aktiviert:

- `~/.config/systemd/user/artwall.service`
- `~/.config/systemd/user/artwall.timer`

## Autostart mit Infobereich

```bash
./install_autostart.sh
```

Dadurch werden diese Dateien erstellt:

- `~/.config/autostart/artwall.desktop`
- `~/.local/share/applications/artwall.desktop`

Der erste Eintrag startet artwall im Infobereich-Modus beim Start der KDE-Sitzung; der zweite macht die Anwendung im KDE-Anwendungsmenü verfügbar.

## Fehlerbehebung beim Autostart

Der Infobereich-Eintrag wird von KDE über `~/.config/autostart/artwall.desktop` gestartet. Falls er beim Start beendet wird, prüfe die erzeugte Benutzer-Sitzungseinheit und das Anwendungsprotokoll:

```bash
systemctl --user status app-artwall@autostart.service --no-pager
tail -80 ~/.local/share/artwall/artwall.log
```

Unter Debian oder Ubuntu benötigt der Start im Infobereich zusätzlich zu den Python-Abhängigkeiten das Systempaket `gir1.2-ayatanaappindicator3-0.1`.

## Pfade

- Konfiguration: `~/.config/artwall/config.json`
- Bildcache: `~/.local/share/artwall/cache`
- Gerenderte Hintergrundbilder: `~/.local/share/artwall/rendered`
- Maximal aufbewahrte gerenderte Hintergrundbilder: `10`
- Aktueller Status: `~/.local/share/artwall/current.json`
- Verlauf zuletzt verwendeter Kunstwerke: `~/.local/share/artwall/recent-artworks.json`
- Protokoll: `~/.local/share/artwall/artwall.log`

## Konfiguration

Die Konfigurationsdatei wird unter `~/.config/artwall/config.json` gespeichert.

Derzeit unterstützte Schlüssel:

- `interval_minutes`
- `source`
- `keep_rendered`
- `paused`
- `avoid_repeat_days`
- `history_retention_days`
- `cache_max_mb`
- `harvard_api_key`
- `language`

Standardwerte für eine neue Konfiguration:

```json
{
  "interval_minutes": 2,
  "source": "random",
  "keep_rendered": 10,
  "paused": false,
  "avoid_repeat_days": 7,
  "history_retention_days": 60,
  "cache_max_mb": 500,
  "harvard_api_key": "",
  "language": "es"
}
```

`avoid_repeat_days` legt fest, wie lange artwall versucht, dasselbe Kunstwerk desselben Museums nicht zu wiederholen.

`history_retention_days` legt fest, wie lange Einträge bereits gezeigter Kunstwerke vor der automatischen Bereinigung erhalten bleiben.

`cache_max_mb` legt die maximale Größe des Bildcaches fest. Überschreitet der Cache dieses Limit, löscht artwall die ältesten Bilder, bis er wieder darunter liegt.

`harvard_api_key` aktiviert die optionale Quelle Harvard Art Museums. Statt den Schlüssel in der Konfigurationsdatei zu speichern, kannst du auch `ARTWALL_HARVARD_API_KEY` in der Umgebung setzen. Harvard-Kandidaten werden vor der Auswahl auf Herunterladbarkeit geprüft; netzwerkspezifische `403`-Antworten werden daher übersprungen.

`recent-artworks.json` speichert den Verlauf gezeigter Kunstwerke je Museum im Format `object_id -> ISO-8601-UTC-Zeitstempel`.

## Hinweise

- Falls dein Hauptbildschirm nicht korrekt erkannt wird, kannst du ihn manuell testen:

```bash
./run.sh once --width 1920 --height 1080
```

- Bei angeschlossenen externen Monitoren rendert artwall für den aktivierten externen Bildschirm mit der höchsten Auflösung. Dadurch verhindert es, dass KDE die untere Beschriftung abschneidet, wenn ein 16:10-Hintergrund auf einem 16:9-Bildschirm angewendet wird.

- Unterstützte Quellen:
  - `met`: The Metropolitan Museum of Art
  - `cma`: Cleveland Museum of Art
  - `aic`: Art Institute of Chicago
  - `harvard`: Harvard Art Museums
  - `ngl`: National Gallery London
  - `rijks`: Rijksmuseum
  - `random`: wählt zufällig zwischen den unterstützten Museen
- Die Standardoption für eine neue Konfiguration ist `random`.
- Bestehende Konfigurationen werden beim Hinzufügen neuer Schlüssel automatisch migriert.
- Auf diesem Rechner ist `avoid_repeat_days` derzeit auf `30` gesetzt.
- Auf diesem Rechner ist `cache_max_mb` derzeit auf `500` gesetzt.
- Diese Version verwendet nur gemeinfreie Kunstwerke mit verfügbarem Bild.
- Die Beschriftung verwendet an die Bildschirmbreite angepasste Schriftgrößen; die Museumszeile ist etwas kleiner als die Künstler- und Datumszeile.

## Sprache

artwall unterstützt Spanisch, Englisch und Deutsch. Das Infobereich-Menü enthält **Sprache → Español / English / Deutsch**; die gewählte Sprache wird in `~/.config/artwall/config.json` gespeichert und bei künftigen Starts wiederverwendet. Beim ersten Start ohne vorhandene Konfiguration folgt artwall `LC_MESSAGES`, `LC_ALL` oder `LANG`, wenn sie mit `en` oder `de` beginnen; andernfalls wird Spanisch verwendet.
