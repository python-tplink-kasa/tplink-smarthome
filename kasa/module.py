"""Interact with modules.

Modules are implemented by devices to encapsulate sets of functionality like
Light, AutoOff, Firmware etc.

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

To see whether a device supports a group of functionality
check for the existence of the module:

>>> if light := dev.modules.get("Light"):
>>>     print(light.brightness)
100

.. include:: ../featureattributes.md
   :parser: myst_parser.sphinx_

To see whether a device supports specific functionality, you can check whether the
module has that feature:

>>> if light.has_feature("hsv"):
>>>     print(light.hsv)
HSV(hue=0, saturation=100, value=100)

If you know or expect the module to exist you can access by index:

>>> light_preset = dev.modules["LightPreset"]
>>> print(light_preset.preset_list)
['Not set', 'Light preset 1', 'Light preset 2', 'Light preset 3',\
 'Light preset 4', 'Light preset 5', 'Light preset 6', 'Light preset 7']

Modules support typing via the Module names in Module:

>>> from typing import reveal_type, TYPE_CHECKING
>>> light_effect = dev.modules.get("LightEffect")
>>> light_effect_typed = dev.modules.get(Module.LightEffect)
>>> if TYPE_CHECKING:
>>>     reveal_type(light_effect)  # Static checker will reveal: str
>>>     reveal_type(light_effect_typed)  # Static checker will reveal: LightEffect

"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cache
from typing import (
    TYPE_CHECKING,
    Final,
    TypeVar,
    get_type_hints,
)

from .exceptions import KasaException
from .feature import Feature
from .modulemapping import ModuleName

if TYPE_CHECKING:
    from . import interfaces
    from .device import Device
    from .iot import modules as iot
    from .smart import modules as smart
    from .smartcam import modules as smartcam

_LOGGER = logging.getLogger(__name__)

ModuleT = TypeVar("ModuleT", bound="Module")


class FeatureAttribute:
    """Class for annotating attributes bound to feature."""

    def __init__(self, feature_name: str | None = None) -> None:
        self.feature_name = feature_name

    def __repr__(self) -> str:
        return "FeatureAttribute"


class Module(ABC):
    """Base class implemention for all modules.

    The base classes should implement `query` to return the query they want to be
    executed during the regular update cycle.
    """

    # Common Modules
    Alarm: Final[ModuleName[interfaces.Alarm]] = ModuleName("Alarm")
    ChildSetup: Final[ModuleName[interfaces.ChildSetup]] = ModuleName("ChildSetup")
    Energy: Final[ModuleName[interfaces.Energy]] = ModuleName("Energy")
    Fan: Final[ModuleName[interfaces.Fan]] = ModuleName("Fan")
    LightEffect: Final[ModuleName[interfaces.LightEffect]] = ModuleName("LightEffect")
    Led: Final[ModuleName[interfaces.Led]] = ModuleName("Led")
    Light: Final[ModuleName[interfaces.Light]] = ModuleName("Light")
    LightPreset: Final[ModuleName[interfaces.LightPreset]] = ModuleName("LightPreset")
    Thermostat: Final[ModuleName[interfaces.Thermostat]] = ModuleName("Thermostat")
    Time: Final[ModuleName[interfaces.Time]] = ModuleName("Time")

    # IOT only Modules
    IotAmbientLight: Final[ModuleName[iot.AmbientLight]] = ModuleName("ambient")
    IotAntitheft: Final[ModuleName[iot.Antitheft]] = ModuleName("anti_theft")
    IotCountdown: Final[ModuleName[iot.Countdown]] = ModuleName("countdown")
    IotDimmer: Final[ModuleName[iot.Dimmer]] = ModuleName("dimmer")
    IotMotion: Final[ModuleName[iot.Motion]] = ModuleName("motion")
    IotSchedule: Final[ModuleName[iot.Schedule]] = ModuleName("schedule")
    IotUsage: Final[ModuleName[iot.Usage]] = ModuleName("usage")
    IotCloud: Final[ModuleName[iot.Cloud]] = ModuleName("cloud")
    IotTurnOnBehavior: Final[ModuleName[iot.TurnOnBehaviorModule]] = ModuleName(
        "turnonbehavior"
    )

    # SMART only Modules
    AutoOff: Final[ModuleName[smart.AutoOff]] = ModuleName("AutoOff")
    BatterySensor: Final[ModuleName[smart.BatterySensor]] = ModuleName("BatterySensor")
    Brightness: Final[ModuleName[smart.Brightness]] = ModuleName("Brightness")
    ChildDevice: Final[ModuleName[smart.ChildDevice]] = ModuleName("ChildDevice")
    Cloud: Final[ModuleName[smart.Cloud]] = ModuleName("Cloud")
    Color: Final[ModuleName[smart.Color]] = ModuleName("Color")
    ColorTemperature: Final[ModuleName[smart.ColorTemperature]] = ModuleName(
        "ColorTemperature"
    )
    ContactSensor: Final[ModuleName[smart.ContactSensor]] = ModuleName("ContactSensor")
    DeviceModule: Final[ModuleName[smart.DeviceModule]] = ModuleName("DeviceModule")
    Firmware: Final[ModuleName[smart.Firmware]] = ModuleName("Firmware")
    FrostProtection: Final[ModuleName[smart.FrostProtection]] = ModuleName(
        "FrostProtection"
    )
    HumiditySensor: Final[ModuleName[smart.HumiditySensor]] = ModuleName(
        "HumiditySensor"
    )
    LightTransition: Final[ModuleName[smart.LightTransition]] = ModuleName(
        "LightTransition"
    )
    MotionSensor: Final[ModuleName[smart.MotionSensor]] = ModuleName("MotionSensor")
    ReportMode: Final[ModuleName[smart.ReportMode]] = ModuleName("ReportMode")
    SmartLightEffect: Final[ModuleName[smart.SmartLightEffect]] = ModuleName(
        "LightEffect"
    )
    IotLightEffect: Final[ModuleName[iot.LightEffect]] = ModuleName("LightEffect")
    TemperatureSensor: Final[ModuleName[smart.TemperatureSensor]] = ModuleName(
        "TemperatureSensor"
    )
    TemperatureControl: Final[ModuleName[smart.TemperatureControl]] = ModuleName(
        "TemperatureControl"
    )
    WaterleakSensor: Final[ModuleName[smart.WaterleakSensor]] = ModuleName(
        "WaterleakSensor"
    )
    ChildProtection: Final[ModuleName[smart.ChildProtection]] = ModuleName(
        "ChildProtection"
    )
    ChildLock: Final[ModuleName[smart.ChildLock]] = ModuleName("ChildLock")
    TriggerLogs: Final[ModuleName[smart.TriggerLogs]] = ModuleName("TriggerLogs")
    PowerProtection: Final[ModuleName[smart.PowerProtection]] = ModuleName(
        "PowerProtection"
    )

    HomeKit: Final[ModuleName[smart.HomeKit]] = ModuleName("HomeKit")
    Matter: Final[ModuleName[smart.Matter]] = ModuleName("Matter")

    # SMARTCAM only modules
    Camera: Final[ModuleName[smartcam.Camera]] = ModuleName("Camera")
    LensMask: Final[ModuleName[smartcam.LensMask]] = ModuleName("LensMask")

    # Vacuum modules
    Clean: Final[ModuleName[smart.Clean]] = ModuleName("Clean")
    Consumables: Final[ModuleName[smart.Consumables]] = ModuleName("Consumables")
    Dustbin: Final[ModuleName[smart.Dustbin]] = ModuleName("Dustbin")
    Speaker: Final[ModuleName[smart.Speaker]] = ModuleName("Speaker")
    Mop: Final[ModuleName[smart.Mop]] = ModuleName("Mop")
    CleanRecords: Final[ModuleName[smart.CleanRecords]] = ModuleName("CleanRecords")

    def __init__(self, device: Device, module: str) -> None:
        self._device = device
        self._module = module
        self._module_features: dict[str, Feature] = {}

    @property
    def device(self) -> Device:
        """Return the device exposing the module."""
        return self._device

    @property
    def _all_features(self) -> dict[str, Feature]:
        """Get the features for this module and any sub modules."""
        return self._module_features

    def has_feature(self, attribute: str | property | Callable) -> bool:
        """Return True if the module attribute feature is supported."""
        return bool(self.get_feature(attribute))

    def get_feature(self, attribute: str | property | Callable) -> Feature | None:
        """Get Feature for a module attribute or None if not supported."""
        return _get_bound_feature(self, attribute)

    @abstractmethod
    def query(self) -> dict:
        """Query to execute during the update cycle.

        The inheriting modules implement this to include their wanted
        queries to the query that gets executed when Device.update() gets called.
        """

    @property
    @abstractmethod
    def data(self) -> dict:
        """Return the module specific raw data from the last update."""

    def _initialize_features(self) -> None:  # noqa: B027
        """Initialize features after the initial update.

        This can be implemented if features depend on module query responses.
        It will only be called once per module and will always be called
        after *_post_update_hook* has been called for every device module and its
        children's modules.
        """

    async def _post_update_hook(self) -> None:  # noqa: B027
        """Perform actions after a device update.

        This can be implemented if a module needs to perform actions each time
        the device has updated like generating collections for property access.
        It will be called after every update and will be called prior to
        *_initialize_features* on the first update.
        """

    def _add_feature(self, feature: Feature) -> None:
        """Add module feature."""
        id_ = feature.id
        if id_ in self._module_features:
            raise KasaException(f"Duplicate id detected {id_}")
        self._module_features[id_] = feature

    def __repr__(self) -> str:
        return (
            f"<Module {self.__class__.__name__} ({self._module})"
            f" for {self._device.host}>"
        )


def _get_feature_attribute(attribute: property | Callable) -> FeatureAttribute | None:
    """Check if an attribute is bound to a feature with FeatureAttribute."""
    if isinstance(attribute, property):
        hints = get_type_hints(attribute.fget, include_extras=True)
    else:
        hints = get_type_hints(attribute, include_extras=True)

    if (return_hints := hints.get("return")) and hasattr(return_hints, "__metadata__"):
        metadata = hints["return"].__metadata__
        for meta in metadata:
            if isinstance(meta, FeatureAttribute):
                return meta

    return None


@cache
def _get_bound_feature(
    module: Module, attribute: str | property | Callable
) -> Feature | None:
    """Get Feature for a bound property or None if not supported."""
    if not isinstance(attribute, str):
        if isinstance(attribute, property):
            # Properties have __name__ in 3.13 so this could be simplified
            # when only 3.13 supported
            attribute_name = attribute.fget.__name__  # type: ignore[union-attr]
        else:
            attribute_name = attribute.__name__
        attribute_callable = attribute
    else:
        if TYPE_CHECKING:
            assert isinstance(attribute, str)
        attribute_name = attribute
        attribute_callable = getattr(module.__class__, attribute, None)  # type: ignore[assignment]
        if not attribute_callable:
            raise KasaException(
                f"No attribute named {attribute_name} in "
                f"module {module.__class__.__name__}"
            )

    if not (fa := _get_feature_attribute(attribute_callable)):
        raise KasaException(
            f"Attribute {attribute_name} of module {module.__class__.__name__}"
            " is not bound to a feature"
        )

    # If a feature_name was passed to the FeatureAttribute use that to check
    # for the feature. Otherwise check the getters and setters in the features
    if fa.feature_name:
        return module._all_features.get(fa.feature_name)

    check = {attribute_name, attribute_callable}
    for feature in module._all_features.values():
        if (getter := feature.attribute_getter) and getter in check:
            return feature

        if (setter := feature.attribute_setter) and setter in check:
            return feature

    return None
