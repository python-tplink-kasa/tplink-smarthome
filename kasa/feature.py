"""Interact with feature.

Features are implemented by devices to represent individual pieces of functionality like
state, time, firmware.

>>> from kasa import Discover, Module
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.3",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>> await dev.update()
>>> print(dev.alias)
Living Room Bulb

Features allow for instrospection and can be interacted with as new features are added
to the API:

>>> for feature_id, feature in dev.features.items():
>>>     print(f"{feature.name} ({feature_id}): {feature.value}")
Device ID (device_id): 0000000000000000000000000000000000000000
State (state): True
Signal Level (signal_level): 2
RSSI (rssi): -52
SSID (ssid): #MASKED_SSID#
Reboot (reboot): <Action>
Brightness (brightness): 100
Cloud connection (cloud_connection): True
HSV (hsv): HSV(hue=0, saturation=100, value=100)
Color temperature (color_temperature): 2700
Auto update enabled (auto_update_enabled): False
Update available (update_available): None
Current firmware version (current_firmware_version): 1.1.6 Build 240130 Rel.173828
Available firmware version (available_firmware_version): None
Check latest firmware (check_latest_firmware): <Action>
Light effect (light_effect): Off
Light preset (light_preset): Not set
Smooth transition on (smooth_transition_on): 2
Smooth transition off (smooth_transition_off): 2
Overheated (overheated): False
Device time (device_time): 2024-02-23 02:40:15+01:00

To see whether a device supports a feature, check for the existence of it:

>>> if feature := dev.features.get("brightness"):
>>>     print(feature.value)
100

You can update the value of a feature

>>> await feature.set_value(50)
>>> await dev.update()
>>> print(feature.value)
50

Features have types that can be used for introspection:

>>> feature = dev.features["light_preset"]
>>> print(feature.type)
Type.Choice

>>> print(feature.choices)
['Not set', 'Light preset 1', 'Light preset 2', 'Light preset 3',\
 'Light preset 4', 'Light preset 5', 'Light preset 6', 'Light preset 7']
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum, auto
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class Feature:
    """Feature defines a generic interface for device features."""

    class Type(Enum):
        """Type to help decide how to present the feature."""

        #: Sensor is an informative read-only value
        Sensor = auto()
        #: BinarySensor is a read-only boolean
        BinarySensor = auto()
        #: Switch is a boolean setting
        Switch = auto()
        #: Action triggers some action on device
        Action = auto()
        #: Number defines a numeric setting
        #: See :attr:`range_getter`, :attr:`Feature.minimum_value`,
        #: and :attr:`maximum_value`
        Number = auto()
        #: Choice defines a setting with pre-defined values
        Choice = auto()
        Unknown = -1

    # Aliases for easy access
    Sensor = Type.Sensor
    BinarySensor = Type.BinarySensor
    Switch = Type.Switch
    Action = Type.Action
    Number = Type.Number
    Choice = Type.Choice

    DEFAULT_MAX = 2**16  # Arbitrary max

    class Category(Enum):
        """Category hint to allow feature grouping."""

        #: Primary features control the device state directly.
        #: Examples include turning the device on/off, or adjusting its brightness.
        Primary = auto()
        #: Config features change device behavior without immediate state changes.
        Config = auto()
        #: Informative/sensor features deliver some potentially interesting information.
        Info = auto()
        #: Debug features deliver more verbose information then informative features.
        #: You may want to hide these per default to avoid cluttering your UI.
        Debug = auto()
        #: The default category if none is specified.
        Unset = -1

    #: Device instance required for getting and setting values
    device: Device
    #: Identifier
    id: str
    #: User-friendly short description
    name: str
    #: Type of the feature
    type: Feature.Type
    #: Callable or name of the property that allows accessing the value
    attribute_getter: str | Callable | None = None
    #: Callable coroutine or name of the method that allows changing the value
    attribute_setter: str | Callable[..., Coroutine[Any, Any, Any]] | None = None
    #: Container storing the data, this overrides 'device' for getters
    container: Any = None
    #: Icon suggestion
    icon: str | None = None
    #: Attribute containing the name of the unit getter property.
    #: If set, this property will be used to get the *unit*.
    unit_getter: str | Callable[[], str] | None = None
    #: Category hint for downstreams
    category: Feature.Category = Category.Unset

    # Display hints offer a way suggest how the value should be shown to users
    #: Hint to help rounding the sensor values to given after-comma digits
    precision_hint: int | None = None

    #: Attribute containing the name of the range getter property.
    #: If set, this property will be used to set *minimum_value* and *maximum_value*.
    range_getter: str | Callable[[], tuple[int, int]] | None = None

    #: Attribute name of the choices getter property.
    #: If set, this property will be used to get *choices*.
    choices_getter: str | Callable[[], list[str]] | None = None

    def __post_init__(self) -> None:
        """Handle late-binding of members."""
        # Populate minimum & maximum values, if range_getter is given
        self._container = self.container if self.container is not None else self.device

        # Set the category, if unset
        if self.category is Feature.Category.Unset:
            if self.attribute_setter:
                self.category = Feature.Category.Config
            else:
                self.category = Feature.Category.Info

        if self.type in (
            Feature.Type.Sensor,
            Feature.Type.BinarySensor,
        ):
            if self.category == Feature.Category.Config:
                raise ValueError(
                    f"Invalid type for configurable feature: {self.name} ({self.id}):"
                    f" {self.type}"
                )
            elif self.attribute_setter is not None:
                raise ValueError(
                    f"Read-only feat defines attribute_setter: {self.name} ({self.id}):"
                )

    def _get_property_value(self, getter: str | Callable | None) -> Any:
        if getter is None:
            return None
        if isinstance(getter, str):
            return getattr(self._container, getter)
        if callable(getter):
            return getter(self._container)
        raise ValueError("Invalid getter: %s", getter)  # pragma: no cover

    @property
    def choices(self) -> list[str] | None:
        """List of choices."""
        return self._get_property_value(self.choices_getter)

    @property
    def unit(self) -> str | None:
        """Unit if applicable."""
        return self._get_property_value(self.unit_getter)

    @cached_property
    def range(self) -> tuple[int, int] | None:
        """Range of values if applicable."""
        return self._get_property_value(self.range_getter)

    @property
    def maximum_value(self) -> int:
        """Maximum value."""
        if range := self.range:
            return range[1]
        return self.DEFAULT_MAX

    @property
    def minimum_value(self) -> int:
        """Minimum value."""
        if range := self.range:
            return range[0]
        return 0

    @property
    def value(self) -> int | float | bool | str | Enum | None:
        """Return the current value."""
        if self.type == Feature.Type.Action:
            return "<Action>"
        if self.attribute_getter is None:
            raise ValueError("Not an action and no attribute_getter set")

        container = self.container if self.container is not None else self.device
        if callable(self.attribute_getter):
            return self.attribute_getter(container)
        return getattr(container, self.attribute_getter)

    async def set_value(self, value: int | float | bool | str | Enum | None) -> Any:
        """Set the value."""
        if self.attribute_setter is None:
            raise ValueError("Tried to set read-only feature.")
        if self.type == Feature.Type.Number:  # noqa: SIM102
            if not isinstance(value, int | float):
                raise ValueError("value must be a number")
            if value < self.minimum_value or value > self.maximum_value:
                raise ValueError(
                    f"Value {value} out of range "
                    f"[{self.minimum_value}, {self.maximum_value}]"
                )
        elif self.type == Feature.Type.Choice:  # noqa: SIM102
            if not self.choices or value not in self.choices:
                raise ValueError(
                    f"Unexpected value for {self.name}: {value}"
                    f" - allowed: {self.choices}"
                )

        if callable(self.attribute_setter):
            attribute_setter = self.attribute_setter
        else:
            container = self.container if self.container is not None else self.device
            attribute_setter = getattr(container, self.attribute_setter)

        if self.type == Feature.Type.Action:
            return await attribute_setter()

        return await attribute_setter(value)

    def __repr__(self) -> str:
        try:
            value = self.value
            choices = self.choices
        except Exception as ex:
            return f"Unable to read value ({self.id}): {ex}"

        if self.type == Feature.Type.Choice:
            if not isinstance(choices, list) or value not in choices:
                _LOGGER.warning(
                    "Invalid value for for choice %s (%s): %s not in %s",
                    self.name,
                    self.id,
                    value,
                    choices,
                )
                return (
                    f"{self.name} ({self.id}): invalid value '{value}' not in {choices}"
                )
            value = " ".join(
                [f"*{choice}*" if choice == value else choice for choice in choices]
            )
        if self.precision_hint is not None and isinstance(value, float):
            value = round(value, self.precision_hint)

        if isinstance(value, Enum):
            value = repr(value)
        s = f"{self.name} ({self.id}): {value}"
        if self.unit is not None:
            s += f" {self.unit}"

        if self.type == Feature.Type.Number:
            s += f" (range: {self.minimum_value}-{self.maximum_value})"

        return s
