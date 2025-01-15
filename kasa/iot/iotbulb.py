"""Module for bulbs (LB*, KL*, KB*)."""

from __future__ import annotations

import logging
import re
from typing import cast

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..interfaces.light import HSV, ColorTempRange
from ..module import Module
from ..protocols import BaseProtocol
from .iotdevice import IotDevice, KasaException, requires_update
from .modules import (
    Antitheft,
    Cloud,
    Countdown,
    Emeter,
    Light,
    LightPreset,
    Schedule,
    Time,
    TurnOnBehaviorModule,
    Usage,
)
from .modules.turnonbehavior import TurnOnBehaviors

TPLINK_KELVIN = {
    "LB130": ColorTempRange(2500, 9000),
    "LB120": ColorTempRange(2700, 6500),
    "LB230": ColorTempRange(2500, 9000),
    "KB130": ColorTempRange(2500, 9000),
    "KL130": ColorTempRange(2500, 9000),
    "KL125": ColorTempRange(2500, 6500),
    "KL135": ColorTempRange(2500, 9000),
    r"KL120\(EU\)": ColorTempRange(2700, 6500),
    r"KL120\(US\)": ColorTempRange(2700, 5000),
    r"KL430": ColorTempRange(2500, 9000),
}


NON_COLOR_MODE_FLAGS = {"transition_period", "on_off"}

_LOGGER = logging.getLogger(__name__)


