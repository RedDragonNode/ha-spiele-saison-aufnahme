# Recorder: Aufnahme direkt vom Kamera-Stream

Seit 0.3.0 der einzige Aufnahmeweg (OBS ist aus der Integration entfernt). Der HA-Server schreibt den RTSP-Stream jeder Kamera **ohne Neukodierung**
(ffmpeg `-c copy`) in eine Datei. Keine GPU, kaum CPU, OBS macht nur noch die Live-Szene.

```
Integration (Steuerung)  ──HTTP──▶  Add-on „Spielpartner Recorder“  ──ffmpeg-copy──▶  Kamera (RTSP)
 Cams, Kürzel, Zähler,              pro Cam ein ffmpeg, Neustart,                      │
 Dateinamen, Discord                Stillstandserkennung, Sidecar                      ▼
                                                                         /media/Aufnahmen/…/Spielen mit …/Saison …/
```

## 1. Speicher (externe Platte)

Bewährte Aufteilung der 4-TB-Platte (SSH auf den Debian-Host, als root via `su -`; Formatieren löscht alles):

| Partition | Label | Einhängepunkt | Zweck |
|---|---|---|---|
| `sdb1` (~3,6 T) | `aufnahmen` | `/var/lib/homeassistant/media/Aufnahmen` | Videos |
| `sdb2` (~5 G) | `backups` | `/var/lib/homeassistant/media/Backups` | HA-Backups (nur die letzten 7 Tage) |

Ordner-Beispiel unter `Aufnahmen`: `Der_Fuchsbau/{Spielen_Spezial,bei_Nacht,bei_Tag,mit_Maschine}` und
`Ueberwachung/{Treppe,Flur,Klingel,Wohnzimmer,Buero}`. In fstab mit **UUID** und `defaults,nofail 0 2` eintragen
(`blkid`), danach `systemctl daemon-reload && mount -a`. Prüfen: `docker exec app_local_spielpartner_recorder df -h /media/Aufnahmen`
muss die große Platte zeigen. Der Mount-Ordner hängt von der HA-Installation ab (`docker inspect <add-on> | grep -A6 '"Destination": "/media"'`).

`nofail` verhindert, dass der Server ohne Platte nicht mehr startet. Ohne eingehängte Platte würde das Add-on auf die
Systemplatte schreiben – `mindest_frei_gb` schützt davor (Start wird verweigert).
Richtwert: 5 Cams ≈ 6 GB pro Stunde (Messung mit Fuchsauge H.264 + 4× Reolink HEVC).

## 2. Add-on

1. Ordner `addon/spielpartner_recorder` auf den Server nach `/addons/spielpartner_recorder` kopieren (Samba-Freigabe `addons`).
2. *Einstellungen → Add-ons → Add-on-Store → ⋮ → Nach Updates suchen* → **Spielpartner Recorder** installieren.
3. Unter *Konfiguration* einen `api_key` setzen (mind. 12 Zeichen), starten.

Optionen siehe `addon/spielpartner_recorder/DOCS.md`. Standard: fragmentiertes MP4 (absturzsicher, auch bei Stromausfall
nur die letzte Sekunde verloren), Audio G.711 → AAC, Neustart nach 20 s ohne Daten.

## 3. Integration

*Konfigurieren* der Integration:

| Einstellung | Wert |
|---|---|
| Recorder-Adresse | `http://local-spielpartner-recorder:8099` |
| Recorder-Schlüssel | derselbe `api_key` wie im Add-on |
| Auslöser (optional) | Schalter/Sensor; an = Recorder starten, aus = stoppen. Leer = nur Button/Service |
| Spielpartner-Ordner | Unterpfad im Add-on-Ordner für „Spielen mit …“, z. B. `Der_Fuchsbau/Spielen_Spezial` (Add-on `aufnahme_ordner` = `/media/Aufnahmen`) |

Pro **Cam** (Cam bearbeiten): *Recorder: diese Cam aufnehmen*, und **entweder** *Stream-Quelle über eine HA-Kamera*
(z. B. die Reolink-Kamera, HA liefert die RTSP-Adresse) **oder** *direkte RTSP-Adresse* (hat Vorrang).
Tipp: den **Hauptstream** (volle Auflösung) verwenden, nicht den Substream.

## Ablauf

