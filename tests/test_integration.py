"""Integration + Recorder-Add-on (Add-on ist durch einen Fake ersetzt)."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from custom_components.spiel_saison_aufnehmen.const import (
    DOMAIN,
    HUB_DOMAIN,
    HUB_SIGNAL,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)
from custom_components.spiel_saison_aufnehmen.recorder_client import RecorderError

BASE = {
    "ordner_praefix": "Spielen mit",
    "dateiformat_endung": " (4K) %DD.%MM.%CCYY",
    "aufnahme_entity": "binary_sensor.rec",
    "recorder_url": "http://addon:8099",
    "recorder_schluessel": "geheimgeheim123",
    "post_nach_minuten": 5,
}


class FakeRecorder:
    """Ersatz fuer RecorderClient."""

    dirs: dict[str, list[str]] = {}
    running = False
    calls: list = []
    fail = False
    stop_reason = ""

    def __init__(self, *_a, **_k):
        pass

    def _chk(self):
        if FakeRecorder.fail:
            raise RecorderError("Recorder-Add-on nicht erreichbar (test)")

    async def status(self):
        self._chk()
        return {
            "aufnahme": FakeRecorder.running,
            "stop_grund": FakeRecorder.stop_reason,
            "wurzel": "/media/aufnahmen",
            "speicher": {"frei_gb": 2500.0, "gesamt_gb": 3000.0},
            "version": "0.2.0",
            "kameras": {},
        }

    async def list_dirs(self, path):
        self._chk()
        return FakeRecorder.dirs.get("/".join(path), [])

    async def make_dirs(self, path):
        self._chk()
        FakeRecorder.dirs.setdefault("/".join(path[:-1]), [])
        if len(path) > 1 and path[-1] not in FakeRecorder.dirs["/".join(path[:-1])]:
            FakeRecorder.dirs["/".join(path[:-1])].append(path[-1])
        return "/".join(path)

    async def start(self, path, cams, session, profile=None):
        self._chk()
        FakeRecorder.calls.append(("start", path, cams, session))
        FakeRecorder.running = True
        return {}

    async def stop(self, profile=None):
        self._chk()
        FakeRecorder.calls.append(("stop",))
        FakeRecorder.running = False
        return {}


@pytest.fixture(autouse=True)
def fake_recorder():
    FakeRecorder.dirs, FakeRecorder.running, FakeRecorder.calls = {}, False, []
    FakeRecorder.fail, FakeRecorder.stop_reason = False, ""
    with patch("custom_components.spiel_saison_aufnehmen.manager.RecorderClient", FakeRecorder):
        yield


CAM_KUERZEL = {
    "Bauleitung": "BL", "Baumeister": "BM", "Faehrtensucher": "FS", "Fellnah": "FN", "Fuchsblick": "FB",
    "Hoelenblick": "HB", "Kesselcam": "KC", "Nachtstreife": "NS", "Ohrenspitze": "OS", "Pfotenabdruck": "PD",
    "Rotpelz": "RP", "Rudelblick": "RB", "Schnauzencam": "sc", "Schweifwedler": "SW", "Unterbau": "UB", "Wildspur": "WS",
}


def _hub_cams() -> list[ConfigSubentryData]:
    """Cams so, wie 'Cam Recorder Profile' sie ablegt."""
    out = []
    for name, kuerzel in CAM_KUERZEL.items():
        data = {"name": name, "kuerzel": kuerzel, "aufnehmen": True, "stream_entity": "", "rtsp_url": ""}
        if name == "Fuchsblick":
            data["rtsp_url"] = "rtsp://u:p@192.168.1.11:554/main"
        elif name == "Kesselcam":
            data["stream_entity"] = "camera.kessel"
        elif name == "Rotpelz":
            data.update(aufnehmen=False, rtsp_url="rtsp://x/y")
        out.append(ConfigSubentryData(subentry_type="cam", title=name, unique_id=name.lower(), subentry_id="cam_" + name, data=data))
    return out


def _add_hub(hass: HomeAssistant, cams: list[ConfigSubentryData] | None = None, options: dict | None = None) -> MockConfigEntry:
    mock_integration(hass, MockModule(HUB_DOMAIN, async_setup_entry=AsyncMock(return_value=True)))
    hub = MockConfigEntry(
        domain=HUB_DOMAIN, data={}, options=options or {}, subentries_data=_hub_cams() if cams is None else cams, unique_id=HUB_DOMAIN
    )
    hub.add_to_hass(hass)
    return hub


def _partner() -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type=SUBENTRY_PARTNER,
        title="Frank",
        unique_id="frank_visselff",
        data={"kennung": "frank_visselff", "anzeige": "Frank", "ordner_nr": 1, "forum_id": "",
              "initial": {"saison": 2, "aufnahmen": 3, "gesamt": 14}},
    )


def _discord_cams() -> list[ConfigSubentryData]:
    return [
        ConfigSubentryData(
            subentry_type=SUBENTRY_CAM,
            title=f"Discord {name}",
            unique_id="cam_" + name,
            data={"cam_id": "cam_" + name, "discord_posten": True, "kamera_entity": f"camera.{name.lower()}_hd"},
        )
        for name in ("Fuchsblick", "Hoelenblick")
    ]


async def _setup(hass: HomeAssistant, **extra) -> MockConfigEntry:
    _add_hub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={**BASE, **extra}, subentries_data=[_partner(), *_discord_cams()], unique_id=DOMAIN
    )
    entry.add_to_hass(hass)
    hass.states.async_set("binary_sensor.rec", "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _stream_patch():
    return patch(
        "custom_components.spiel_saison_aufnehmen.manager.async_get_stream_source",
        AsyncMock(return_value="rtsp://k:k@192.168.1.12/stream"),
    )


async def test_prepare_creates_folders(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    r = await m.async_prepare("frank_visselff")
    heute = dt_util.now().strftime("%d,%m,%Y")
    assert FakeRecorder.dirs["Spielen mit Frank #01"] == [f"Saison 02 vom {heute}"]
    assert r["ordner"] == f"/media/aufnahmen/Spielen mit Frank #01/Saison 02 vom {heute}"
    assert m.state_of("frank_visselff")["rec_rel"] == ["Spielen mit Frank #01", f"Saison 02 vom {heute}"]
    assert not r["hinweise"]


async def test_new_season_detected_via_recorder(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    FakeRecorder.dirs["Spielen mit Frank #01"] = ["Saison 02 vom 01,01,2026"]
    r = await entry.runtime_data.async_prepare("frank_visselff")
    assert r["neue_saison"] and r["saison"] == 3 and r["aufnahme_in_saison"] == 1
    r = await entry.runtime_data.async_prepare("frank_visselff")  # selber Tag: Ordner existiert jetzt
    assert not r["neue_saison"] and r["saison"] == 3


async def test_start_stop_service_counts_once_and_names_files(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with _stream_patch():
        res = await hass.services.async_call(DOMAIN, "recorder_starten", {}, blocking=True, return_response=True)
    assert res["gestartet"] and set(res["cams"]) == {"Fuchsblick", "Kesselcam"}
    assert "Rotpelz" not in res["cams"] and "Bauleitung" in res["ohne_stream"]
    _, rel, cams, session = FakeRecorder.calls[0]
    heute = dt_util.now()
    stem = next(c["stem"] for c in cams if c["name"] == "Fuchsblick")
    assert stem == f"#01.02.03.FB.14 (4K) {heute:%d.%m.%Y}" and "%" not in stem
    assert next(c["url"] for c in cams if c["name"] == "Fuchsblick") == "rtsp://u:p@192.168.1.11:554/main"
    assert next(c["url"] for c in cams if c["name"] == "Kesselcam").startswith("rtsp://k:k@")
    assert session == "#01.02.03 Sitzung"
    assert hass.states.get("binary_sensor.spiel_saison_aufnehmen_recorder_recording").state == "on"
    again = await m.async_recorder_start()
    assert again["gestartet"] is False  # idempotent
    await hass.services.async_call(DOMAIN, "recorder_stoppen", {}, blocking=True)
    s = m.state_of("frank_visselff")
    assert (s["aufnahmen"], s["gesamt"]) == (4, 15)
    await m.async_recorder_stop()  # zweites Stoppen zaehlt nicht nochmal
    assert (s["aufnahmen"], s["gesamt"]) == (4, 15)
    assert hass.states.get("binary_sensor.spiel_saison_aufnehmen_recorder_recording").state == "off"


async def test_start_requires_active_partner_and_prepare(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    with pytest.raises(ServiceValidationError):  # kein aktiver Partner
        await m.async_recorder_start()
    m.data["active"] = "frank_visselff"
    with pytest.raises(ServiceValidationError):  # nie vorbereitet -> kein Recorder-Ordner
        await m.async_recorder_start()


async def test_unreachable_addon_does_not_mark_running(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    FakeRecorder.fail = True
    with _stream_patch(), pytest.raises(RecorderError):
        await m.async_recorder_start()
    assert not m.recorder_running
    assert m._rec_active is False


async def test_trigger_entity_starts_and_stops(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with _stream_patch():
        hass.states.async_set("binary_sensor.rec", "on")
        await hass.async_block_till_done()
    assert FakeRecorder.running
    hass.states.async_set("binary_sensor.rec", "off")
    await hass.async_block_till_done()
    assert not FakeRecorder.running
    assert m.state_of("frank_visselff")["gesamt"] == 15


async def test_no_trigger_entity_means_no_auto_start(hass: HomeAssistant) -> None:
    entry = await _setup(hass, aufnahme_entity="")
    await entry.runtime_data.async_prepare("frank_visselff")
    hass.states.async_set("binary_sensor.rec", "on")
    await hass.async_block_till_done()
    assert not FakeRecorder.running


async def test_lost_recording_is_counted_once_with_reason(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with _stream_patch():
        await m.async_recorder_start()
    FakeRecorder.running, FakeRecorder.stop_reason = False, "speicher_voll"  # Add-on hat selbst beendet
    await m._poll_recorder(None)
    await m._poll_recorder(None)
    assert not m.recorder_running
    assert m.state_of("frank_visselff")["gesamt"] == 15
    assert "speicher_voll" in m.data["status"]["text"]


async def test_reattach_after_restart(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with _stream_patch():
        await m.async_recorder_start()
    await m._store.async_save(m.data)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    m2 = entry.runtime_data
    assert m2.recorder_running and m2._rec_active  # Aufnahme laeuft weiter, wieder verbunden
    await m2.async_recorder_stop()
    assert m2.state_of("frank_visselff")["gesamt"] == 15


async def test_discord_subentry_flow_and_reconfigure(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_CAM), context={"source": "user"})
    assert flow["type"] == "form"
    offered = {o["value"] for o in flow["data_schema"].schema["cam_id"].config["options"]}
    assert "cam_Kesselcam" in offered and "cam_Fuchsblick" not in offered  # Fuchsblick hat schon einen Zusatz
    done = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"cam_id": "cam_Kesselcam", "discord_posten": True, "kamera_entity": "camera.kessel_hd"}
    )
    assert done["type"] == "create_entry"
    await hass.async_block_till_done()
    cam = next(c for c in entry.runtime_data.cams if c.name == "Kesselcam")
    assert cam.post and cam.camera_entity == "camera.kessel_hd"
    sid = next(i for i, s in entry.subentries.items() if s.data.get("cam_id") == "cam_Kesselcam")
    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_CAM), context={"source": "reconfigure", "subentry_id": sid}
    )
    assert "name" not in {str(k) for k in flow["data_schema"].schema}  # Name/Stream gehoeren dem Hub
    done = await hass.config_entries.subentries.async_configure(flow["flow_id"], {"discord_posten": False})
    assert done["type"] == "abort"
    assert entry.subentries[sid].data["discord_posten"] is False

async def test_setup_and_entities(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass)
    ids = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    for key in ("saison", "aufnahmen_in_saison", "gesamt", "vorbereiten", "dateiformat", "speicher_adresse"):
        assert f"{entry.entry_id}_frank_visselff_{key}" in ids
    assert sum(1 for i in ids if "_camfmt_" in i) == 16  # eine pro Cam aus dem Hub
    assert not any("_prof_" in i for i in ids)
    m = entry.runtime_data
    assert m.format_for("frank_visselff", None) == "#01.02.03.Cam ID.14 (4K) %DD.%MM.%CCYY"
    assert not hass.services.has_service(DOMAIN, "dateiformat_anwenden")
    assert not hass.services.has_service(DOMAIN, "profil_starten")

async def test_discord_post_sequence(hass: HomeAssistant) -> None:
    entry = await _setup(hass, post_abstand_sekunden=0)
    m = entry.runtime_data
    m.data["active"] = "frank_visselff"
    m.state_of("frank_visselff")["thread_id"] = "99"
    posted = []

    class FakeImg:
        content = b"jpg"
        content_type = "image/jpeg"

    class FakeClient:
        async def post_message(self, channel, text, images=None):
            posted.append((channel, text, images))

    with patch.object(m, "_discord", return_value=FakeClient()), patch(
        "custom_components.spiel_saison_aufnehmen.manager.async_get_image", AsyncMock(return_value=FakeImg())
    ):
        r = await m.async_post_update()
        await m._post_task
    assert r["gepostet"] and r["cams"] == ["Fuchsblick", "Hoelenblick"]
    assert posted[0][1].startswith("Aufnahme laeuft seit 5 Minuten.")
    assert posted[1][1] == "" and posted[1][2][0][0].startswith("Fuchsblick_")
    assert "#01.02.03.FB.14" in posted[2][1] and "%" not in posted[2][1]
    assert len(posted) == 5


async def test_set_counters_service_and_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.services.async_call(
        DOMAIN, "zaehler_setzen", {"spielpartner": "frank_visselff", "saison": 5, "gesamt": 100}, blocking=True
    )
    s = entry.runtime_data.state_of("frank_visselff")
    assert (s["saison"], s["aufnahmen"], s["gesamt"]) == (5, 3, 100)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_and_subentry_flow(hass: HomeAssistant) -> None:
    _add_hub(hass)
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert res["type"] == "form"
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"], {"discord_token": "", "ordner_praefix": "Spielen mit", "post_nach_minuten": 5}
    )
    assert res["type"] == "create_entry"
    entry = res["result"]
    await hass.async_block_till_done()
    assert not entry.subentries  # keine Cams hier: die liegen in Cam Recorder Profile
    assert len(entry.runtime_data.cams) == 16
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_PARTNER), context={"source": "user"})
    bad = await hass.config_entries.subentries.async_configure(flow["flow_id"], {"kennung": "Gross Klein"})
    assert bad["errors"]["kennung"] == "invalid_kennung"
    done = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"kennung": "neu_a", "anzeige": "Neu A", "ordner_nr": 7, "start_saison": 4, "start_gesamt": 21}
    )
    assert done["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.state_of("neu_a")["saison"] == 4

async def test_options_flow_reloads_and_drops_old_obs_options(hass: HomeAssistant) -> None:
    entry = await _setup(hass, basis_pfad_obs="X:/alt", werkzeug_timeout=3, modus="obs")
    res = await hass.config_entries.options.async_init(entry.entry_id)
    assert res["type"] == "form"
    res = await hass.config_entries.options.async_configure(res["flow_id"], {**BASE, "post_nach_minuten": 9})
    assert res["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["post_nach_minuten"] == 9
    assert "basis_pfad_obs" not in entry.options and "modus" not in entry.options


async def test_no_profile_button_offered(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    from custom_components.spiel_saison_aufnehmen.config_flow import (
        SpielpartnerConfigFlow,
    )

    assert set(SpielpartnerConfigFlow.async_get_supported_subentry_types(entry)) == {"spielpartner", "cam"}


async def test_broken_subentry_is_skipped_not_fatal(hass: HomeAssistant) -> None:
    _add_hub(hass)
    subs = [
        ConfigSubentryData(subentry_type=SUBENTRY_CAM, title="Waise", unique_id="waise", data={"cam_id": "gibt-es-nicht", "discord_posten": True}),
        ConfigSubentryData(subentry_type=SUBENTRY_PARTNER, title="Leer", unique_id="leer", data={}),
    ]
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=BASE, subentries_data=subs, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.cams) == 16 and not entry.runtime_data.partners

async def test_counters_imported_from_old_integration_store(hass: HomeAssistant) -> None:
    import json
    from pathlib import Path

    folder = Path(hass.config.path(".storage"))
    folder.mkdir(parents=True, exist_ok=True)
    old = {"version": 1, "key": "spielpartner_aufnahme.abc", "data": {"active": None, "partners": {
        "frank_visselff": {"saison": 5, "aufnahmen": 7, "gesamt": 42, "thread_id": "99", "thread_saison": "05", "pfad": "", "vorbereitet": None}}}}
    legacy = folder / "spielpartner_aufnahme.abc"
    legacy.write_text(json.dumps(old))
    try:
        entry = await _setup(hass)
        st = entry.runtime_data.state_of("frank_visselff")
    finally:
        legacy.unlink(missing_ok=True)
    assert (st["saison"], st["aufnahmen"], st["gesamt"], st["thread_id"]) == (5, 7, 42, "99")


# ------------------------------------------------------------- Cam Recorder Profile
def _legacy_cams() -> list[ConfigSubentryData]:
    """So lagen die Cams bis 0.5.x hier."""
    out = []
    for sub in _hub_cams():
        name = sub["data"]["name"]
        camera = {"Fuchsblick": "camera.fuchsblick_hd", "Hoelenblick": "camera.hoelenblick_hd"}.get(name, "")
        out.append({**sub, "data": {**sub["data"], "kamera_entity": camera, "discord_posten": bool(camera)}})
    return out


def _legacy_profile() -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type="profil", title="Treppe", unique_id="treppe", subentry_id="prof_treppe",
        data={"name": "Treppe", "ordner": "Ueberwachung/Treppe", "cams": ["cam_Kesselcam"], "dateimuster": "{cam}",
              "ausloeser": [], "nachlauf_sekunden": 0, "max_dauer_minuten": 0, "zeit_von": "", "zeit_bis": "", "sonne": ""},
    )


async def test_migration_moves_cams_and_profiles_to_hub(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    hub = _add_hub(hass, cams=[], options={})
    entry = MockConfigEntry(
        domain=DOMAIN, data={},
        options={**BASE, "recorder_url": "http://local-spielpartner-recorder:8099"},
        subentries_data=[_partner(), *_legacy_cams(), _legacy_profile()], unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    stale = ent_reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_cam_cam_Kesselcam_format", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hub_cams = {sid: s for sid, s in hub.subentries.items() if s.subentry_type == "cam"}
    assert len(hub_cams) == 16 and hub_cams["cam_Fuchsblick"].data["rtsp_url"].startswith("rtsp://u:p@")
    assert "prof_treppe" in hub.subentries and hub.subentries["prof_treppe"].data["cams"] == ["cam_Kesselcam"]
    # hier bleiben nur Spielpartner und die Discord-Zusaetze (Fuchsblick, Hoelenblick)
    kinds = sorted(s.subentry_type for s in entry.subentries.values())
    assert kinds == ["cam", "cam", "spielpartner"]
    assert all(set(s.data) == {"cam_id", "discord_posten", "kamera_entity"} for s in entry.subentries.values() if s.subentry_type == "cam")
    assert hub.options["recorder_schluessel"] == "geheimgeheim123"
    assert "recorder_url" not in entry.options and "recorder_schluessel" not in entry.options
    assert entry.runtime_data.opt("recorder_url") == "http://local-cam-recorder:8099"
    assert ent_reg.async_get(stale.entity_id) is None
    assert entry.runtime_data.state_of("frank_visselff")["gesamt"] == 14
    assert [c.name for c in entry.runtime_data.cams if c.post] == ["Fuchsblick", "Hoelenblick"]


async def test_migration_keeps_existing_hub_cam_and_own_recorder_address(hass: HomeAssistant) -> None:
    hub = _add_hub(hass, options={"recorder_url": "http://hub:8099", "recorder_schluessel": "hubhubhubhub"})
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={**BASE, "recorder_url": "http://anderes:8099"},
        subentries_data=[_partner(), *_legacy_cams()], unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len([s for s in hub.subentries.values() if s.subentry_type == "cam"]) == 16  # nichts doppelt
    assert hub.options["recorder_schluessel"] == "hubhubhubhub"  # Hub-Schluessel wird nicht ueberschrieben
    assert entry.options["recorder_url"] == "http://anderes:8099"  # bewusst abweichend -> bleibt


async def test_waits_for_hub_and_loses_nothing(hass: HomeAssistant) -> None:
    from homeassistant.config_entries import ConfigEntryState

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=BASE, subentries_data=[_partner(), *_legacy_cams()], unique_id=DOMAIN)
    entry.add_to_hass(hass)
    mock_integration(hass, MockModule(HUB_DOMAIN, async_setup_entry=AsyncMock(return_value=True)))
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert len(entry.subentries) == 1 + 16  # unveraendert, nichts geloescht


async def test_recorder_address_follows_hub(hass: HomeAssistant) -> None:
    _add_hub(hass, options={"recorder_url": "http://hub:8099", "recorder_schluessel": "hubhubhubhub"})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"ordner_praefix": "Spielen mit"}, subentries_data=[_partner()], unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    assert m.opt("recorder_url") == "http://hub:8099" and m.opt("recorder_schluessel") == "hubhubhubhub"


async def test_hub_change_reloads_and_new_cam_appears(hass: HomeAssistant) -> None:
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    entry = await _setup(hass)
    hub = hass.config_entries.async_entries(HUB_DOMAIN)[0]
    hass.config_entries.async_add_subentry(
        hub, ConfigSubentry(data={"name": "Neucam", "kuerzel": "NC", "aufnehmen": True}, subentry_type="cam", title="Neucam", unique_id="neucam")
    )
    async_dispatcher_send(hass, HUB_SIGNAL)
    await hass.async_block_till_done()
    assert "Neucam" in [c.name for c in entry.runtime_data.cams]


async def test_cams_busy_in_a_profile_are_skipped(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    m.rec_status = {"profile": {"prof_treppe": {"aufnahme": True, "kameras": {"cam_Kesselcam": {"status": "laeuft"}}}}}
    with _stream_patch(), patch.object(m, "_poll_recorder", AsyncMock()):
        res = await m.async_recorder_start()
    assert "Kesselcam" not in res["cams"] and any("Kesselcam" in x for x in res["ohne_stream"])


async def test_recorder_calls_use_the_default_session(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    seen = []

    class Spy(FakeRecorder):
        async def start(self, path, cams, session, profile=None):
            seen.append(("start", profile))
            return await super().start(path, cams, session, profile)

        async def stop(self, profile=None):
            seen.append(("stop", profile))
            return await super().stop(profile)

    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with patch("custom_components.spiel_saison_aufnehmen.manager.RecorderClient", Spy), _stream_patch():
        await m.async_recorder_start()
        await m.async_recorder_stop()
    assert seen == [("start", "default"), ("stop", "default")]


async def test_cam_can_be_excluded_from_spielpartner_recording(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    m = entry.runtime_data
    sid = next(i for i, s in entry.subentries.items() if s.data.get("cam_id") == "cam_Fuchsblick")
    hass.config_entries.async_update_subentry(entry, entry.subentries[sid], data={**entry.subentries[sid].data, "bei_spielpartner": False})
    await hass.async_block_till_done()
    m = entry.runtime_data
    await m.async_prepare("frank_visselff")
    with _stream_patch():
        res = await m.async_recorder_start()
    assert "Fuchsblick" not in res["cams"] and "Kesselcam" in res["cams"]


async def test_stored_thread_of_wrong_forum_is_replaced(hass: HomeAssistant) -> None:
    from custom_components.spiel_saison_aufnehmen.discord_client import DiscordError

    entry = await _setup(hass)
    m = entry.runtime_data
    p = m.partners["frank_visselff"]
    p.forum_id = "111"
    s = m.state_of("frank_visselff")
    s["thread_id"], s["thread_saison"] = "999", "02"
    created = []

    class Fake:
        parent = "222"
        missing = False

        async def get_channel(self, cid):
            if self.missing:
                raise DiscordError("Discord HTTP 404: Unknown Channel")
            return {"id": cid, "parent_id": self.parent}

        async def create_forum_thread(self, forum, name, **kw):
            created.append(forum)
            return "555"

    fake = Fake()
    with patch.object(m, "_discord", return_value=fake):
        hints: list[str] = []
        assert "neuer Thread" in await m._ensure_thread(p, s, hints) and s["thread_id"] == "555" and hints
        fake.parent = "111"  # passender Thread bleibt
        hints = []
        assert "vorhanden" in await m._ensure_thread(p, s, hints) and created == ["111"] and not hints
        fake.missing = True  # geloescht -> neu
        s["thread_id"] = "777"
        assert "neuer Thread" in await m._ensure_thread(p, s, [])
