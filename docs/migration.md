# Migration vom alten System

Das alte System bleibt **unverändert aktiv**, bis du bewusst umschaltest. Beide parallel laufen zu lassen,
verfälscht keine Daten – nur Aufnahmen werden doppelt gezählt, wenn beide Systeme laufen. Also: erst ein
Spielpartner testen, dann das alte System abschalten.

## 1. Integration einrichten und Spielpartner übernehmen

Pro Spielpartner: *Spielpartner hinzufügen*, Kennung eintragen (der Suffix der alten Helfer, z. B. `frank_visselff`),
Haken bei **Alte Helfer übernehmen**. Gelesen werden:

| Alter Helfer | wird zu |
|---|---|
| `counter.saison_mit_<kennung>` | Zähler Saison |
| `counter.aufnahmen_in_aktueller_saison_mit_<kennung>` | Zähler Aufnahmen in Saison |
| `counter.gesamt_aufnahmen_mit_<kennung>` | Zähler Aufnahmen gesamt |
| `input_text.video_ordner_<kennung>` (oder `_master`) | Anzeigename und Ordner-Nummer |
| `input_text.discord_kanal_id_log_<kennung>` | Forum-Kanal-ID |
| `input_text.discord_thread_saison_<kennung>` (`id\|saison`) | vorhandener Saison-Thread |

Ist ein Helfer nicht vorhanden, gelten Vorgaben (Zähler 1) oder die Felder im Formular. Prüfe danach die drei
Zahlenfelder am Spielpartner-Gerät und korrigiere sie bei Bedarf direkt.

## 2. Discord

Den Bot-Token (derselbe wie beim bisherigen `notify`/`rest_command`) in den Einstellungen eintragen.

## 3. Testlauf

Button *Aufnahme vorbereiten* drücken, Benachrichtigung lesen, in OBS Pfad und Dateinamen eines Source-Record-Filters prüfen.

## 4. Altes System abschalten

Erst wenn der Testlauf stimmt:

- Skript `script.aufnahme_vorbereitung` und `script.obs_source_record_format` entfernen
- Automationen *Aufnahme beendet – Zähler hochzählen* und *Aufnahme läuft 5 Min – …* entfernen
  (**beide** – sonst wird doppelt gezählt/gepostet)
- Helfer pro Spielpartner (Zähler, Thread, Kanal-ID, Dateiformat, Speicher-Adresse, Ordner) löschen
- Dashboard-Knöpfe auf den neuen Button/Service umstellen (siehe [Dashboard](dashboard.md))

Nicht zur Integration gehören und bleiben deshalb bestehen: Lichtsteuerung (*Saison ist zuende*,
*Saison aufnahmen => Licht Steuerung*) und alles von ha-obs-stream-monitor.
