from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

from kasa import (
    Credentials,
    Device,
    DeviceType,
    Discover,
)
from kasa.iot import IotBulb, IotDimmer, IotLightStrip, IotPlug, IotStrip, IotWallSwitch
from kasa.smart import SmartDevice
from kasa.smartcam import SmartCamDevice

from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol
from .fakeprotocol_smartcam import FakeSmartCamProtocol
from .fixtureinfo import (
    FIXTURE_DATA,
    ComponentFilter,
    FixtureInfo,
    filter_fixtures,
    idgenerator,
)

# Tapo bulbs
BULBS_SMART_VARIABLE_TEMP = {"L530E", "L930-5"}
BULBS_SMART_LIGHT_STRIP = {"L900-5", "L900-10", "L920-5", "L930-5"}
BULBS_SMART_COLOR = {"L530E", *BULBS_SMART_LIGHT_STRIP}
BULBS_SMART_DIMMABLE = {"L510B", "L510E"}
BULBS_SMART = (
    BULBS_SMART_VARIABLE_TEMP.union(BULBS_SMART_COLOR)
    .union(BULBS_SMART_DIMMABLE)
    .union(BULBS_SMART_LIGHT_STRIP)
)

# Kasa (IOT-prefixed) bulbs
BULBS_IOT_LIGHT_STRIP = {"KL400L5", "KL430", "KL420L5"}
BULBS_IOT_VARIABLE_TEMP = {
    "LB120",
    "LB130",
    "KL120",
    "KL125",
    "KL130",
    "KL135",
    "KL430",
}
BULBS_IOT_COLOR = {"LB130", "KL125", "KL130", "KL135", *BULBS_IOT_LIGHT_STRIP}
BULBS_IOT_DIMMABLE = {"KL50", "KL60", "LB100", "LB110", "KL110"}
BULBS_IOT = (
    BULBS_IOT_VARIABLE_TEMP.union(BULBS_IOT_COLOR)
    .union(BULBS_IOT_DIMMABLE)
    .union(BULBS_IOT_LIGHT_STRIP)
)

BULBS_VARIABLE_TEMP = {*BULBS_SMART_VARIABLE_TEMP, *BULBS_IOT_VARIABLE_TEMP}
BULBS_COLOR = {*BULBS_SMART_COLOR, *BULBS_IOT_COLOR}


LIGHT_STRIPS = {*BULBS_SMART_LIGHT_STRIP, *BULBS_IOT_LIGHT_STRIP}
BULBS = {
    *BULBS_IOT,
    *BULBS_SMART,
}


PLUGS_IOT = {
    "HS100",
    "HS103",
    "HS105",
    "HS110",
    "EP10",
    "KP100",
    "KP105",
    "KP115",
    "KP125",
    "KP401",
}
PLUGS_SMART = {
    "P100",
    "P110",
    "P110M",
    "P115",
    "KP125M",
    "EP25",
    "P125M",
    "TP15",
}
PLUGS = {
    *PLUGS_IOT,
    *PLUGS_SMART,
}
SWITCHES_IOT = {
    "HS200",
    "HS210",
    "KS200",
    "KS200M",
}
SWITCHES_SMART = {
    "HS200",
    "KS205",
    "KS225",
    "KS240",
    "S500D",
    "S505",
    "S505D",
}
SWITCHES = {*SWITCHES_IOT, *SWITCHES_SMART}
STRIPS_IOT = {"HS107", "HS300", "KP303", "KP200", "KP400", "EP40"}
STRIPS_SMART = {"P300", "P304M", "TP25", "EP40M", "P210M", "P306"}
STRIPS = {*STRIPS_IOT, *STRIPS_SMART}

DIMMERS_IOT = {"ES20M", "HS220", "KS220", "KS220M", "KS230", "KP405"}
DIMMERS_SMART = {"HS220", "KS225", "S500D", "P135"}
DIMMERS = {
    *DIMMERS_IOT,
    *DIMMERS_SMART,
}

HUBS_SMART = {"H100", "KH100"}
SENSORS_SMART = {
    "T310",
    "T315",
    "T300",
    "T100",
    "T110",
    "S200B",
    "S200D",
    "S210",
    "S220",
    "D100C",  # needs a home category?
}
THERMOSTATS_SMART = {"KE100"}

WITH_EMETER_IOT = {"HS110", "HS300", "KP115", "KP125", *BULBS_IOT}
WITH_EMETER_SMART = {"P110", "P110M", "P115", "KP125M", "EP25", "P304M"}
WITH_EMETER = {*WITH_EMETER_IOT, *WITH_EMETER_SMART}

DIMMABLE = {*BULBS, *DIMMERS}

