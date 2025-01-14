"""Module for Fan Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated

from ..module import FeatureAttribute, Module


class Fan(Module, ABC):
    """Interface for a Fan."""

    @property
    @abstractmethod
    def fan_speed_level(self) -> Annotated[int, FeatureAttribute()]:
        """Return fan speed level."""

    @abstractmethod
    async def set_fan_speed_level(
        self, level: int
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set fan speed level."""


Fan.get_fan_speed_level = Fan.fan_speed_level.fget  # type: ignore[attr-defined]
