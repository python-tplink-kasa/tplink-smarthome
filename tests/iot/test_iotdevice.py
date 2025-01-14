"""Module for common iotdevice tests."""

import re
from datetime import datetime

import pytest
from voluptuous import (
    REMOVE_EXTRA,
    All,
    Any,
    Boolean,
    In,
    Invalid,
    Optional,
    Range,
    Schema,
)

from kasa import DeviceType, KasaException, Module
from kasa.iot import IotDevice
from kasa.iot.iotmodule import _merge_dict
from tests.conftest import get_device_for_fixture_protocol, handle_turn_on, turn_on
from tests.device_fixtures import device_iot, has_emeter_iot, no_emeter_iot
from tests.fakeprotocol_iot import FakeIotProtocol

TZ_SCHEMA = Schema(
    {"zone_str": str, "dst_offset": int, "index": All(int, Range(min=0)), "tz_str": str}
)


def check_mac(x):
    if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", x.lower()):
        return x
    raise Invalid(x)


SYSINFO_SCHEMA = Schema(
    {
        "active_mode": In(["schedule", "none", "count_down"]),
        "alias": str,
        "dev_name": str,
        "deviceId": str,
        "feature": str,
        "fwId": str,
        "hwId": str,
        "hw_ver": str,
        "icon_hash": str,
        "led_off": Boolean,
        "latitude": Any(All(float, Range(min=-90, max=90)), 0, None),
        "latitude_i": Any(
            All(int, Range(min=-900000, max=900000)),
            All(float, Range(min=-900000, max=900000)),
            0,
            None,
        ),
        "longitude": Any(All(float, Range(min=-180, max=180)), 0, None),
        "longitude_i": Any(
            All(int, Range(min=-18000000, max=18000000)),
            All(float, Range(min=-18000000, max=18000000)),
            0,
            None,
        ),
        "mac": check_mac,
        "model": str,
        "oemId": str,
        "on_time": int,
        "relay_state": int,
        "rssi": Any(int, None),  # rssi can also be positive, see #54
        "sw_ver": str,
        "type": str,
        "mic_type": str,
        "updating": Boolean,
        # these are available on hs220
        "brightness": int,
        "preferred_state": [
            {"brightness": All(int, Range(min=0, max=100)), "index": int}
        ],
        "next_action": {"type": int},
        "child_num": Optional(Any(None, int)),
        "children": Optional(list),
    },
    extra=REMOVE_EXTRA,
)


@device_iot
async def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


@pytest.mark.requires_dummy
@device_iot
async def test_invalid_connection(mocker, dev):
    mocker.patch.object(FakeIotProtocol, "query", side_effect=KasaException)
    with pytest.raises(KasaException):
        await dev.update()


@has_emeter_iot
async def test_initial_update_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = {}
    dev._legacy_features = set()
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    # Devices with small buffers may require 3 queries
    expected_queries = 2 if dev.max_device_response_size > 4096 else 3
    assert spy.call_count == expected_queries + len(dev.children)


@no_emeter_iot
async def test_initial_update_no_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = {}
    dev._legacy_features = set()
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    # child calls will happen if a child has a module with a query (e.g. schedule)
    child_calls = 0
    for child in dev.children:
        for module in child.modules.values():
            if module.query():
                child_calls += 1
                break
    # 2 parent are necessary as some devices crash on unexpected modules
    # See #105, #120, #161
    assert spy.call_count == 2 + child_calls


@device_iot
async def test_query_helper(dev):
    with pytest.raises(KasaException):
        await dev._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


@device_iot
@turn_on
async def test_state(dev, turn_on):
    orig_state = dev.is_on
    await handle_turn_on(dev, turn_on)
    await dev.update()
    if orig_state:
        await dev.turn_off()
        await dev.update()
        assert not dev.is_on
        assert dev.is_off

        await dev.turn_on()
        await dev.update()
        assert dev.is_on
        assert not dev.is_off
    else:
        await dev.turn_on()
        await dev.update()
        assert dev.is_on
        assert not dev.is_off

        await dev.turn_off()
        await dev.update()
        assert not dev.is_on
        assert dev.is_off


