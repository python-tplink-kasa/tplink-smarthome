"""Implementation of vacuum cleaning records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

from mashumaro import DataClassDictMixin, field_options
from mashumaro.types import SerializationStrategy

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class AreaUnit(IntEnum):
    """Area unit."""

    Sqm = 0
    Sqft = 1
    Ping = 2


@dataclass
class LatestRecord(DataClassDictMixin):
    """Stats from last clean.

    TODO: this is just a list-formatted Record, with only some fields being available.
    """

    timestamp: datetime
    clean_time: int
    clean_area: int
    error: int  # most likely


@dataclass
class Record(DataClassDictMixin):
    """Historical cleanup result.

    Example:
     {
      "error": 1,
      "clean_time": 19,
      "clean_area": 11,
      "dust_collection": false,
      "timestamp": 1705156162,
      "start_type": 1,
      "task_type": 0,
      "record_index": 9
    }
    """

    #: Total time cleaned (in minutes)
    clean_time: timedelta = field(
        metadata=field_options(lambda x: timedelta(minutes=x))
    )
    #: Total area cleaned
    clean_area: int
    dust_collection: bool
    timestamp: datetime = field(
        metadata=field_options(
            deserialize=lambda x: datetime.fromtimestamp(x) if x else None
        )
    )
    info_num: int | None = None
    message: int | None = None
    map_id: int | None = None
    start_type: int | None = None
    task_type: int | None = None
    record_index: int | None = None

    #: Error code from cleaning
    error: int = field(default=0)


class LatestClean(SerializationStrategy):
    """Strategy to deserialize list of maps into a dict."""

    def deserialize(self, value: list[int]) -> Record:
        """Deserialize list of maps into a dict."""
        data = {
            "timestamp": value[0],
            "clean_time": value[1],
            "clean_area": value[2],
            "dust_collection": value[3],
        }
        return Record.from_dict(data)


@dataclass
class Records(DataClassDictMixin):
    """Response payload for getCleanRecords.

    Example:
        {"total_time": 185,
        "total_area": 149,
        "total_number": 10,
        "record_list_num": 10,
        "lastest_day_record": [
            1705156162,
            19,
            11,
            1
        ],
        "record_list": [
        <record>,
        ]
    }
    """

    total_time: timedelta = field(
        metadata=field_options(lambda x: timedelta(minutes=x))
    )
    total_area: int
    total_count: int = field(metadata=field_options(alias="total_number"))

    records: list[Record] = field(metadata=field_options(alias="record_list"))
    latest_clean: Record = field(
        metadata=field_options(
            serialization_strategy=LatestClean(), alias="lastest_day_record"
        )
    )


class VacuumRecords(SmartModule):
    """Implementation of vacuum cleaning records."""

    REQUIRED_COMPONENT = "clean_percent"
    _parsed_data: Records

    async def _post_update_hook(self) -> None:
        """Cache parsed data after an update."""
        self._parsed_data = Records.from_dict(self.data["getCleanRecords"])

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="total_clean_area",
                name="Total area cleaned",
                container=self,
                attribute_getter="total_clean_area",
                unit_getter="area_unit",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="total_clean_time",
                name="Total time cleaned",
                container=self,
                attribute_getter="total_clean_time",
                unit_getter=lambda: "min",  # ha-friendly unit, see UnitOfTime.MINUTES
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="total_clean_count",
                name="Total clean count",
                container=self,
                attribute_getter="total_clean_count",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getCleanRecords": {},
            "getAreaUnit": {},
        }

    @property
    def total_clean_area(self) -> int:
        """Return total cleaning area."""
        return self._parsed_data.total_area

    @property
    def total_clean_time(self) -> timedelta:
        """Return total cleaning time."""
        return self._parsed_data.total_time

    @property
    def total_clean_count(self) -> int:
        """Return total clean count."""
        return self._parsed_data.total_count

    @property
    def latest_clean_area(self) -> int:
        """Return latest cleaning area."""
        return self._parsed_data.latest_clean.clean_area

    @property
    def latest_clean_time(self) -> timedelta:
        """Return total cleaning time."""
        return self._parsed_data.latest_clean.clean_time

    @property
    def latest_clean_timestamp(self) -> datetime:
        """Return latest cleaning timestamp."""
        return self._parsed_data.latest_clean.timestamp

    @property
    def area_unit(self) -> AreaUnit:
        """Return area unit."""
        return AreaUnit(self.data["getAreaUnit"]["area_unit"])

    @property
    def parsed_data(self) -> Records:
        """Return parsed records data."""
        return self._parsed_data
