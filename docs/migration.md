# Migration

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
