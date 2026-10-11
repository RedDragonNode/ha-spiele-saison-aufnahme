"""Config-Flow, Optionen und Subentries (Spielpartner / Cams)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    CONF_INIT_AUFNAHMEN,
    CONF_INIT_GESAMT,
    CONF_INIT_SAISON,
    CONF_INITIAL,
    CONF_KENNUNG,
    CONF_ORDNER_NR,
    CONF_POST_DELAY,
    CONF_POST_GAP,
    CONF_PROF_AFTER,
    CONF_PROF_CAMS,
    CONF_PROF_FOLDER,
    CONF_PROF_FROM,
    CONF_PROF_MAIN,
    CONF_PROF_MAX,
    CONF_PROF_NAME,
    CONF_PROF_PATTERN,
    CONF_PROF_SUB,
    CONF_PROF_SUN,
    CONF_PROF_TO,
    CONF_PROF_TRIGGERS,
    CONF_RECORDER_KEY,
    CONF_RECORDER_URL,
    CONF_RECORDING_ENTITY,
    CONF_SPIEL_BASE,
    CONF_SWING_ENTITY,
    DEFAULT_CAMERAS,
    DEFAULT_CAMS,
    DEFAULT_OPTIONS,
    DEFAULT_PATTERN,
    DOMAIN,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
    SUBENTRY_PROFILE,
)
from .recorder_client import RecorderClient, RecorderError

_TEXT = selector.TextSelector()
_SECRET = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _ent(*domains: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


def _num(lo: int, hi: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=lo, max=hi, step=1, mode=selector.NumberSelectorMode.BOX)
    )


def _suggest(schema: vol.Schema, values: dict[str, Any]) -> vol.Schema:
    """Vorbelegung als 'suggested_value' (Felder lassen sich so wieder leeren)."""
    return vol.Schema(
        {
            (type(k)(k.schema, default=k.default, description={"suggested_value": values.get(k.schema)}) if k.schema in values else k): v
            for k, v in schema.schema.items()
        }
    )


SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RECORDER_URL): _TEXT,
        vol.Required(CONF_RECORDER_KEY): _SECRET,
        vol.Optional(CONF_DISCORD_TOKEN): _SECRET,
        vol.Required(CONF_FOLDER_PREFIX): _TEXT,
        vol.Optional(CONF_FORMAT_SUFFIX): _TEXT,
        vol.Optional(CONF_SPIEL_BASE): _TEXT,
        vol.Optional(CONF_RECORDING_ENTITY): _ent("binary_sensor", "switch", "input_boolean"),
        vol.Required(CONF_POST_DELAY): _num(1, 120),
        vol.Optional(CONF_POST_GAP): _num(0, 300),
        vol.Optional(CONF_SWING_ENTITY): _ent("cover"),
    }
)


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in user_input.items() if v not in (None, "")}
    for key in (CONF_POST_DELAY, CONF_POST_GAP):
        if key in out:
            out[key] = int(out[key])
    return out


def _recorder_fields(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_CAM_RECORD: bool(user_input.get(CONF_CAM_RECORD, True)),
        CONF_CAM_STREAM: user_input.get(CONF_CAM_STREAM, "") or "",
        CONF_CAM_RTSP: (user_input.get(CONF_CAM_RTSP, "") or "").strip(),
    }


def _default_subentries() -> list[ConfigSubentryData]:
    return [
        ConfigSubentryData(
            subentry_type=SUBENTRY_CAM,
            title=name,
            unique_id=logic.norm(name),
            data={
                CONF_CAM_NAME: name,
                CONF_CAM_KUERZEL: kuerzel,
                CONF_CAM_CAMERA: DEFAULT_CAMERAS.get(name, ""),
                CONF_CAM_POST: name in DEFAULT_CAMERAS,
                CONF_CAM_RECORD: True,
                CONF_CAM_STREAM: "",
                CONF_CAM_RTSP: "",
            },
        )
        for name, kuerzel in DEFAULT_CAMS.items()
    ]


class SpielpartnerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Spielpartner Aufnahme",
                data={},
                options=_clean(user_input),
                subentries=_default_subentries(),
            )
        return self.async_show_form(step_id="user", data_schema=_suggest(SETTINGS_SCHEMA, DEFAULT_OPTIONS))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SpielpartnerOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_PARTNER: PartnerSubentryFlow,
            SUBENTRY_CAM: CamSubentryFlow,
            SUBENTRY_PROFILE: ProfileSubentryFlow,
        }


class SpielpartnerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_suggest(SETTINGS_SCHEMA, current))


# --------------------------------------------------------------- Spielpartner
class PartnerSubentryFlow(ConfigSubentryFlow):
    """Spielpartner anlegen / bearbeiten."""

    def _existing(self) -> dict[str, str]:
        return {
            s.data[CONF_KENNUNG]: sid
            for sid, s in self._get_entry().subentries.items()
            if s.subentry_type == SUBENTRY_PARTNER
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            kennung = user_input[CONF_KENNUNG].strip().lower()
            if not logic.valid_kennung(kennung):
                errors[CONF_KENNUNG] = "invalid_kennung"
            elif kennung in self._existing():
                errors[CONF_KENNUNG] = "already_configured"
            else:
                anzeige = (user_input.get(CONF_ANZEIGE) or logic.default_anzeige(kennung)).strip()
                initial = {
                    "saison": user_input.get(CONF_INIT_SAISON),
                    "aufnahmen": user_input.get(CONF_INIT_AUFNAHMEN),
                    "gesamt": user_input.get(CONF_INIT_GESAMT),
                }
                data = {
                    CONF_KENNUNG: kennung,
                    CONF_ANZEIGE: anzeige,
                    CONF_ORDNER_NR: int(user_input.get(CONF_ORDNER_NR) or 1),
                    CONF_FORUM_ID: str(user_input.get(CONF_FORUM_ID) or "").strip(),
                    CONF_INITIAL: {k: v for k, v in initial.items() if v not in (None, "")},
                }
                return self.async_create_entry(title=anzeige, data=data, unique_id=kennung)
        schema = vol.Schema(
            {
                vol.Required(CONF_KENNUNG): _TEXT,
                vol.Optional(CONF_ANZEIGE): _TEXT,
                vol.Optional(CONF_ORDNER_NR): _num(1, 99),
                vol.Optional(CONF_FORUM_ID): _TEXT,
                vol.Optional(CONF_INIT_SAISON): _num(1, 999),
                vol.Optional(CONF_INIT_AUFNAHMEN): _num(1, 9999),
                vol.Optional(CONF_INIT_GESAMT): _num(1, 9999),
            }
        )
        return self.async_show_form(step_id="user", data_schema=_suggest(schema, user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        if user_input is not None:
            data = {
                **sub.data,
                CONF_ANZEIGE: (user_input.get(CONF_ANZEIGE) or sub.data[CONF_ANZEIGE]).strip(),
                CONF_ORDNER_NR: int(user_input[CONF_ORDNER_NR]),
                CONF_FORUM_ID: str(user_input.get(CONF_FORUM_ID) or "").strip(),
            }
            return self.async_update_and_abort(
                self._get_entry(), sub, title=data[CONF_ANZEIGE], data=data
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_ANZEIGE): _TEXT,
                vol.Required(CONF_ORDNER_NR): _num(1, 99),
                vol.Optional(CONF_FORUM_ID): _TEXT,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=_suggest(schema, dict(sub.data)))


# ----------------------------------------------------------------------- Cams
class CamSubentryFlow(ConfigSubentryFlow):
    """Cam mit Kuerzel anlegen / bearbeiten."""

    @staticmethod
    def _schema(with_name: bool, post_default: bool = False) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if with_name:
            fields[vol.Required(CONF_CAM_NAME)] = _TEXT
        fields[vol.Required(CONF_CAM_KUERZEL)] = _TEXT
        fields[vol.Optional(CONF_CAM_POST, default=post_default)] = selector.BooleanSelector()
        fields[vol.Optional(CONF_CAM_CAMERA)] = _ent("camera")
        fields[vol.Optional(CONF_CAM_RECORD, default=True)] = selector.BooleanSelector()
        fields[vol.Optional(CONF_CAM_STREAM)] = _ent("camera")
        fields[vol.Optional(CONF_CAM_RTSP)] = _SECRET
        return vol.Schema(fields)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_CAM_NAME].strip()
            taken = {
                logic.norm(s.data[CONF_CAM_NAME])
                for s in self._get_entry().subentries.values()
                if s.subentry_type == SUBENTRY_CAM
            }
            if logic.norm(name) in taken:
                errors[CONF_CAM_NAME] = "already_configured"
            elif not user_input[CONF_CAM_KUERZEL].strip():
                errors[CONF_CAM_KUERZEL] = "kuerzel_required"
            else:
                data = {
                    CONF_CAM_NAME: name,
                    CONF_CAM_KUERZEL: user_input[CONF_CAM_KUERZEL].strip(),
                    CONF_CAM_CAMERA: user_input.get(CONF_CAM_CAMERA, "") or "",
                    CONF_CAM_POST: bool(user_input.get(CONF_CAM_POST, False)),
                    **_recorder_fields(user_input),
                }
                return self.async_create_entry(title=name, data=data, unique_id=logic.norm(name))
        return self.async_show_form(
            step_id="user", data_schema=_suggest(self._schema(True), user_input or {}), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CAM_KUERZEL].strip():
                errors[CONF_CAM_KUERZEL] = "kuerzel_required"
            else:
                data = {k: v for k, v in sub.data.items() if k != "filter_entity"}
                data.update(
                    {
                        CONF_CAM_KUERZEL: user_input[CONF_CAM_KUERZEL].strip(),
                        CONF_CAM_CAMERA: user_input.get(CONF_CAM_CAMERA, "") or "",
                        CONF_CAM_POST: bool(user_input.get(CONF_CAM_POST, False)),
                        **_recorder_fields(user_input),
                    }
                )
                return self.async_update_and_abort(self._get_entry(), sub, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_suggest(
                self._schema(False, bool(sub.data.get(CONF_CAM_POST, bool(sub.data.get(CONF_CAM_CAMERA))))),
                user_input or dict(sub.data),
            ),
            errors=errors,
        )


# ------------------------------------------------------------------- Profile
def _folder_select(options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=o, label=o) for o in options],
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


class ProfileSubentryFlow(ConfigSubentryFlow):
    """Aufnahme-Profil: wohin, welche Cams, welcher Ausloeser (Schritt 1 Hauptordner, Schritt 2 Unterordner)."""

    _pending: dict[str, Any]
    _own: str | None = None

    async def _dirs(self, parts: list[str]) -> list[str]:
        """Ordner aus dem Recorder (leer, wenn er nicht erreichbar ist - Eingabe von Hand bleibt moeglich)."""
        opts = self._get_entry().options
        url, key = opts.get(CONF_RECORDER_URL), opts.get(CONF_RECORDER_KEY)
        if not url or not key:
            return []
        try:
            return await RecorderClient(async_get_clientsession(self.hass), url, key).list_dirs(parts)
        except RecorderError:
            return []

    def _schema(self, main_options: list[str]) -> vol.Schema:
        cams = [
            selector.SelectOptionDict(value=sid, label=s.data[CONF_CAM_NAME])
            for sid, s in sorted(self._get_entry().subentries.items(), key=lambda kv: logic.norm(kv[1].data.get(CONF_CAM_NAME, "")))
            if s.subentry_type == SUBENTRY_CAM
        ]
        return vol.Schema(
            {
                vol.Required(CONF_PROF_NAME): _TEXT,
                vol.Required(CONF_PROF_MAIN): _folder_select(main_options),
                vol.Required(CONF_PROF_CAMS): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=cams, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_PROF_PATTERN, default=DEFAULT_PATTERN): _TEXT,
                vol.Optional(CONF_PROF_TRIGGERS): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "switch", "input_boolean", "sensor"], multiple=True
                    )
                ),
                vol.Optional(CONF_PROF_AFTER): _num(0, 3600),
                vol.Optional(CONF_PROF_MAX): _num(0, 1440),
                vol.Optional(CONF_PROF_FROM): selector.TimeSelector(),
                vol.Optional(CONF_PROF_TO): selector.TimeSelector(),
                vol.Optional(CONF_PROF_SUN): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="", label="egal"),
                            selector.SelectOptionDict(value="tag", label="nur bei Tag (Sonne über dem Horizont)"),
                            selector.SelectOptionDict(value="nacht", label="nur bei Nacht (Sonne unter dem Horizont)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    @staticmethod
    def _data(user_input: dict[str, Any]) -> dict[str, Any]:
        main = logic.split_path(user_input.get(CONF_PROF_MAIN, ""))
        return {
            CONF_PROF_NAME: user_input[CONF_PROF_NAME].strip(),
            CONF_PROF_FOLDER: "/".join(main),
            CONF_PROF_CAMS: list(user_input.get(CONF_PROF_CAMS) or []),
            CONF_PROF_PATTERN: (user_input.get(CONF_PROF_PATTERN) or DEFAULT_PATTERN).strip(),
            CONF_PROF_TRIGGERS: list(user_input.get(CONF_PROF_TRIGGERS) or []),
            CONF_PROF_AFTER: int(user_input.get(CONF_PROF_AFTER) or 0),
            CONF_PROF_MAX: int(user_input.get(CONF_PROF_MAX) or 0),
            CONF_PROF_FROM: user_input.get(CONF_PROF_FROM) or "",
            CONF_PROF_TO: user_input.get(CONF_PROF_TO) or "",
            CONF_PROF_SUN: user_input.get(CONF_PROF_SUN) or "",
        }

    def _errors(self, data: dict[str, Any], own: str | None) -> dict[str, str]:
        errors: dict[str, str] = {}
        taken = {
            logic.norm(s.data[CONF_PROF_NAME])
            for sid, s in self._get_entry().subentries.items()
            if s.subentry_type == SUBENTRY_PROFILE and sid != own
        }
        if not data[CONF_PROF_NAME] or logic.norm(data[CONF_PROF_NAME]) in taken:
            errors[CONF_PROF_NAME] = "already_configured"
        if not data[CONF_PROF_FOLDER]:
            errors[CONF_PROF_MAIN] = "folder_required"
        if not data[CONF_PROF_CAMS]:
            errors[CONF_PROF_CAMS] = "cams_required"
        if bool(data[CONF_PROF_FROM]) != bool(data[CONF_PROF_TO]):
            errors[CONF_PROF_TO] = "time_both"
        return errors

    async def _step_one(self, step_id: str, user_input: dict[str, Any] | None, current: dict[str, Any]) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = self._data(user_input)
            errors = self._errors(data, self._own)
            if not errors:
                self._pending = data
                return await self.async_step_unterordner()
        main_options = await self._dirs([])
        return self.async_show_form(
            step_id=step_id, data_schema=_suggest(self._schema(main_options), user_input or current), errors=errors
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._own = None
        return await self._step_one("user", user_input, {})

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        self._own = sub.subentry_id
        parts = logic.split_path(sub.data.get(CONF_PROF_FOLDER, ""))
        current = {**sub.data, CONF_PROF_MAIN: parts[0] if parts else ""}
        return await self._step_one("reconfigure", user_input, current)

    async def async_step_unterordner(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        main = logic.split_path(self._pending[CONF_PROF_FOLDER])
        if user_input is not None:
            sub = logic.split_path(user_input.get(CONF_PROF_SUB, ""))
            data = {**self._pending, CONF_PROF_FOLDER: "/".join([*main, *sub])}
            if self._own is None:
                return self.async_create_entry(title=data[CONF_PROF_NAME], data=data, unique_id=logic.norm(data[CONF_PROF_NAME]))
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), title=data[CONF_PROF_NAME], data=data
            )
        existing = logic.split_path(self._get_reconfigure_subentry().data.get(CONF_PROF_FOLDER, "")) if self._own else []
        suggested = "/".join(existing[1:]) if existing[:1] == main[:1] else ""
        schema = vol.Schema({vol.Optional(CONF_PROF_SUB): _folder_select(await self._dirs(main))})
        return self.async_show_form(
            step_id="unterordner",
            data_schema=_suggest(schema, {CONF_PROF_SUB: suggested}),
            description_placeholders={"hauptordner": "/".join(main)},
        )
