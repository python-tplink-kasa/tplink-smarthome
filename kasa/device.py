"""Interact with TPLink Smart Home devices.

Once you have a device via :ref:`Discovery <discover_target>` or
:ref:`Connect <connect_target>` you can start interacting with a device.

>>> from kasa import Discover
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.2",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>>

Most devices can be turned on and off

>>> await dev.turn_on()
>>> await dev.update()
>>> print(dev.is_on)
True

>>> await dev.turn_off()
>>> await dev.update()
>>> print(dev.is_on)
False

All devices provide several informational properties:

>>> dev.alias
Bedroom Lamp Plug
>>> dev.model
HS110
>>> dev.rssi
-71
>>> dev.mac
50:C7:BF:00:00:00

Some information can also be changed programmatically:

>>> await dev.set_alias("new alias")
>>> await dev.update()
>>> dev.alias
new alias

Devices support different functionality that are exposed via
:ref:`modules <module_target>` that you can access via :attr:`~kasa.Device.modules`:

>>> for module_name in dev.modules:
>>>     print(module_name)
Energy
schedule
usage
anti_theft
Time
cloud
Led

>>> led_module = dev.modules["Led"]
>>> print(led_module.led)
False
>>> await led_module.set_led(True)
>>> await dev.update()
>>> print(led_module.led)
True

Individual pieces of functionality are also exposed via :ref:`features <feature_target>`
which you can access via :attr:`~kasa.Device.features` and will only be present if
they are supported.

Features are similar to modules in that they provide functionality that may or may
not be present.

Whereas modules group functionality into a common interface, features expose a single
function that may or may not be part of a module.

The advantage of features is that they have a simple common interface of `id`, `name`,
`value` and `set_value` so no need to learn the module API.

They are useful if you want write code that dynamically adapts as new features are
added to the API.

>>> for feature_name in dev.features:
>>>     print(feature_name)
state
rssi
on_since
reboot
power
consumption_today
consumption_this_month
consumption_total
voltage
current
cloud_connection
led

>>> led_feature = dev.features["led"]
>>> print(led_feature.value)
True
>>> await led_feature.set_value(False)
>>> await dev.update()
>>> print(led_feature.value)
False
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Any, TypeAlias
from warnings import warn

from .credentials import Credentials as _Credentials
from .device_type import DeviceType
from .deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from .exceptions import KasaException
from .feature import Feature
from .module import Module
from .protocols import BaseProtocol, IotProtocol
from .transports import XorTransport

if TYPE_CHECKING:
    from .modulemapping import ModuleMapping, ModuleName


@dataclass
class WifiNetwork:
    """Wifi network container."""

    ssid: str
    key_type: int
    # These are available only on softaponboarding
    cipher_type: int | None = None
    bssid: str | None = None
    channel: int | None = None
    rssi: int | None = None

    # For SMART devices
    signal_level: int | None = None


_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Device Model Information."""

    short_name: str
    long_name: str
    brand: str
    device_family: str
    device_type: DeviceType
    hardware_version: str
    firmware_version: str
    firmware_build: str | None
    requires_auth: bool
    region: str | None


