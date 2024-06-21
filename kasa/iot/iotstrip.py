"""Module for multi-socket devices (HS300, HS107, KP303, ..)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..emeterstatus import EmeterStatus
from ..exceptions import KasaException
from ..feature import Feature
from ..interfaces import Energy
from ..module import Module
from ..protocol import BaseProtocol
from .iotdevice import (
    IotDevice,
    requires_update,
)
from .iotmodule import IotModule
from .iotplug import IotPlug
from .modules import Antitheft, Countdown, Schedule, Time, Usage

_LOGGER = logging.getLogger(__name__)


def merge_sums(dicts):
    """Merge the sum of dicts."""
    total_dict: defaultdict[int, float] = defaultdict(lambda: 0.0)
    for sum_dict in dicts:
        for day, value in sum_dict.items():
            total_dict[day] += value
    return total_dict


class IotStrip(IotDevice):
    r"""Representation of a TP-Link Smart Power Strip.

    A strip consists of the parent device and its children.
    All methods of the parent act on all children, while the child devices
    share the common API with the :class:`SmartPlug` class.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values,
    but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`KasaException`\s,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> strip = IotStrip("127.0.0.1")
        >>> asyncio.run(strip.update())
        >>> strip.alias
        Bedroom Power Strip

        All methods act on the whole strip:

        >>> for plug in strip.children:
        >>>    print(f"{plug.alias}: {plug.is_on}")
        Plug 1: True
        Plug 2: False
        Plug 3: False
        >>> strip.is_on
        True
        >>> asyncio.run(strip.turn_off())
        >>> asyncio.run(strip.update())

        Accessing individual plugs can be done using the `children` property:

        >>> len(strip.children)
        3
        >>> for plug in strip.children:
        >>>    print(f"{plug.alias}: {plug.is_on}")
        Plug 1: False
        Plug 2: False
        Plug 3: False
        >>> asyncio.run(strip.children[1].turn_on())
        >>> asyncio.run(strip.update())
        >>> strip.is_on
        True

    For more examples, see the :class:`Device` class.
    """

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip

    async def _initialize_modules(self):
        """Initialize modules."""
        # Strip has different modules to plug so do not call super
        self.add_module(Module.IotAntitheft, Antitheft(self, "anti_theft"))
        self.add_module(Module.IotSchedule, Schedule(self, "schedule"))
        self.add_module(Module.IotUsage, Usage(self, "schedule"))
        self.add_module(Module.IotTime, Time(self, "time"))
        self.add_module(Module.IotCountdown, Countdown(self, "countdown"))
        if self.has_emeter:
            _LOGGER.debug(
                "The device has emeter, querying its information along sysinfo"
            )
            self.add_module(Module.Energy, StripEmeter(self, self.emeter_type))

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return if any of the outlets are on."""
        return any(plug.is_on for plug in self.children)

    async def update(self, update_children: bool = True):
        """Update some of the attributes.

        Needed for methods that are decorated with `requires_update`.
        """
        # Super initializes modules and features
        await super().update(update_children)

        initialize_children = not self.children
        # Initialize the child devices during the first update.
        if initialize_children:
            children = self.sys_info["children"]
            _LOGGER.debug("Initializing %s child sockets", len(children))
            self._children = {
                f"{self.mac}_{child['id']}": IotStripPlug(
                    self.host, parent=self, child_id=child["id"]
                )
                for child in children
            }
            for child in self._children.values():
                await child._initialize_modules()

        if update_children:
            for plug in self.children:
                await plug.update()

        if not self.features:
            await self._initialize_features()

    async def _initialize_features(self):
        """Initialize common features."""
        # Do not initialize features until children are created
        if not self.children:
            return
        await super()._initialize_features()

    async def turn_on(self, **kwargs):
        """Turn the strip on."""
        await self._query_helper("system", "set_relay_state", {"state": 1})

    async def turn_off(self, **kwargs):
        """Turn the strip off."""
        await self._query_helper("system", "set_relay_state", {"state": 0})

    @property  # type: ignore
    @requires_update
    def on_since(self) -> datetime | None:
        """Return the maximum on-time of all outlets."""
        if self.is_off:
            return None

        return min(plug.on_since for plug in self.children if plug.on_since is not None)


