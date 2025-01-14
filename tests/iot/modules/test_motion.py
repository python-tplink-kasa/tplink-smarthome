import pytest
from pytest_mock import MockerFixture

from kasa import KasaException, Module
from kasa.iot import IotDimmer
from kasa.iot.modules.motion import Motion, Range

from ...device_fixtures import dimmer_iot


@dimmer_iot
def test_motion_getters(dev: IotDimmer):
    assert Module.IotMotion in dev.modules
    motion: Motion = dev.modules[Module.IotMotion]

    assert motion.enabled == motion.config["enable"]
    assert motion.inactivity_timeout == motion.config["cold_time"]
    assert motion.range.value == motion.config["trigger_index"]


@dimmer_iot
async def test_motion_setters(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    await motion.set_enabled(True)
    query_helper.assert_called_with("smartlife.iot.PIR", "set_enable", {"enable": True})

    await motion.set_inactivity_timeout(10)
    query_helper.assert_called_with(
        "smartlife.iot.PIR", "set_cold_time", {"cold_time": 10}
    )


@dimmer_iot
async def test_motion_range(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    for range in Range:
        await motion.set_range(range)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": range.value},
        )


@dimmer_iot
async def test_motion_range_from_string(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    ranges_good = {
        "near": Range.Near,
        "MID": Range.Mid,
        "fAr": Range.Far,
        " Custom   ": Range.Custom,
    }
    for range_str, range in ranges_good.items():
        await motion._set_range_from_str(range_str)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": range.value},
        )

    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")
    ranges_bad = ["near1", "MD", "F\nAR", "Custom Near", '"FAR"', "'FAR'"]
    for range_str in ranges_bad:
        with pytest.raises(KasaException):
            await motion._set_range_from_str(range_str)
        query_helper.assert_not_called()


@dimmer_iot
async def test_motion_threshold(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    for range in Range:
        # Switch to a given range.
        await motion.set_range(range)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": range.value},
        )

        # Assert that the range always goes to custom, regardless of current range.
        await motion.set_threshold(123)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": Range.Custom.value, "value": 123},
        )


@dimmer_iot
async def test_motion_realtime(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    await motion.get_pir_state()
    query_helper.assert_called_with("smartlife.iot.PIR", "get_adc_value", None)


@dimmer_iot
def test_motion_feature(dev: IotDimmer):
    assert Module.IotMotion in dev.modules
    motion: Motion = dev.modules[Module.IotMotion]

    pir_enabled = dev.features["pir_enabled"]
    assert motion.enabled == pir_enabled.value