ALL_DEVICES_IOT = (
    BULBS_IOT.union(PLUGS_IOT).union(STRIPS_IOT).union(DIMMERS_IOT).union(SWITCHES_IOT)
)
ALL_DEVICES_SMART = (
    BULBS_SMART.union(PLUGS_SMART)
    .union(STRIPS_SMART)
    .union(DIMMERS_SMART)
    .union(HUBS_SMART)
    .union(SENSORS_SMART)
    .union(SWITCHES_SMART)
    .union(THERMOSTATS_SMART)
)
ALL_DEVICES = ALL_DEVICES_IOT.union(ALL_DEVICES_SMART)

IP_FIXTURE_CACHE: dict[str, FixtureInfo] = {}


def parametrize_combine(parametrized: list[pytest.MarkDecorator]):
    """Combine multiple pytest parametrize dev marks into one set of fixtures."""
    fixtures = set()
    for param in parametrized:
        if param.args[0] != "dev":
            raise Exception(f"Supplied mark is not for dev fixture: {param.args[0]}")
        fixtures.update(param.args[1])
    return pytest.mark.parametrize(
        "dev",
        sorted(list(fixtures)),
        indirect=True,
        ids=idgenerator,
    )


def parametrize_subtract(params: pytest.MarkDecorator, subtract: pytest.MarkDecorator):
    """Combine multiple pytest parametrize dev marks into one set of fixtures."""
    if params.args[0] != "dev" or subtract.args[0] != "dev":
        raise Exception(
            f"Supplied mark is not for dev fixture: {params.args[0]} {subtract.args[0]}"
        )
    fixtures = []
    for param in params.args[1]:
        if param not in subtract.args[1]:
            fixtures.append(param)
    return pytest.mark.parametrize(
        "dev",
        sorted(fixtures),
        indirect=True,
        ids=idgenerator,
    )


def parametrize(
    desc,
    *,
    model_filter=None,
    protocol_filter=None,
    component_filter: str | ComponentFilter | None = None,
    data_root_filter=None,
    device_type_filter=None,
    ids=None,
    fixture_name="dev",
):
    if ids is None:
        ids = idgenerator
    return pytest.mark.parametrize(
        fixture_name,
        filter_fixtures(
            desc,
            model_filter=model_filter,
            protocol_filter=protocol_filter,
            component_filter=component_filter,
            data_root_filter=data_root_filter,
            device_type_filter=device_type_filter,
        ),
        indirect=True,
        ids=ids,
    )


has_emeter = parametrize(
    "has emeter", model_filter=WITH_EMETER, protocol_filter={"SMART", "IOT"}
)
no_emeter = parametrize(
    "no emeter",
    model_filter=ALL_DEVICES - WITH_EMETER,
    protocol_filter={"SMART", "IOT"},
)
has_emeter_smart = parametrize(
    "has emeter smart", model_filter=WITH_EMETER_SMART, protocol_filter={"SMART"}
)
has_emeter_iot = parametrize(
    "has emeter iot", model_filter=WITH_EMETER_IOT, protocol_filter={"IOT"}
)
no_emeter_iot = parametrize(
    "no emeter iot",
    model_filter=ALL_DEVICES_IOT - WITH_EMETER_IOT,
    protocol_filter={"IOT"},
)

plug = parametrize("plugs", model_filter=PLUGS, protocol_filter={"IOT", "SMART"})
plug_iot = parametrize("plugs iot", model_filter=PLUGS, protocol_filter={"IOT"})
wallswitch = parametrize(
    "wall switches", model_filter=SWITCHES, protocol_filter={"IOT", "SMART"}
)
wallswitch_iot = parametrize(
    "wall switches iot", model_filter=SWITCHES, protocol_filter={"IOT"}
)
strip = parametrize("strips", model_filter=STRIPS, protocol_filter={"SMART", "IOT"})
dimmer_iot = parametrize("dimmers", model_filter=DIMMERS, protocol_filter={"IOT"})
lightstrip_iot = parametrize(
    "lightstrips", model_filter=LIGHT_STRIPS, protocol_filter={"IOT"}
)

# bulb types
dimmable_iot = parametrize("dimmable", model_filter=DIMMABLE, protocol_filter={"IOT"})
non_dimmable_iot = parametrize(
    "non-dimmable", model_filter=BULBS - DIMMABLE, protocol_filter={"IOT"}
)
variable_temp = parametrize(
    "variable color temp",
    model_filter=BULBS_VARIABLE_TEMP,
    protocol_filter={"SMART", "IOT"},
)
non_variable_temp = parametrize(
    "non-variable color temp",
    model_filter=BULBS - BULBS_VARIABLE_TEMP,
    protocol_filter={"SMART", "IOT"},
)
color_bulb = parametrize(
    "color bulbs", model_filter=BULBS_COLOR, protocol_filter={"SMART", "IOT"}
)
non_color_bulb = parametrize(
    "non-color bulbs",
    model_filter=BULBS - BULBS_COLOR,
    protocol_filter={"SMART", "IOT"},
)

