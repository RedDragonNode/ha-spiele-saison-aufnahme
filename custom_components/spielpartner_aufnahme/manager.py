"""Kern der Integration: Zustand, Aufnahme-Vorbereitung, Zaehler, Recorder und Discord."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    CONF_PROF_AFTER,
    CONF_PROF_CAMS,
    CONF_PROF_FOLDER,
    CONF_PROF_FROM,
    CONF_PROF_MAX,
    CONF_PROF_NAME,
    CONF_PROF_PATTERN,
    CONF_PROF_SUN,
    CONF_PROF_TO,
    CONF_PROF_TRIGGERS,
    CONF_RECORDER_KEY,
    CONF_RECORDER_URL,
    CONF_RECORDING_ENTITY,
    CONF_SPIEL_BASE,
    CONF_SWING_ENTITY,
    COUNTER_START,
    DEFAULT_OPTIONS,
    DEFAULT_PATTERN,
    DOMAIN,
    LEGACY_PROFILE,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
    SUBENTRY_PROFILE,
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
    subentry_id: str
    name: str
    kuerzel: str
    camera_entity: str
    post: bool
    record: bool = True
    stream_entity: str = ""
    rtsp_url: str = ""


@dataclass
class ProfileCfg:
    """Aufnahme-Profil: wohin, welche Cams, wann."""

    subentry_id: str
    name: str
    folder: list[str]
    cam_ids: list[str]
    pattern: str = DEFAULT_PATTERN
    triggers: list[str] = field(default_factory=list)
    after_s: int = 0
    max_min: int = 0
    time_from: str = ""
    time_to: str = ""
    sun: str = ""

    @property
    def has_window(self) -> bool:
        return bool((self.time_from and self.time_to) or self.sun)


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
        self.profiles: dict[str, ProfileCfg] = {}
        self.profile_state: dict[str, dict[str, Any]] = {}  # laufende Profile (Laufzeit)
        self._prof_lock = asyncio.Lock()
        self._capped: set[str] = set()
        self._read_subentries()

    # ------------------------------------------------------------------ Setup
    def _read_subentries(self) -> None:
        for sid, sub in self.entry.subentries.items():
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
            elif sub.subentry_type == SUBENTRY_CAM:
                camera = d.get(CONF_CAM_CAMERA, "") or ""
                self.cams.append(
                    CamCfg(
                        subentry_id=sid,
                        name=d[CONF_CAM_NAME],
                        kuerzel=d[CONF_CAM_KUERZEL],
                        camera_entity=camera,
                        post=bool(d.get(CONF_CAM_POST, bool(camera))),
                        record=bool(d.get(CONF_CAM_RECORD, True)),
                        stream_entity=d.get(CONF_CAM_STREAM, "") or "",
                        rtsp_url=d.get(CONF_CAM_RTSP, "") or "",
                    )
                )
            elif sub.subentry_type == SUBENTRY_PROFILE:
                self.profiles[sid] = ProfileCfg(
                    subentry_id=sid,
                    name=d[CONF_PROF_NAME],
                    folder=logic.split_path(d.get(CONF_PROF_FOLDER, "")),
                    cam_ids=list(d.get(CONF_PROF_CAMS) or []),
                    pattern=d.get(CONF_PROF_PATTERN) or DEFAULT_PATTERN,
                    triggers=list(d.get(CONF_PROF_TRIGGERS) or []),
                    after_s=int(d.get(CONF_PROF_AFTER) or 0),
                    max_min=int(d.get(CONF_PROF_MAX) or 0),
                    time_from=d.get(CONF_PROF_FROM) or "",
                    time_to=d.get(CONF_PROF_TO) or "",
                    sun=d.get(CONF_PROF_SUN) or "",
                )
        self.cams.sort(key=lambda c: logic.norm(c.name))

    async def async_load(self) -> None:
        stored = await self._store.async_load()
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

    @callback
    def async_start(self) -> None:
        rec = self.opt(CONF_RECORDING_ENTITY)
        if rec:
            self._unsubs.append(async_track_state_change_event(self.hass, [rec], self._recording_changed))
        watch = {e for p in self.profiles.values() for e in p.triggers}
        if any(p.sun for p in self.profiles.values()):
            watch.add("sun.sun")
        if watch:
            self._unsubs.append(async_track_state_change_event(self.hass, sorted(watch), self._profile_state_changed))
        if self.profiles:
            self._unsubs.append(async_track_time_interval(self.hass, self._profile_tick, timedelta(seconds=20)))
        if self.opt(CONF_RECORDER_URL):
            self._unsubs.append(async_track_time_interval(self.hass, self._poll_recorder, timedelta(seconds=15)))
            self.hass.async_create_background_task(self._first_sync(), name=f"{DOMAIN}_poll")
        elif self.profiles:
            self.hass.async_create_background_task(self._profile_tick(None), name=f"{DOMAIN}_profiles")

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
            busy = self._busy_cam_ids(LEGACY_PROFILE)
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
                await client.start(rel, cams, session)
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
                await client.stop()
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
        await self._sync_profiles(st)
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

    # ------------------------------------------------------------------ Profile
    def profile(self, ref: str) -> ProfileCfg:
        if ref in self.profiles:
            return self.profiles[ref]
        norm = logic.norm(ref)
        for p in self.profiles.values():
            if norm == logic.norm(p.name):
                return p
        raise ServiceValidationError(f"Aufnahme-Profil '{ref}' gibt es nicht")

    def profile_running(self, pid: str) -> bool:
        return pid in self.profile_state

    def _busy_cam_ids(self, exclude: str) -> set[str]:
        """Cams, die gerade in einem anderen Profil aufnehmen (nach Add-on-Stand und eigenem Merker)."""
        busy: set[str] = set()
        for pid, st in self.profile_state.items():
            if pid != exclude:
                busy |= set(st.get("cams") or [])
        for pid, ps in (self.rec_status.get("profile") or {}).items():
            if pid != exclude and ps.get("aufnahme"):
                busy |= {k for k, c in (ps.get("kameras") or {}).items() if c.get("status") != "beendet"}
        return busy

    def _trigger_on(self, p: ProfileCfg) -> bool:
        return any((st := self.hass.states.get(e)) is not None and st.state == STATE_ON for e in p.triggers)

    def _window_open(self, p: ProfileCfg, now: datetime) -> bool:
        if p.time_from and p.time_to and not logic.in_time_window(now, p.time_from, p.time_to):
            return False
        if p.sun:
            sun = self.hass.states.get("sun.sun")
            if sun is None or sun.state not in ("above_horizon", "below_horizon"):
                return False
            if (sun.state == "above_horizon") != (p.sun == "tag"):
                return False
        return True

    def _wanted(self, p: ProfileCfg, now: datetime) -> bool:
        if not p.triggers and not p.has_window:
            return False  # nur manuell
        if not self._window_open(p, now):
            return False
        return self._trigger_on(p) if p.triggers else True

    @callback
    def _profile_state_changed(self, _event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._profile_tick(None))

    async def _first_sync(self) -> None:
        """Beim Start erst den Add-on-Stand holen (laufende Profile erkennen), dann Ausloeser auswerten."""
        await self._poll_recorder(None)
        await self._profile_tick(None)

    async def _profile_tick(self, _now: datetime | None) -> None:
        """Gleicht jedes Profil mit seinen Ausloesern ab (Start, Nachlauf, Hoechstdauer, Zeitfenster)."""
        async with self._prof_lock:
            now = dt_util.now()
            for p in list(self.profiles.values()):
                try:
                    await self._reconcile(p, now)
                except HomeAssistantError as err:
                    _LOGGER.error("Profil %s: %s", p.name, err)
                    self._set_status(f"Profil {p.name}: {err}")
                    self.notify()

    async def _reconcile(self, p: ProfileCfg, now: datetime) -> None:
        run = self.profile_state.get(p.subentry_id)
        wanted = self._wanted(p, now)
        if not wanted:
            self._capped.discard(p.subentry_id)  # Trigger vorbei -> naechste Runde darf wieder starten
        if run is None:
            if wanted and p.subentry_id not in self._capped:
                await self._profile_start(p, manual=False)
            return
        if run.get("manual"):
            return
        if wanted:
            run["off_since"] = None
            if p.max_min and (dt_util.utcnow() - dt_util.parse_datetime(run["start"])).total_seconds() >= p.max_min * 60:
                self._capped.add(p.subentry_id)
                await self._profile_stop(p, "hoechstdauer")
            return
        if p.has_window and not self._window_open(p, now):
            await self._profile_stop(p, "zeitfenster")
            return
        off = run.get("off_since")
        if off is None:
            run["off_since"] = dt_util.utcnow().isoformat()
            off = run["off_since"]
        if (dt_util.utcnow() - dt_util.parse_datetime(off)).total_seconds() >= p.after_s:
            await self._profile_stop(p, "ausloeser_aus")

    async def async_profile_start(self, ref: str) -> dict[str, Any]:
        p = self.profile(ref)
        async with self._prof_lock:
            if p.subentry_id in self.profile_state:
                return {"gestartet": False, "grund": "Profil nimmt bereits auf"}
            return await self._profile_start(p, manual=True)

    async def async_profile_stop(self, ref: str) -> dict[str, Any]:
        p = self.profile(ref)
        async with self._prof_lock:
            if p.subentry_id not in self.profile_state:
                return {"gestoppt": False, "grund": "Profil nimmt nicht auf"}
            await self._profile_stop(p, "manuell")
            return {"gestoppt": True}

    async def _profile_start(self, p: ProfileCfg, manual: bool) -> dict[str, Any]:
        client = self._recorder()
        busy = self._busy_cam_ids(p.subentry_id)
        now = dt_util.now()
        by_id = {c.subentry_id: c for c in self.cams}
        cams: list[dict[str, str]] = []
        skipped: list[str] = []
        for cid in p.cam_ids:
            cam = by_id.get(cid)
            if cam is None or not cam.record:
                continue
            if cid in busy:
                skipped.append(f"{cam.name} (belegt)")
                continue
            url = await self._stream_url(cam)
            if not url:
                skipped.append(f"{cam.name} (keine Stream-Quelle)")
                continue
            stem = logic.render_pattern(p.pattern, now, cam=cam.name, kuerzel=cam.kuerzel, profil=p.name)
            cams.append({"id": cid, "name": cam.name, "url": url, "stem": stem})
        if not cams:
            if manual:
                raise ServiceValidationError(f"Profil {p.name}: keine Cam frei oder ohne Stream-Quelle ({', '.join(skipped) or 'keine Cams gewaehlt'})")
            return {"gestartet": False, "grund": "keine Cam verfuegbar", "uebersprungen": skipped}
        session = logic.render_pattern("{profil} %CCYY-%MM-%DD %hh-%mm-%ss", now, cam="", kuerzel="", profil=p.name)
        try:
            await client.start(p.folder, cams, session, p.subentry_id)
        except RecorderError as err:
            if "nicht erreichbar" in str(err):
                self.rec_online = False
            self._set_status(f"Profil {p.name}: Start fehlgeschlagen: {err}")
            self.notify()
            if manual:
                raise
            _LOGGER.warning("Profil %s konnte nicht starten: %s", p.name, err)
            return {"gestartet": False, "grund": str(err)}
        self.profile_state[p.subentry_id] = {
            "start": dt_util.utcnow().isoformat(),
            "manual": manual,
            "cams": [c["id"] for c in cams],
            "off_since": None,
        }
        self._set_status(f"Profil {p.name}: nimmt auf ({len(cams)} Cams)")
        self.notify()
        return {"gestartet": True, "cams": [c["name"] for c in cams], "uebersprungen": skipped, "ordner": "/".join(p.folder)}

    async def _profile_stop(self, p: ProfileCfg, reason: str) -> None:
        client = self._recorder()
        try:
            await client.stop(p.subentry_id)
        except RecorderError as err:
            self._set_status(f"Profil {p.name}: Stoppen fehlgeschlagen: {err}")
            self.notify()
            raise
        self.profile_state.pop(p.subentry_id, None)
        self._set_status(f"Profil {p.name}: Aufnahme beendet ({reason})")
        self.notify()

    async def _sync_profiles(self, st: dict[str, Any]) -> None:
        """Add-on-Stand uebernehmen: nach HA-Neustart weiterlaufende Profile erkennen, verlorene melden."""
        if "profile" not in st:
            return
        remote = st["profile"]
        for pid, p in self.profiles.items():
            ps = remote.get(pid) or {}
            if ps.get("aufnahme") and pid not in self.profile_state:
                cams = [k for k, c in (ps.get("kameras") or {}).items() if c.get("status") != "beendet"]
                self.profile_state[pid] = {"start": dt_util.utcnow().isoformat(), "manual": False, "cams": cams, "off_since": None}
            elif not ps.get("aufnahme") and pid in self.profile_state and not self._prof_lock.locked():
                self.profile_state.pop(pid, None)
                reason = ps.get("stop_grund") or "unbekannt (Add-on neu gestartet?)"
                persistent_notification.async_create(
                    self.hass,
                    f"Das Profil '{p.name}' wurde vom Recorder beendet. Grund: {reason}.",
                    title="Recorder: Profil unerwartet beendet",
                    notification_id=f"{DOMAIN}_profile_lost_{pid}",
                )
                self._set_status(f"Profil {p.name}: beendet - Grund: {reason}")

    async def _post_due(self, _now: datetime) -> None:
        self._post_cancel = None
        if self.active is not None:
            try:
                await self.async_post_update()
            except HomeAssistantError as err:
                _LOGGER.error("Statusbeitrag fehlgeschlagen: %s", err)
