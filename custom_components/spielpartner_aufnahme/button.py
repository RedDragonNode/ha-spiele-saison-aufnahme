"""Button 'Aufnahme vorbereiten' je Spielpartner."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpielpartnerConfigEntry
from .const import SUBENTRY_PARTNER
from .entity import SpielpartnerEntity, partner_device
from .manager import PartnerCfg, SpielpartnerManager


async def async_setup_entry(
    hass: HomeAssistant, entry: SpielpartnerConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    m = entry.runtime_data
    for sid, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_PARTNER:
            async_add_entities([PrepareButton(m, m.partners[sub.data["kennung"]])], config_subentry_id=sid)


class PrepareButton(SpielpartnerEntity, ButtonEntity):
    _attr_translation_key = "vorbereiten"
    _attr_icon = "mdi:video-plus"

    def __init__(self, m: SpielpartnerManager, p: PartnerCfg) -> None:
        super().__init__(m)
        self.partner = p
        self._attr_unique_id = f"{m.entry.entry_id}_{p.kennung}_vorbereiten"
        self._attr_device_info = partner_device(m, p)

    async def async_press(self) -> None:
        await self.manager.async_prepare(self.partner.kennung)
