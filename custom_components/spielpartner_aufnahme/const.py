"""Konstanten der Integration Spielpartner Aufnahme."""
from __future__ import annotations

DOMAIN = "spielpartner_aufnahme"

SUBENTRY_PARTNER = "spielpartner"
SUBENTRY_CAM = "cam"

# --- Einstellungen (config_entry.options) -------------------------------------
CONF_DISCORD_TOKEN = "discord_token"
CONF_BASE_UNIX = "basis_pfad_obs"
CONF_BASE_WIN = "basis_pfad_windows"
CONF_FOLDER_PREFIX = "ordner_praefix"
CONF_FORMAT_SUFFIX = "dateiformat_endung"
CONF_RECORDING_ENTITY = "aufnahme_entity"
CONF_POST_DELAY = "post_nach_minuten"
CONF_POST_GAP = "post_abstand_sekunden"
CONF_SWING_ENTITY = "schaukel_entity"
CONF_TOOL_BASE_BTN = "werkzeug_basis_button"
CONF_TOOL_ENTER_BTN = "werkzeug_wechseln_button"
CONF_TOOL_NAME_TEXT = "werkzeug_name_text"
CONF_TOOL_PATH_SENSOR = "werkzeug_pfad_sensor"
CONF_TOOL_FOLDER_SELECT = "werkzeug_ordner_select"
CONF_TOOL_STATUS_SENSOR = "werkzeug_status_sensor"
CONF_TOOL_TIMEOUT = "werkzeug_timeout"

DEFAULT_OPTIONS: dict[str, object] = {
    CONF_BASE_UNIX: "X:/#2.0 Meine Videos OBS aufnahmen",
    CONF_BASE_WIN: "X:\\#2.0 Meine Videos OBS aufnahmen",
    CONF_FOLDER_PREFIX: "Spielen mit",
    CONF_FORMAT_SUFFIX: " (4K) %DD.%MM.%CCYY",
    CONF_RECORDING_ENTITY: "binary_sensor.obs_stream_gay_fox_88_aufnahme",
    CONF_POST_DELAY: 5,
    CONF_POST_GAP: 20,
    CONF_TOOL_BASE_BTN: "button.spielzimmer_pc_ordner_werkzeug_zur_basis_wechseln",
    CONF_TOOL_ENTER_BTN: "button.spielzimmer_pc_ordner_werkzeug_in_ordner_wechseln",
    CONF_TOOL_NAME_TEXT: "text.spielzimmer_pc_ordner_werkzeug_neuer_ordner_name",
    CONF_TOOL_PATH_SENSOR: "sensor.spielzimmer_pc_ordner_werkzeug_aktueller_ordner_adresse",
    CONF_TOOL_FOLDER_SELECT: "select.spielzimmer_pc_ordner_werkzeug_ordner_auswaehlen_wechseln",
    CONF_TOOL_STATUS_SENSOR: "sensor.spielzimmer_pc_ordner_werkzeug_ordner_status",
    CONF_TOOL_TIMEOUT: 15,
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
CONF_CAM_CAMERA = "kamera_entity"

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
SERVICE_APPLY_FORMATS = "dateiformat_anwenden"

NO_SUBFOLDERS = "(keine Unterordner)"
