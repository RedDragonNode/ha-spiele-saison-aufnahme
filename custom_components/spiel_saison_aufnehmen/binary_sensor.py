"""Binaersensoren des Recorders."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpielpartnerConfigEntry
from .entity import SpielpartnerEntity, hub_device
from .manager import SpielpartnerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: SpielpartnerConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    m = entry.runtime_data
    async_add_entities([RecorderOnlineSensor(m), RecorderRunningSensor(m)])


class RecorderOnlineSensor(SpielpartnerEntity, BinarySensorEntity):
    _attr_translation_key = "recorder_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_recorder_online"
        self._attr_device_info = hub_device(m)

    @property
    def is_on(self) -> bool:
        return bool(self.manager.rec_online)

    @property
    def extra_state_attributes(self) -> dict:
        return {"version": self.manager.rec_status.get("version")}


class RecorderRunningSensor(SpielpartnerEntity, BinarySensorEntity):
    _attr_translation_key = "recorder_aufnahme"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:record-rec"

    def __init__(self, m: SpielpartnerManager) -> None:
        super().__init__(m)
        self._attr_unique_id = f"{m.entry.entry_id}_recorder_aufnahme"
        self._attr_device_info = hub_device(m)

    @property
    def is_on(self) -> bool:
        return self.manager.recorder_running

    @property
    def extra_state_attributes(self) -> dict:
        r = self.manager.data.get("recorder") or {}
        return {"seit": r.get("start"), "spielpartner": r.get("partner")}
