from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules import Alarm

from ...device_fixtures import get_parent_and_child_modules, parametrize

alarm = parametrize("has alarm", component_filter="alarm", protocol_filter={"SMART"})


@alarm
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("alarm", "active", bool),
        ("alarm_source", "source", str | None),
        ("alarm_sound", "alarm_sound", str),
        ("alarm_volume", "alarm_volume", str),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    alarm = next(get_parent_and_child_modules(dev, Module.Alarm))
    assert alarm is not None

    prop = getattr(alarm, prop_name)
    assert isinstance(prop, type)

    feat = alarm._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@alarm
@pytest.mark.parametrize(
    ("kwargs", "request_params"),
    [
        pytest.param({"volume": "low"}, {"alarm_volume": "low"}, id="volume"),
        pytest.param({"volume": 0}, {"alarm_volume": "mute"}, id="volume-integer"),
        pytest.param({"duration": 1}, {"alarm_duration": 1}, id="duration"),
        pytest.param(
            {"sound": "Doorbell Ring 1"}, {"alarm_type": "Doorbell Ring 1"}, id="sound"
        ),
    ],
)
async def test_play(dev: SmartDevice, kwargs, request_params, mocker: MockerFixture):
    """Test that play parameters are handled correctly."""
    alarm: Alarm = next(get_parent_and_child_modules(dev, Module.Alarm))
    call_spy = mocker.spy(alarm, "call")
    await alarm.play(**kwargs)

    call_spy.assert_called_with("play_alarm", request_params)

    with pytest.raises(ValueError, match="Invalid duration"):
        await alarm.play(duration=-1)

    with pytest.raises(ValueError, match="Invalid sound"):
        await alarm.play(sound="unknown")

    with pytest.raises(ValueError, match="Invalid volume"):
        await alarm.play(volume="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid volume"):
        await alarm.play(volume=-1)


@alarm
async def test_stop(dev: SmartDevice, mocker: MockerFixture):
    """Test that stop creates the correct call."""
    alarm: Alarm = next(get_parent_and_child_modules(dev, Module.Alarm))
    call_spy = mocker.spy(alarm, "call")
    await alarm.stop()

    call_spy.assert_called_with("stop_alarm")


@alarm
@pytest.mark.parametrize(
    ("method", "value", "target_key"),
    [
        pytest.param(
            "set_alarm_sound", "Doorbell Ring 1", "type", id="set_alarm_sound"
        ),
        pytest.param("set_alarm_volume", "low", "volume", id="set_alarm_volume"),
        pytest.param("set_alarm_duration", 10, "duration", id="set_alarm_duration"),
    ],
)
async def test_set_alarm_configure(
    dev: SmartDevice,
    mocker: MockerFixture,
    method: str,
    value: str | int,
    target_key: str,
):
    """Test that set_alarm_sound creates the correct call."""
    alarm: Alarm = next(get_parent_and_child_modules(dev, Module.Alarm))
    call_spy = mocker.spy(alarm, "call")
    await getattr(alarm, method)(value)

    expected_params = {"duration": mocker.ANY, "type": mocker.ANY, "volume": mocker.ANY}
    expected_params[target_key] = value

    call_spy.assert_called_with("set_alarm_configure", expected_params)
