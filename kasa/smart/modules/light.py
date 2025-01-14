"""Module for led controls."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from ...exceptions import KasaException
from ...feature import Feature
from ...interfaces.light import HSV, LightState
from ...interfaces.light import Light as LightInterface
from ...module import FeatureAttribute, Module
from ..smartmodule import SmartModule


class Light(SmartModule, LightInterface):
    """Implementation of a light."""

    _light_state: LightState

    @property
    def _all_features(self) -> dict[str, Feature]:
        """Get the features for this module and any sub modules."""
        ret: dict[str, Feature] = {}
        if brightness := self._device.modules.get(Module.Brightness):
            ret.update(**brightness._module_features)
        if color := self._device.modules.get(Module.Color):
            ret.update(**color._module_features)
        if temp := self._device.modules.get(Module.ColorTemperature):
            ret.update(**temp._module_features)
        return ret

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def hsv(self) -> Annotated[HSV, FeatureAttribute()]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if Module.Color not in self._device.modules:
            raise KasaException("Bulb does not support color.")

        return self._device.modules[Module.Color].hsv

    @property
    def color_temp(self) -> Annotated[int, FeatureAttribute()]:
        """Whether the bulb supports color temperature changes."""
        if Module.ColorTemperature not in self._device.modules:
            raise KasaException("Bulb does not support colortemp.")

        return self._device.modules[Module.ColorTemperature].color_temp

    @property
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness in percentage."""
        if Module.Brightness not in self._device.modules:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return self._device.modules[Module.Brightness].brightness

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value between 1 and 100
        :param int transition: transition in milliseconds.
        """
        if Module.Color not in self._device.modules:
            raise KasaException("Bulb does not support color.")

        return await self._device.modules[Module.Color].set_hsv(hue, saturation, value)

    async def set_color_temp(
        self, temp: int, *, brightness: int | None = None, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if Module.ColorTemperature not in self._device.modules:
            raise KasaException("Bulb does not support colortemp.")
        return await self._device.modules[Module.ColorTemperature].set_color_temp(
            temp, brightness=brightness
        )

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if Module.Brightness not in self._device.modules:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return await self._device.modules[Module.Brightness].set_brightness(brightness)

    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
        state_dict = asdict(state)
        # brightness of 0 turns off the light, it's not a valid brightness
        if state.brightness == 0:
            state_dict["device_on"] = False
            del state_dict["brightness"]
        elif state.light_on is not None:
            state_dict["device_on"] = state.light_on
            del state_dict["light_on"]
        else:
            state_dict["device_on"] = True

        params = {k: v for k, v in state_dict.items() if v is not None}
        return await self.call("set_device_info", params)

    @property
    def state(self) -> LightState:
        """Return the current light state."""
        return self._light_state

    async def _post_update_hook(self) -> None:
        device = self._device
        if device.is_on is False:
            state = LightState(light_on=False)
        else:
            state = LightState(light_on=True)
            if Module.Brightness in device.modules:
                state.brightness = self.brightness
            if Module.Color in device.modules:
                hsv = self.hsv
                state.hue = hsv.hue
                state.saturation = hsv.saturation
            if Module.ColorTemperature in device.modules:
                state.color_temp = self.color_temp
        self._light_state = state
