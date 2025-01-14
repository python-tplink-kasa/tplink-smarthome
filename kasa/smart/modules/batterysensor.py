"""Implementation of battery module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class BatterySensor(SmartModule):
    """Implementation of battery module."""

    REQUIRED_COMPONENT = "battery_detect"
    QUERY_GETTER_NAME = "get_battery_detect_info"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                "battery_low",
                "Battery low",
                container=self,
                attribute_getter="battery_low",
                icon="mdi:alert",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )

        # Some devices, like T110 contact sensor do not report the battery percentage
        if "battery_percentage" in self._device.sys_info:
            self._add_feature(
                Feature(
                    self._device,
                    "battery_level",
                    "Battery level",
                    container=self,
                    attribute_getter="battery",
                    icon="mdi:battery",
                    unit_getter=lambda: "%",
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def battery(self) -> int:
        """Return battery level."""
        return self._device.sys_info["battery_percentage"]

    @property
    def battery_low(self) -> bool:
        """Return True if battery is low."""
        return self._device.sys_info.get(
            "at_low_battery", self._device.sys_info.get("is_low")
        )
