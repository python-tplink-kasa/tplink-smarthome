"""Implementation of brightness module."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Annotated, cast

from ...device_type import DeviceType
from ...exceptions import KasaException
from ...feature import Feature
from ...interfaces.light import HSV, LightState
from ...interfaces.light import Light as LightInterface
from ...module import FeatureAttribute
from ..iotmodule import IotModule

if TYPE_CHECKING:
    from ..iotbulb import IotBulb
    from ..iotdimmer import IotDimmer


BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100


class Light(IotModule, LightInterface):
    """Implementation of brightness module."""

    _device: IotBulb | IotDimmer
    _light_state: LightState

    def _initialize_features(self) -> None:
        """Initialize features."""
        super()._initialize_features()
        device = self._device

        if device._is_dimmable:
            self._add_feature(
                Feature(
                    device,
                    id="brightness",
                    name="Brightness",
                    container=self,
                    attribute_getter="brightness",
                    attribute_setter="set_brightness",
                    range_getter=lambda: (BRIGHTNESS_MIN, BRIGHTNESS_MAX),
                    type=Feature.Type.Number,
                    category=Feature.Category.Primary,
                )
            )
        if device._is_variable_color_temp:
            if TYPE_CHECKING:
                assert isinstance(device, IotBulb)
            self._add_feature(
                Feature(
                    device=device,
                    id="color_temperature",
                    name="Color temperature",
                    container=self,
                    attribute_getter="color_temp",
                    attribute_setter="set_color_temp",
                    range_getter=lambda: device._valid_temperature_range,
                    category=Feature.Category.Primary,
                    type=Feature.Type.Number,
                )
            )
        if device._is_color:
            self._add_feature(
                Feature(
                    device=device,
                    id="hsv",
                    name="HSV",
                    container=self,
                    attribute_getter="hsv",
                    attribute_setter="set_hsv",
                    # TODO proper type for setting hsv
                    type=Feature.Type.Unknown,
                )
            )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    def _get_bulb_device(self) -> IotBulb | None:
        """For type checker this gets an IotBulb.

        IotDimmer is not a subclass of IotBulb and using isinstance
        here at runtime would create a circular import.
        """
        if self._device.device_type in {DeviceType.Bulb, DeviceType.LightStrip}:
            return cast("IotBulb", self._device)
        return None

    @property  # type: ignore
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness in percentage."""
        return self._device._brightness

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the brightness in percentage. A value of 0 will turn off the light.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        return await self.set_state(
            LightState(brightness=brightness, transition=transition)
        )

    @property
    def hsv(self) -> Annotated[HSV, FeatureAttribute()]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if (bulb := self._get_bulb_device()) is None or not bulb._is_color:
            raise KasaException("Light does not support color.")
        return bulb._hsv

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
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """
        if (bulb := self._get_bulb_device()) is None or not bulb._is_color:
            raise KasaException("Light does not support color.")
        return await bulb._set_hsv(hue, saturation, value, transition=transition)

    @property
    def color_temp(self) -> Annotated[int, FeatureAttribute()]:
        """Whether the bulb supports color temperature changes."""
        if (
            bulb := self._get_bulb_device()
        ) is None or not bulb._is_variable_color_temp:
            raise KasaException("Light does not support colortemp.")
        return bulb._color_temp

    async def set_color_temp(
        self, temp: int, *, brightness: int | None = None, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if (
            bulb := self._get_bulb_device()
        ) is None or not bulb._is_variable_color_temp:
            raise KasaException("Light does not support colortemp.")
        return await bulb._set_color_temp(
            temp, brightness=brightness, transition=transition
        )

    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
        # iot protocol Dimmers and smart protocol devices do not support
        # brightness of 0 so 0 will turn off all devices for consistency
        if (bulb := self._get_bulb_device()) is None:  # Dimmer
            if TYPE_CHECKING:
                assert isinstance(self._device, IotDimmer)
            if state.brightness == 0 or state.light_on is False:
                return await self._device.turn_off(transition=state.transition)
            elif state.brightness:
                # set_dimmer_transition will turn on the device
                return await self._device.set_dimmer_transition(
                    state.brightness, state.transition or 0
                )
            return await self._device.turn_on(transition=state.transition)
        else:
            transition = state.transition
            state_dict = asdict(state)
            state_dict = {k: v for k, v in state_dict.items() if v is not None}
            if "transition" in state_dict:
                del state_dict["transition"]
            state_dict["on_off"] = 1 if state.light_on is None else int(state.light_on)
            if state_dict.get("brightness") == 0:
                state_dict["on_off"] = 0
                del state_dict["brightness"]
            # If light on state not set default to on.
            elif state.light_on is None:
                state_dict["on_off"] = 1
            else:
                state_dict["on_off"] = int(state.light_on)
            # Remove the light_on from the dict
            state_dict.pop("light_on", None)
            return await bulb._set_light_state(state_dict, transition=transition)

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
            if device._is_dimmable:
                state.brightness = self.brightness
            if device._is_color:
                hsv = self.hsv
                state.hue = hsv.hue
                state.saturation = hsv.saturation
            if device._is_variable_color_temp:
                state.color_temp = self.color_temp
        self._light_state = state

    async def _deprecated_set_light_state(
        self, state: dict, *, transition: int | None = None
    ) -> dict:
        """Set the light state."""
        if (bulb := self._get_bulb_device()) is None:
            raise KasaException("Device does not support set_light_state")
        else:
            return await bulb._set_light_state(state, transition=transition)
