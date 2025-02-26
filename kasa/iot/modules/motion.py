"""Implementation of the motion detection (PIR) module found in some dimmers."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum

from ...exceptions import KasaException
from ...feature import Feature
from ..iotmodule import IotModule, merge

_LOGGER = logging.getLogger(__name__)


class Range(Enum):
    """Range for motion detection."""

    Far = 0
    Mid = 1
    Near = 2
    Custom = 3

    def __str__(self) -> str:
        return self.name


@dataclass
class PIRConfig:
    """Dataclass representing a PIR sensor configuration."""

    enabled: bool
    adc_min: int
    adc_max: int
    range: Range
    threshold: int

    @property
    def adc_mid(self) -> int:
        """Compute the ADC midpoint from the configured ADC Max and Min values."""
        return math.floor(abs(self.adc_max - self.adc_min) / 2)


@dataclass
class PIRStatus:
    """Dataclass representing the current trigger state of an ADC PIR sensor."""

    pir_config: PIRConfig
    adc_value: int

    @property
    def pir_value(self) -> int:
        """
        Get the PIR status value in integer form.

        Computes the PIR status value that this object represents,
        using the given PIR configuration.
        """
        return self.pir_config.adc_mid - self.adc_value

    @property
    def pir_percent(self) -> float:
        """
        Get the PIR status value in percentile form.

        Computes the PIR status percentage that this object represents,
        using the given PIR configuration.
        """
        value = self.pir_value
        divisor = (
            (self.pir_config.adc_mid - self.pir_config.adc_min)
            if (value < 0)
            else (self.pir_config.adc_max - self.pir_config.adc_mid)
        )
        return (float(value) / divisor) * 100

    @property
    def pir_triggered(self) -> bool:
        """
        Get the PIR status trigger state.

        Compute the PIR trigger state this object represents,
        using the given PIR configuration.
        """
        return (self.pir_config.enabled) and (
            abs(self.pir_percent) > (100 - self.pir_config.threshold)
        )


class Motion(IotModule):
    """Implements the motion detection (PIR) module."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Only add features if the device supports the module
        if "get_config" not in self.data:
            return

        # Require that ADC value is also present.
        if "get_adc_value" not in self.data:
            _LOGGER.warning("%r initialized, but no get_adc_value in response")
            return

        if "enable" not in self.config:
            _LOGGER.warning("%r initialized, but no enable in response")
            return

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_enabled",
                name="PIR enabled",
                icon="mdi:motion-sensor",
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_range",
                name="Motion Sensor Range",
                icon="mdi:motion-sensor",
                attribute_getter="range",
                attribute_setter="_set_range_from_str",
                type=Feature.Type.Choice,
                choices_getter="ranges",
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_threshold",
                name="Motion Sensor Threshold",
                icon="mdi:motion-sensor",
                attribute_getter="threshold",
                attribute_setter="set_threshold",
                type=Feature.Type.Number,
                category=Feature.Category.Config,
                range_getter=lambda: (0, 100),
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_triggered",
                name="PIR Triggered",
                icon="mdi:motion-sensor",
                attribute_getter="pir_triggered",
                attribute_setter=None,
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Primary,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_value",
                name="PIR Value",
                icon="mdi:motion-sensor",
                attribute_getter="pir_value",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Info,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_adc_value",
                name="PIR ADC Value",
                icon="mdi:motion-sensor",
                attribute_getter="adc_value",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_adc_min",
                name="PIR ADC Min",
                icon="mdi:motion-sensor",
                attribute_getter="adc_min",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_adc_mid",
                name="PIR ADC Mid",
                icon="mdi:motion-sensor",
                attribute_getter="adc_mid",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_adc_max",
                name="PIR ADC Max",
                icon="mdi:motion-sensor",
                attribute_getter="adc_max",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_percent",
                name="PIR Percentile",
                icon="mdi:motion-sensor",
                attribute_getter="pir_percent",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
                unit_getter=lambda: "%",
            )
        )

    def query(self) -> dict:
        """Request PIR configuration."""
        req = merge(
            self.query_for_command("get_config"),
            self.query_for_command("get_adc_value"),
        )

        return req

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return self.data["get_config"]

    @property
    def pir_config(self) -> PIRConfig:
        """Return PIR sensor configuration."""
        pir_range = Range(self.config["trigger_index"])
        return PIRConfig(
            enabled=bool(self.config["enable"]),
            adc_min=int(self.config["min_adc"]),
            adc_max=int(self.config["max_adc"]),
            range=pir_range,
            threshold=self.get_range_threshold(pir_range),
        )

    @property
    def enabled(self) -> bool:
        """Return True if module is enabled."""
        return self.pir_config.enabled

    @property
    def adc_min(self) -> int:
        """Return minimum ADC sensor value."""
        return self.pir_config.adc_min

    @property
    def adc_max(self) -> int:
        """Return maximum ADC sensor value."""
        return self.pir_config.adc_max

    @property
    def adc_mid(self) -> int:
        """
        Return the midpoint for the ADC.

        The midpoint represents the zero point for the PIR sensor waveform.

        Currently this is estimated by:
            math.floor(abs(adc_max - adc_min) / 2)
        """
        return self.pir_config.adc_mid

    async def set_enabled(self, state: bool) -> dict:
        """Enable/disable PIR."""
        return await self.call("set_enable", {"enable": int(state)})

    @property
    def ranges(self) -> list[str]:
        """Return set of supported range classes."""
        range_min = 0
        range_max = len(self.config["array"])
        valid_ranges = list()
        for r in Range:
            if (r.value >= range_min) and (r.value < range_max):
                valid_ranges.append(r.name)
        return valid_ranges

    @property
    def range(self) -> Range:
        """Return motion detection Range."""
        return self.pir_config.range

    async def set_range(self, range: Range) -> dict:
        """Set the Range for the sensor.

        :param Range: the range class to use.
        """
        payload = {"index": range.value}
        return await self.call("set_trigger_sens", payload)

    def _parse_range_value(self, value: str) -> Range:
        """Attempt to parse a range value from the given string."""
        value = value.strip().capitalize()
        try:
            return Range[value]
        except KeyError:
            raise KasaException(
                f"Invalid range value: '{value}'."
                f" Valid options are: {Range._member_names_}"
            ) from KeyError

    async def _set_range_from_str(self, input: str) -> dict:
        value = self._parse_range_value(input)
        return await self.set_range(range=value)

    def get_range_threshold(self, range_type: Range) -> int:
        """Get the distance threshold at which the PIR sensor is will trigger."""
        if range_type.value < 0 or range_type.value >= len(self.config["array"]):
            raise KasaException(
                "Range type is outside the bounds of the configured device ranges."
            )
        return int(self.config["array"][range_type.value])

    @property
    def threshold(self) -> int:
        """Return motion detection Range."""
        return self.pir_config.threshold

    async def set_threshold(self, value: int) -> dict:
        """Set the distance threshold at which the PIR sensor is will trigger."""
        payload = {"index": Range.Custom.value, "value": value}
        return await self.call("set_trigger_sens", payload)

    @property
    def inactivity_timeout(self) -> int:
        """Return inactivity timeout in milliseconds."""
        return self.config["cold_time"]

    async def set_inactivity_timeout(self, timeout: int) -> dict:
        """Set inactivity timeout in milliseconds.

        Note, that you need to delete the default "Smart Control" rule in the app
        to avoid reverting this back to 60 seconds after a period of time.
        """
        return await self.call("set_cold_time", {"cold_time": timeout})

    @property
    def pir_state(self) -> PIRStatus:
        """Return cached PIR status."""
        return PIRStatus(self.pir_config, self.data["get_adc_value"]["value"])

    async def get_pir_state(self) -> PIRStatus:
        """Return real-time PIR status."""
        latest = await self.call("get_adc_value")
        self.data["get_adc_value"] = latest
        return PIRStatus(self.pir_config, latest["value"])

    @property
    def adc_value(self) -> int:
        """Return motion adc value."""
        return self.pir_state.adc_value

    @property
    def pir_value(self) -> int:
        """Return the computed PIR sensor value."""
        return self.pir_state.pir_value

    @property
    def pir_percent(self) -> float:
        """Return the computed PIR sensor value, in percentile form."""
        return self.pir_state.pir_percent

    @property
    def pir_triggered(self) -> bool:
        """Return if the motion sensor has been triggered."""
        return self.pir_state.pir_triggered
