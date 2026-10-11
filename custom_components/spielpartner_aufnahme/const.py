"""Konstanten der Integration Spielpartner Aufnahme."""
from __future__ import annotations

DOMAIN = "spielpartner_aufnahme"

SUBENTRY_PARTNER = "spielpartner"
SUBENTRY_CAM = "cam"
SUBENTRY_PROFILE = "profil"
LEGACY_PROFILE = "default"  # Profil-ID des Spielpartner-Ablaufs im Recorder

# --- Einstellungen (config_entry.options) -------------------------------------
CONF_DISCORD_TOKEN = "discord_token"
CONF_FOLDER_PREFIX = "ordner_praefix"
CONF_FORMAT_SUFFIX = "dateiformat_endung"
CONF_RECORDING_ENTITY = "aufnahme_entity"  # optionaler Ausloeser (Schalter/Sensor)
CONF_POST_DELAY = "post_nach_minuten"
CONF_POST_GAP = "post_abstand_sekunden"
CONF_SWING_ENTITY = "schaukel_entity"
CONF_RECORDER_URL = "recorder_url"
CONF_RECORDER_KEY = "recorder_schluessel"
CONF_SPIEL_BASE = "spielen_ordner"  # Unterpfad im Recorder-Stammordner fuer die Spielpartner-Ordner

DEFAULT_OPTIONS: dict[str, object] = {
    CONF_FOLDER_PREFIX: "Spielen mit",
    CONF_FORMAT_SUFFIX: " (4K) %DD.%MM.%CCYY",
    CONF_POST_DELAY: 5,
    CONF_POST_GAP: 20,
    CONF_RECORDER_URL: "http://local-spielpartner-recorder:8099",
}

# --- Spielpartner (Subentry) ---------------------------------------------------
CONF_KENNUNG = "kennung"
CONF_ANZEIGE = "anzeige"
CONF_ORDNER_NR = "ordner_nr"
CONF_FORUM_ID = "forum_id"
CONF_INIT_SAISON = "start_saison"
CONF_INIT_AUFNAHMEN = "start_aufnahmen_in_saison"
CONF_INIT_GESAMT = "start_gesamt"
CONF_INITIAL = "initial"  # intern: Startwerte, werden einmalig in den Speicher uebernommen

# --- Cam (Subentry) ------------------------------------------------------------
CONF_CAM_NAME = "name"
CONF_CAM_KUERZEL = "kuerzel"
CONF_CAM_FILTER = "filter_entity"  # alt, wird nicht mehr genutzt
CONF_CAM_POST = "discord_posten"
CONF_CAM_CAMERA = "kamera_entity"  # Schnappschuss fuer Discord
CONF_CAM_RECORD = "aufnehmen"  # Recorder: diese Cam aufnehmen
CONF_CAM_STREAM = "stream_entity"  # Recorder: Stream-Quelle ueber eine HA-Kamera
CONF_CAM_RTSP = "rtsp_url"  # Recorder: oder direkte RTSP-Adresse (hat Vorrang)

# --- Aufnahme-Profil (Subentry) -------------------------------------------------
CONF_PROF_NAME = "name"
CONF_PROF_FOLDER = "ordner"
CONF_PROF_CAMS = "cams"  # Liste von Cam-Subentry-IDs
CONF_PROF_PATTERN = "dateimuster"
CONF_PROF_TRIGGERS = "ausloeser"  # Liste von Entities (an = aufnehmen)
CONF_PROF_AFTER = "nachlauf_sekunden"
CONF_PROF_MAX = "max_dauer_minuten"
CONF_PROF_FROM = "zeit_von"
CONF_PROF_TO = "zeit_bis"
CONF_PROF_SUN = "sonne"  # "", "tag", "nacht"
DEFAULT_PATTERN = "{cam} %CCYY-%MM-%DD %hh-%mm-%ss"

COUNTER_START = 1  # Startwert nach Saisonwechsel / fuer neue Spielpartner

# Standard-Kuerzel (Stand: erste Version, aus der Cam-Uebersicht des Nutzers)
DEFAULT_CAMS: dict[str, str] = {
    "Bauleitung": "BL",
    "Baumeister": "BM",
    "Faehrtensucher": "FS",
    "Fellnah": "FN",
    "Fuchsblick": "FB",
    "Hoelenblick": "HB",
    "Kesselcam": "KC",
    "Nachtstreife": "NS",
    "Ohrenspitze": "OS",
    "Pfotenabdruck": "PD",
    "Rotpelz": "RP",
    "Rudelblick": "RB",
    "Schnauzencam": "sc",
    "Schweifwedler": "SW",
    "Unterbau": "UB",
    "Wildspur": "WS",
}
# Cams mit eigener HA-Kamera-Entity fuer Schnappschuesse (wie im alten System)
DEFAULT_CAMERAS: dict[str, str] = {
    "Fuchsblick": "camera.fuchsblick_schnappschusse_in_hochauflosung",
    "Hoelenblick": "camera.hoelenblick_schnappschusse_in_hochauflosung",
}

DISCORD_API = "https://discord.com/api/v10"
DISCORD_COLOR_GREEN = 3066993

SERVICE_PREPARE = "aufnahme_vorbereiten"
SERVICE_SET_COUNTERS = "zaehler_setzen"
SERVICE_COUNT = "aufnahme_zaehlen"
SERVICE_POST = "aufnahme_posten"
SERVICE_REC_START = "recorder_starten"
SERVICE_REC_STOP = "recorder_stoppen"
SERVICE_PROFILE_START = "profil_starten"
SERVICE_PROFILE_STOP = "profil_stoppen"

NO_SUBFOLDERS = "(keine Unterordner)"