class Device(ABC):
    """Common device interface.

    Do not instantiate this class directly, instead get a device instance from
    :func:`Device.connect()`, :func:`Discover.discover()`
    or :func:`Discover.discover_single()`.
    """

    # All types required to create devices directly via connect are aliased here
    # to avoid consumers having to do multiple imports.

    #: The type of device
    Type: TypeAlias = DeviceType
    #: The credentials for authentication
    Credentials: TypeAlias = _Credentials
    #: Configuration for connecting to the device
    Config: TypeAlias = DeviceConfig
    #: The family of the device, e.g. SMART.KASASWITCH.
    Family: TypeAlias = DeviceFamily
    #: The encryption for the device, e.g. Klap or Aes
    EncryptionType: TypeAlias = DeviceEncryptionType
    #: The connection type for the device.
    ConnectionParameters: TypeAlias = DeviceConnectionParameters

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        """Create a new Device instance.

        :param str host: host name or IP address of the device
        :param DeviceConfig config: device configuration
        :param BaseProtocol protocol: protocol for communicating with the device
        """
        if config and protocol:
            protocol._transport._config = config
        self.protocol: BaseProtocol = protocol or IotProtocol(
            transport=XorTransport(config=config or DeviceConfig(host=host)),
        )
        self._last_update: dict[str, Any] = {}
        _LOGGER.debug("Initializing %s of type %s", host, type(self))
        self._device_type = DeviceType.Unknown
        # TODO: typing Any is just as using dict | None would require separate
        #       checks in accessors. the @updated_required decorator does not ensure
        #       mypy that these are not accessed incorrectly.
        self._discovery_info: dict[str, Any] | None = None

        self._features: dict[str, Feature] = {}
        self._parent: Device | None = None
        self._children: Mapping[str, Device] = {}

    @staticmethod
    async def connect(
        *,
        host: str | None = None,
        config: DeviceConfig | None = None,
    ) -> Device:
        """Connect to a single device by the given hostname or device configuration.

        This method avoids the UDP based discovery process and
        will connect directly to the device.

        It is generally preferred to avoid :func:`discover_single()` and
        use this function instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param config: Connection parameters to ensure the correct protocol
            and connection options are used.
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        from .device_factory import connect  # pylint: disable=import-outside-toplevel

        return await connect(host=host, config=config)  # type: ignore[arg-type]

    @abstractmethod
    async def update(self, update_children: bool = True) -> None:
        """Update the device."""

    async def disconnect(self) -> None:
        """Disconnect and close any underlying connection resources."""
        await self.protocol.close()

    @property
    @abstractmethod
    def modules(self) -> ModuleMapping[Module]:
        """Return the device modules."""

    @property
    @abstractmethod
    def is_on(self) -> bool:
        """Return true if the device is on."""

    @property
    def is_off(self) -> bool:
        """Return True if device is off."""
        return not self.is_on

    @abstractmethod
    async def turn_on(self, **kwargs) -> dict:
        """Turn on the device."""

    @abstractmethod
    async def turn_off(self, **kwargs) -> dict:
        """Turn off the device."""

    @abstractmethod
    async def set_state(self, on: bool) -> dict:
        """Set the device state to *on*.

        This allows turning the device on and off.
        See also *turn_off* and *turn_on*.
        """

    @property
    def host(self) -> str:
        """The device host."""
        return self.protocol._transport._host

    @host.setter
    def host(self, value: str) -> None:
        """Set the device host.

        Generally used by discovery to set the hostname after ip discovery.
        """
        self.protocol._transport._host = value
        self.protocol._transport._config.host = value

    @property
    def port(self) -> int:
        """The device port."""
        return self.protocol._transport._port

    @property
    def credentials(self) -> _Credentials | None:
        """The device credentials."""
        return self.protocol._transport._credentials

    @property
    def credentials_hash(self) -> str | None:
        """The protocol specific hash of the credentials the device is using."""
        return self.protocol._transport.credentials_hash

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return self._device_type

    @abstractmethod
    def update_from_discover_info(self, info: dict) -> None:
        """Update state from info from the discover call."""

    @property
    def config(self) -> DeviceConfig:
        """Return the device configuration."""
        return self.protocol.config

    @property
    @abstractmethod
    def model(self) -> str:
        """Returns the device model."""

    @property
    def region(self) -> str | None:
        """Returns the device region."""
        return self.device_info.region

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return self._get_device_info(self._last_update, self._discovery_info)

    @staticmethod
    @abstractmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get device info."""

    @property
    @abstractmethod
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""

    async def _raw_query(self, request: str | dict) -> dict:
        """Send a raw query to the device."""
        return await self.protocol.query(request=request)

    @property
    def parent(self) -> Device | None:
        """Return the parent on child devices."""
        return self._parent

    @property
    def children(self) -> Sequence[Device]:
        """Returns the child devices."""
        return list(self._children.values())

    def get_child_device(self, name_or_id: str) -> Device | None:
        """Return child device by its device_id or alias."""
        if name_or_id in self._children:
            return self._children[name_or_id]
        name_lower = name_or_id.lower()
        for child in self.children:
            if child.alias and child.alias.lower() == name_lower:
                return child
        return None

    @property
    @abstractmethod
    def sys_info(self) -> dict[str, Any]:
        """Returns the device info."""

    def get_plug_by_name(self, name: str) -> Device:
        """Return child device for the given name."""
        for p in self.children:
            if p.alias == name:
                return p

        raise KasaException(f"Device has no child with {name}")

    def get_plug_by_index(self, index: int) -> Device:
        """Return child device for the given index."""
        if index + 1 > len(self.children) or index < 0:
            raise KasaException(
                f"Invalid index {index}, device has {len(self.children)} plugs"
            )
        return self.children[index]

    @property
    @abstractmethod
    def time(self) -> datetime:
        """Return the time."""

    @property
    @abstractmethod
    def timezone(self) -> tzinfo:
        """Return the timezone and time_difference."""

    @property
    @abstractmethod
    def hw_info(self) -> dict:
        """Return hardware info for the device."""

    @property
    @abstractmethod
    def location(self) -> dict:
        """Return the device location."""

    @property
    @abstractmethod
    def rssi(self) -> int | None:
        """Return the rssi."""

    @property
    @abstractmethod
    def mac(self) -> str:
        """Return the mac formatted with colons."""

    @property
    @abstractmethod
    def device_id(self) -> str:
        """Return the device id."""

    @property
    @abstractmethod
    def internal_state(self) -> dict:
        """Return all the internal state data."""

    @property
    def state_information(self) -> dict[str, Any]:
        """Return available features and their values."""
        return {feat.name: feat.value for feat in self._features.values()}

    @property
    def features(self) -> dict[str, Feature]:
        """Return the list of supported features."""
        return self._features

    def _add_feature(self, feature: Feature) -> None:
        """Add a new feature to the device."""
        if feature.id in self._features:
            raise KasaException(f"Duplicate feature id {feature.id}")
        assert feature.id is not None  # TODO: hack for typing # noqa: S101
        self._features[feature.id] = feature

    @property
    @abstractmethod
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""

    @property
    @abstractmethod
    def on_since(self) -> datetime | None:
        """Return the time that the device was turned on or None if turned off.

        This returns a cached value if the device reported value difference is under
        five seconds to avoid device-caused jitter.
        """

    @abstractmethod
    async def wifi_scan(self) -> list[WifiNetwork]:
        """Scan for available wifi networks."""

    @abstractmethod
    async def wifi_join(
        self, ssid: str, password: str, keytype: str = "wpa2_psk"
    ) -> dict:
        """Join the given wifi network."""

    @abstractmethod
    async def set_alias(self, alias: str) -> dict:
        """Set the device name (alias)."""

    @abstractmethod
    async def reboot(self, delay: int = 1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.
        """

    @abstractmethod
    async def factory_reset(self) -> None:
        """Reset device back to factory settings.

        Note, this does not downgrade the firmware.
        """

    def __repr__(self) -> str:
        update_needed = " - update() needed" if not self._last_update else ""
        if not self._last_update and not self._discovery_info:
            return f"<{self.device_type} at {self.host}{update_needed}>"
        return (
            f"<{self.device_type} at {self.host} -"
            f" {self.alias} ({self.model}){update_needed}>"
        )

    _deprecated_device_type_attributes = {
        # is_type
        "is_bulb": (None, DeviceType.Bulb),
        "is_dimmer": (None, DeviceType.Dimmer),
        "is_light_strip": (None, DeviceType.LightStrip),
        "is_plug": (None, DeviceType.Plug),
        "is_wallswitch": (None, DeviceType.WallSwitch),
        "is_strip": (None, DeviceType.Strip),
        "is_strip_socket": (None, DeviceType.StripSocket),
    }

    def _get_replacing_attr(
        self, module_name: ModuleName | None, *attrs: Any
    ) -> str | None:
        # If module name is None check self
        if not module_name:
            check = self
        elif (check := self.modules.get(module_name)) is None:
            return None

        for attr in attrs:
            # Use dir() as opposed to hasattr() to avoid raising exceptions
            # from properties
            if attr in dir(check):
                return attr

        return None

    def _get_deprecated_callable_attribute(self, name: str) -> Any | None:
        vals: dict[str, tuple[ModuleName, Callable[[Any], Any], str]] = {
            "is_dimmable": (
                Module.Light,
                lambda c: c.has_feature("brightness"),
                'light_module.has_feature("brightness")',
            ),
            "is_color": (
                Module.Light,
                lambda c: c.has_feature("hsv"),
                'light_module.has_feature("hsv")',
            ),
            "is_variable_color_temp": (
                Module.Light,
                lambda c: c.has_feature("color_temp"),
                'light_module.has_feature("color_temp")',
            ),
            "valid_temperature_range": (
                Module.Light,
                lambda c: c._deprecated_valid_temperature_range(),
                'minimum and maximum value of get_feature("color_temp")',
            ),
            "has_effects": (
                Module.Light,
                lambda c: Module.LightEffect in c._device.modules,
                "Module.LightEffect in device.modules",
            ),
        }
        if mod_call_msg := vals.get(name):
            mod, call, msg = mod_call_msg
            msg = f"{name} is deprecated, use: {msg} instead"
            warn(msg, DeprecationWarning, stacklevel=2)
            if (module := self.modules.get(mod)) is None:
                raise AttributeError(f"Device has no attribute {name!r}")
            return call(module)

        return None

    _deprecated_other_attributes = {
        # light attributes
        "brightness": (Module.Light, ["brightness"]),
        "set_brightness": (Module.Light, ["set_brightness"]),
        "hsv": (Module.Light, ["hsv"]),
        "set_hsv": (Module.Light, ["set_hsv"]),
        "color_temp": (Module.Light, ["color_temp"]),
        "set_color_temp": (Module.Light, ["set_color_temp"]),
        "_deprecated_set_light_state": (Module.Light, ["has_effects"]),
        # led attributes
        "led": (Module.Led, ["led"]),
        "set_led": (Module.Led, ["set_led"]),
        # light effect attributes
        # The return values for effect is a str instead of dict so the lightstrip
        # modules have a _deprecated method to return the value as before.
        "effect": (Module.LightEffect, ["_deprecated_effect", "effect"]),
        # The return values for effect_list includes the Off effect so the lightstrip
        # modules have a _deprecated method to return the values as before.
        "effect_list": (Module.LightEffect, ["_deprecated_effect_list", "effect_list"]),
        "set_effect": (Module.LightEffect, ["set_effect"]),
        "set_custom_effect": (Module.LightEffect, ["set_custom_effect"]),
        # light preset attributes
        "presets": (Module.LightPreset, ["_deprecated_presets", "preset_states_list"]),
        "save_preset": (Module.LightPreset, ["_deprecated_save_preset"]),
        # Emeter attribues
        "get_emeter_realtime": (Module.Energy, ["get_status"]),
        "emeter_realtime": (Module.Energy, ["status"]),
        "emeter_today": (Module.Energy, ["consumption_today"]),
        "emeter_this_month": (Module.Energy, ["consumption_this_month"]),
        "current_consumption": (Module.Energy, ["power"]),
        "get_emeter_daily": (Module.Energy, ["get_daily_stats"]),
        "get_emeter_monthly": (Module.Energy, ["get_monthly_stats"]),
        # Other attributes
        "supported_modules": (None, ["modules"]),
    }

    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            # is_device_type
            if dep_device_type_attr := self._deprecated_device_type_attributes.get(
                name
            ):
                msg = f"{name} is deprecated, use device_type property instead"
                warn(msg, DeprecationWarning, stacklevel=2)
                return self.device_type == dep_device_type_attr[1]
            # callable
            if (result := self._get_deprecated_callable_attribute(name)) is not None:
                return result
            # Other deprecated attributes
            if (dep_attr := self._deprecated_other_attributes.get(name)) and (
                (replacing_attr := self._get_replacing_attr(dep_attr[0], *dep_attr[1]))
                is not None
            ):
                mod = dep_attr[0]
                dev_or_mod = self.modules[mod] if mod else self
                replacing = f"Module.{mod} in device.modules" if mod else replacing_attr
                msg = f"{name} is deprecated, use: {replacing} instead"
                warn(msg, DeprecationWarning, stacklevel=2)
                return getattr(dev_or_mod, replacing_attr)
            raise AttributeError(f"Device has no attribute {name!r}")
