"""TP-Link device types."""

from __future__ import annotations

from enum import Enum


class DeviceType(Enum):
    """Device type enum."""

    # The values match what the cli has historically used
    Plug = "plug"
    Bulb = "bulb"
    Strip = "strip"
    Camera = "camera"
    WallSwitch = "wallswitch"
    StripSocket = "stripsocket"
    Dimmer = "dimmer"
    LightStrip = "lightstrip"
    Sensor = "sensor"
    Hub = "hub"
    Fan = "fan"
    Thermostat = "thermostat"
    Vacuum = "vacuum"
    Chime = "chime"
    Unknown = "unknown"

    @staticmethod
    def from_value(name: str) -> DeviceType:
        """Return device type from string value."""
        for device_type in DeviceType:
            if device_type.value == name:
                return device_type
        return DeviceType.Unknown
