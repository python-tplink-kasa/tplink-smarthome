"""Implementation of vacuum cleaning records."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from mashumaro import DataClassDictMixin

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


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

    #: Error code from cleaning
    error: int
    #: Total time cleaned (in minutes)
    clean_time: int
    #: Total area cleaned (in sqm?)
    clean_area: int
    dust_collection: bool
    timestamp: datetime

    start_type: int
    task_type: int
    record_index: int


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

    total_time: int
    total_area: int
    total_number: int
    record_list_num: int
    record_list: list[Record]
    # TODO: conversion from list to dict/basemodel input TBD
    # latest_clean: LatestRecord = Field(alias="lastest_day_record"))


class VacuumRecords(SmartModule):
    """Implementation of vacuum cleaning records."""

    REQUIRED_COMPONENT = "consumables"
    QUERY_GETTER_NAME = "getCleanRecords"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="total_clean_area",
                name="Total area cleaned",
                container=self,
                attribute_getter="total_clean_area",
                unit_getter=lambda: "sqm",
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

    @property
    def total_clean_area(self) -> int:
        """Return total cleaning area."""
        return self.data["total_area"]

    @property
    def total_clean_time(self) -> int:
        """Return total cleaning time."""
        return self.data["total_time"]

    @property
    def total_clean_count(self) -> int:
        """Return total clean count."""
        return self.data["total_number"]
