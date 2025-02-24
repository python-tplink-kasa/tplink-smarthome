import datetime
from unittest.mock import Mock

import pytest
from voluptuous import (
    All,
    Any,
    Coerce,
    Range,
    Schema,
)

from kasa import Device, DeviceType, EmeterStatus, Module
from kasa.interfaces.energy import Energy
from kasa.iot import IotStrip
from kasa.iot.modules.emeter import Emeter
from tests.conftest import has_emeter_iot, no_emeter_iot

CURRENT_CONSUMPTION_SCHEMA = Schema(
    Any(
        {
            "voltage_mv": Any(All(float, Range(min=0, max=300000)), int, None),
            "power_mw": Any(Coerce(float), None),
            "current_ma": Any(All(float), int, None),
            "energy_wh": Any(Coerce(float), None),
            "total_wh": Any(Coerce(float), None),
            "voltage": Any(All(float, Range(min=0, max=300)), None),
            "power": Any(Coerce(float), None),
            "current": Any(All(float), None),
            "total": Any(Coerce(float), None),
            "energy": Any(Coerce(float), None),
            "slot_id": Any(Coerce(int), None),
        },
        None,
    )
)


@no_emeter_iot
async def test_no_emeter(dev):
    assert not dev.has_emeter

    with pytest.raises(AttributeError):
        await dev.get_emeter_realtime()

    with pytest.raises(AttributeError):
        await dev.get_emeter_daily()
    with pytest.raises(AttributeError):
        await dev.get_emeter_monthly()
    with pytest.raises(AttributeError):
        await dev.erase_emeter_stats()


@has_emeter_iot
async def test_get_emeter_realtime(dev):
    emeter = dev.modules[Module.Energy]

    current_emeter = await emeter.get_status()
    # Check realtime query gets the same value as status property
    # iot _query_helper strips out the error code from module responses.
    # but it's not stripped out of the _modular_update queries.
    assert current_emeter == {k: v for k, v in emeter.status.items() if k != "err_code"}
    CURRENT_CONSUMPTION_SCHEMA(current_emeter)


@has_emeter_iot
@pytest.mark.requires_dummy
async def test_get_emeter_daily(dev):
    emeter = dev.modules[Module.Energy]

    assert await emeter.get_daily_stats(year=1900, month=1) == {}

    d = await emeter.get_daily_stats()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await emeter.get_daily_stats(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter_iot
@pytest.mark.requires_dummy
async def test_get_emeter_monthly(dev):
    emeter = dev.modules[Module.Energy]

    assert await emeter.get_monthly_stats(year=1900) == {}

    d = await emeter.get_monthly_stats()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await emeter.get_monthly_stats(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter_iot
async def test_emeter_status(dev):
    emeter = dev.modules[Module.Energy]

    d = await emeter.get_status()

    with pytest.raises(KeyError):
        assert d["foo"]

    assert d["power_mw"] == d["power"] * 1000
    # bulbs have only power according to tplink simulator.
    if (
        dev.device_type is not DeviceType.Bulb
        and dev.device_type is not DeviceType.LightStrip
    ):
        assert d["voltage_mv"] == d["voltage"] * 1000

        assert d["current_ma"] == d["current"] * 1000
        assert d["total_wh"] == d["total"] * 1000


@pytest.mark.skip("not clearing your stats..")
@has_emeter_iot
async def test_erase_emeter_stats(dev):
    emeter = dev.modules[Module.Energy]

    await emeter.erase_emeter()


@has_emeter_iot
async def test_power(dev):
    emeter = dev.modules[Module.Energy]
    x = emeter.power
    assert isinstance(x, float)
    assert x >= 0.0


async def test_emeterstatus_missing_current():
    """KL125 does not report 'current' for emeter."""
    regular = EmeterStatus(
        {"err_code": 0, "power_mw": 0, "total_wh": 13, "current_ma": 123}
    )
    assert regular["current"] == 0.123

    with pytest.raises(KeyError):
        regular["invalid_key"]

    missing_current = EmeterStatus({"err_code": 0, "power_mw": 0, "total_wh": 13})
    assert missing_current["current"] is None


async def test_emeter_daily():
    """Test fetching the emeter for today.

    This test uses inline data since the fixtures
    will not have data for the current day.
    """
    emeter_data = {
        "get_daystat": {
            "day_list": [{"day": 1, "energy_wh": 8, "month": 1, "year": 2023}],
            "err_code": 0,
        }
    }

    class MockEmeter(Emeter):
        @property
        def data(self):
            return emeter_data

    emeter = MockEmeter(Mock(), "emeter")
    now = datetime.datetime.now()
    emeter_data["get_daystat"]["day_list"].append(
        {"day": now.day, "energy_wh": 500, "month": now.month, "year": now.year}
    )
    assert emeter.consumption_today == 0.500


@has_emeter_iot
async def test_supported(dev: Device):
    energy_module = dev.modules.get(Module.Energy)
    assert energy_module

    info = (
        dev._last_update
        if not isinstance(dev, IotStrip)
        else dev.children[0].internal_state
    )
    emeter = info[energy_module._module]["get_realtime"]
    has_total = "total" in emeter or "total_wh" in emeter
    has_voltage_current = "voltage" in emeter or "voltage_mv" in emeter
    assert energy_module.supports(Energy.ModuleFeature.CONSUMPTION_TOTAL) is has_total
    assert (
        energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT)
        is has_voltage_current
    )
    assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is True
