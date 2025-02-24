"""Implementation of the turn on behavior for bulbs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig
from mashumaro.types import Alias

from ...feature import Feature
from ..iotmodule import IotModule

_LOGGER = logging.getLogger(__name__)


class TurnOnBehaviorModule(IotModule):
    """Implements the turn on behavior module."""

    def query(self) -> dict:
        """Request default behavior configuration."""
        return self.query_for_command("get_default_behavior")

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Only add features if the device supports the module
        if "get_default_behavior" not in self.data:
            return

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="turn_on_hard",
                name="Turn on hard",
                icon="mdi:motion-sensor",
                attribute_getter="turn_on_hard",
                # attribute_setter="set_turn_on_hard",
                type=Feature.Type.Choice,
                choices_getter=lambda: list(BehaviorMode),
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="turn_on_soft",
                name="Turn on soft",
                icon="mdi:motion-sensor",
                attribute_getter="turn_on_soft",
                # attribute_setter="set_turn_on_hard",
                type=Feature.Type.Choice,
                choices_getter=lambda: list(BehaviorMode),
                category=Feature.Category.Config,
            )
        )

    @property
    def behaviors(self) -> TurnOnBehaviors:
        """Current turn on behaviors."""
        return TurnOnBehaviors.from_dict(self.data["get_default_behavior"])

    @property
    def turn_on_hard(self) -> BehaviorMode:
        """Current turn on hard behavior."""
        return self.behaviors.hard.mode

    @property
    def turn_on_soft(self) -> BehaviorMode:
        """Current turn on soft behavior."""
        return self.behaviors.hard.mode


class BehaviorMode(str, Enum):
    """Enum to present type of turn on behavior."""

    #: Return to the last state known state.
    Last = "last_status"
    #: Use chosen preset.
    Preset = "customize_preset"
    #: Circadian
    Circadian = "circadian"


@dataclass
class TurnOnBehavior(DataClassDictMixin):
    """Model to present a single turn on behavior.

    :param int preset: the index number of wanted preset.
    :param BehaviorMode mode: last status or preset mode.
     If you are changing existing settings, you should not set this manually.

    To change the behavior, it is only necessary to change the :attr:`preset` field
    to contain either the preset index, or ``None`` for the last known state.
    """

    class Config(BaseConfig):
        """Serialization config."""

        omit_none = True
        serialize_by_alias = True

    #: Wanted behavior
    mode: BehaviorMode
    #: Index of preset to use, or ``None`` for the last known state.
    preset: Annotated[int | None, Alias("index")] = None
    brightness: int | None = None
    color_temp: int | None = None
    hue: int | None = None
    saturation: int | None = None


@dataclass
class TurnOnBehaviors(DataClassDictMixin):
    """Model to contain turn on behaviors."""

    #: The behavior when the bulb is turned on programmatically.
    soft: Annotated[TurnOnBehavior, Alias("soft_on")]
    #: The behavior when the bulb has been off from mains power.
    hard: Annotated[TurnOnBehavior, Alias("hard_on")]