color_bulb_iot = parametrize(
    "color bulbs iot", model_filter=BULBS_IOT_COLOR, protocol_filter={"IOT"}
)
variable_temp_iot = parametrize(
    "variable color temp iot",
    model_filter=BULBS_IOT_VARIABLE_TEMP,
    protocol_filter={"IOT"},
)
variable_temp_smart = parametrize(
    "variable color temp smart",
    model_filter=BULBS_SMART_VARIABLE_TEMP,
    protocol_filter={"SMART"},
)

bulb_smart = parametrize(
    "bulb devices smart",
    device_type_filter=[DeviceType.Bulb, DeviceType.LightStrip],
    protocol_filter={"SMART"},
)
bulb_iot = parametrize(
    "bulb devices iot", model_filter=BULBS_IOT, protocol_filter={"IOT"}
)
bulb = parametrize_combine([bulb_smart, bulb_iot])

strip_iot = parametrize(
    "strip devices iot", model_filter=STRIPS_IOT, protocol_filter={"IOT"}
)
strip_smart = parametrize(
    "strip devices smart", model_filter=STRIPS_SMART, protocol_filter={"SMART"}
)

plug_smart = parametrize(
    "plug devices smart", model_filter=PLUGS_SMART, protocol_filter={"SMART"}
)
switch_smart = parametrize(
    "switch devices smart", model_filter=SWITCHES_SMART, protocol_filter={"SMART"}
)
dimmers_smart = parametrize(
    "dimmer devices smart", model_filter=DIMMERS_SMART, protocol_filter={"SMART"}
)
hubs_smart = parametrize(
    "hubs smart", model_filter=HUBS_SMART, protocol_filter={"SMART"}
)
sensors_smart = parametrize(
    "sensors smart", model_filter=SENSORS_SMART, protocol_filter={"SMART.CHILD"}
)
thermostats_smart = parametrize(
    "thermostats smart", model_filter=THERMOSTATS_SMART, protocol_filter={"SMART.CHILD"}
)
device_smart = parametrize(
    "devices smart", model_filter=ALL_DEVICES_SMART, protocol_filter={"SMART"}
)
device_iot = parametrize(
    "devices iot", model_filter=ALL_DEVICES_IOT, protocol_filter={"IOT"}
)
device_smartcam = parametrize("devices smartcam", protocol_filter={"SMARTCAM"})
camera_smartcam = parametrize(
    "camera smartcam",
    device_type_filter=[DeviceType.Camera],
    protocol_filter={"SMARTCAM", "SMARTCAM.CHILD"},
)
hub_smartcam = parametrize(
    "hub smartcam",
    device_type_filter=[DeviceType.Hub],
    protocol_filter={"SMARTCAM"},
)


def check_categories():
    """Check that every fixture file is categorized."""
    categorized_fixtures = set(
        dimmer_iot.args[1]
        + strip.args[1]
        + plug.args[1]
        + bulb.args[1]
        + wallswitch.args[1]
        + lightstrip_iot.args[1]
        + bulb_smart.args[1]
        + dimmers_smart.args[1]
        + hubs_smart.args[1]
        + sensors_smart.args[1]
        + thermostats_smart.args[1]
        + camera_smartcam.args[1]
        + hub_smartcam.args[1]
    )
    diffs: set[FixtureInfo] = set(FIXTURE_DATA) - set(categorized_fixtures)
    if diffs:
        print(diffs)
        for diff in diffs:
            print(
                f"No category for file {diff.name} protocol {diff.protocol}, add to the corresponding set (BULBS, PLUGS, ..)"
            )
        raise Exception(f"Missing category for {diff.name}")


check_categories()


def device_for_fixture_name(model, protocol):
    if protocol in {"SMART", "SMART.CHILD"}:
        return SmartDevice
    elif protocol in {"SMARTCAM", "SMARTCAM.CHILD"}:
        return SmartCamDevice
    else:
        for d in STRIPS_IOT:
            if d in model:
                return IotStrip

        for d in PLUGS_IOT:
            if d in model:
                return IotPlug
        for d in SWITCHES_IOT:
            if d in model:
                return IotWallSwitch

        # Light strips are recognized also as bulbs, so this has to go first
        for d in BULBS_IOT_LIGHT_STRIP:
            if d in model:
                return IotLightStrip

        for d in BULBS_IOT:
            if d in model:
                return IotBulb

        for d in DIMMERS_IOT:
            if d in model:
                return IotDimmer

    raise Exception("Unable to find type for %s", model)


async def _update_and_close(d) -> Device:
    await d.update()
    await d.protocol.close()
    return d


