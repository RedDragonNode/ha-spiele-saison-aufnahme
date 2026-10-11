"""Konstanten der Integration Spiel Saison aufnehmen."""
from __future__ import annotations

DOMAIN = "spiel_saison_aufnehmen"

# Cams, Aufnahme-Profile und die Recorder-Adresse verwaltet die Integration 'Cam Recorder Profile'
HUB_DOMAIN = "cam_recorder_profile"
HUB_SUBENTRY_CAM = "cam"
HUB_SIGNAL = f"{HUB_DOMAIN}_loaded"  # wird dort nach jedem (Neu-)Laden gesendet

SUBENTRY_PARTNER = "spielpartner"
SUBENTRY_CAM = "cam"  # hier nur noch die Discord-Zusaetze einer Cam (Verweis auf die Cam im Hub)
SUBENTRY_PROFILE = "profil"  # nur noch zum Aufraeumen alter Eintraege (bis 0.5.x)
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
}
DEFAULT_RECORDER_URL = "http://local-cam-recorder:8099"
OLD_RECORDER_URL = "http://local-spielpartner-recorder:8099"  # Adresse des frueheren Add-ons

# --- Spielpartner (Subentry) ---------------------------------------------------
CONF_KENNUNG = "kennung"
CONF_ANZEIGE = "anzeige"
CONF_ORDNER_NR = "ordner_nr"
CONF_FORUM_ID = "forum_id"
CONF_INIT_SAISON = "start_saison"
CONF_INIT_AUFNAHMEN = "start_aufnahmen_in_saison"
CONF_INIT_GESAMT = "start_gesamt"
CONF_INITIAL = "initial"  # intern: Startwerte, werden einmalig in den Speicher uebernommen

# --- Cam (Subentry: Discord-Zusaetze) / Cam im Hub -----------------------------
CONF_CAM_ID = "cam_id"  # ID der Cam in Cam Recorder Profile
CONF_CAM_NAME = "name"
CONF_CAM_KUERZEL = "kuerzel"
CONF_CAM_FILTER = "filter_entity"  # alt, wird nicht mehr genutzt
CONF_CAM_SPIEL = "bei_spielpartner"  # Cam bei der Spielpartner-Aufnahme mitnehmen (Standard: ja)
CONF_CAM_POST = "discord_posten"
CONF_CAM_CAMERA = "kamera_entity"  # Schnappschuss fuer Discord
CONF_CAM_RECORD = "aufnehmen"  # Recorder: diese Cam aufnehmen
CONF_CAM_STREAM = "stream_entity"  # Recorder: Stream-Quelle ueber eine HA-Kamera
CONF_CAM_RTSP = "rtsp_url"  # Recorder: oder direkte RTSP-Adresse (hat Vorrang)

COUNTER_START = 1  # Startwert nach Saisonwechsel / fuer neue Spielpartner

DISCORD_API = "https://discord.com/api/v10"
DISCORD_COLOR_GREEN = 3066993

SERVICE_PREPARE = "aufnahme_vorbereiten"
SERVICE_SET_COUNTERS = "zaehler_setzen"
SERVICE_COUNT = "aufnahme_zaehlen"
SERVICE_POST = "aufnahme_posten"
SERVICE_REC_START = "recorder_starten"
SERVICE_REC_STOP = "recorder_stoppen"

NO_SUBFOLDERS = "(keine Unterordner)"
