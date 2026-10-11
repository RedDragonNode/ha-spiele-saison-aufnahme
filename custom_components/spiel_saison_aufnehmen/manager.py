"""Kern der Integration: Zustand, Aufnahme-Vorbereitung, Zaehler, Recorder und Discord."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    CONF_ANZEIGE,
    CONF_CAM_CAMERA,
    CONF_CAM_ID,
    CONF_CAM_KUERZEL,
    CONF_CAM_NAME,
    CONF_CAM_POST,
    CONF_CAM_RECORD,
    CONF_CAM_RTSP,
    CONF_CAM_STREAM,
    CONF_DISCORD_TOKEN,
    CONF_FOLDER_PREFIX,
    CONF_FORMAT_SUFFIX,
    CONF_FORUM_ID,
    CONF_INITIAL,
    CONF_KENNUNG,
    CONF_ORDNER_NR,
    CONF_POST_DELAY,
    CONF_POST_GAP,
    CONF_RECORDER_KEY,
    CONF_RECORDER_URL,
    CONF_RECORDING_ENTITY,
    CONF_SPIEL_BASE,
    CONF_SWING_ENTITY,
    COUNTER_START,
    DEFAULT_OPTIONS,
    DEFAULT_RECORDER_URL,
    DOMAIN,
    HUB_DOMAIN,
    HUB_SUBENTRY_CAM,
    LEGACY_PROFILE,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)
from .discord_client import DiscordClient, DiscordError
from .recorder_client import RecorderClient, RecorderError

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


async def async_get_stream_source(hass: HomeAssistant, entity_id: str) -> str | None:
    """RTSP-Adresse einer HA-Kamera holen (Camera-Komponente erst bei Bedarf laden)."""
    from homeassistant.components.camera import async_get_stream_source as _get

    return await _get(hass, entity_id)


async def async_get_image(hass: HomeAssistant, entity_id: str) -> Any:
    """Schnappschuss holen (Camera-Komponente erst bei Bedarf laden)."""
    from homeassistant.components.camera import async_get_image as _get

    return await _get(hass, entity_id)


@dataclass
class PartnerCfg:
    subentry_id: str
    kennung: str
    anzeige: str
    ordner_nr: int
    forum_id: str
    initial: dict[str, Any] = field(default_factory=dict)


@dataclass
class CamCfg:
    """Eine Cam aus 'Cam Recorder Profile' (subentry_id = Cam-ID im Recorder) plus die Discord-Zusaetze von hier."""

    subentry_id: str
    name: str
    kuerzel: str
    camera_entity: str = ""
    post: bool = False
    record: bool = True
    stream_entity: str = ""
    rtsp_url: str = ""


class SpielpartnerManager:
    """Haelt alle Daten eines Config-Entries."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.signal = f"{DOMAIN}_update_{entry.entry_id}"
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {"active": None, "partners": {}, "status": {}}
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._post_cancel: CALLBACK_TYPE | None = None
        self._post_task: asyncio.Task[None] | None = None
        self._rec_lock = asyncio.Lock()
        self._rec_active = False  # Aufnahme-Ablauf (Statusbeitrag, Zaehlen) laeuft
        self._rec_running = False  # Recorder-Add-on nimmt auf (von uns gestartet)
        self._reattach = False
        self.rec_status: dict[str, Any] = {}
        self.rec_online: bool | None = None
        self.partners: dict[str, PartnerCfg] = {}
        self.cams: list[CamCfg] = []
        self._read_subentries()

    # ------------------------------------------------------------------ Setup
    def hub_entry(self) -> ConfigEntry | None:
        """Der Eintrag von 'Cam Recorder Profile' (dort liegen Cams, Profile und die Recorder-Adresse)."""
        return next(iter(self.hass.config_entries.async_entries(HUB_DOMAIN)), None)

    def _read_subentries(self) -> None:
        for sid, sub in self.entry.subentries.items():
            try:
                self._read_subentry(sid, sub)
            except (KeyError, TypeError, ValueError) as err:
                # Ein defekter Eintrag darf nicht die ganze Integration lahmlegen
                _LOGGER.error(
                    "Unterintrag '%s' (%s, id %s) ist unvollstaendig (fehlt: %s) und wird uebersprungen - bitte loeschen oder neu anlegen",
                    sub.title,
                    sub.subentry_type,
                    sid,
                    err,
                )
        hub = self.hub_entry()
        by_id: dict[str, CamCfg] = {}
        for sid, sub in (hub.subentries if hub else {}).items():
            d = sub.data
            if sub.subentry_type != HUB_SUBENTRY_CAM or not d.get(CONF_CAM_NAME):
                continue
            by_id[sid] = CamCfg(
                subentry_id=sid,
                name=d[CONF_CAM_NAME],
                kuerzel=d.get(CONF_CAM_KUERZEL) or d[CONF_CAM_NAME][:2].upper(),
                record=bool(d.get(CONF_CAM_RECORD, True)),
                stream_entity=d.get(CONF_CAM_STREAM, "") or "",
                rtsp_url=d.get(CONF_CAM_RTSP, "") or "",
            )
        for sub in self.entry.subentries.values():  # Discord-Zusaetze je Cam
            if sub.subentry_type != SUBENTRY_CAM:
                continue
            cam = by_id.get(sub.data.get(CONF_CAM_ID, ""))
            if cam is None:
                _LOGGER.warning("Discord-Eintrag '%s' gehoert zu keiner Cam in Cam Recorder Profile", sub.title)
                continue
            cam.camera_entity = sub.data.get(CONF_CAM_CAMERA, "") or ""
            cam.post = bool(sub.data.get(CONF_CAM_POST, bool(cam.camera_entity)))
        self.cams = sorted(by_id.values(), key=lambda c: logic.norm(c.name))

    def _read_subentry(self, sid: str, sub: Any) -> None:
        d = sub.data
        if sub.subentry_type == SUBENTRY_PARTNER:
            p = PartnerCfg(
                subentry_id=sid,
                kennung=d[CONF_KENNUNG],
                anzeige=d.get(CONF_ANZEIGE) or logic.default_anzeige(d[CONF_KENNUNG]),
                ordner_nr=int(d.get(CONF_ORDNER_NR, 1)),
                forum_id=str(d.get(CONF_FORUM_ID, "") or ""),
                initial=dict(d.get(CONF_INITIAL, {})),
            )
            self.partners[p.kennung] = p

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            stored = await self.hass.async_add_executor_job(self._import_old_store)
        if stored:
            self.data.update(stored)
        self.data.setdefault("partners", {})
        for kennung, p in self.partners.items():
            if kennung not in self.data["partners"]:
                ini = p.initial
                self.data["partners"][kennung] = {
                    "saison": int(ini.get("saison") or COUNTER_START),
                    "aufnahmen": int(ini.get("aufnahmen") or COUNTER_START),
                    "gesamt": int(ini.get("gesamt") or COUNTER_START),
                    "thread_id": str(ini.get("thread_id") or ""),
                    "thread_saison": str(ini.get("thread_saison") or ""),
                    "pfad": "",
                    "vorbereitet": None,
                }
        if self.data.get("active") not in self.partners:
            self.data["active"] = None
        self._rec_running = self._reattach = bool((self.data.get("recorder") or {}).get("laeuft"))
        self._save_later()

    def _import_old_store(self) -> dict[str, Any] | None:
        """Zaehler/Threads aus der frueheren Integration 'spielpartner_aufnahme' uebernehmen (einmalig, falls vorhanden)."""
        folder = Path(self.hass.config.path(".storage"))
        try:
            files = sorted(folder.glob("spielpartner_aufnahme.*"), key=lambda f: f.stat().st_mtime, reverse=True)
        except OSError:
            return None
        for f in files:
            if f.suffix in (".bak", ".tmp"):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8")).get("data") or {}
            except (OSError, ValueError):
                continue
            if isinstance(data.get("partners"), dict):
                _LOGGER.info("Zaehler aus der frueheren Integration uebernommen (%s)", f.name)
                keep = ("active", "partners", "status")
                return {k: data[k] for k in keep if k in data}
        return None

    @callback
    def async_start(self) -> None:
        rec = self.opt(CONF_RECORDING_ENTITY)
        if rec:
            self._unsubs.append(async_track_state_change_event(self.hass, [rec], self._recording_changed))
        if self.opt(CONF_RECORDER_URL):
            self._unsubs.append(async_track_time_interval(self.hass, self._poll_recorder, timedelta(seconds=15)))
            self.hass.async_create_background_task(self._poll_recorder(None), name=f"{DOMAIN}_poll")

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._post_cancel:
            self._post_cancel()
            self._post_cancel = None
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
        await self._store.async_save(self.data)

    # ---------------------------------------------------------------- Helfer
    def opt(self, key: str) -> Any:
        val = self.entry.options.get(key)
        if val in (None, "") and key in (CONF_RECORDER_URL, CONF_RECORDER_KEY):
            hub = self.hub_entry()  # leer = Einstellung von Cam Recorder Profile
            val = hub.options.get(key) if hub else None
            return val or (DEFAULT_RECORDER_URL if key == CONF_RECORDER_URL else None)
        return DEFAULT_OPTIONS.get(key) if val is None and key in DEFAULT_OPTIONS else val

    @property
    def recorder_running(self) -> bool:
        return self._rec_running

    def partner(self, kennung: str) -> PartnerCfg:
        if kennung in self.partners:
            return self.partners[kennung]
        norm = logic.norm(kennung)
        for p in self.partners.values():
            if norm in (logic.norm(p.kennung), logic.norm(p.anzeige)):
                return p
        raise ServiceValidationError(f"Spielpartner '{kennung}' ist nicht eingerichtet")

    def state_of(self, kennung: str) -> dict[str, Any]:
        return self.data["partners"][kennung]

    @property
    def active(self) -> PartnerCfg | None:
        return self.partners.get(self.data.get("active") or "")

    @callback
    def _save_later(self) -> None:
        self._store.async_delay_save(lambda: self.data, 2)

    @callback
    def notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    def _set_status(self, text: str) -> None:
        self.data["status"] = {"text": text, "zeit": dt_util.now().isoformat()}

    def _discord(self) -> DiscordClient | None:
        token = self.opt(CONF_DISCORD_TOKEN)
        if not token:
            return None
        return DiscordClient(async_get_clientsession(self.hass), token)

    def _recorder(self) -> RecorderClient:
        url, key = self.opt(CONF_RECORDER_URL), self.opt(CONF_RECORDER_KEY)
        if not url or not key:
            raise ServiceValidationError("Recorder: Adresse und Schluessel fehlen in den Einstellungen")
        return RecorderClient(async_get_clientsession(self.hass), url, key)

    # --------------------------------------------------------------- Formate
    def video_id(self, kennung: str, cam: CamCfg | None, when: datetime | None = None) -> str:
        """Dateiname ohne Endung, mit echtem Datum (Datums-Platzhalter aufgeloest)."""
        return logic.render_tokens(self.format_for(kennung, cam), when or dt_util.now())

    def format_for(self, kennung: str, cam: CamCfg | None) -> str:
        p, s = self.partners[kennung], self.state_of(kennung)
        return logic.file_format(
            p.ordner_nr,
            s["saison"],
            s["aufnahmen"],
            cam.kuerzel if cam else "Cam ID",
            s["gesamt"],
            self.opt(CONF_FORMAT_SUFFIX) or "",
        )


    # ------------------------------------------------------------- Vorbereiten
    async def async_prepare(self, kennung: str) -> dict[str, Any]:
        """Entspricht dem frueheren Skript 'Aufnahme Vorbereitung'."""
        async with self._lock:
            return await self._prepare(self.partner(kennung))

    async def _prepare(self, p: PartnerCfg) -> dict[str, Any]:
        s = self.state_of(p.kennung)
        hints: list[str] = []
        self.data["active"] = p.kennung
        ordner = logic.partner_folder(self.opt(CONF_FOLDER_PREFIX), p.anzeige, p.ordner_nr)
        datum = dt_util.now().strftime("%d,%m,%Y")

        # 1) Ordner ueber den Recorder anlegen, neue Saison pruefen
        existing: list[str] | None = None
        client = None
        base = logic.split_path(self.opt(CONF_SPIEL_BASE) or "")
        try:
            client = self._recorder()
            self.rec_status = await client.status()
            self.rec_online = True
            await client.make_dirs([*base, ordner])
            existing = await client.list_dirs([*base, ordner])
        except (RecorderError, ServiceValidationError) as err:
            if isinstance(err, RecorderError):
                self.rec_online = False
            client = None
            hints.append(f"Recorder: Ordner nicht angelegt, Saisonwechsel nicht geprueft ({err})")
        neuer_tag = logic.is_new_day(existing, logic.season_folder(s["saison"], datum))
        if neuer_tag:
            s["saison"] += 1
            s["aufnahmen"] = COUNTER_START
        saison_ordner = logic.season_folder(s["saison"], datum)
        pfad = ""
        s["rec_rel"] = []
        if client is not None:
            try:
                await client.make_dirs([*base, ordner, saison_ordner])
                s["rec_rel"] = [*base, ordner, saison_ordner]
                pfad = "/".join([str(self.rec_status.get("wurzel") or "recorder").rstrip("/"), *base, ordner, saison_ordner])
            except RecorderError as err:
                hints.append(f"Recorder: Saison-Ordner nicht angelegt ({err})")
        s["pfad"] = pfad

        # 2) Discord
        discord_status = await self._ensure_thread(p, s, hints)

        s["vorbereitet"] = dt_util.now().isoformat()
        result = {
            "spielpartner": p.kennung,
            "anzeige": p.anzeige,
            "ordner": pfad,
            "neue_saison": neuer_tag,
            "saison": s["saison"],
            "aufnahme_in_saison": s["aufnahmen"],
            "gesamt": s["gesamt"],
            "dateiformat": self.format_for(p.kennung, None),
            "discord": discord_status,
            "hinweise": hints,
        }
        self._set_status(f"{p.anzeige}: vorbereitet ({'neue Saison' if neuer_tag else 'gleiche Saison'})")
        self._save_later()
        self.notify()
        self._notification(p, result)
        return result

    def _notification(self, p: PartnerCfg, r: dict[str, Any]) -> None:
        lines = [
            f"Ordner: {r['ordner'] or 'NICHT angelegt'}",
            f"Dateiformat: {r['dateiformat']}",
            (
                f"Saison {logic.pad(r['saison'])}, Aufnahme {logic.pad(r['aufnahme_in_saison'])} dieser Saison, "
                f"{logic.pad(r['gesamt'])} insgesamt."
            ),
            f"Neue Saison erkannt: {'ja' if r['neue_saison'] else 'nein'}",
            f"Discord: {r['discord']}",
        ]
        if r["hinweise"]:
            lines.append("ACHTUNG:\n- " + "\n- ".join(r["hinweise"]))
        persistent_notification.async_create(
            self.hass,
            "\n\n".join(lines),
            title=f"Aufnahme vorbereitet: {p.anzeige}",
            notification_id=f"{DOMAIN}_prepare_{p.kennung}",
        )

    # ----------------------------------------------------------------- Discord
    async def _ensure_thread(self, p: PartnerCfg, s: dict[str, Any], hints: list[str]) -> str:
        client = self._discord()
        if client is None:
            return "nicht eingerichtet (kein Bot-Token)"
        if not p.forum_id:
            return "kein Forum-Kanal fuer diesen Spielpartner hinterlegt"
        if s["thread_id"] and s["thread_saison"] == logic.pad(s["saison"]):
            return f"Thread vorhanden ({s['thread_id']})"
        saison = logic.pad(s["saison"])
        try:
            thread = await client.create_forum_thread(
                p.forum_id,
                f"Saison {saison}",
                title=f"Saison {saison}",
                description=f"Aufnahmen mit {p.anzeige} - Saison {saison}",
                message=f"Neue Saison gestartet: Saison {saison} mit {p.anzeige}.",
            )
        except DiscordError as err:
            hints.append(f"Discord-Thread konnte nicht angelegt werden: {err}")
            return "FEHLER beim Anlegen des Threads"
        s["thread_id"], s["thread_saison"] = thread, saison
        return f"neuer Thread angelegt ({thread})"

    async def async_post_update(self, kennung: str | None = None) -> dict[str, Any]:
        """Statusbeitrag starten: Kopfzeile, danach jede angehakte Cam einzeln und zeitlich versetzt."""
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner")
        s = self.state_of(p.kennung)
        if self._discord() is None or not s["thread_id"]:
            persistent_notification.async_create(
                self.hass,
                f"Fuer {p.anzeige} gibt es keinen aktuellen Saison-Thread. Bitte zuerst 'Aufnahme vorbereiten' ausfuehren.",
                title="Kein Discord-Thread gefunden",
                notification_id=f"{DOMAIN}_kein_thread_{p.kennung}",
            )
            return {"gepostet": False, "grund": "kein Thread"}
        cams = [c for c in self.cams if c.post]
        if not cams:
            return {"gepostet": False, "grund": "bei keiner Cam ist 'In Discord posten' angehakt"}
        # IDs jetzt festhalten: sie gehoeren zu dieser Aufnahme, auch wenn sich Zaehler spaeter aendern
        now = dt_util.now()
        items = [(c, self.video_id(p.kennung, c, now)) for c in cams]
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
        self._post_task = self.hass.async_create_background_task(
            self._post_sequence(p, s["thread_id"], items), name=f"{DOMAIN}_post"
        )
        gap = int(self.opt(CONF_POST_GAP) or 0)
        return {"gepostet": True, "cams": [c.name for c in cams], "abstand_sekunden": gap}

    async def _post_sequence(self, p: PartnerCfg, thread_id: str, items: list[tuple[CamCfg, str]]) -> None:
        client = self._discord()
        if client is None:
            return
        gap = max(0, int(self.opt(CONF_POST_GAP) or 0))
        swing = None
        swing_entity = self.opt(CONF_SWING_ENTITY)
        if swing_entity and (st := self.hass.states.get(swing_entity)):
            swing = st.attributes.get("current_position", st.state)
        sent = 0
        try:
            await client.post_message(thread_id, logic.build_post_header(int(self.opt(CONF_POST_DELAY) or 5), swing))
            for i, (cam, video_id) in enumerate(items):
                if i and gap:
                    await asyncio.sleep(gap)
                images = []
                if cam.camera_entity:
                    try:
                        img = await async_get_image(self.hass, cam.camera_entity)
                        ext = "png" if "png" in (img.content_type or "") else "jpg"
                        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
                        images.append((f"{cam.name}_{stamp}.{ext}", img.content, img.content_type or "image/jpeg"))
                    except HomeAssistantError as err:
                        _LOGGER.warning("Schnappschuss von %s fehlgeschlagen: %s", cam.camera_entity, err)
                if images:
                    await client.post_message(thread_id, "", images)  # erst das Bild ...
                await client.post_message(thread_id, logic.build_cam_caption(cam.name, video_id))  # ... direkt darunter die ID
                sent += 1
        except DiscordError as err:
            _LOGGER.error("Discord-Beitrag fehlgeschlagen: %s", err)
            self._set_status(f"Discord-Beitrag fehlgeschlagen: {err}")
        else:
            self._set_status(f"{p.anzeige}: Statusbeitrag gepostet ({sent} Cams)")
        self.notify()

    # ------------------------------------------------------------------ Zaehler
    async def async_count_recording(self, kennung: str | None = None) -> None:
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner")
        s = self.state_of(p.kennung)
        s["aufnahmen"] += 1
        s["gesamt"] += 1
        self._set_status(f"{p.anzeige}: Aufnahme gezaehlt")
        self._save_later()
        self.notify()

    async def async_set_counters(
        self, kennung: str, saison: int | None, aufnahmen: int | None, gesamt: int | None
    ) -> None:
        p = self.partner(kennung)
        s = self.state_of(p.kennung)
        for key, val in (("saison", saison), ("aufnahmen", aufnahmen), ("gesamt", gesamt)):
            if val is not None:
                s[key] = max(0, int(val))
        self._save_later()
        self.notify()

    # --------------------------------------------------------- Aufnahme-Ereignis
    @callback
    def _rec_started(self) -> None:
        """Aufnahme hat begonnen - nur einmal."""
        if self._rec_active:
            return
        self._rec_active = True
        if self._post_cancel:
            self._post_cancel()
        delay = int(self.opt(CONF_POST_DELAY) or 5) * 60
        self._post_cancel = async_call_later(self.hass, delay, self._post_due)
        self.notify()

    async def _rec_stopped(self) -> None:
        """Aufnahme ist zu Ende - zaehlt genau einmal."""
        if not self._rec_active:
            return
        self._rec_active = False
        if self._post_cancel:
            self._post_cancel()
            self._post_cancel = None
        if self.active is not None:
            await self.async_count_recording()
        self.notify()

    @callback
    def _recording_changed(self, event: Event[EventStateChangedData]) -> None:
        """Optionaler Ausloeser (beliebiger Schalter/Sensor): an = Recorder starten, aus = stoppen."""
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        if old.state == STATE_OFF and new.state == STATE_ON:
            self.hass.async_create_task(self._follow_trigger(True))
        elif old.state == STATE_ON and new.state == STATE_OFF:
            self.hass.async_create_task(self._follow_trigger(False))

    async def _follow_trigger(self, on: bool) -> None:
        try:
            if on:
                await self.async_recorder_start()
            else:
                await self.async_recorder_stop()
        except HomeAssistantError as err:
            _LOGGER.error("Recorder konnte dem Ausloeser nicht folgen: %s", err)
            self._set_status(f"Recorder: {err}")
            self.notify()

    def _busy_cam_ids(self) -> set[str]:
        """Cams, die gerade in einem Aufnahme-Profil (Cam Recorder Profile) aufnehmen."""
        busy: set[str] = set()
        for pid, ps in (self.rec_status.get("profile") or {}).items():
            if pid != LEGACY_PROFILE and ps.get("aufnahme"):
                busy |= {k for k, c in (ps.get("kameras") or {}).items() if c.get("status") != "beendet"}
        return busy

    # ------------------------------------------------------------------ Recorder
    async def _stream_url(self, cam: CamCfg) -> str | None:
        if cam.rtsp_url:
            return cam.rtsp_url
        if cam.stream_entity:
            try:
                return await async_get_stream_source(self.hass, cam.stream_entity)
            except HomeAssistantError as err:
                _LOGGER.warning("Stream-Quelle von %s nicht lesbar: %s", cam.stream_entity, err)
        return None

    async def async_recorder_start(self, kennung: str | None = None) -> dict[str, Any]:
        async with self._rec_lock:
            client = self._recorder()
            p = self.partner(kennung) if kennung else self.active
            if p is None:
                raise ServiceValidationError("Kein aktiver Spielpartner - zuerst 'Aufnahme vorbereiten' ausfuehren")
            if self._rec_running:
                return {"gestartet": False, "grund": "Aufnahme laeuft bereits"}
            s = self.state_of(p.kennung)
            rel = s.get("rec_rel")
            if not rel:
                raise ServiceValidationError(
                    f"Fuer {p.anzeige} gibt es keinen Recorder-Ordner - 'Aufnahme vorbereiten' ausfuehren (Recorder erreichbar?)"
                )
            now = dt_util.now()
            cams: list[dict[str, str]] = []
            skipped: list[str] = []
            busy = self._busy_cam_ids()
            for cam in self.cams:
                if not cam.record:
                    continue
                if cam.subentry_id in busy:
                    skipped.append(f"{cam.name} (nimmt in einem Profil auf)")
                    continue
                url = await self._stream_url(cam)
                if not url:
                    skipped.append(cam.name)
                    continue
                cams.append({"id": cam.subentry_id, "name": cam.name, "url": url, "stem": self.video_id(p.kennung, cam, now)})
            if not cams:
                raise ServiceValidationError(
                    "Keine Cam mit Stream-Quelle - bei den Cams 'Stream-Kamera' oder 'RTSP-Adresse' eintragen"
                )
            session = f"#{logic.pad(p.ordner_nr)}.{logic.pad(s['saison'])}.{logic.pad(s['aufnahmen'])} Sitzung"
            try:
                await client.start(rel, cams, session, LEGACY_PROFILE)
            except RecorderError as err:
                self.rec_online = False if "nicht erreichbar" in str(err) else self.rec_online
                self._set_status(f"Recorder konnte nicht starten: {err}")
                persistent_notification.async_create(
                    self.hass, str(err), title="Recorder: Start fehlgeschlagen", notification_id=f"{DOMAIN}_rec_start"
                )
                self.notify()
                raise
            self._rec_running = True
            self.data["recorder"] = {"laeuft": True, "start": now.isoformat(), "partner": p.kennung}
            self._save_later()
            self._set_status(f"{p.anzeige}: Recorder nimmt auf ({len(cams)} Cams)")
            self._rec_started()
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_rec_start")
            self.notify()
            return {"gestartet": True, "cams": [c["name"] for c in cams], "ohne_stream": skipped, "ordner": "/".join(rel)}

    async def async_recorder_stop(self) -> dict[str, Any]:
        async with self._rec_lock:
            client = self._recorder()
            if not self._rec_running:
                return {"gestoppt": False, "grund": "Es laeuft keine Aufnahme des Recorders"}
            try:
                await client.stop(LEGACY_PROFILE)
            except RecorderError as err:
                self._set_status(f"Recorder konnte nicht stoppen: {err}")
                persistent_notification.async_create(
                    self.hass, str(err), title="Recorder: Stoppen fehlgeschlagen", notification_id=f"{DOMAIN}_rec_stop"
                )
                self.notify()
                raise
            self._rec_running = False
            self.data["recorder"] = {"laeuft": False}
            self._save_later()
            self._set_status("Recorder: Aufnahme beendet")
            await self._rec_stopped()
            await self._poll_recorder(None)
            return {"gestoppt": True}

    async def _poll_recorder(self, _now: datetime | None) -> None:
        """Zustand des Add-ons holen; verlorene Aufnahmen (Absturz, Platte voll) erkennen."""
        try:
            client = self._recorder()
            st = await client.status()
        except (RecorderError, ServiceValidationError):
            if self.rec_online is not False:
                self.rec_online = False
                self.notify()
            return
        self.rec_status, self.rec_online = st, True
        legacy = (st.get("profile") or {}).get(LEGACY_PROFILE) or {} if "profile" in st else st
        if self._rec_running and not self._rec_lock.locked():
            if legacy.get("aufnahme"):
                if self._reattach:  # HA wurde neu gestartet, Aufnahme laeuft weiter
                    self._rec_active = True
                self._reattach = False
            else:
                self._reattach = False
                self._rec_running = False
                self.data["recorder"] = {"laeuft": False}
                self._save_later()
                reason = legacy.get("stop_grund") or "unbekannt (Add-on neu gestartet?)"
                persistent_notification.async_create(
                    self.hass,
                    f"Der Recorder hat die Aufnahme beendet. Grund: {reason}. Bereits geschriebene Dateien bleiben erhalten.",
                    title="Recorder: Aufnahme unerwartet beendet",
                    notification_id=f"{DOMAIN}_rec_lost",
                )
                self._rec_active = True  # genau einmal zaehlen
                await self._rec_stopped()
                self._set_status(f"Recorder: Aufnahme ist beendet worden - Grund: {reason}")
        self.notify()

    async def _post_due(self, _now: datetime) -> None:
        self._post_cancel = None
        if self.active is not None:
            try:
                await self.async_post_update()
            except HomeAssistantError as err:
                _LOGGER.error("Statusbeitrag fehlgeschlagen: %s", err)