async def _discover_update_and_close(ip, username, password) -> Device:
    if username and password:
        credentials = Credentials(username=username, password=password)
    else:
        credentials = None
    d = await Discover.discover_single(ip, timeout=10, credentials=credentials)
    return await _update_and_close(d)


async def get_device_for_fixture(
    fixture_data: FixtureInfo, *, verbatim=False, update_after_init=True
) -> Device:
    # if the wanted file is not an absolute path, prepend the fixtures directory

    d = device_for_fixture_name(fixture_data.name, fixture_data.protocol)(
        host="127.0.0.123"
    )
    if fixture_data.protocol in {"SMART", "SMART.CHILD"}:
        d.protocol = FakeSmartProtocol(
            fixture_data.data, fixture_data.name, verbatim=verbatim
        )
    elif fixture_data.protocol in {"SMARTCAM", "SMARTCAM.CHILD"}:
        d.protocol = FakeSmartCamProtocol(
            fixture_data.data, fixture_data.name, verbatim=verbatim
        )
    else:
        d.protocol = FakeIotProtocol(fixture_data.data, verbatim=verbatim)

    discovery_data = None
    if "discovery_result" in fixture_data.data:
        discovery_data = fixture_data.data["discovery_result"]["result"]
    elif "system" in fixture_data.data:
        discovery_data = {
            "system": {"get_sysinfo": fixture_data.data["system"]["get_sysinfo"]}
        }

    if discovery_data:  # Child devices do not have discovery info
        d.update_from_discover_info(discovery_data)

    if update_after_init:
        await _update_and_close(d)
    return d


async def get_device_for_fixture_protocol(fixture, protocol):
    finfo = FixtureInfo(name=fixture, protocol=protocol, data={})
    for fixture_info in FIXTURE_DATA:
        if finfo == fixture_info:
            return await get_device_for_fixture(fixture_info)


def get_fixture_info(fixture, protocol):
    finfo = FixtureInfo(name=fixture, protocol=protocol, data={})
    for fixture_info in FIXTURE_DATA:
        if finfo == fixture_info:
            return fixture_info


def get_nearest_fixture_to_ip(dev):
    if isinstance(dev, SmartDevice):
        protocol_fixtures = filter_fixtures("", protocol_filter={"SMART"})
    elif isinstance(dev, SmartCamDevice):
        protocol_fixtures = filter_fixtures("", protocol_filter={"SMARTCAM"})
    else:
        protocol_fixtures = filter_fixtures("", protocol_filter={"IOT"})
    assert protocol_fixtures, "Unknown device type"

    # This will get the best fixture with a match on model region
    if (di := dev.device_info) and (
        model_region_fixtures := filter_fixtures(
            "",
            model_filter={di.long_name + (f"({di.region})" if di.region else "")},
            fixture_list=protocol_fixtures,
        )
    ):
        return next(iter(model_region_fixtures))

    # This will get the best fixture based on model starting with the name.
    if "(" in dev.model:
        model, _, _ = dev.model.partition("(")
    else:
        model = dev.model
    if model_fixtures := filter_fixtures(
        "", model_startswith_filter=model, fixture_list=protocol_fixtures
    ):
        return next(iter(model_fixtures))

    if device_type_fixtures := filter_fixtures(
        "", device_type_filter={dev.device_type}, fixture_list=protocol_fixtures
    ):
        return next(iter(device_type_fixtures))

    return next(iter(protocol_fixtures))


@pytest.fixture(params=filter_fixtures("main devices"), ids=idgenerator)
async def dev(request) -> AsyncGenerator[Device, None]:
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    fixture_data: FixtureInfo = request.param
    dev: Device

    ip = request.config.getoption("--ip")
    username = request.config.getoption("--username") or os.environ.get("KASA_USERNAME")
    password = request.config.getoption("--password") or os.environ.get("KASA_PASSWORD")
    if ip:
        fixture = IP_FIXTURE_CACHE.get(ip)

        d = None
        if not fixture:
            d = await _discover_update_and_close(ip, username, password)
            IP_FIXTURE_CACHE[ip] = fixture = get_nearest_fixture_to_ip(d)
        assert fixture
        if fixture.name != fixture_data.name:
            pytest.skip(f"skipping file {fixture_data.name}")
            dev = None
        else:
            dev = d if d else await _discover_update_and_close(ip, username, password)
    else:
        dev = await get_device_for_fixture(fixture_data)

    yield dev

    if dev:
        await dev.disconnect()


def get_parent_and_child_modules(device: Device, module_name):
    """Return iterator of module if exists on parent and children.

    Useful for testing devices that have components listed on the parent that are only
    supported on the children, i.e. ks240.
    """
    if module_name in device.modules:
        yield device.modules[module_name]
    for child in device.children:
        if module_name in child.modules:
            yield child.modules[module_name]
