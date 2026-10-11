# Spielpartner Recorder

Schreibt die RTSP-Streams der Kameras **ohne Neukodierung** (ffmpeg `-c copy`) in Dateien. Gesteuert wird das Add-on
von der Integration *Spielpartner Aufnahme* (Modus „Recorder" oder „Beide"). Das Add-on selbst hat keine Oberflaeche.

## Einrichtung
1. Ordner `addon/spielpartner_recorder` aus dem Repository nach `/addons/spielpartner_recorder` auf dem HA-Server kopieren
   (Samba-Freigabe `addons`).
2. *Einstellungen → Add-ons → Add-on-Store → ⋮ → Nach Updates suchen* → „Spielpartner Recorder" installieren.
3. Unter *Konfiguration* einen **api_key** setzen (mindestens 12 Zeichen, frei waehlbar) und starten.
4. In der Integration unter *Einstellungen → Recorder* Adresse `http://local-spielpartner-recorder:8099` und denselben
   Schluessel eintragen.

## Einstellungen
| Option | Bedeutung |
| --- | --- |
| `api_key` | Zugangsschluessel zwischen Integration und Add-on |
| `aufnahme_ordner` | Stammordner (voller Pfad, z. B. `/media/Aufnahmen` auf der externen Platte); darunter legen Profile/Spielpartner ihre Ordner an |
| `container` | `mp4` (fragmentiert, absturzsicher) oder `mkv` |
| `audio` | `aac` (G.711 der Kamera wird nach AAC umgewandelt, minimale Last), `copy`, `none` |
| `stillstand_sekunden` | Wenn so lange keine Daten geschrieben werden, wird die Kamera neu verbunden (neue Datei „… Teil 2") |
| `mindest_frei_gb` | Start wird verweigert / Aufnahme beendet, wenn weniger Platz frei ist |
| `wallclock_zeitstempel` | Nur aktivieren, wenn eine Kamera fehlerhafte Zeitstempel liefert |
| `ffmpeg_loglevel` | `warning` (Standard), bei Problemen `info` oder `verbose`: dann zeigt das Protokoll die genaue ffmpeg-Ausgabe |
| `video_tag` | `hvc1` setzt HEVC in MP4 so, dass Windows/Apple-Player es abspielen. Wirkt nur bei MP4; bei Cams mit H.264 wird der Tag automatisch weggelassen |

## Dateien
Pro Sitzung entsteht neben den Videos eine `<Sitzung>.json` mit Start/Ende jeder Kamera und jedes Teils (UTC) –
damit lassen sich die Kameras spaeter zeitgenau synchronisieren.

## Mehrere Profile gleichzeitig (ab 0.3.0)
`POST /start` nimmt optional `profile` an, `POST /stop` optional `profile` (ohne = alle). Jedes Profil hat eigenen Ordner,
eigene Sidecar-Datei und eigenen Speicherwaechter. Eine Kamera-ID kann nie in zwei Profilen gleichzeitig aufnehmen
(Start wird mit „Kamera nimmt bereits in einem anderen Profil auf" abgelehnt). `GET /status` enthaelt zusaetzlich `profile`.
