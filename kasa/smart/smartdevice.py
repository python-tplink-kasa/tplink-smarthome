"""Module for a SMART device."""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from ..device import Device, DeviceInfo, WifiNetwork
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..exceptions import AuthenticationError, DeviceError, KasaException, SmartErrorCode
from ..feature import Feature
from ..module import Module
from ..modulemapping import ModuleMapping, ModuleName
from ..protocols import SmartProtocol
from ..transports import AesTransport
from .modules import (
    ChildDevice,
    Cloud,
    DeviceModule,
    Firmware,
    Light,
    Thermostat,
    Time,
)
from .smartmodule import SmartModule

if TYPE_CHECKING:
    from .smartchilddevice import SmartChildDevice
_LOGGER = logging.getLogger(__name__)


# List of modules that non hub devices with children, i.e. ks240/P300, report on
# the child but only work on the parent.  See longer note below in _initialize_modules.
# This list should be updated when creating new modules that could have the
# same issue, homekit perhaps?
NON_HUB_PARENT_ONLY_MODULES = [DeviceModule, Time, Firmware, Cloud]

ComponentsRaw: TypeAlias = dict[str, list[dict[str, int | str]]]


# Device must go last as the other interfaces also inherit Device
# and python needs a consistent method resolution order.
class SmartDevice(Device):
    """Base class to represent a SMART protocol based device."""

    # Modules that are called as part of the init procedure on first update
    FIRST_UPDATE_MODULES = {DeviceModule, ChildDevice, Cloud}

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        _protocol = protocol or SmartProtocol(
            transport=AesTransport(config=config or DeviceConfig(host=host)),
        )
        super().__init__(host=host, config=config, protocol=_protocol)
        self.protocol: SmartProtocol
        self._components_raw: ComponentsRaw | None = None
        self._components: dict[str, int] = {}
        self._state_information: dict[str, Any] = {}
        self._modules: dict[str | ModuleName[Module], SmartModule] = {}
        self._parent: SmartDevice | None = None
        self._children: Mapping[str, SmartDevice] = {}
        self._last_update_time: float | None = None
        self._on_since: datetime | None = None
        self._info: dict[str, Any] = {}

    async def _initialize_children(self) -> None:
        """Initialize children for power strips."""
        child_info_query = {
            "get_child_device_component_list": None,
            "get_child_device_list": None,
        }
        resp = await self.protocol.query(child_info_query)
        self.internal_state.update(resp)

        children = self.internal_state["get_child_device_list"]["child_device_list"]
        children_components_raw = {
            child["device_id"]: child
            for child in self.internal_state["get_child_device_component_list"][
                "child_component_list"
            ]
        }
        from .smartchilddevice import SmartChildDevice

        self._children = {
            child_info["device_id"]: await SmartChildDevice.create(
                parent=self,
                child_info=child_info,
                child_components_raw=children_components_raw[child_info["device_id"]],
            )
            for child_info in children
        }

    @property
    def children(self) -> Sequence[SmartDevice]:
        """Return list of children."""
        return list(self._children.values())

    @property
    def modules(self) -> ModuleMapping[SmartModule]:
        """Return the device modules."""
        return cast(ModuleMapping[SmartModule], self._modules)

    def _try_get_response(
        self, responses: dict, request: str, default: Any | None = None
    ) -> dict:
        response = responses.get(request)
        if isinstance(response, SmartErrorCode):
            _LOGGER.debug(
                "Error %s getting request %s for device %s",
                response,
                request,
                self.host,
            )
            response = None
        if response is not None:
            return response
        if default is not None:
            return default
        raise KasaException(
            f"{request} not found in {responses} for device {self.host}"
        )

    @staticmethod
    def _parse_components(components_raw: ComponentsRaw) -> dict[str, int]:
        return {
            str(comp["id"]): int(comp["ver_code"])
            for comp in components_raw["component_list"]
        }

    async def _negotiate(self) -> None:
        """Perform initialization.

        We fetch the device info and the available components as early as possible.
        If the device reports supporting child devices, they are also initialized.
        """
        initial_query = {
            "component_nego": None,
            "get_device_info": None,
            "get_connect_cloud_state": None,
        }
        resp = await self.protocol.query(initial_query)

        # Save the initial state to allow modules access the device info already
        # during the initialization, which is necessary as some information like the
        # supported color temperature range is contained within the response.
        self._last_update.update(resp)
        self._info = self._try_get_response(resp, "get_device_info")

        # Create our internal presentation of available components
        self._components_raw = cast(ComponentsRaw, resp["component_nego"])

        self._components = self._parse_components(self._components_raw)

        if "child_device" in self._components and not self.children:
            await self._initialize_children()

    def _update_children_info(self) -> None:
        """Update the internal child device info from the parent info."""
        if child_info := self._try_get_response(
            self._last_update, "get_child_device_list", {}
        ):
            for info in child_info["child_device_list"]:
                child_id = info["device_id"]
                if child_id not in self._children:
                    _LOGGER.debug(
                        "Skipping child update for %s, probably unsupported device",
                        child_id,
                    )
                    continue
                self._children[child_id]._update_internal_state(info)

    def _update_internal_info(self, info_resp: dict) -> None:
        """Update the internal device info."""
        self._info = self._try_get_response(info_resp, "get_device_info")

    async def update(self, update_children: bool = True) -> None:
        """Update the device."""
        if self.credentials is None and self.credentials_hash is None:
            raise AuthenticationError("Tapo plug requires authentication.")

        first_update = self._last_update_time is None
        now = time.monotonic()
        self._last_update_time = now

        if first_update:
            await self._negotiate()
            await self._initialize_modules()
            # Run post update for the cloud module
            if cloud_mod := self.modules.get(Module.Cloud):
                await self._handle_module_post_update(cloud_mod, now, had_query=True)

        resp = await self._modular_update(first_update, now)

        self._update_children_info()
        # Call child update which will only update module calls, info is updated
        # from get_child_device_list. update_children only affects hub devices, other
        # devices will always update children to prevent errors on module access.
        # This needs to go after updating the internal state of the children so that
        # child modules have access to their sysinfo.
        if first_update or update_children or self.device_type != DeviceType.Hub:
            for child in self._children.values():
                if TYPE_CHECKING:
                    assert isinstance(child, SmartChildDevice)
                await child._update()

        # We can first initialize the features after the first update.
        # We make here an assumption that every device has at least a single feature.
        if not self._features:
            await self._initialize_features()

        if _LOGGER.isEnabledFor(logging.DEBUG):
            updated = self._last_update if first_update else resp
            _LOGGER.debug("Update completed %s: %s", self.host, list(updated.keys()))

    async def _handle_module_post_update(
        self, module: SmartModule, update_time: float, had_query: bool
    ) -> None:
        if module.disabled:
            return  # pragma: no cover
        if had_query:
            module._last_update_time = update_time
        try:
            await module._post_update_hook()
            module._set_error(None)
        except Exception as ex:
            # Only set the error if a query happened.
            if had_query:
                module._set_error(ex)
                _LOGGER.warning(
                    "Error processing %s for device %s, module will be unavailable: %s",
                    module.name,
                    self.host,
                    ex,
                )

    async def _modular_update(
        self, first_update: bool, update_time: float
    ) -> dict[str, Any]:
        """Update the device with via the module queries."""
        req: dict[str, Any] = {}
        # Keep a track of actual module queries so we can track the time for
        # modules that do not need to be updated frequently
        module_queries: list[SmartModule] = []
        mq = {
            module: query
            for module in self._modules.values()
            if (first_update or module.disabled is False) and (query := module.query())
        }
        for module, query in mq.items():
            if first_update and module.__class__ in self.FIRST_UPDATE_MODULES:
                module._last_update_time = update_time
                continue
            if module._should_update(update_time):
                module_queries.append(module)
                req.update(query)

        _LOGGER.debug(
            "Querying %s for modules: %s",
            self.host,
            ", ".join(mod.name for mod in module_queries),
        )

        try:
            resp = await self.protocol.query(req)
        except Exception as ex:
            resp = await self._handle_modular_update_error(
                ex, first_update, ", ".join(mod.name for mod in module_queries), req
            )

        info_resp = self._last_update if first_update else resp
        self._last_update.update(**resp)
        self._update_internal_info(info_resp)

        # Call handle update for modules that want to update internal data
        for module in self._modules.values():
            await self._handle_module_post_update(
                module, update_time, had_query=module in module_queries
            )

        return resp

    async def _handle_modular_update_error(
        self,
        ex: Exception,
        first_update: bool,
        module_names: str,
        requests: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle an error on calling module update.

        Will try to call all modules individually
        and any errors such as timeouts will be set as a SmartErrorCode.
        """
        msg_part = "on first update" if first_update else "after first update"

        _LOGGER.error(
            "Error querying %s for modules '%s' %s: %s",
            self.host,
            module_names,
            msg_part,
            ex,
        )
        responses = {}
        for meth, params in requests.items():
            try:
                resp = await self.protocol.query({meth: params})
                responses[meth] = resp[meth]
            except Exception as iex:
                _LOGGER.error(
                    "Error querying %s individually for module query '%s' %s: %s",
                    self.host,
                    meth,
                    msg_part,
                    iex,
                )
                responses[meth] = SmartErrorCode.INTERNAL_QUERY_ERROR
        return responses

    async def _initialize_modules(self) -> None:
        """Initialize modules based on component negotiation response."""
        from .smartmodule import SmartModule

        # Some wall switches (like ks240) are internally presented as having child
        # devices which report the child's components on the parent's sysinfo, even
        # when they need to be accessed through the children.
        # The logic below ensures that such devices add all but whitelisted, only on
        # the child device.
        # It also ensures that devices like power strips do not add modules such as
        # firmware to the child devices.
        skip_parent_only_modules = False
        child_modules_to_skip: dict = {}  # TODO: this is never non-empty
        if self._parent and self._parent.device_type != DeviceType.Hub:
            skip_parent_only_modules = True

        for mod in SmartModule.REGISTERED_MODULES.values():
            if (
                skip_parent_only_modules and mod in NON_HUB_PARENT_ONLY_MODULES
            ) or mod.__name__ in child_modules_to_skip:
                continue
            required_component = cast(str, mod.REQUIRED_COMPONENT)
            if required_component in self._components or any(
                self.sys_info.get(key) is not None for key in mod.SYSINFO_LOOKUP_KEYS
            ):
                _LOGGER.debug(
                    "Device %s, found required %s, adding %s to modules.",
                    self.host,
                    required_component,
                    mod.__name__,
                )
                module = mod(self, required_component)
                if await module._check_supported():
                    self._modules[module.name] = module

        if (
            Module.Brightness in self._modules
            or Module.Color in self._modules
            or Module.ColorTemperature in self._modules
        ):
            self._modules[Light.__name__] = Light(self, "light")
        if (
            Module.TemperatureControl in self._modules
            and Module.TemperatureSensor in self._modules
        ):
            self._modules[Thermostat.__name__] = Thermostat(self, "thermostat")

    async def _initialize_features(self) -> None:
        """Initialize device features."""
        self._add_feature(
            Feature(
                self,
                id="device_id",
                name="Device ID",
                attribute_getter="device_id",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        if "device_on" in self._info:
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

        if "signal_level" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="signal_level",
                    name="Signal Level",
                    attribute_getter=lambda x: x._info["signal_level"],
                    icon="mdi:signal",
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

        if "rssi" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="rssi",
                    name="RSSI",
                    attribute_getter=lambda x: x._info["rssi"],
                    icon="mdi:signal",
                    unit_getter=lambda: "dBm",
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )

        if "ssid" in self._info:
            self._add_feature(
                Feature(
                    device=self,
                    id="ssid",
                    name="SSID",
                    attribute_getter="ssid",
                    icon="mdi:wifi",
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )

        # We check for the key available, and not for the property truthiness,
        # as the value is falsy when the device is off.
        if "on_time" in self._info:
            self._add_feature(
                Feature(
                    device=self,
                    id="on_since",
                    name="On since",
                    attribute_getter="on_since",
                    icon="mdi:clock",
                    category=Feature.Category.Debug,
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
            for feat in module._module_features.values():
                self._add_feature(feat)
        for child in self._children.values():
            await child._initialize_features()

    @property
    def _is_hub_child(self) -> bool:
        """Returns true if the device is a child of a hub."""
        return self.parent is not None and self.parent.device_type is DeviceType.Hub

    @property
    def is_cloud_connected(self) -> bool:
        """Returns if the device is connected to the cloud."""
        if Module.Cloud not in self.modules:
            return False
        return self.modules[Module.Cloud].is_connected

    @property
    def sys_info(self) -> dict[str, Any]:
        """Returns the device info."""
        return self._info  # type: ignore

    @property
    def model(self) -> str:
        """Returns the device model."""
        # If update hasn't been called self._device_info can't be used
        if self._last_update:
            return self.device_info.short_name

        disco_model = str(self._info.get("device_model"))
        long_name, _, _ = disco_model.partition("(")
        return long_name

    @property
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""
        if self._info and (nickname := self._info.get("nickname")):
            return base64.b64decode(nickname).decode()
        else:
            return None

    @property
    def time(self) -> datetime:
        """Return the time."""
        if (time_mod := self.modules.get(Module.Time)) or (
            self._parent and (time_mod := self._parent.modules.get(Module.Time))
        ):
            return time_mod.time

        # We have no device time, use current local time.
        return datetime.now(UTC).astimezone().replace(microsecond=0)

    @property
    def on_since(self) -> datetime | None:
        """Return the time that the device was turned on or None if turned off.

        This returns a cached value if the device reported value difference is under
        five seconds to avoid device-caused jitter.
        """
        if (
            not self._info.get("device_on")
            or (on_time := self._info.get("on_time")) is None
        ):
            self._on_since = None
            return None

        on_time = cast(float, on_time)
        on_since = self.time - timedelta(seconds=on_time)
        if not self._on_since or timedelta(
            seconds=0
        ) < on_since - self._on_since > timedelta(seconds=5):
            self._on_since = on_since
        return self._on_since

    @property
    def timezone(self) -> tzinfo:
        """Return the timezone and time_difference."""
        if TYPE_CHECKING:
            assert self.time.tzinfo
        return self.time.tzinfo

    @property
    def hw_info(self) -> dict:
        """Return hardware info for the device."""
        return {
            "sw_ver": self._info.get("fw_ver"),
            "hw_ver": self._info.get("hw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("device_id"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }

    @property
    def location(self) -> dict:
        """Return the device location."""
        loc = {
            "latitude": cast(float, self._info.get("latitude", 0)) / 10_000,
            "longitude": cast(float, self._info.get("longitude", 0)) / 10_000,
        }
        return loc

    @property
    def rssi(self) -> int | None:
        """Return the rssi."""
        rssi = self._info.get("rssi")
        return int(rssi) if rssi else None

    @property
    def mac(self) -> str:
        """Return the mac formatted with colons."""
        return str(self._info.get("mac")).replace("-", ":")

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return str(self._info.get("device_id"))

    @property
    def internal_state(self) -> dict:
        """Return all the internal state data."""
        return self._last_update

    def _update_internal_state(self, info: dict[str, Any]) -> None:
        """Update the internal info state.

        This is used by the parent to push updates to its children.
        """
        self._info = info

    async def _query_helper(
        self, method: str, params: dict | None = None, child_ids: None = None
    ) -> dict:
        res = await self.protocol.query({method: params})

        return res

    @property
    def ssid(self) -> str:
        """Return ssid of the connected wifi ap."""
        ssid = self._info.get("ssid")
        ssid = base64.b64decode(ssid).decode() if ssid else "No SSID"
        return ssid

    @property
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""
        return Module.Energy in self.modules

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return bool(self._info.get("device_on"))

    async def set_state(self, on: bool) -> dict:
        """Set the device state.

        See :meth:`is_on`.
        """
        return await self.protocol.query({"set_device_info": {"device_on": on}})

    async def turn_on(self, **kwargs: Any) -> dict:
        """Turn on the device."""
        return await self.set_state(True)

    async def turn_off(self, **kwargs: Any) -> dict:
        """Turn off the device."""
        return await self.set_state(False)

    def update_from_discover_info(
        self,
        info: dict,
    ) -> None:
        """Update state from info from the discover call."""
        self._discovery_info = info
        self._info = info

    async def wifi_scan(self) -> list[WifiNetwork]:
        """Scan for available wifi networks."""

        def _net_for_scan_info(res: dict) -> WifiNetwork:
            return WifiNetwork(
                ssid=base64.b64decode(res["ssid"]).decode(),
                cipher_type=res["cipher_type"],
                key_type=res["key_type"],
                channel=res["channel"],
                signal_level=res["signal_level"],
                bssid=res["bssid"],
            )

        _LOGGER.debug("Querying networks")

        resp = await self.protocol.query({"get_wireless_scan_info": {"start_index": 0}})
        networks = [
            _net_for_scan_info(net) for net in resp["get_wireless_scan_info"]["ap_list"]
        ]
        return networks

    async def wifi_join(
        self, ssid: str, password: str, keytype: str = "wpa2_psk"
    ) -> dict:
        """Join the given wifi network.

        This method returns nothing as the device tries to activate the new
        settings immediately instead of responding to the request.

        If joining the network fails, the device will return to the previous state
        after some delay.
        """
        if not self.credentials:
            raise AuthenticationError("Device requires authentication.")

        payload = {
            "account": {
                "username": base64.b64encode(
                    self.credentials.username.encode()
                ).decode(),
                "password": base64.b64encode(
                    self.credentials.password.encode()
                ).decode(),
            },
            "wireless": {
                "key_type": keytype,
                "password": base64.b64encode(password.encode()).decode(),
                "ssid": base64.b64encode(ssid.encode()).decode(),
            },
            "time": self.internal_state["get_device_time"],
        }

        # The device does not respond to the request but changes the settings
        # immediately which causes us to timeout.
        # Thus, We limit retries and suppress the raised exception as useless.
        try:
            return await self.protocol.query({"set_qs_info": payload}, retry_count=0)
        except DeviceError:
            raise  # Re-raise on device-reported errors
        except KasaException:
            _LOGGER.debug(
                "Received a kasa exception for wifi join, but this is expected"
            )
            return {}

    async def update_credentials(self, username: str, password: str) -> dict:
        """Update device credentials.

        This will replace the existing authentication credentials on the device.
        """
        time_data = self.internal_state["get_device_time"]
        payload = {
            "account": {
                "username": base64.b64encode(username.encode()).decode(),
                "password": base64.b64encode(password.encode()).decode(),
            },
            "time": time_data,
        }
        return await self.protocol.query({"set_qs_info": payload})

    async def set_alias(self, alias: str) -> dict:
        """Set the device name (alias)."""
        return await self.protocol.query(
            {"set_device_info": {"nickname": base64.b64encode(alias.encode()).decode()}}
        )

    async def reboot(self, delay: int = 1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.
        """
        await self.protocol.query({"device_reboot": {"delay": delay}})

    async def factory_reset(self) -> None:
        """Reset device back to factory settings.

        Note, this does not downgrade the firmware.
        """
        await self.protocol.query("device_reset")

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        if self._device_type is not DeviceType.Unknown:
            return self._device_type

        if (
            not (type_str := self._info.get("type", self._info.get("device_type")))
            or not self._components
        ):
            # no update or discovery info
            return self._device_type

        self._device_type = self._get_device_type_from_components(
            list(self._components.keys()), type_str
        )

        return self._device_type

    @staticmethod
    def _get_device_type_from_components(
        components: list[str], device_type: str
    ) -> DeviceType:
        """Find type to be displayed as a supported device category."""
        if "HUB" in device_type:
            return DeviceType.Hub
        if "PLUG" in device_type:
            if "child_device" in components:
                return DeviceType.Strip
            return DeviceType.Plug
        if "light_strip" in components:
            return DeviceType.LightStrip
        if "SWITCH" in device_type and "child_device" in components:
            return DeviceType.WallSwitch
        if "dimmer_calibration" in components:
            return DeviceType.Dimmer
        if "brightness" in components:
            return DeviceType.Bulb
        if "SWITCH" in device_type:
            return DeviceType.WallSwitch
        if "SENSOR" in device_type:
            return DeviceType.Sensor
        if "ENERGY" in device_type:
            return DeviceType.Thermostat
        if "ROBOVAC" in device_type:
            return DeviceType.Vacuum
        if "TAPOCHIME" in device_type:
            return DeviceType.Chime
        _LOGGER.warning("Unknown device type, falling back to plug")
        return DeviceType.Plug

    @staticmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get model information for a device."""
        di = info["get_device_info"]
        components = [comp["id"] for comp in info["component_nego"]["component_list"]]

        # Get model/region info
        short_name = di["model"]
        region = None
        if discovery_info:
            device_model = discovery_info["device_model"]
            long_name, _, region = device_model.partition("(")
            if region:  # P100 doesn't have region
                region = region.replace(")", "")
        else:
            long_name = short_name
        if not region:  # some devices have region in specs
            region = di.get("specs")

        # Get other info
        device_family = di["type"]
        device_type = SmartDevice._get_device_type_from_components(
            components, device_family
        )
        fw_version_full = di["fw_ver"]
        firmware_version, firmware_build = fw_version_full.split(" ", maxsplit=1)
        _protocol, devicetype = device_family.split(".")
        # Brand inferred from SMART.KASAPLUG/SMART.TAPOPLUG etc.
        brand = devicetype[:4].lower()

        return DeviceInfo(
            short_name=short_name,
            long_name=long_name,
            brand=brand,
            device_family=device_family,
            device_type=device_type,
            hardware_version=di["hw_ver"],
            firmware_version=firmware_version,
            firmware_build=firmware_build,
            requires_auth=True,
            region=region,
        )
