"""Kern der Integration: Zustand, Aufnahme-Vorbereitung, Zaehler, OBS und Discord."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    CONF_ANZEIGE,
    CONF_BASE_UNIX,
    CONF_BASE_WIN,
    CONF_CAM_CAMERA,
    CONF_CAM_FILTER,
    CONF_CAM_KUERZEL,
    CONF_CAM_NAME,
    CONF_DISCORD_TOKEN,
    CONF_FOLDER_PREFIX,
    CONF_FORMAT_SUFFIX,
    CONF_FORUM_ID,
    CONF_INITIAL,
    CONF_KENNUNG,
    CONF_ORDNER_NR,
    CONF_POST_DELAY,
    CONF_RECORDING_ENTITY,
    CONF_SWING_ENTITY,
    CONF_TOOL_BASE_BTN,
    CONF_TOOL_ENTER_BTN,
    CONF_TOOL_FOLDER_SELECT,
    CONF_TOOL_NAME_TEXT,
    CONF_TOOL_PATH_SENSOR,
    CONF_TOOL_STATUS_SENSOR,
    CONF_TOOL_TIMEOUT,
    COUNTER_START,
    DEFAULT_OPTIONS,
    DOMAIN,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)
from .discord_client import DiscordClient, DiscordError

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


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
    filter_entity: str
    camera_entity: str


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
        self.partners: dict[str, PartnerCfg] = {}
        self.cams: list[CamCfg] = []
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
                self.cams.append(
                    CamCfg(
                        subentry_id=sid,
                        name=d[CONF_CAM_NAME],
                        kuerzel=d[CONF_CAM_KUERZEL],
                        filter_entity=d.get(CONF_CAM_FILTER, "") or "",
                        camera_entity=d.get(CONF_CAM_CAMERA, "") or "",
                    )
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
        self._save_later()

    @callback
    def async_start(self) -> None:
        rec = self.opt(CONF_RECORDING_ENTITY)
        if rec:
            self._unsubs.append(async_track_state_change_event(self.hass, [rec], self._recording_changed))

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._post_cancel:
            self._post_cancel()
            self._post_cancel = None
        await self._store.async_save(self.data)

    # ---------------------------------------------------------------- Helfer
    def opt(self, key: str) -> Any:
        val = self.entry.options.get(key)
        return DEFAULT_OPTIONS.get(key) if val is None and key in DEFAULT_OPTIONS else val

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

    # --------------------------------------------------------------- Formate
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

    def _source_filters(self, only_on: bool = False) -> list[tuple[str, str]]:
        res = []
        for st in self.hass.states.async_all("switch"):
            if st.attributes.get("filter_kind") != "source_record_filter":
                continue
            if st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            if only_on and st.state != STATE_ON:
                continue
            res.append((st.entity_id, str(st.attributes.get("source", ""))))
        return res

    def cam_filters(self, cam: CamCfg, only_on: bool = False) -> list[str]:
        available = self._source_filters(only_on)
        if cam.filter_entity:
            return [cam.filter_entity] if cam.filter_entity in {e for e, _ in available} else []
        return logic.match_filters(cam.name, available)

    # ------------------------------------------------------------------- OBS
    async def _obs_set(self, entity_id: str, settings: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            "obs_stream_monitor",
            "set_settings",
            {"entity_id": entity_id, "settings": settings},
            blocking=True,
        )

    async def _apply_path(self, path: str) -> tuple[int, list[str]]:
        ok, errors = 0, []
        for entity_id, _ in self._source_filters():
            try:
                await self._obs_set(entity_id, {"path": path})
                ok += 1
            except HomeAssistantError as err:
                errors.append(f"{entity_id}: {err}")
        return ok, errors

    async def _apply_formats(self, kennung: str) -> tuple[int, list[str], list[str]]:
        ok, errors, without = 0, [], []
        for cam in self.cams:
            for entity_id in self.cam_filters(cam):
                try:
                    await self._obs_set(entity_id, {"filename_formatting": self.format_for(kennung, cam)})
                    ok += 1
                except HomeAssistantError as err:
                    errors.append(f"{entity_id}: {err}")
        mapped = {e for cam in self.cams for e in self.cam_filters(cam)}
        without = [e for e, _ in self._source_filters() if e not in mapped]
        return ok, errors, without

    async def async_apply_formats(self, kennung: str | None = None) -> dict[str, Any]:
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner - zuerst 'Aufnahme vorbereiten' ausfuehren")
        ok, errors, without = await self._apply_formats(p.kennung)
        return {"gesetzt": ok, "fehler": errors, "ohne_kuerzel": without}

    # --------------------------------------------------------- Ordner-Werkzeug
    def _tool_ids(self) -> dict[str, str]:
        return {
            "base": self.opt(CONF_TOOL_BASE_BTN) or "",
            "enter": self.opt(CONF_TOOL_ENTER_BTN) or "",
            "name": self.opt(CONF_TOOL_NAME_TEXT) or "",
            "path": self.opt(CONF_TOOL_PATH_SENSOR) or "",
            "select": self.opt(CONF_TOOL_FOLDER_SELECT) or "",
            "status": self.opt(CONF_TOOL_STATUS_SENSOR) or "",
        }

    def _tool_available(self) -> bool:
        ids = self._tool_ids()
        for key in ("base", "enter", "name", "path", "select"):
            st = self.hass.states.get(ids[key])
            if st is None or st.state == STATE_UNAVAILABLE:
                return False
        return True

    async def _wait_state(self, entity_id: str, target: str) -> bool:
        """Wartet (bis Timeout), dass die Entity den Zielwert hat."""
        current = self.hass.states.get(entity_id)
        if current is not None and current.state == target:
            return True
        fut: asyncio.Future[bool] = self.hass.loop.create_future()

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            new = event.data["new_state"]
            if new is not None and new.state == target and not fut.done():
                fut.set_result(True)

        unsub = async_track_state_change_event(self.hass, [entity_id], _changed)
        try:
            await asyncio.wait_for(fut, timeout=float(self.opt(CONF_TOOL_TIMEOUT) or 15))
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            unsub()

    async def _tool_enter(self, ids: dict[str, str], folder: str, expect_path: str) -> bool:
        await self.hass.services.async_call("text", "set_value", {"entity_id": ids["name"], "value": folder}, blocking=True)
        await self.hass.services.async_call("button", "press", {"entity_id": ids["enter"]}, blocking=True)
        return await self._wait_state(ids["path"], expect_path)

    # ------------------------------------------------------------- Vorbereiten
    async def async_prepare(self, kennung: str) -> dict[str, Any]:
        """Entspricht dem frueheren Skript 'Aufnahme Vorbereitung'."""
        async with self._lock:
            return await self._prepare(self.partner(kennung))

    async def _prepare(self, p: PartnerCfg) -> dict[str, Any]:
        s = self.state_of(p.kennung)
        hints: list[str] = []
        self.data["active"] = p.kennung
        base_win, base_unix = self.opt(CONF_BASE_WIN), self.opt(CONF_BASE_UNIX)
        ordner = logic.partner_folder(self.opt(CONF_FOLDER_PREFIX), p.anzeige, p.ordner_nr)
        datum = dt_util.now().strftime("%d,%m,%Y")

        # 1) Ordner-Werkzeug: Spielpartner-Ordner, neue Saison pruefen, Saison-Ordner
        neuer_tag = False
        tool_status = "nicht verfuegbar (Ordner wurde NICHT angelegt)"
        ids = self._tool_ids()
        if self._tool_available():
            await self.hass.services.async_call("button", "press", {"entity_id": ids["base"]}, blocking=True)
            await self._wait_state(ids["path"], base_win)
            if not await self._tool_enter(ids, ordner, logic.join_win(base_win, ordner)):
                hints.append("Spielpartner-Ordner: Zeitueberschreitung beim Wechseln")
            sel = self.hass.states.get(ids["select"])
            existing = list(sel.attributes.get("options") or []) if sel else []
            neuer_tag = logic.is_new_day(existing, logic.season_folder(s["saison"], datum))
            if neuer_tag:
                s["saison"] += 1
                s["aufnahmen"] = COUNTER_START
            saison_ordner = logic.season_folder(s["saison"], datum)
            if not await self._tool_enter(ids, saison_ordner, logic.join_win(base_win, ordner, saison_ordner)):
                hints.append("Saison-Ordner: Zeitueberschreitung beim Wechseln")
            st = self.hass.states.get(ids["status"]) if ids["status"] else None
            tool_status = st.state if st else "ok"
        else:
            hints.append(
                "Ordner-Werkzeug nicht erreichbar - Ordner nicht angelegt, Saisonwechsel nicht geprueft"
            )
            saison_ordner = logic.season_folder(s["saison"], datum)

        pfad = logic.join_unix(base_unix, ordner, saison_ordner)
        s["pfad"] = pfad

        # 2) OBS
        n_pfad, err_pfad = await self._apply_path(pfad)
        n_fmt, err_fmt, ohne = await self._apply_formats(p.kennung)
        if n_pfad == 0:
            hints.append("Kein OBS-Filter erreichbar - laeuft OBS? Pfad/Dateiformat wurden NICHT gesetzt")
        hints += err_pfad + err_fmt
        if ohne:
            hints.append("Filter ohne Cam-Kuerzel (Pfad gesetzt, Dateiformat nicht): " + ", ".join(ohne))

        # 3) Discord
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
            "obs_pfad_gesetzt": n_pfad,
            "obs_format_gesetzt": n_fmt,
            "discord": discord_status,
            "hinweise": hints,
        }
        self._set_status(f"{p.anzeige}: vorbereitet ({'neue Saison' if neuer_tag else 'gleiche Saison'})")
        self._save_later()
        self.notify()
        self._notification(p, result, tool_status, ohne)
        return result

    def _notification(self, p: PartnerCfg, r: dict[str, Any], tool_status: str, ohne: list[str]) -> None:
        lines = [
            f"Ordner: {r['ordner']}",
            f"Ordner-Werkzeug-Status: {tool_status}",
            f"Dateiformat: {r['dateiformat']}",
            f"OBS: Pfad bei {r['obs_pfad_gesetzt']} Filtern, Dateiformat bei {r['obs_format_gesetzt']} Filtern gesetzt.",
            f"Saison {logic.pad(r['saison'])}, Aufnahme {logic.pad(r['aufnahme_in_saison'])} dieser Saison, "
            f"{logic.pad(r['gesamt'])} insgesamt.",
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
        """Statusbeitrag mit Video-IDs, Schaukel-Position und Schnappschuessen."""
        p = self.partner(kennung) if kennung else self.active
        if p is None:
            raise ServiceValidationError("Kein aktiver Spielpartner")
        s = self.state_of(p.kennung)
        client = self._discord()
        if client is None or not s["thread_id"]:
            persistent_notification.async_create(
                self.hass,
                f"Fuer {p.anzeige} gibt es keinen aktuellen Saison-Thread. Bitte zuerst 'Aufnahme vorbereiten' ausfuehren.",
                title="Kein Discord-Thread gefunden",
                notification_id=f"{DOMAIN}_kein_thread_{p.kennung}",
            )
            return {"gepostet": False}
        lines, images = [], []
        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
        for cam in self.cams:
            if not self.cam_filters(cam, only_on=True):
                continue
            lines.append(f"{cam.name}: {self.format_for(p.kennung, cam)}")
            if cam.camera_entity:
                try:
                    img = await async_get_image(self.hass, cam.camera_entity)
                    ext = "png" if "png" in (img.content_type or "") else "jpg"
                    images.append((f"{cam.name}_{stamp}.{ext}", img.content, img.content_type or "image/jpeg"))
                except HomeAssistantError as err:
                    _LOGGER.warning("Schnappschuss von %s fehlgeschlagen: %s", cam.camera_entity, err)
        swing = None
        swing_entity = self.opt(CONF_SWING_ENTITY)
        if swing_entity and (st := self.hass.states.get(swing_entity)):
            swing = st.attributes.get("current_position", st.state)
        text = logic.build_post_text(int(self.opt(CONF_POST_DELAY) or 5), swing, lines)
        try:
            await client.post_message(s["thread_id"], text, images)
        except DiscordError as err:
            _LOGGER.error("Discord-Beitrag fehlgeschlagen: %s", err)
            self._set_status(f"Discord-Beitrag fehlgeschlagen: {err}")
            self.notify()
            return {"gepostet": False, "fehler": str(err)}
        self._set_status(f"{p.anzeige}: Statusbeitrag gepostet ({len(images)} Bilder)")
        self.notify()
        return {"gepostet": True, "bilder": len(images), "zeilen": lines}

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
        try:
            await self._apply_formats(p.kennung)
        except HomeAssistantError as err:
            _LOGGER.warning("Dateiformat konnte nach dem Zaehlen nicht gesetzt werden: %s", err)

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
        if self.data.get("active") == p.kennung:
            try:
                await self._apply_formats(p.kennung)
            except HomeAssistantError as err:
                _LOGGER.warning("Dateiformat konnte nicht aktualisiert werden: %s", err)

    # --------------------------------------------------------- Aufnahme-Ereignis
    @callback
    def _recording_changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        if old.state == STATE_OFF and new.state == STATE_ON:
            if self._post_cancel:
                self._post_cancel()
            delay = int(self.opt(CONF_POST_DELAY) or 5) * 60
            self._post_cancel = async_call_later(self.hass, delay, self._post_due)
        elif old.state == STATE_ON and new.state == STATE_OFF:
            if self._post_cancel:
                self._post_cancel()
                self._post_cancel = None
            if self.active is not None:
                self.hass.async_create_task(self.async_count_recording())

    async def _post_due(self, _now: datetime) -> None:
        self._post_cancel = None
        if self.active is not None:
            try:
                await self.async_post_update()
            except HomeAssistantError as err:
                _LOGGER.error("Statusbeitrag fehlgeschlagen: %s", err)
