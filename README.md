<p align="center">
  <img src="custom_components/spiel_saison_aufnehmen/brand/logo.png" alt="Spiel Saison aufnehmen" width="520">
</p>

# Spiel Saison aufnehmen

> **Umbenannt in 0.5.0** (vorher *Spielpartner Aufnahme*, Domain `spielpartner_aufnahme`). Neue Domain `spiel_saison_aufnehmen`: alte Integration entfernen, neue hinzufügen; Zähler und Discord-Threads der alten Integration werden beim ersten Start automatisch übernommen. Entity-IDs ändern sich (`…spiel_saison_aufnehmen_…`), Dashboards/Automationen anpassen.
>
> **Neu in 0.6.0:** Cams, Aufnahme-Profile und das Recorder-Add-on gehören der Schwester-Integration
> **[Cam Recorder Profile](https://github.com/RedDragonNode/ha-cam-recorder-profile)**. Diese Integration braucht sie
> (Abhängigkeit) und kümmert sich nur noch um Spielpartner, Zähler, Dateinamen und Discord. Umzug siehe [docs/migration.md](docs/migration.md).

Private Home-Assistant-Integration für **Spielen Spezial**: Spielpartner anlegen und pflegen, Aufnahmen
vorbereiten, Zähler führen, die Cams über *Cam Recorder Profile* aufnehmen und Discord-Threads bedienen.

> Privates Repo, MIT-Lizenz.

## Bausteine

| Baustein | Aufgabe |
|---|---|
| Integration `spiel_saison_aufnehmen` (dieses Repo) | Spielpartner, Zähler, Dateinamen, Discord, Start/Stopp der Spielpartner-Aufnahme |
| Integration `cam_recorder_profile` | Cams, Aufnahme-Profile (Zeitplan, Sonne, Bewegung), Adresse des Add-ons |
| Add-on **Cam Recorder** (im Repo von `cam_recorder_profile`) | schreibt die Streams per ffmpeg auf die Platte, überwacht und startet bei Abbruch neu |

## Installation

1. **Zuerst** *Cam Recorder Profile* und das Add-on einrichten (siehe dortiges README).
2. **Diese Integration:** Ordner `spiel_saison_aufnehmen` aus dem Archiv nach `config/custom_components/` kopieren,
   Home Assistant neu starten, dann *Einstellungen → Geräte & Dienste → Integration hinzufügen → „Spiel Saison aufnehmen“*.
3. **Speicher:** siehe [docs/recorder.md](docs/recorder.md).

## Einrichtung

1. **Grundeinstellungen:** Ordner-Präfix, Dateiname-Endung, Wartezeit für den Statusbeitrag, optional Discord-Bot-Token,
   Schaukel-Cover und ein **Auslöser** (Schalter/Sensor: an = Recorder starten, aus = stoppen).
   Recorder-Adresse und -Schlüssel leer lassen = wie in *Cam Recorder Profile*.
2. **Cams** legst du in *Cam Recorder Profile* an (Name, Kürzel, Stream-Quelle oder RTSP-Adresse). Alle diese Cams nehmen
   bei der Spielpartner-Aufnahme mit auf (es sei denn dort „aufnehmen“ abgewählt ist).
3. **Discord-Zusatz je Cam (optional):** *Discord-Cam hinzufügen* – Schnappschuss-Kamera und „In Discord posten“.
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
Pro Cam: **Dateiformat** (am Cam-Gerät von *Cam Recorder Profile*; dort auch der Aufnahme-Status).
Global: **Aktueller Spielpartner**, **Status**, **Recorder erreichbar**, **Recorder nimmt auf**,
**Recorder: freier Speicher**, Buttons **Recorder starten/stoppen**.

## Services

| Service | Zweck |
|---|---|
| `spiel_saison_aufnehmen.aufnahme_vorbereiten` | wie der Button; liefert Ordner, Saison, Hinweise |
| `spiel_saison_aufnehmen.recorder_starten` | startet die Aufnahme aller Cams |
| `spiel_saison_aufnehmen.recorder_stoppen` | beendet sauber und zählt die Aufnahme |
| `spiel_saison_aufnehmen.zaehler_setzen` | Saison / Aufnahmen in Saison / Gesamt auf feste Werte |
| `spiel_saison_aufnehmen.aufnahme_zaehlen` | Aufnahme manuell mitzählen |
| `spiel_saison_aufnehmen.aufnahme_posten` | Statusbeitrag sofort posten |

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

- [Recorder: Speicher, Zusammenspiel mit Cam Recorder Profile](docs/recorder.md)
- [Migration (0.6.0, 0.3.0, altes System)](docs/migration.md)
- [Dashboard-Beispiel](docs/dashboard.md)

## Bekannte Eigenheiten

- Die Zähler zeigen die Nummer, die die **nächste** Aufnahme bekommt; nach dem Stoppen werden sie erhöht.
- Das Kürzel `sc` (Schnauzencam) ist klein geschrieben, wie angegeben.
- Ist der Recorder beim Vorbereiten nicht erreichbar, wird kein Ordner angelegt und der Saisonwechsel nicht geprüft –
  die Benachrichtigung sagt es.
