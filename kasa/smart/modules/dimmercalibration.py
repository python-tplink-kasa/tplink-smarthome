"""Implementation of the dimmer config module found in dimmers."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

from ...exceptions import KasaException
from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


def _td_to_ms(td: timedelta) -> int:
    """
    Convert timedelta to integer milliseconds.

    Uses default float to integer rounding.
    """
    return int(td / timedelta(milliseconds=1))


class DimmerCalibration(SmartModule):
    """Implements the dimmer config module."""

    REQUIRED_COMPONENT = "dimmer_calibration"
    QUERY_GETTER_NAME = "get_dimmer_calibration"

    THRESHOLD_ABS_MIN: Final[int] = 0
    THRESHOLD_ABS_MAX: Final[int] = 99

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_threshold_min",
                name="Minimum dimming level",
                icon="mdi:lightbulb-on-20",
                attribute_getter="threshold_min",
                attribute_setter="set_threshold_min",
                range_getter=lambda: (self.THRESHOLD_ABS_MIN, self.THRESHOLD_ABS_MAX),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_threshold_max",
                name="Maximum dimming level",
                icon="mdi:lightbulb-on-80",
                attribute_getter="threshold_max",
                attribute_setter="set_threshold_max",
                range_getter=lambda: (self.THRESHOLD_ABS_MIN, self.THRESHOLD_ABS_MAX),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Request Dimming configuration."""
        if self.supported_version >= 1:
            return {"get_calibrate_brightness": None}
        return {}

    @property
    def threshold_min(self) -> int:
        """Return the minimum dimming level for this dimmer."""
        return self.data["min_threshold"]

    async def set_threshold_min(self, min: int) -> dict:
        """Set the minimum dimming level for this dimmer.

        The value will depend on the luminaries connected to the dimmer.

        :param min: The minimum dimming level, in the range 0-99.
        """
        if min < self.THRESHOLD_ABS_MIN or min > self.THRESHOLD_ABS_MAX:
            raise KasaException(
                "Minimum dimming threshold is outside the supported range: "
                f"{self.THRESHOLD_ABS_MIN}-{self.THRESHOLD_ABS_MAX}"
            )
        return await self.call("set_calibrate_brightness", {"min_threshold": min})

    @property
    def threshold_max(self) -> int:
        """Return the maximum dimming level for this dimmer."""
        return self.data["max_threshold"]

    async def set_threshold_max(self, max: int) -> dict:
        """Set the maximum dimming level for this dimmer.

        The value will depend on the luminaries connected to the dimmer.

        :param max: The minimum dimming level, in the range 0-99.
        """
        if max < self.THRESHOLD_ABS_MIN or max > self.THRESHOLD_ABS_MAX:
            raise KasaException(
                "Minimum dimming threshold is outside the supported range: "
                f"{self.THRESHOLD_ABS_MIN}-{self.THRESHOLD_ABS_MAX}"
            )
        return await self.call("set_calibrate_brightness", {"max_threshold": max})
