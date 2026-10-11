"""Einmalige Uebernahme der Cams und Profile (bis 0.5.x hier angelegt) nach 'Cam Recorder Profile'.

Die Subentry-IDs bleiben gleich: sie sind die Cam-IDs im Recorder und werden von den Profilen als Verweis benutzt.
Hier bleiben nur die Discord-Zusaetze einer Cam (Verweis ``cam_id``).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CAM_CAMERA,
    CONF_CAM_ID,
    CONF_CAM_KUERZEL,
    CONF_CAM_NAME,
    CONF_CAM_POST,
    CONF_CAM_RECORD,
    CONF_CAM_RTSP,
    CONF_CAM_STREAM,
    CONF_RECORDER_KEY,
    CONF_RECORDER_URL,
    DOMAIN,
    HUB_SUBENTRY_CAM,
    OLD_RECORDER_URL,
    SUBENTRY_CAM,
    SUBENTRY_PROFILE,
)

_LOGGER = logging.getLogger(__name__)
HUB_CAM_KEYS = (CONF_CAM_NAME, CONF_CAM_KUERZEL, CONF_CAM_RECORD, CONF_CAM_STREAM, CONF_CAM_RTSP)


def needs_migration(entry: ConfigEntry) -> bool:
    return any(
        (s.subentry_type == SUBENTRY_CAM and CONF_CAM_ID not in s.data) or s.subentry_type == SUBENTRY_PROFILE
        for s in entry.subentries.values()
    )


def _add_to_hub(hass: HomeAssistant, hub: ConfigEntry, sid: str, sub: ConfigSubentry, data: dict[str, Any]) -> None:
    hass.config_entries.async_add_subentry(
        hub,
        ConfigSubentry(data=data, subentry_type=sub.subentry_type, title=sub.title, unique_id=sub.unique_id, subentry_id=sid),
    )


def migrate(hass: HomeAssistant, entry: ConfigEntry, hub: ConfigEntry) -> None:
    """Cams/Profile in den Hub kopieren (nichts ueberschreiben), hier auf die Discord-Zusaetze kuerzen."""
    hub_cams = {sid: s for sid, s in hub.subentries.items() if s.subentry_type == HUB_SUBENTRY_CAM}
    by_unique = {s.unique_id: sid for sid, s in hub_cams.items() if s.unique_id}
    id_map: dict[str, str] = {}

    for sid, sub in list(entry.subentries.items()):
        if sub.subentry_type != SUBENTRY_CAM or CONF_CAM_ID in sub.data:
            continue
        d = sub.data
        if not d.get(CONF_CAM_NAME) or not d.get(CONF_CAM_KUERZEL):
            _LOGGER.warning("Cam '%s' ist unvollstaendig und wird nicht uebernommen", sub.title)
            hass.config_entries.async_remove_subentry(entry, sid)
            continue
        target = sid
        if sid not in hub_cams:
            if sub.unique_id in by_unique:
                target = by_unique[sub.unique_id]
            else:
                _add_to_hub(hass, hub, sid, sub, {k: d[k] for k in HUB_CAM_KEYS if k in d})
        id_map[sid] = target
        camera = d.get(CONF_CAM_CAMERA, "") or ""
        post = bool(d.get(CONF_CAM_POST, bool(camera)))
        if post or camera:
            hass.config_entries.async_update_subentry(
                entry, sub, data={CONF_CAM_ID: target, CONF_CAM_POST: post, CONF_CAM_CAMERA: camera}
            )
        else:  # nichts Eigenes mehr: die Cam kommt ganz aus dem Hub
            hass.config_entries.async_remove_subentry(entry, sid)

    for sid, sub in list(entry.subentries.items()):
        if sub.subentry_type != SUBENTRY_PROFILE:
            continue
        if sid not in hub.subentries and sub.data.get("name"):
            data = {**sub.data, "cams": [id_map.get(c, c) for c in sub.data.get("cams") or []]}
            _add_to_hub(hass, hub, sid, sub, data)
        hass.config_entries.async_remove_subentry(entry, sid)

    _move_recorder_options(hass, entry, hub)


def _move_recorder_options(hass: HomeAssistant, entry: ConfigEntry, hub: ConfigEntry) -> None:
    """Adresse/Schluessel gehoeren jetzt zu Cam Recorder Profile; hier nur noch, wenn bewusst abweichend."""
    url = (entry.options.get(CONF_RECORDER_URL) or "").rstrip("/")
    key = entry.options.get(CONF_RECORDER_KEY) or ""
    if not url and not key:
        return
    hub_opts = dict(hub.options)
    if key and not hub_opts.get(CONF_RECORDER_KEY):
        hub_opts[CONF_RECORDER_KEY] = key
        hass.config_entries.async_update_entry(hub, options=hub_opts)
    own = {k: v for k, v in entry.options.items() if k not in (CONF_RECORDER_URL, CONF_RECORDER_KEY)}
    if url and url != OLD_RECORDER_URL and url != hub_opts.get(CONF_RECORDER_URL, "").rstrip("/"):
        own[CONF_RECORDER_URL] = url  # eigene, abweichende Adresse behalten
        if key:
            own[CONF_RECORDER_KEY] = key
    hass.config_entries.async_update_entry(entry, options=own)


def cleanup_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entities/Geraete der frueheren Cam- und Profil-Eintraege entfernen (die Hub-Integration hat eigene)."""
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = ent.unique_id
        if f"{entry.entry_id}_prof_" in uid or (f"{entry.entry_id}_cam_" in uid and uid.endswith(("_aufnahme", "_format"))):
            ent_reg.async_remove(ent.entity_id)
    dev_reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if any(
            dom == DOMAIN and (ident.startswith((f"{entry.entry_id}_c_", f"{entry.entry_id}_prof_")))
            for dom, ident in dev.identifiers
        ):
            dev_reg.async_remove_device(dev.id)
