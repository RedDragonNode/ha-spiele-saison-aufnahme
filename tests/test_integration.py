"""Integration + Recorder-Add-on (Add-on ist durch einen Fake ersetzt)."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spielpartner_aufnahme.config_flow import _default_subentries
from custom_components.spielpartner_aufnahme.const import (
    DOMAIN,
    SUBENTRY_CAM,
    SUBENTRY_PARTNER,
)
from custom_components.spielpartner_aufnahme.recorder_client import RecorderError

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

    async def start(self, path, cams, session):
        self._chk()
        FakeRecorder.calls.append(("start", path, cams, session))
        FakeRecorder.running = True
        return {}

    async def stop(self):
        self._chk()
        FakeRecorder.calls.append(("stop",))
        FakeRecorder.running = False
        return {}


@pytest.fixture(autouse=True)
def fake_recorder():
    FakeRecorder.dirs, FakeRecorder.running, FakeRecorder.calls = {}, False, []
    FakeRecorder.fail, FakeRecorder.stop_reason = False, ""
    with patch("custom_components.spielpartner_aufnahme.manager.RecorderClient", FakeRecorder):
        yield


async def _setup(hass: HomeAssistant, **extra) -> MockConfigEntry:
    subs = _default_subentries()
    for sub in subs:
        if sub["data"]["name"] == "Fuchsblick":
            sub["data"]["rtsp_url"] = "rtsp://u:p@192.168.1.11:554/main"
        elif sub["data"]["name"] == "Kesselcam":
            sub["data"]["stream_entity"] = "camera.kessel"
        elif sub["data"]["name"] == "Rotpelz":
            sub["data"]["aufnehmen"] = False
            sub["data"]["rtsp_url"] = "rtsp://x/y"
    subs.append(
        ConfigSubentryData(
            subentry_type=SUBENTRY_PARTNER,
            title="Frank",
            unique_id="frank_visselff",
            data={"kennung": "frank_visselff", "anzeige": "Frank", "ordner_nr": 1, "forum_id": "",
                  "initial": {"saison": 2, "aufnahmen": 3, "gesamt": 14}},
        )
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={**BASE, **extra}, subentries_data=subs, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    hass.states.async_set("binary_sensor.rec", "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _stream_patch():
    return patch(
        "custom_components.spielpartner_aufnahme.manager.async_get_stream_source",
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
    assert hass.states.get("binary_sensor.spielpartner_aufnahme_recorder_recording").state == "on"
    again = await m.async_recorder_start()
    assert again["gestartet"] is False  # idempotent
    await hass.services.async_call(DOMAIN, "recorder_stoppen", {}, blocking=True)
    s = m.state_of("frank_visselff")
    assert (s["aufnahmen"], s["gesamt"]) == (4, 15)
    await m.async_recorder_stop()  # zweites Stoppen zaehlt nicht nochmal
    assert (s["aufnahmen"], s["gesamt"]) == (4, 15)
    assert hass.states.get("binary_sensor.spielpartner_aufnahme_recorder_recording").state == "off"


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


async def test_cam_subentry_recorder_fields(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    sid = next(i for i, s in entry.subentries.items() if s.subentry_type == SUBENTRY_CAM and s.data["name"] == "Kesselcam")
    flow = await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_CAM), context={"source": "reconfigure", "subentry_id": sid})
    assert flow["type"] == "form" and "rtsp_url" in {str(k) for k in flow["data_schema"].schema}
    done = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"kuerzel": "KC", "rtsp_url": " rtsp://h/s ", "aufnehmen": True, "stream_entity": "camera.kessel"}
    )
    assert done["type"] == "abort"
    assert entry.subentries[sid].data["rtsp_url"] == "rtsp://h/s"


async def test_setup_and_entities(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass)
    ids = {e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    for key in ("saison", "aufnahmen_in_saison", "gesamt", "vorbereiten", "dateiformat", "speicher_adresse"):
        assert f"{entry.entry_id}_frank_visselff_{key}" in ids
    assert sum(1 for i in ids if i.endswith("_format")) == 16
    assert sum(1 for i in ids if i.endswith("_aufnahme")) == 17  # je Cam + Recorder
    m = entry.runtime_data
    assert m.format_for("frank_visselff", None) == "#01.02.03.Cam ID.14 (4K) %DD.%MM.%CCYY"
    assert not hass.services.has_service(DOMAIN, "dateiformat_anwenden")


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
        "custom_components.spielpartner_aufnahme.manager.async_get_image", AsyncMock(return_value=FakeImg())
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
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert res["type"] == "form"
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"],
        {"recorder_url": "http://addon:8099", "recorder_schluessel": "geheimgeheim123", "ordner_praefix": "Spielen mit", "post_nach_minuten": 5},
    )
    assert res["type"] == "create_entry"
    entry = res["result"]
    await hass.async_block_till_done()
    assert sum(1 for s in entry.subentries.values() if s.subentry_type == SUBENTRY_CAM) == 16
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