1. **Aufnahme vorbereiten** – legt Ordner über den Recorder an, erkennt neue Saison, Discord-Thread wie gehabt.
2. **Recorder starten** (Button, Service `recorder_starten` oder Auslöser) – pro Cam eine Datei
   `#01.02.03.FB.14 (4K) 10.10.2026.mp4` (Datum bereits aufgelöst).
3. Nach *x* Minuten: Discord-Statusbeitrag wie bisher.
4. **Recorder stoppen** – Dateien werden sauber abgeschlossen, die Aufnahme wird **einmal** gezählt.

Bricht eine Kamera ab, verbindet der Recorder neu und schreibt in `… Teil 2.mp4`. Beendet das Add-on die Aufnahme
selbst (Platte fast voll, Add-on-Neustart), meldet die Integration das mit Grund und zählt trotzdem einmal.
Nach einem HA-Neustart verbindet sich die Integration wieder mit der laufenden Aufnahme.

## Aufnahme-Profile (ab Integration 0.4.0 / Add-on 0.3.0)

Ein Profil bestimmt, **wohin** welche Cams aufnehmen und **wann**. Anlegen: *Integration → Aufnahme-Profil hinzufügen*.

| Feld | Bedeutung |
|---|---|
| Name | z. B. `Treppe`, `bei Nacht` |
| Zielordner | relativ zum Add-on-Ordner, z. B. `Ueberwachung/Treppe` (wird angelegt) |
| Cams | beliebig viele; eine Cam darf in mehreren Profilen stehen |
| Dateiname | `{cam}`, `{kuerzel}`, `{profil}` und Datum/Zeit `%CCYY %MM %DD %hh %mm %ss`; Standard `{cam} %CCYY-%MM-%DD %hh-%mm-%ss` |
| Auslöser | Bewegungsmelder, Schalter, Sensor (mehrere möglich): irgendeiner „an" = aufnehmen |
| Nachlauf | Sekunden, die nach „aus" weiter aufgenommen wird |
| Höchstdauer | Minuten pro Aufnahme (0 = unbegrenzt); danach erst nach „aus → an" wieder |
| Von / bis, Sonne | Zeitfenster (auch über Mitternacht) und/oder nur Tag bzw. Nacht (`sun.sun`) |

Regeln:

- **Nur Zeitfenster/Sonne, kein Auslöser:** nimmt im Fenster durchgehend auf (z. B. „bei Nacht").
- **Auslöser (+ Fenster):** nimmt auf, solange ein Auslöser „an" ist und das Fenster offen ist.
- **Nichts angegeben:** nur von Hand (`profil_starten` / `profil_stoppen`, Name als Parameter).
- **Eine Cam nimmt nie in zwei Profilen gleichzeitig auf:** wer zuerst kommt, belegt sie; das andere Profil
  nimmt ohne diese Cam auf und meldet sie als „belegt". Das gilt auch gegenüber dem Spielpartner-Ablauf.
- Von Hand gestartete Profile laufen bis zum manuellen Stopp. Nach HA-Neustart werden laufende Profile wieder erkannt.
- Pro Profil gibt es einen Binärsensor *Aufnahme* (Ordner, seit, Cams) am Gerät „Profil …".

Beispiel Überwachung Treppe: Ordner `Ueberwachung/Treppe`, Cam Treppe, Auslöser Bewegungsmelder Treppe, Nachlauf 30 s, Höchstdauer 10 min.

## Dateien & Synchronisation

Neben den Videos liegt `#01.02.03 Sitzung.json` (bei Profilen `<Profil> <Datum Zeit>.json`) (Start/Ende je Cam und Teil in UTC). Fuer den Schnitt
lassen sich die Kameras damit zeitgenau ausrichten. Ein-/Ausschaltverzoegerungen von wenigen Sekunden zwischen den
Cams sind normal (RTSP-Verbindungsaufbau).

## Entities

Global: *Recorder erreichbar*, *Recorder nimmt auf*, *freier Speicher*, Buttons *Recorder starten/stoppen*.
Pro Cam: *Aufnahme* (Status, Datei, Teil, Neustarts, Größe, letzter Fehler).

## Sicherheit

Das Add-on ist nur im internen Home-Assistant-Netz erreichbar (kein veröffentlichter Port) und verlangt den
`api_key`. Zugangsdaten in RTSP-Adressen werden in Logs und Status maskiert. Pfade werden bereinigt;
Ordner außerhalb von `aufnahme_ordner` sind nicht erreichbar.
