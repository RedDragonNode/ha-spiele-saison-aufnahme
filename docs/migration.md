# Migration

## Von 0.5.x auf 0.6.0 (Cams und Profile ziehen um)

- **Voraussetzung:** die Integration *Cam Recorder Profile* ist eingerichtet. Ohne sie wartet „Spiel Saison aufnehmen“
  (Status „Wird erneut versucht“) und ändert nichts.
- Beim ersten Start kopiert 0.6.0 alle Cams und Profile mit **gleicher ID** nach *Cam Recorder Profile*
  (was dort schon liegt, bleibt unangetastet) und löscht sie hier. Bleiben: Spielpartner und pro Cam nur der
  Discord-Zusatz (Schnappschuss-Kamera / „In Discord posten“), und zwar nur dort, wo er gebraucht wurde.
- Recorder-Adresse und -Schlüssel wandern in *Cam Recorder Profile* (nur wenn dort noch keiner steht); hier bleiben sie
  nur, wenn sie bewusst abweichen. Die alte Add-on-Adresse `local-spielpartner-recorder` wird verworfen.
- Die alten Entities der Cams/Profile hier (Aufnahme-Status, Dateiformat je Cam) werden entfernt; das Dateiformat je Cam
  gibt es neu am Cam-Gerät. Die Services `profil_starten`/`profil_stoppen` heißen jetzt gleich unter `cam_recorder_profile`.
- Das Add-on liegt nicht mehr in diesem Repo, sondern bei *Cam Recorder Profile*.

## Von 0.2.x auf 0.3.0 (OBS entfernt)

- Die Integration spricht nicht mehr mit OBS: Source-Record-Filter, Pfade und Dateinamen in OBS werden nicht mehr gesetzt,
  der Service `dateiformat_anwenden` und das PC-Ordner-Werkzeug entfallen, es gibt keinen Modus mehr.
- Bestehende Spielpartner, Cams und Zähler bleiben erhalten. Alte OBS-Einstellungen (Basis-Pfade, Werkzeug-Entities)
  werden beim nächsten Speichern der Einstellungen entfernt.
- Die Source-Record-Filter in OBS kannst du ausschalten oder löschen; OBS macht nur noch die Live-Szene.
- Die frühere OBS-Aufnahme-Entity ist jetzt ein optionaler **Auslöser** – ohne Eintrag startest du den Recorder per Button/Service.
- Neu zu setzen: Recorder-Adresse und -Schlüssel (siehe [recorder.md](recorder.md)) und pro Cam die Stream-Quelle.

## Vom alten Helfer-/Skript-System

Alte Automationen, Skripte und Helfer sind in Home Assistant bereits entfernt. Spielpartner mit den früheren Zählerständen
als Startwerte anlegen, bei jeder Discord-Cam „In Discord posten“ anhaken und eine Kamera für den Schnappschuss hinterlegen.
