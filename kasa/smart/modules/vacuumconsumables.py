"""Implementation of vacuum consumables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


@dataclass
class Consumable:
    """Consumable container."""

    #: Name of the consumable.
    name: str
    #: Feature base name
    feature_basename: str
    #: Data key in the device reported data
    data_key: str
    #: Lifetime
    lifetime: timedelta


CONSUMABLES = [
    # TODO: there is also main_brush_lid_time
    Consumable(
        "Main brush",
        feature_basename="main_brush",
        data_key="roll_brush_time",
        lifetime=timedelta(hours=400),
    ),
    Consumable(
        "Side brush",
        feature_basename="side_brush",
        data_key="edge_brush_time",
        lifetime=timedelta(hours=200),
    ),
    Consumable(
        "Filter",
        feature_basename="filter",
        data_key="filter_time",
        lifetime=timedelta(hours=200),
    ),
    Consumable(
        "Sensor",
        feature_basename="sensor",
        data_key="sensor_time",
        lifetime=timedelta(hours=30),
    ),
    Consumable(
        "Charging contacts",
        feature_basename="contacts",
        data_key="charge_contact_time",
        lifetime=timedelta(hours=30),
    ),
    # unknown data, does not seem to be mop used
    # Consumable("Rag", key="rag_time", lifetime=timedelta(hours=30))
]


class VacuumConsumables(SmartModule):
    """Implementation of vacuum consumables."""

    REQUIRED_COMPONENT = "consumables"
    QUERY_GETTER_NAME = "getConsumablesInfo"

    def _initialize_features(self) -> None:
        """Initialize features."""
        for consumable in CONSUMABLES:
            if consumable.data_key not in self.data:
                continue

            self._add_feature(
                Feature(
                    self._device,
                    id=f"vacuum_{consumable.feature_basename}_used",
                    name=f"{consumable.name} used",
                    container=self.data,
                    attribute_getter=lambda container, item=consumable: timedelta(
                        minutes=container.get(item.data_key)
                    ),
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )

            self._add_feature(
                Feature(
                    self._device,
                    id=f"vacuum_{consumable.feature_basename}_remaining",
                    name=f"{consumable.name} remaining",
                    container=self.data,
                    attribute_getter=lambda container, item=consumable: item.lifetime
                    - timedelta(minutes=container.get(item.data_key)),
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

            self._add_feature(
                Feature(
                    self._device,
                    id=f"vacuum_{consumable.feature_basename}_reset",
                    name=f"Reset {consumable.name}",
                    container=self.data,
                    attribute_setter=lambda _, item=consumable: self.reset_consumable(
                        item
                    ),
                    category=Feature.Category.Info,
                    type=Feature.Type.Action,
                )
            )

    async def reset_consumable(self, consumable: Consumable) -> dict:
        """Reset consumable stats."""
        consumable_name = consumable.data_key.removesuffix("_time")
        return await self.call(
            "resetConsumablesTime", {"reset_list": [consumable_name]}
        )
