# Dashboard-Beispiele

Entity-IDs entstehen aus Anzeigename und Sprache; in der Oberfläche anklicken und kopieren, falls sie abweichen.

## Spielpartner-Karte

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: sensor.spiel_saison_aufnehmen_aktueller_spielpartner
    name: Aktueller Spielpartner
    icon: mdi:account-voice
  - type: entities
    title: Frank
    entities:
      - entity: number.spielpartner_frank_saison
      - entity: number.spielpartner_frank_aufnahmen_in_saison
      - entity: number.spielpartner_frank_aufnahmen_gesamt
      - entity: sensor.spielpartner_frank_speicher_adresse
      - entity: sensor.spielpartner_frank_dateiformat
  - type: button
    entity: button.spielpartner_frank_aufnahme_vorbereiten
    name: Aufnahme vorbereiten
```

## Knopf über den Service

```yaml
type: button
name: Aufnahme vorbereiten (Frank)
icon: mdi:video-plus
tap_action:
  action: perform-action
  perform_action: spiel_saison_aufnehmen.aufnahme_vorbereiten
  data:
    spielpartner: frank_visselff
```

## Status der Cams

```yaml
type: entities
title: Dateinamen der Cams
entities:
  - sensor.cam_fuchsblick_dateiformat
  - sensor.cam_hoelenblick_dateiformat
  - sensor.cam_kesselcam_dateiformat
```

## Recorder

```yaml
type: entities
title: Recorder
entities:
  - binary_sensor.spiel_saison_aufnehmen_recorder_erreichbar
  - binary_sensor.spiel_saison_aufnehmen_recorder_nimmt_auf
  - sensor.spiel_saison_aufnehmen_recorder_freier_speicher
  - button.spiel_saison_aufnehmen_recorder_starten
  - button.spiel_saison_aufnehmen_recorder_stoppen
```