class IotBulb(IotDevice):
    r"""Representation of a TP-Link Smart Bulb.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values,
    so you must await :func:`update()` to fetch updates values from the device.

    Errors reported by the device are raised as
    :class:`KasaException <kasa.exceptions.KasaException>`,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> bulb = IotBulb("127.0.0.1")
        >>> asyncio.run(bulb.update())
        >>> print(bulb.alias)
        Bulb2

        Bulbs, like any other supported devices, can be turned on and off:

        >>> asyncio.run(bulb.turn_off())
        >>> asyncio.run(bulb.turn_on())
        >>> asyncio.run(bulb.update())
        >>> print(bulb.is_on)
        True

        You can use the ``is_``-prefixed properties to check for supported features:

        >>> bulb.is_dimmable
        True
        >>> bulb.is_color
        True
        >>> bulb.is_variable_color_temp
        True

        All known bulbs support changing the brightness:

        >>> bulb.brightness
        30
        >>> asyncio.run(bulb.set_brightness(50))
        >>> asyncio.run(bulb.update())
        >>> bulb.brightness
        50

        Bulbs supporting color temperature can be queried for the supported range:

        >>> bulb.valid_temperature_range
        ColorTempRange(min=2500, max=9000)
        >>> asyncio.run(bulb.set_color_temp(3000))
        >>> asyncio.run(bulb.update())
        >>> bulb.color_temp
        3000

        Color bulbs can be adjusted by passing hue, saturation and value:

        >>> asyncio.run(bulb.set_hsv(180, 100, 80))
        >>> asyncio.run(bulb.update())
        >>> bulb.hsv
        HSV(hue=180, saturation=100, value=80)

        If you don't want to use the default transitions,
        you can pass `transition` in milliseconds.
        All methods changing the state of the device support this parameter:

        * :func:`turn_on`
        * :func:`turn_off`
        * :func:`set_hsv`
        * :func:`set_color_temp`
        * :func:`set_brightness`

        Light strips (e.g., KL420L5) do not support this feature,
        but silently ignore the parameter.
        The following changes the brightness over a period of 10 seconds:

        >>> asyncio.run(bulb.set_brightness(100, transition=10_000))

        Bulb configuration presets can be accessed using the :func:`presets` property:

        >>> [ preset.to_dict() for preset in bulb.presets }
        [{'brightness': 50, 'hue': 0, 'saturation': 0, 'color_temp': 2700, 'index': 0}, {'brightness': 100, 'hue': 0, 'saturation': 75, 'color_temp': 0, 'index': 1}, {'brightness': 100, 'hue': 120, 'saturation': 75, 'color_temp': 0, 'index': 2}, {'brightness': 100, 'hue': 240, 'saturation': 75, 'color_temp': 0, 'index': 3}]

        To modify an existing preset, pass :class:`~kasa.interfaces.light.LightPreset`
        instance to :func:`save_preset` method:

        >>> preset = bulb.presets[0]
        >>> preset.brightness
        50
        >>> preset.brightness = 100
        >>> asyncio.run(bulb.save_preset(preset))
        >>> asyncio.run(bulb.update())
        >>> bulb.presets[0].brightness
        100

    """  # noqa: E501

    LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"
    SET_LIGHT_METHOD = "transition_light_state"
    emeter_type = "smartlife.iot.common.emeter"

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.Bulb

    async def _initialize_modules(self) -> None:
        """Initialize modules not added in init."""
        await super()._initialize_modules()
        self.add_module(
            Module.IotSchedule, Schedule(self, "smartlife.iot.common.schedule")
        )
        self.add_module(Module.IotUsage, Usage(self, "smartlife.iot.common.schedule"))
        self.add_module(
            Module.IotAntitheft, Antitheft(self, "smartlife.iot.common.anti_theft")
        )
        self.add_module(Module.Time, Time(self, "smartlife.iot.common.timesetting"))
        self.add_module(
            Module.IotTurnOnBehavior,
            TurnOnBehaviorModule(self, "smartlife.iot.smartbulb.lightingservice"),
        )
        self.add_module(Module.Energy, Emeter(self, self.emeter_type))
        self.add_module(Module.IotCountdown, Countdown(self, "countdown"))
        self.add_module(Module.IotCloud, Cloud(self, "smartlife.iot.common.cloud"))
        self.add_module(Module.Light, Light(self, self.LIGHT_SERVICE))
        self.add_module(Module.LightPreset, LightPreset(self, self.LIGHT_SERVICE))

    @property  # type: ignore
    @requires_update
    def _is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_color"])

    @property  # type: ignore
    @requires_update
    def _is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_dimmable"])

    @property  # type: ignore
    @requires_update
    def _is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_variable_color_temp"])

    @property  # type: ignore
    @requires_update
    def _valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self._is_variable_color_temp:
            raise KasaException("Color temperature not supported")

        for model, temp_range in TPLINK_KELVIN.items():
            sys_info = self.sys_info
            if re.match(model, sys_info["model"]):
                return temp_range

        _LOGGER.warning("Unknown color temperature range, fallback to 2700-5000")
        return ColorTempRange(2700, 5000)

    @property  # type: ignore
    @requires_update
    def light_state(self) -> dict[str, str]:
        """Query the light state."""
        light_state = self.sys_info["light_state"]
        if light_state is None:
            raise KasaException(
                "The device has no light_state or you have not called update()"
            )

        # if the bulb is off, its state is stored under a different key
        # as is_on property depends on on_off itself, we check it here manually
        is_on = light_state["on_off"]
        if not is_on:
            off_state = {**light_state["dft_on_state"], "on_off": is_on}
            return cast(dict, off_state)

        return light_state

    @property  # type: ignore
    @requires_update
    def _has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return "lighting_effect_state" in self.sys_info

    async def get_light_details(self) -> dict[str, int]:
        """Return light details.

        Example::

            {'lamp_beam_angle': 290, 'min_voltage': 220, 'max_voltage': 240,
             'wattage': 5, 'incandescent_equivalent': 40, 'max_lumens': 450,
              'color_rendering_index': 80}
        """
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_details")

    async def get_turn_on_behavior(self) -> TurnOnBehaviors:
        """Return the behavior for turning the bulb on."""
        return TurnOnBehaviors.from_dict(
            await self._query_helper(self.LIGHT_SERVICE, "get_default_behavior")
        )

    async def set_turn_on_behavior(self, behavior: TurnOnBehaviors) -> dict:
        """Set the behavior for turning the bulb on.

        If you do not want to manually construct the behavior object,
        you should use :func:`get_turn_on_behavior` to get the current settings.
        """
        return await self._query_helper(
            self.LIGHT_SERVICE, "set_default_behavior", behavior.to_dict()
        )

    async def get_light_state(self) -> dict[str, dict]:
        """Query the light state."""
        # TODO: add warning and refer to use light.state?
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def _set_light_state(
        self, state: dict, *, transition: int | None = None
    ) -> dict:
        """Set the light state."""
        state = {**state}
        if transition is not None:
            state["transition_period"] = transition

        if "brightness" in state:
            self._raise_for_invalid_brightness(state["brightness"])

        # if no on/off is defined, turn on the light
        if "on_off" not in state:
            state["on_off"] = 1

        # If we are turning on without any color mode flags,
        # we do not want to set ignore_default to ensure
        # we restore the previous state.
        if state["on_off"] and NON_COLOR_MODE_FLAGS.issuperset(state):
            state["ignore_default"] = 0
        else:
            # This is necessary to allow turning on into a specific state
            state["ignore_default"] = 1

        light_state = await self._query_helper(
            self.LIGHT_SERVICE, self.SET_LIGHT_METHOD, state
        )
        return light_state

    @property  # type: ignore
    @requires_update
    def _hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if not self._is_color:
            raise KasaException("Bulb does not support color.")

        light_state = cast(dict, self.light_state)

        hue = light_state["hue"]
        saturation = light_state["saturation"]
        value = self._brightness

        # Simple HSV(hue, saturation, value) is less efficent than below
        # due to the cpython implementation.
        return tuple.__new__(HSV, (hue, saturation, value))

    @requires_update
    async def _set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> dict:
        """Set new HSV.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """
        if not self._is_color:
            raise KasaException("Bulb does not support color.")

        if not isinstance(hue, int):
            raise TypeError("Hue must be an integer.")
        if not (0 <= hue <= 360):
            raise ValueError(f"Invalid hue value: {hue} (valid range: 0-360)")

        if not isinstance(saturation, int):
            raise TypeError("Saturation must be an integer.")
        if not (0 <= saturation <= 100):
            raise ValueError(
                f"Invalid saturation value: {saturation} (valid range: 0-100%)"
            )

        light_state = {
            "hue": hue,
            "saturation": saturation,
            "color_temp": 0,
        }

        if value is not None:
            self._raise_for_invalid_brightness(value)
            light_state["brightness"] = value

        return await self._set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def _color_temp(self) -> int:
        """Return color temperature of the device in kelvin."""
        if not self._is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")

        light_state = self.light_state
        return int(light_state["color_temp"])

    @requires_update
    async def _set_color_temp(
        self, temp: int, *, brightness: int | None = None, transition: int | None = None
    ) -> dict:
        """Set the color temperature of the device in kelvin.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if not self._is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")

        valid_temperature_range = self._valid_temperature_range
        if temp < valid_temperature_range[0] or temp > valid_temperature_range[1]:
            raise ValueError(
                "Temperature should be between {} and {}, was {}".format(
                    *valid_temperature_range, temp
                )
            )

        light_state = {"color_temp": temp}
        if brightness is not None:
            light_state["brightness"] = brightness

        return await self._set_light_state(light_state, transition=transition)

    def _raise_for_invalid_brightness(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError("Brightness must be an integer")
        if not (0 <= value <= 100):
            raise ValueError(f"Invalid brightness value: {value} (valid range: 0-100%)")

    @property  # type: ignore
    @requires_update
    def _brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self._is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        # If the device supports effects and one is active, we get the brightness
        # from the effect. This is not required when setting the brightness as
        # the device handles it via set_light_state
        if (
            light_effect := self.modules.get(Module.IotLightEffect)
        ) is not None and light_effect.effect != light_effect.LIGHT_EFFECTS_OFF:
            return light_effect.brightness
        light_state = self.light_state
        return int(light_state["brightness"])

    @requires_update
    async def _set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self._is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        return await self._set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether the device is on."""
        light_state = self.light_state
        return bool(light_state["on_off"])

    async def turn_off(self, *, transition: int | None = None, **kwargs) -> dict:
        """Turn the bulb off.

        :param int transition: transition in milliseconds.
        """
        return await self._set_light_state({"on_off": 0}, transition=transition)

    async def turn_on(self, *, transition: int | None = None, **kwargs) -> dict:
        """Turn the bulb on.

        :param int transition: transition in milliseconds.
        """
        return await self._set_light_state({"on_off": 1}, transition=transition)

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the bulb has an emeter."""
        return True

    async def set_alias(self, alias: str) -> dict:
        """Set the device name (alias).

        Overridden to use a different module name.
        """
        return await self._query_helper(
            "smartlife.iot.common.system", "set_dev_alias", {"alias": alias}
        )

    @property
    def max_device_response_size(self) -> int:
        """Returns the maximum response size the device can safely construct."""
        return 4096