@device_iot
@turn_on
async def test_on_since(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    orig_state = dev.is_on
    if "on_time" not in dev.sys_info and dev.device_type is not DeviceType.Strip:
        assert dev.on_since is None
    elif orig_state:
        assert isinstance(dev.on_since, datetime)
    else:
        assert dev.on_since is None


@device_iot
async def test_time(dev):
    assert isinstance(dev.modules[Module.Time].time, datetime)


@device_iot
async def test_timezone(dev):
    TZ_SCHEMA(await dev.modules[Module.Time].get_timezone())


@device_iot
async def test_hw_info(dev):
    SYSINFO_SCHEMA(dev.hw_info)


@device_iot
async def test_location(dev):
    SYSINFO_SCHEMA(dev.location)


@device_iot
async def test_rssi(dev):
    SYSINFO_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


@device_iot
async def test_mac(dev):
    SYSINFO_SCHEMA({"mac": dev.mac})  # wrapping for val


@device_iot
async def test_representation(dev):
    pattern = re.compile(r"<DeviceType\..+ at .+? - .*? \(.+?\)>")
    assert pattern.match(str(dev))


@device_iot
async def test_children(dev):
    """Make sure that children property is exposed by every device."""
    if dev.device_type is DeviceType.Strip:
        assert len(dev.children) > 0
    else:
        assert len(dev.children) == 0


@device_iot
async def test_modules_preserved(dev: IotDevice):
    """Make modules that are not being updated are preserved between updates."""
    dev._last_update["some_module_not_being_updated"] = "should_be_kept"
    await dev.update()
    assert dev._last_update["some_module_not_being_updated"] == "should_be_kept"


@device_iot
async def test_internal_state(dev):
    """Make sure the internal state returns the last update results."""
    assert dev.internal_state == dev._last_update


@device_iot
async def test_features(dev):
    """Make sure features is always accessible."""
    sysinfo = dev._last_update["system"]["get_sysinfo"]
    if "feature" in sysinfo:
        assert dev._legacy_features == set(sysinfo["feature"].split(":"))
    else:
        assert dev._legacy_features == set()


@device_iot
async def test_max_device_response_size(dev):
    """Make sure every device return has a set max response size."""
    assert dev.max_device_response_size > 0


@device_iot
async def test_estimated_response_sizes(dev):
    """Make sure every module has an estimated response size set."""
    for mod in dev.modules.values():
        assert mod.estimated_query_response_size > 0


@device_iot
async def test_modules_not_supported(dev: IotDevice):
    """Test that unsupported modules do not break the device."""
    for module in dev.modules.values():
        assert module.is_supported is not None
    await dev.update()
    for module in dev.modules.values():
        assert module.is_supported is not None


async def test_get_modules():
    """Test getting modules for child and parent modules."""
    dummy_device = await get_device_for_fixture_protocol(
        "HS100(US)_2.0_1.5.6.json", "IOT"
    )
    from kasa.iot.modules import Cloud

    # Modules on device
    module = dummy_device.modules.get("cloud")
    assert module
    assert module._device == dummy_device
    assert isinstance(module, Cloud)

    module = dummy_device.modules.get(Module.IotCloud)
    assert module
    assert module._device == dummy_device
    assert isinstance(module, Cloud)

    # Invalid modules
    module = dummy_device.modules.get("DummyModule")
    assert module is None

    module = dummy_device.modules.get(Module.Cloud)
    assert module is None


def test_merge_dict():
    """Test the recursive dict merge."""
    dest = {"a": 1, "b": {"c": 2, "d": 3}}
    source = {"b": {"c": 4, "e": 5}}
    assert _merge_dict(dest, source) == {"a": 1, "b": {"c": 4, "d": 3, "e": 5}}

    dest = {"smartlife.iot.common.emeter": {"get_realtime": None}}
    source = {
        "smartlife.iot.common.emeter": {"get_daystat": {"month": 8, "year": 2024}}
    }
    assert _merge_dict(dest, source) == {
        "smartlife.iot.common.emeter": {
            "get_realtime": None,
            "get_daystat": {"month": 8, "year": 2024},
        }
    }
