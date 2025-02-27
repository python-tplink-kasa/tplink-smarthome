"""Modules for SMART devices."""

from ..effects import SmartLightEffect
from .alarm import Alarm
from .autooff import AutoOff
from .batterysensor import BatterySensor
from .brightness import Brightness
from .childdevice import ChildDevice
from .childlock import ChildLock
from .childprotection import ChildProtection
from .childsetup import ChildSetup
from .clean import Clean
from .cleanrecords import CleanRecords
from .cloud import Cloud
from .color import Color
from .colortemperature import ColorTemperature
from .consumables import Consumables
from .contactsensor import ContactSensor
from .devicemodule import DeviceModule
from .dimmercalibration import DimmerCalibration
from .dustbin import Dustbin
from .energy import Energy
from .fan import Fan
from .firmware import Firmware
from .frostprotection import FrostProtection
from .homekit import HomeKit
from .humiditysensor import HumiditySensor
from .led import Led
from .light import Light
from .lighteffect import LightEffect
from .lightpreset import LightPreset
from .lightstripeffect import LightStripEffect
from .lighttransition import LightTransition
from .matter import Matter
from .mop import Mop
from .motionsensor import MotionSensor
from .overheatprotection import OverheatProtection
from .powerprotection import PowerProtection
from .reportmode import ReportMode
from .speaker import Speaker
from .temperaturecontrol import TemperatureControl
from .temperaturesensor import TemperatureSensor
from .thermostat import Thermostat
from .time import Time
from .triggerlogs import TriggerLogs
from .waterleaksensor import WaterleakSensor

__all__ = [
    "Alarm",
    "Time",
    "Energy",
    "DeviceModule",
    "DimmerCalibration",
    "ChildDevice",
    "ChildLock",
    "ChildSetup",
    "BatterySensor",
    "HumiditySensor",
    "TemperatureSensor",
    "TemperatureControl",
    "ChildProtection",
    "ReportMode",
    "AutoOff",
    "Led",
    "Brightness",
    "Fan",
    "LightPreset",
    "Firmware",
    "Cloud",
    "Light",
    "LightEffect",
    "LightStripEffect",
    "LightTransition",
    "ColorTemperature",
    "Color",
    "WaterleakSensor",
    "ContactSensor",
    "MotionSensor",
    "TriggerLogs",
    "FrostProtection",
    "Thermostat",
    "Clean",
    "Consumables",
    "CleanRecords",
    "SmartLightEffect",
    "PowerProtection",
    "OverheatProtection",
    "Speaker",
    "HomeKit",
    "Matter",
    "Dustbin",
    "Mop",
]
