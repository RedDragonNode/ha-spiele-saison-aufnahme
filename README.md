<p align="center">
  <img src="custom_components/spielpartner_aufnahme/brand/logo.png" alt="Spielpartner Aufnahme" width="520">
</p>

# Spielpartner Aufnahme

Private Home-Assistant-Integration für **Spielen Spezial**: Spielpartner anlegen und pflegen, Aufnahmen
vorbereiten, Zähler führen, Kameras **direkt vom RTSP-Stream aufnehmen** und Discord-Threads bedienen –
alles an einem Ort. Seit 0.3.0 ohne OBS: Die Aufnahme läuft über das Add-on **Spielpartner Recorder**
(ffmpeg Stream-Copy, keine Neukodierung, keine GPU-Last).

> Privates Repo, MIT-Lizenz.

## Bausteine

| Baustein | Aufgabe |
|---|---|
| Integration `spielpartner_aufnahme` | Spielpartner, Cams, Zähler, Dateinamen, Discord, Steuerung |
| Add-on `addon/spielpartner_recorder` | schreibt die Streams per ffmpeg auf die Platte, überwacht und startet bei Abbruch neu |

## Installation

1. **Integration:** Ordner `spielpartner_aufnahme` aus dem Archiv nach `config/custom_components/` kopieren,
   Home Assistant neu starten, dann *Einstellungen → Geräte & Dienste → Integration hinzufügen → „Spielpartner Aufnahme“*.
2. **Add-on und Speicher:** siehe [docs/recorder.md](docs/recorder.md).

## Einrichtung

1. **Grundeinstellungen:** Adresse und Schlüssel des Recorder-Add-ons, Ordner-Präfix, Dateiname-Endung,
   Wartezeit für den Statusbeitrag, optional Discord-Bot-Token, Schaukel-Cover und ein **Auslöser**
   (Schalter/Sensor: an = Recorder starten, aus = stoppen).
2. Die **16 Standard-Cams** (Bauleitung … Wildspur) werden mit ihrem Kürzel angelegt. Nicht vorhandene Cams
   über das Drei-Punkte-Menü löschen oder bei der Cam „Recorder: diese Cam aufnehmen“ abwählen.
3. **Cams bearbeiten:** Stream-Quelle (HA-Kamera **oder** RTSP-Adresse), Kürzel, „In Discord posten“,
   Kamera für Schnappschüsse.
4. **Spielpartner hinzufügen:** Kennung, Anzeigename, Ordner-Nummer (`#01`), Discord-Forum-Kanal-ID und Startwerte
   der Zähler (leer = 1).

## Ablauf einer Aufnahme

1. **Aufnahme vorbereiten** (Button am Spielpartner-Gerät oder Service):
   Ordner `Spielen mit <Name> #<Nr>` und `Saison <SS> vom <TT,MM,JJJJ>` werden über den Recorder angelegt.
   Existieren schon Saison-Ordner und der heutige fehlt → **neue Saison** (Saison +1, Aufnahmen in Saison auf 1).
   Fehlt der Discord-Thread der Saison, wird er angelegt. Eine Benachrichtigung fasst alles zusammen.
2. **Recorder starten** (Button, Service oder Auslöser): pro Cam eine Datei.
3. **Aufnahme läuft x Minuten:** Beitrag im Saison-Thread – Kopfzeile mit Schaukel-Position, danach jede angehakte
   Cam einzeln und zeitlich versetzt (Standard 20 s): Schnappschuss, direkt darunter die Video-ID.
4. **Recorder stoppen:** Dateien werden sauber abgeschlossen, „Aufnahmen in Saison“ und „Gesamt“ steigen um 1.

### Dateiname

```
#<Ordner-Nr>.<Saison>.<Aufnahme in Saison>.<Cam-Kürzel>.<Gesamt><Endung>
#01.02.03.FB.14 (4K) 10.10.2026.mp4
```

Alle Zahlen zweistellig, das Datum ist in der Endung bereits eingesetzt (`%DD.%MM.%CCYY` u. a. Platzhalter).
Abbrüche einer Kamera erzeugen `… Teil 2.mp4`. Pro Sitzung liegt eine `.json` mit den Startzeiten aller Cams daneben.

## Entities

Pro Spielpartner (eigenes Gerät): Zähler **Saison**, **Aufnahmen in Saison**, **Aufnahmen gesamt**
(editierbar), Sensoren **Speicher-Adresse**, **Dateiformat**, **Discord-Thread**, Button **Aufnahme vorbereiten**.
Pro Cam: **Dateiformat** und **Aufnahme** (Status, Datei, Teil, Neustarts, Größe, letzter Fehler).
Global: **Aktueller Spielpartner**, **Status**, **Recorder erreichbar**, **Recorder nimmt auf**,
**Recorder: freier Speicher**, Buttons **Recorder starten/stoppen**.

## Services

| Service | Zweck |
|---|---|
| `spielpartner_aufnahme.aufnahme_vorbereiten` | wie der Button; liefert Ordner, Saison, Hinweise |
| `spielpartner_aufnahme.recorder_starten` | startet die Aufnahme aller Cams |
| `spielpartner_aufnahme.recorder_stoppen` | beendet sauber und zählt die Aufnahme |
| `spielpartner_aufnahme.zaehler_setzen` | Saison / Aufnahmen in Saison / Gesamt auf feste Werte |
| `spielpartner_aufnahme.aufnahme_zaehlen` | Aufnahme manuell mitzählen |
| `spielpartner_aufnahme.aufnahme_posten` | Statusbeitrag sofort posten |

`spielpartner` ist die Kennung (z. B. `frank_visselff`) oder der Anzeigename; leer = aktueller Spielpartner.

## Discord einrichten

Bot im Developer Portal anlegen, auf den Server einladen, Token in den Einstellungen eintragen.
Der Bot braucht im Forum-Kanal: *Kanäle ansehen*, *Beiträge erstellen*, *Nachrichten in Beiträgen senden*,
*Dateien anhängen*, *Links einbetten*. Die Kanal-ID steht beim Spielpartner (Rechtsklick auf das Forum → ID kopieren).
Ohne Token bleibt Discord aus.

## Tests

```bash
pip install -r requirements_test.txt
pytest
```

## Weitere Doku

- [Recorder: Add-on, SSD, Betrieb](docs/recorder.md)
- [Migration vom alten System / von 0.2.x](docs/migration.md)
- [Dashboard-Beispiel](docs/dashboard.md)

## Bekannte Eigenheiten

- Die Zähler zeigen die Nummer, die die **nächste** Aufnahme bekommt; nach dem Stoppen werden sie erhöht.
- Das Kürzel `sc` (Schnauzencam) ist klein geschrieben, wie angegeben.
- Ist der Recorder beim Vorbereiten nicht erreichbar, wird kein Ordner angelegt und der Saisonwechsel nicht geprüft –
  die Benachrichtigung sagt es.
