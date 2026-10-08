"""Spielpartner Aufnahme: Spielpartner, Cams, Zaehler, OBS-Dateinamen und Discord an einem Ort."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_APPLY_FORMATS,
    SERVICE_COUNT,
    SERVICE_POST,
    SERVICE_PREPARE,
    SERVICE_SET_COUNTERS,
)
from .manager import SpielpartnerManager

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type SpielpartnerConfigEntry = ConfigEntry[SpielpartnerManager]

_PARTNER = vol.Required("spielpartner")
_OPT_PARTNER = vol.Optional("spielpartner")
_COUNTER = vol.All(vol.Coerce(int), vol.Range(min=0, max=9999))


def _manager(hass: HomeAssistant) -> SpielpartnerManager:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if getattr(entry, "runtime_data", None) is not None:
            return entry.runtime_data
    raise ServiceValidationError("Spielpartner Aufnahme ist nicht eingerichtet oder nicht geladen")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def prepare(call: ServiceCall) -> dict:
        return await _manager(hass).async_prepare(call.data["spielpartner"])

    async def set_counters(call: ServiceCall) -> None:
        await _manager(hass).async_set_counters(
            call.data["spielpartner"], call.data.get("saison"), call.data.get("aufnahmen_in_saison"), call.data.get("gesamt")
        )

    async def count(call: ServiceCall) -> None:
        await _manager(hass).async_count_recording(call.data.get("spielpartner"))

    async def post(call: ServiceCall) -> dict:
        return await _manager(hass).async_post_update(call.data.get("spielpartner"))

    async def apply_formats(call: ServiceCall) -> dict:
        return await _manager(hass).async_apply_formats(call.data.get("spielpartner"))

    hass.services.async_register(
        DOMAIN, SERVICE_PREPARE, prepare, vol.Schema({_PARTNER: cv.string}), supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_COUNTERS,
        set_counters,
        vol.Schema(
            {
                _PARTNER: cv.string,
                vol.Optional("saison"): _COUNTER,
                vol.Optional("aufnahmen_in_saison"): _COUNTER,
                vol.Optional("gesamt"): _COUNTER,
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_COUNT, count, vol.Schema({_OPT_PARTNER: cv.string}))
    hass.services.async_register(
        DOMAIN, SERVICE_POST, post, vol.Schema({_OPT_PARTNER: cv.string}), supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_FORMATS,
        apply_formats,
        vol.Schema({_OPT_PARTNER: cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SpielpartnerConfigEntry) -> bool:
    manager = SpielpartnerManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Spielpartner Aufnahme",
        manufacturer="RedDragonNode",
        model="Aufnahme-Verwaltung",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    manager.async_start()
    entry.async_on_unload(entry.add_update_listener(_reload_on_change))
    return True


async def _reload_on_change(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Spielpartner/Cams oder Einstellungen wurden geaendert -> neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SpielpartnerConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok
