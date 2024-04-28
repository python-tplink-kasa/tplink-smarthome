"""Implementation of cloud module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...exceptions import SmartErrorCode
from ...feature import Feature, HassCompat
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class CloudModule(SmartModule):
    """Implementation of cloud module."""

    QUERY_GETTER_NAME = "get_connect_cloud_state"
    REQUIRED_COMPONENT = "cloud_connect"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)

        self._add_feature(
            Feature(
                device,
                "Cloud connection",
                container=self,
                attribute_getter="is_connected",
                icon="mdi:cloud",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
                hass_compat=HassCompat(device_class=HassCompat.DeviceClass.Connected),
            )
        )

    @property
    def is_connected(self):
        """Return True if device is connected to the cloud."""
        if isinstance(self.data, SmartErrorCode):
            return False
        return self.data["status"] == 0
