"""Python library supporting TP-Link Smart Home devices.

The communication protocol was reverse engineered by Lubomir Stroetmann and
Tobias Esser in 'Reverse Engineering the TP-Link HS110':
https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/

This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
Stroetmann which is licensed under the Apache License, Version 2.0.

You may obtain a copy of the license at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, cast
from warnings import warn

from ..device import Device, DeviceInfo, WifiNetwork
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..exceptions import KasaException
from ..feature import Feature
from ..module import Module
from ..modulemapping import ModuleMapping, ModuleName
from ..protocols import BaseProtocol
from .iotmodule import IotModule, merge
from .modules import Emeter

_LOGGER = logging.getLogger(__name__)


def requires_update(f: Callable) -> Any:
    """Indicate that `update` should be called before accessing this method."""  # noqa: D202
    if inspect.iscoroutinefunction(f):

        @functools.wraps(f)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            self = args[0]
            if not self._last_update and (
                self._sys_info is None or f.__name__ not in self._sys_info
            ):
                raise KasaException("You need to await update() to access the data")
            return await f(*args, **kwargs)

    else:

        @functools.wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self = args[0]
            if not self._last_update and (
                self._sys_info is None or f.__name__ not in self._sys_info
            ):
                raise KasaException("You need to await update() to access the data")
            return f(*args, **kwargs)

    f.requires_update = True  # type: ignore[attr-defined]
    return wrapped


@functools.lru_cache
def _parse_features(features: str) -> set[str]:
    """Parse features string."""
    return set(features.split(":"))


def _extract_sys_info(info: dict[str, Any]) -> dict[str, Any]:
    """Return the system info structure."""
    sysinfo_default = info.get("system", {}).get("get_sysinfo", {})
    sysinfo_nest = sysinfo_default.get("system", {})

    if len(sysinfo_nest) > len(sysinfo_default) and isinstance(sysinfo_nest, dict):
        return sysinfo_nest
    return sysinfo_default


class IotDevice(Device):
    """Base class for all supported device types.

    You don't usually want to initialize this class manually,
    but either use :class:`Discover` class, or use one of the subclasses:

    * :class:`IotPlug`
    * :class:`IotBulb`
    * :class:`IotStrip`
    * :class:`IotDimmer`
    * :class:`IotLightStrip`

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await update() separately.

    Errors reported by the device are raised as
    :class:`KasaException <kasa.exceptions.KasaException>`,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> dev = IotDevice("127.0.0.1")
        >>> asyncio.run(dev.update())

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

        >>> asyncio.run(dev.set_alias("new alias"))
        >>> asyncio.run(dev.set_mac("01:23:45:67:89:ab"))
        >>> asyncio.run(dev.update())
        >>> dev.alias
        new alias
        >>> dev.mac
        01:23:45:67:89:ab

        When initialized using discovery or using a subclass,
        you can check the type of the device:

        >>> dev.is_bulb
        False
        >>> dev.is_strip
        False
        >>> dev.is_plug
        True

        You can also get the hardware and software as a dict,
        or access the full device response:

        >>> dev.hw_info
        {'sw_ver': '1.2.5 Build 171213 Rel.101523',
         'hw_ver': '1.0',
         'mac': '01:23:45:67:89:ab',
         'type': 'IOT.SMARTPLUGSWITCH',
         'hwId': '00000000000000000000000000000000',
         'fwId': '00000000000000000000000000000000',
         'oemId': '00000000000000000000000000000000',
         'dev_name': 'Wi-Fi Smart Plug With Energy Monitoring'}
        >>> dev.sys_info

        All devices can be turned on and off:

        >>> asyncio.run(dev.turn_off())
        >>> asyncio.run(dev.turn_on())
        >>> asyncio.run(dev.update())
        >>> dev.is_on
        True

        Some devices provide energy consumption meter,
        and regular update will already fetch some information:

        >>> dev.has_emeter
        True
        >>> dev.emeter_realtime
        <EmeterStatus power=0.928511 voltage=231.067823 current=0.014937 total=55.139>
        >>> dev.emeter_today
        >>> dev.emeter_this_month

        You can also query the historical data (note that these needs to be awaited),
        keyed with month/day:

        >>> asyncio.run(dev.get_emeter_monthly(year=2016))
        {11: 1.089, 12: 1.582}
        >>> asyncio.run(dev.get_emeter_daily(year=2016, month=11))
        {24: 0.026, 25: 0.109}

    """

    emeter_type = "emeter"

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        """Create a new IotDevice instance."""
        super().__init__(host=host, config=config, protocol=protocol)

        self._sys_info: Any = None  # TODO: this is here to avoid changing tests
        self._supported_modules: dict[str | ModuleName[Module], IotModule] | None = None
        self._legacy_features: set[str] = set()
        self._children: Mapping[str, IotDevice] = {}
        self._modules: dict[str | ModuleName[Module], IotModule] = {}
        self._on_since: datetime | None = None

    @property
    def children(self) -> Sequence[IotDevice]:
        """Return list of children."""
        return list(self._children.values())

    @property
    @requires_update
    def modules(self) -> ModuleMapping[IotModule]:
        """Return the device modules."""
        if TYPE_CHECKING:
            return cast(ModuleMapping[IotModule], self._supported_modules)
        return self._supported_modules

    def add_module(self, name: str | ModuleName[Module], module: IotModule) -> None:
        """Register a module."""
        if name in self._modules:
            _LOGGER.debug("Module %s already registered, ignoring...", name)
            return

        _LOGGER.debug("Adding module %s", module)
        self._modules[name] = module

    def _create_request(
        self,
        target: str,
        cmd: str,
        arg: dict | None = None,
        child_ids: list | None = None,
    ) -> dict:
        if arg is None:
            arg = {}
        request: dict[str, Any] = {target: {cmd: arg}}
        if child_ids is not None:
            request = {"context": {"child_ids": child_ids}, target: {cmd: arg}}

        return request

    def _verify_emeter(self) -> None:
        """Raise an exception if there is no emeter."""
        if not self.has_emeter:
            raise KasaException("Device has no emeter")
        if self.emeter_type not in self._last_update:
            raise KasaException("update() required prior accessing emeter")

    async def _query_helper(
        self,
        target: str,
        cmd: str,
        arg: dict | None = None,
        child_ids: list | None = None,
    ) -> dict:
        """Query device, return results or raise an exception.

        :param target: Target system {system, time, emeter, ..}
        :param cmd: Command to execute
        :param arg: payload dict to be send to the device
        :param child_ids: ids of child devices
        :return: Unwrapped result for the call.
        """
        request = self._create_request(target, cmd, arg, child_ids)

        try:
            response = await self._raw_query(request=request)
        except Exception as ex:
            raise KasaException(f"Communication error on {target}:{cmd}") from ex

        if target not in response:
            raise KasaException(f"No required {target} in response: {response}")

        result = response[target]
        if "err_code" in result and result["err_code"] != 0:
            raise KasaException(f"Error on {target}.{cmd}: {result}")

        if cmd not in result:
            raise KasaException(f"No command in response: {response}")
        result = result[cmd]
        if "err_code" in result and result["err_code"] != 0:
            raise KasaException(f"Error on {target} {cmd}: {result}")

        if "err_code" in result:
            del result["err_code"]

        return result

    @property  # type: ignore
    @requires_update
    def features(self) -> dict[str, Feature]:
        """Return a set of features that the device supports."""
        return self._features

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return True if device has an energy meter."""
        return "ENE" in self._legacy_features

    async def get_sys_info(self) -> dict[str, Any]:
        """Retrieve system information."""
        return await self._query_helper("system", "get_sysinfo")

    async def update(self, update_children: bool = True) -> None:
        """Query the device to update the data.

        Needed for properties that are decorated with `requires_update`.
        """
        req = {}
        req.update(self._create_request("system", "get_sysinfo"))

        # If this is the initial update, check only for the sysinfo
        # This is necessary as some devices crash on unexpected modules
        # See #105, #120, #161
        if not self._last_update:
            _LOGGER.debug("Performing the initial update to obtain sysinfo")
            response = await self.protocol.query(req)
            self._last_update = response
            self._set_sys_info(_extract_sys_info(response))

        if not self._modules:
            await self._initialize_modules()

        await self._modular_update(req)

        self._set_sys_info(_extract_sys_info(self._last_update))
        for module in self._modules.values():
            await module._post_update_hook()

        if not self._features:
            await self._initialize_features()

    async def _initialize_modules(self) -> None:
        """Initialize modules not added in init."""
        if self.has_emeter:
            _LOGGER.debug(
                "The device has emeter, querying its information along sysinfo"
            )
            self.add_module(Module.Energy, Emeter(self, self.emeter_type))

    async def _initialize_features(self) -> None:
        """Initialize common features."""
        self._add_feature(
            Feature(
                self,
                id="state",
                name="State",
                attribute_getter="is_on",
                attribute_setter="set_state",
                type=Feature.Type.Switch,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device=self,
                id="rssi",
                name="RSSI",
                attribute_getter="rssi",
                icon="mdi:signal",
                unit_getter=lambda: "dBm",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        # iot strips calculate on_since from the children
        if "on_time" in self._sys_info or self.device_type == Device.Type.Strip:
            self._add_feature(
                Feature(
                    device=self,
                    id="on_since",
                    name="On since",
                    attribute_getter="on_since",
                    icon="mdi:clock",
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

        self._add_feature(
            Feature(
                device=self,
                id="reboot",
                name="Reboot",
                attribute_setter="reboot",
                icon="mdi:restart",
                category=Feature.Category.Debug,
                type=Feature.Type.Action,
            )
        )

        for module in self.modules.values():
            module._initialize_features()
            for module_feat in module._module_features.values():
                self._add_feature(module_feat)

    async def _modular_update(self, req: dict) -> None:
        """Execute an update query."""
        request_list = []
        est_response_size = 1024 if "system" in req else 0
        for module in self._modules.values():
            if not module.is_supported:
                _LOGGER.debug("Module %s not supported, skipping", module)
                continue

            est_response_size += module.estimated_query_response_size
            if est_response_size > self.max_device_response_size:
                request_list.append(req)
                req = {}
                est_response_size = module.estimated_query_response_size

            q = module.query()
            _LOGGER.debug("Adding query for %s: %s", module, q)
            req = merge(req, q)
        request_list.append(req)

        responses = [
            await self.protocol.query(request) for request in request_list if request
        ]

        # Preserve the last update and merge
        # responses on top of it so we remember
        # which modules are not supported, otherwise
        # every other update will query for them
        update: dict = self._last_update.copy() if self._last_update else {}
        for response in responses:
            for k, v in response.items():
                # The same module could have results in different responses
                # i.e. smartlife.iot.common.schedule for Usage and
                # Schedule, so need to call update(**v) here. If a module is
                # not supported the response
                # {'err_code': -1, 'err_msg': 'module not support'}
                # become top level key/values of the response so check for dict
                if isinstance(v, dict):
                    update.setdefault(k, {}).update(**v)
        self._last_update = update

        # IOT modules are added as default but could be unsupported post first update
        if self._supported_modules is None:
            supported = {}
            for module_name, module in self._modules.items():
                if module.is_supported:
                    supported[module_name] = module

            self._supported_modules = supported

    def update_from_discover_info(self, info: dict[str, Any]) -> None:
        """Update state from info from the discover call."""
        self._discovery_info = info
        if "system" in info and (sys_info := info["system"].get("get_sysinfo")):
            self._last_update = info
            self._set_sys_info(sys_info)
        else:
            # This allows setting of some info properties directly
            # from partial discovery info that will then be found
            # by the requires_update decorator
            discovery_model = info["device_model"]
            no_region_model, _, _ = discovery_model.partition("(")
            self._set_sys_info({**info, "model": no_region_model})

    def _set_sys_info(self, sys_info: dict[str, Any]) -> None:
        """Set sys_info."""
        self._sys_info = sys_info
        if features := sys_info.get("feature"):
            self._legacy_features = _parse_features(features)

    @property  # type: ignore
    @requires_update
    def sys_info(self) -> dict[str, Any]:
        """
        Return system information.

        Do not call this function from within the SmartDevice
        class itself as @requires_update will be affected for other properties.
        """
        return self._sys_info  # type: ignore

    @property
    @requires_update
    def model(self) -> str:
        """Returns the device model."""
        if self._last_update:
            return self.device_info.short_name
        return self._sys_info["model"]

    @property  # type: ignore
    def alias(self) -> str | None:
        """Return device name (alias)."""
        sys_info = self._sys_info
        return sys_info.get("alias") if sys_info else None

    async def set_alias(self, alias: str) -> dict:
        """Set the device name (alias)."""
        return await self._query_helper("system", "set_dev_alias", {"alias": alias})

    @property
    @requires_update
    def time(self) -> datetime:
        """Return current time from the device."""
        return self.modules[Module.Time].time

    @property
    @requires_update
    def timezone(self) -> tzinfo:
        """Return the current timezone."""
        return self.modules[Module.Time].timezone

    async def get_time(self) -> datetime:
        """Return current time from the device, if available."""
        msg = "Use `time` property instead, this call will be removed in the future."
        warn(msg, DeprecationWarning, stacklevel=2)
        return self.time

    async def get_timezone(self) -> tzinfo:
        """Return timezone information."""
        msg = (
            "Use `timezone` property instead, this call will be removed in the future."
        )
        warn(msg, DeprecationWarning, stacklevel=2)
        return self.timezone

    @property  # type: ignore
    @requires_update
    def hw_info(self) -> dict:
        """Return hardware information.

        This returns just a selection of sysinfo keys that are related to hardware.
        """
        keys = [
            "sw_ver",
            "hw_ver",
            "mac",
            "mic_mac",
            "type",
            "mic_type",
            "hwId",
            "fwId",
            "oemId",
            "dev_name",
        ]
        sys_info = self._sys_info
        return {key: sys_info[key] for key in keys if key in sys_info}

    @property  # type: ignore
    @requires_update
    def location(self) -> dict:
        """Return geographical location."""
        sys_info = self._sys_info
        loc = {"latitude": None, "longitude": None}

        if "latitude" in sys_info and "longitude" in sys_info:
            loc["latitude"] = sys_info["latitude"]
            loc["longitude"] = sys_info["longitude"]
        elif "latitude_i" in sys_info and "longitude_i" in sys_info:
            loc["latitude"] = sys_info["latitude_i"] / 10000
            loc["longitude"] = sys_info["longitude_i"] / 10000
        else:
            _LOGGER.debug("Unsupported device location.")

        return loc

    @property  # type: ignore
    @requires_update
    def rssi(self) -> int | None:
        """Return WiFi signal strength (rssi)."""
        rssi = self._sys_info.get("rssi")
        return None if rssi is None else int(rssi)

    @property  # type: ignore
    @requires_update
    def mac(self) -> str:
        """Return mac address.

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        """
        sys_info = self._sys_info
        mac = sys_info.get("mac", sys_info.get("mic_mac"))
        if not mac:
            raise KasaException(
                "Unknown mac, please submit a bug report with sys_info output."
            )
        mac = mac.replace("-", ":")
        # Format a mac that has no colons (usually from mic_mac field)
        if ":" not in mac:
            mac = ":".join(format(s, "02x") for s in bytes.fromhex(mac))

        return mac

    async def set_mac(self, mac: str) -> dict:
        """Set the mac address.

        :param str mac: mac in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        """
        return await self._query_helper("system", "set_mac_addr", {"mac": mac})

    async def reboot(self, delay: int = 1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.
        """
        await self._query_helper("system", "reboot", {"delay": delay})

    async def factory_reset(self) -> None:
        """Reset device back to factory settings.

        Note, this does not downgrade the firmware.
        """
        await self._query_helper("system", "reset")

    async def turn_off(self, **kwargs) -> dict:
        """Turn off the device."""
        raise NotImplementedError("Device subclass needs to implement this.")

    async def turn_on(self, **kwargs) -> dict:
        """Turn device on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return True if the device is on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    async def set_state(self, on: bool) -> dict:
        """Set the device state."""
        if on:
            return await self.turn_on()
        else:
            return await self.turn_off()

    @property  # type: ignore
    @requires_update
    def on_since(self) -> datetime | None:
        """Return the time that the device was turned on or None if turned off.

        This returns a cached value if the device reported value difference is under
        five seconds to avoid device-caused jitter.
        """
        if self.is_off or "on_time" not in self._sys_info:
            self._on_since = None
            return None

        on_time = self._sys_info["on_time"]

        on_since = self.time - timedelta(seconds=on_time)
        if not self._on_since or timedelta(
            seconds=0
        ) < on_since - self._on_since > timedelta(seconds=5):
            self._on_since = on_since
        return self._on_since

    @property  # type: ignore
    @requires_update
    def device_id(self) -> str:
        """Return unique ID for the device.

        If not overridden, this is the MAC address of the device.
        Individual sockets on strips will override this.
        """
        return self.mac

    async def wifi_scan(self) -> list[WifiNetwork]:  # noqa: D202
        """Scan for available wifi networks."""

        async def _scan(target: str) -> dict:
            return await self._query_helper(target, "get_scaninfo", {"refresh": 1})

        try:
            info = await _scan("netif")
        except KasaException as ex:
            _LOGGER.debug(
                "Unable to scan using 'netif', retrying with 'softaponboarding': %s", ex
            )
            info = await _scan("smartlife.iot.common.softaponboarding")

        if "ap_list" not in info:
            raise KasaException(f"Invalid response for wifi scan: {info}")

        return [WifiNetwork(**x) for x in info["ap_list"]]

    async def wifi_join(self, ssid: str, password: str, keytype: str = "3") -> dict:  # noqa: D202
        """Join the given wifi network.

        If joining the network fails, the device will return to AP mode after a while.
        """

        async def _join(target: str, payload: dict) -> dict:
            return await self._query_helper(target, "set_stainfo", payload)

        try:
            keytype = int(keytype)
        except ValueError:
            match keytype.lower():
                case "open":
                    keytype = 0
                case "wep":
                    keytype = 1
                case "wpa":
                    keytype = 2
                case "wpa2":
                    keytype = 3
                case "wpa3":
                    keytype = 4
                case _:
                    raise KasaException(f"Unknown network keytype: {keytype}")
        payload = {"ssid": ssid, "password": password, "key_type": keytype}
        try:
            return await _join("netif", payload)
        except KasaException as ex:
            _LOGGER.debug(
                "Unable to join using 'netif', retrying with 'softaponboarding': %s", ex
            )
            return await _join("smartlife.iot.common.softaponboarding", payload)

    @property
    def max_device_response_size(self) -> int:
        """Returns the maximum response size the device can safely construct."""
        return 16 * 1024

    @property
    def internal_state(self) -> Any:
        """Return the internal state of the instance.

        The returned object contains the raw results from the last update call.
        This should only be used for debugging purposes.
        """
        return self._last_update or self._discovery_info

    @staticmethod
    def _get_device_type_from_sys_info(info: dict[str, Any]) -> DeviceType:
        """Find SmartDevice subclass for device described by passed data."""
        if "system" in info.get("system", {}).get("get_sysinfo", {}):
            return DeviceType.Camera

        if "system" not in info or "get_sysinfo" not in info["system"]:
            raise KasaException("No 'system' or 'get_sysinfo' in response")

        sysinfo: dict[str, Any] = _extract_sys_info(info)
        type_: str | None = sysinfo.get("type", sysinfo.get("mic_type"))
        if type_ is None:
            raise KasaException("Unable to find the device type field!")

        if "dev_name" in sysinfo and "Dimmer" in sysinfo["dev_name"]:
            return DeviceType.Dimmer

        if "smartplug" in type_.lower():
            if "children" in sysinfo:
                return DeviceType.Strip
            if (dev_name := sysinfo.get("dev_name")) and "light" in dev_name.lower():
                return DeviceType.WallSwitch
            return DeviceType.Plug

        if "smartbulb" in type_.lower():
            if "length" in sysinfo:  # strips have length
                return DeviceType.LightStrip

            return DeviceType.Bulb

        _LOGGER.warning("Unknown device type %s, falling back to plug", type_)
        return DeviceType.Plug

    @staticmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get model information for a device."""
        sys_info = _extract_sys_info(info)

        # Get model and region info
        region = None
        device_model = sys_info["model"]
        long_name, _, region = device_model.partition("(")
        if region:  # All iot devices have region but just in case
            region = region.replace(")", "")

        # Get other info
        device_family = sys_info.get("type", sys_info.get("mic_type"))
        device_type = IotDevice._get_device_type_from_sys_info(info)
        fw_version_full = sys_info["sw_ver"]
        if " " in fw_version_full:
            firmware_version, firmware_build = fw_version_full.split(" ", maxsplit=1)
        else:
            firmware_version, firmware_build = fw_version_full, None
        auth = bool(discovery_info and ("mgt_encrypt_schm" in discovery_info))

        return DeviceInfo(
            short_name=long_name,
            long_name=long_name,
            brand="kasa",
            device_family=device_family,
            device_type=device_type,
            hardware_version=sys_info["hw_ver"],
            firmware_version=firmware_version,
            firmware_build=firmware_build,
            requires_auth=auth,
            region=region,
        )