class StripEmeter(IotModule, Energy):
    """Energy module implementation to aggregate child modules."""

    _supported = (
        Energy.ModuleFeature.CONSUMPTION_TOTAL
        | Energy.ModuleFeature.PERIODIC_STATS
        | Energy.ModuleFeature.VOLTAGE_CURRENT
    )

    def supports(self, module_feature: Energy.ModuleFeature) -> bool:
        """Return True if module supports the feature."""
        return module_feature in self._supported

    def query(self):
        """Return the base query."""
        return {}

    @property
    def current_consumption(self) -> float | None:
        """Get the current power consumption in watts."""
        return sum(
            v if (v := plug.modules[Module.Energy].current_consumption) else 0.0
            for plug in self._device.children
        )

    async def get_status(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        emeter_rt = await self._async_get_emeter_sum("get_status", {})
        # Voltage is averaged since each read will result
        # in a slightly different voltage since they are not atomic
        emeter_rt["voltage_mv"] = int(
            emeter_rt["voltage_mv"] / len(self._device.children)
        )
        return EmeterStatus(emeter_rt)

    async def get_daily_stats(
        self, year: int | None = None, month: int | None = None, kwh: bool = True
    ) -> dict:
        """Retrieve daily statistics for a given month.

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistics (default: this
                      month)
        :param kwh: return usage in kWh (default: True)
        :return: mapping of day of month to value
        """
        return await self._async_get_emeter_sum(
            "get_daily_stats", {"year": year, "month": month, "kwh": kwh}
        )

    async def get_monthly_stats(
        self, year: int | None = None, kwh: bool = True
    ) -> dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        """
        return await self._async_get_emeter_sum(
            "get_monthly_stats", {"year": year, "kwh": kwh}
        )

    async def _async_get_emeter_sum(self, func: str, kwargs: dict[str, Any]) -> dict:
        """Retrieve emeter stats for a time period from children."""
        return merge_sums(
            [
                await getattr(plug.modules[Module.Energy], func)(**kwargs)
                for plug in self._device.children
            ]
        )

    async def erase_stats(self):
        """Erase energy meter statistics for all plugs."""
        for plug in self._device.children:
            await plug.modules[Module.Energy].erase_stats()

    @property  # type: ignore
    def consumption_this_month(self) -> float | None:
        """Return this month's energy consumption in kWh."""
        return sum(
            v if (v := plug.modules[Module.Energy].consumption_this_month) else 0.0
            for plug in self._device.children
        )

    @property  # type: ignore
    def consumption_today(self) -> float | None:
        """Return this month's energy consumption in kWh."""
        return sum(
            v if (v := plug.modules[Module.Energy].consumption_today) else 0.0
            for plug in self._device.children
        )

    @property  # type: ignore
    def consumption_total(self) -> float | None:
        """Return total energy consumption since reboot in kWh."""
        return sum(
            v if (v := plug.modules[Module.Energy].consumption_total) else 0.0
            for plug in self._device.children
        )

    @property  # type: ignore
    def status(self) -> EmeterStatus:
        """Return current energy readings."""
        emeter = merge_sums(
            [plug.modules[Module.Energy].status for plug in self._device.children]
        )
        # Voltage is averaged since each read will result
        # in a slightly different voltage since they are not atomic
        emeter["voltage_mv"] = int(emeter["voltage_mv"] / len(self._device.children))
        return EmeterStatus(emeter)

    @property
    def current(self) -> float | None:
        """Return the current in A."""
        return self.status.current

    @property
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        return self.status.voltage


class IotStripPlug(IotPlug):
    """Representation of a single socket in a power strip.

    This allows you to use the sockets as they were SmartPlug objects.
    Instead of calling an update on any of these, you should call an update
    on the parent device before accessing the properties.

    The plug inherits (most of) the system information from the parent.
    """

    def __init__(self, host: str, parent: IotStrip, child_id: str) -> None:
        super().__init__(host)

        self.parent = parent
        self.child_id = child_id
        self._last_update = parent._last_update
        self._set_sys_info(parent.sys_info)
        self._device_type = DeviceType.StripSocket
        self.protocol = parent.protocol  # Must use the same connection as the parent

    async def _initialize_modules(self):
        """Initialize modules not added in init."""
        await super()._initialize_modules()
        self.add_module("time", Time(self, "time"))

    async def _initialize_features(self):
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
                id="on_since",
                name="On since",
                attribute_getter="on_since",
                icon="mdi:clock",
                category=Feature.Category.Debug,
            )
        )
        for module in self._supported_modules.values():
            module._initialize_features()
            for module_feat in module._module_features.values():
                self._add_feature(module_feat)

    async def update(self, update_children: bool = True):
        """Query the device to update the data.

        Needed for properties that are decorated with `requires_update`.
        """
        await self._modular_update({})
        if not self._features:
            await self._initialize_features()

    def _create_request(
        self, target: str, cmd: str, arg: dict | None = None, child_ids=None
    ):
        request: dict[str, Any] = {
            "context": {"child_ids": [self.child_id]},
            target: {cmd: arg},
        }
        return request

    async def _query_helper(
        self, target: str, cmd: str, arg: dict | None = None, child_ids=None
    ) -> Any:
        """Override query helper to include the child_ids."""
        return await self.parent._query_helper(
            target, cmd, arg, child_ids=[self.child_id]
        )

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether device is on."""
        info = self._get_child_info()
        return bool(info["state"])

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led.

        This is always false for subdevices.
        """
        return False

    @property  # type: ignore
    @requires_update
    def device_id(self) -> str:
        """Return unique ID for the socket.

        This is a combination of MAC and child's ID.
        """
        return f"{self.mac}_{self.child_id}"

    @property  # type: ignore
    @requires_update
    def alias(self) -> str:
        """Return device name (alias)."""
        info = self._get_child_info()
        return info["alias"]

    @property  # type: ignore
    @requires_update
    def next_action(self) -> dict:
        """Return next scheduled(?) action."""
        info = self._get_child_info()
        return info["next_action"]

    @property  # type: ignore
    @requires_update
    def on_since(self) -> datetime | None:
        """Return on-time, if available."""
        if self.is_off:
            return None

        info = self._get_child_info()
        on_time = info["on_time"]

        return datetime.now(timezone.utc).astimezone().replace(
            microsecond=0
        ) - timedelta(seconds=on_time)

    @property  # type: ignore
    @requires_update
    def model(self) -> str:
        """Return device model for a child socket."""
        sys_info = self.parent.sys_info
        return f"Socket for {sys_info['model']}"

    def _get_child_info(self) -> dict:
        """Return the subdevice information for this device."""
        for plug in self.parent.sys_info["children"]:
            if plug["id"] == self.child_id:
                return plug

        raise KasaException(f"Unable to find children {self.child_id}")
