"""Module for listen event types."""

from enum import StrEnum, auto


class EventType(StrEnum):
    """Listen event types."""

    MOTION_DETECTED = auto()
    PERSON_DETECTED = auto()
    TAMPER_DETECTED = auto()
    BABY_CRY_DETECTED = auto()
