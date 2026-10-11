# Recorder: Aufnahme direkt vom Kamera-Stream

Die Aufnahme läuft über das Add-on **Cam Recorder**. Der HA-Server schreibt den RTSP-Stream jeder Kamera **ohne Neukodierung**
(ffmpeg `-c copy`) in eine Datei. Keine GPU, kaum CPU, OBS macht nur noch die Live-Szene.

```
Integration (Steuerung)  ──HTTP──▶  Add-on „Cam Recorder“  ──ffmpeg-copy──▶  Kamera (RTSP)
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
(`blkid`), danach `systemctl daemon-reload && mount -a`. Prüfen: `docker exec app_local_cam_recorder df -h /media/Aufnahmen`
muss die große Platte zeigen. Der Mount-Ordner hängt von der HA-Installation ab (`docker inspect <add-on> | grep -A6 '"Destination": "/media"'`).

`nofail` verhindert, dass der Server ohne Platte nicht mehr startet. Ohne eingehängte Platte würde das Add-on auf die
Systemplatte schreiben – `mindest_frei_gb` schützt davor (Start wird verweigert).
Richtwert: 5 Cams ≈ 6 GB pro Stunde (Messung mit Fuchsauge H.264 + 4× Reolink HEVC).

## 2. Add-on und Cams: Cam Recorder Profile

Seit 0.6.0 liegt alles Technische rund um die Kameras in der Schwester-Integration **Cam Recorder Profile**
([RedDragonNode/ha-cam-recorder-profile](https://github.com/RedDragonNode/ha-cam-recorder-profile)):

- das Add-on **Cam Recorder** (Ordner `addon/cam_recorder` dort),
- die **Cams** (Name, Kürzel, Stream-Quelle oder RTSP-Adresse, „aufnehmen“),
- die **Aufnahme-Profile** (Ordner, Cams, Auslöser, Zeitfenster/Sonne),
- Adresse und Schlüssel des Add-ons.

„Spiel Saison aufnehmen“ benutzt diese Cams und diese Adresse (leer lassen in den eigenen Einstellungen = wie dort)
und kümmert sich nur um Spielpartner, Zähler, Dateinamen und Discord. Die Spielpartner-Aufnahme läuft im Add-on als
Sitzung `default`; Profile laufen parallel in eigenen Sitzungen. Eine Cam nimmt nie in zwei Sitzungen gleichzeitig auf –
ist sie in einem Profil belegt, überspringt der Spielpartner-Start sie und sagt es.

## 3. Discord-Zusätze je Cam

In „Spiel Saison aufnehmen“ gibt es pro Cam optional einen **Discord-Zusatz** (Unterkachel *Discord-Cam hinzufügen*):
Schnappschuss-Kamera und „In Discord posten“. Cams ohne Zusatz nehmen normal auf, erscheinen aber nicht im Discord-Beitrag.

## Ablauf

1. **Aufnahme vorbereiten** – legt Ordner über den Recorder an, erkennt neue Saison, Discord-Thread wie gehabt.
2. **Recorder starten** (Button, Service `recorder_starten` oder Auslöser) – pro Cam eine Datei
   `#01.02.03.FB.14 (4K) 10.10.2026.mp4` (Datum bereits aufgelöst).
3. Nach *x* Minuten: Discord-Statusbeitrag wie bisher.
4. **Recorder stoppen** – Dateien werden sauber abgeschlossen, die Aufnahme wird **einmal** gezählt.

Bricht eine Kamera ab, verbindet der Recorder neu und schreibt in `… Teil 2.mp4`. Beendet das Add-on die Aufnahme
selbst (Platte fast voll, Add-on-Neustart), meldet die Integration das mit Grund und zählt trotzdem einmal.
Nach einem HA-Neustart verbindet sich die Integration wieder mit der laufenden Aufnahme.

## Dateien & Synchronisation

Neben den Videos liegt `#01.02.03 Sitzung.json` (Start/Ende je Cam und Teil in UTC). Für den Schnitt lassen sich die
Kameras damit zeitgenau ausrichten. Ein-/Ausschaltverzögerungen von wenigen Sekunden zwischen den Cams sind normal
(RTSP-Verbindungsaufbau).

## Entities

Global: *Recorder erreichbar*, *Recorder nimmt auf*, *freier Speicher*, Buttons *Recorder starten/stoppen*.
Pro Cam: *Dateiformat* (hängt am Cam-Gerät von Cam Recorder Profile). Der Aufnahme-Status je Cam steht in Cam Recorder Profile.
