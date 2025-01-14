#!/usr/bin/env python
"""Script that checks supported devices and updates README.md and SUPPORTED.md."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from string import Template
from typing import Any, NamedTuple

from kasa.device_type import DeviceType
from kasa.iot import IotDevice
from kasa.smart import SmartDevice
from kasa.smartcam import SmartCamChild, SmartCamDevice


class SupportedVersion(NamedTuple):
    """Supported version."""

    region: str | None
    hw: str
    fw: str
    auth: bool


# The order of devices in this dict drives the display order
DEVICE_TYPE_TO_PRODUCT_GROUP = {
    DeviceType.Plug: "Plugs",
    DeviceType.Strip: "Power Strips",
    DeviceType.StripSocket: "Power Strips",
    DeviceType.Dimmer: "Wall Switches",
    DeviceType.WallSwitch: "Wall Switches",
    DeviceType.Fan: "Wall Switches",
    DeviceType.Bulb: "Bulbs",
    DeviceType.LightStrip: "Light Strips",
    DeviceType.Camera: "Cameras",
    DeviceType.Hub: "Hubs",
    DeviceType.Sensor: "Hub-Connected Devices",
    DeviceType.Thermostat: "Hub-Connected Devices",
    DeviceType.Chime: "Hub-Connected Devices",
}


SUPPORTED_FILENAME = "SUPPORTED.md"
README_FILENAME = "README.md"

IOT_FOLDER = "tests/fixtures/iot/"
SMART_FOLDER = "tests/fixtures/smart/"
SMART_CHILD_FOLDER = "tests/fixtures/smart/child"
SMARTCAM_FOLDER = "tests/fixtures/smartcam/"
SMARTCAM_CHILD_FOLDER = "tests/fixtures/smartcam/child"


def generate_supported(args):
    """Generate the SUPPORTED.md from the fixtures."""
    print_diffs = "--print-diffs" in args
    running_in_ci = "CI" in os.environ
    print("Generating supported devices")
    if running_in_ci:
        print_diffs = True
        print("Detected running in CI")

    supported = {"kasa": {}, "tapo": {}}

    _get_supported_devices(supported, IOT_FOLDER, IotDevice)
    _get_supported_devices(supported, SMART_FOLDER, SmartDevice)
    _get_supported_devices(supported, SMART_CHILD_FOLDER, SmartDevice)
    _get_supported_devices(supported, SMARTCAM_FOLDER, SmartCamDevice)
    _get_supported_devices(supported, SMARTCAM_CHILD_FOLDER, SmartCamChild)

    readme_updated = _update_supported_file(
        README_FILENAME, _supported_summary(supported), print_diffs
    )
    supported_updated = _update_supported_file(
        SUPPORTED_FILENAME, _supported_detail(supported), print_diffs
    )
    if not readme_updated and not supported_updated:
        print("Supported devices unchanged.")


def _update_supported_file(filename, supported_text, print_diffs) -> bool:
    with open(filename) as f:
        contents = f.readlines()

    start_index = end_index = None
    for index, line in enumerate(contents):
        if line == "<!--SUPPORTED_START-->\n":
            start_index = index + 1
        if line == "<!--SUPPORTED_END-->\n":
            end_index = index

    current_text = "".join(contents[start_index:end_index])
    if current_text != supported_text:
        print(
            f"{filename} has been modified with updated "
            + "supported devices, add file to commit."
        )
        if print_diffs:
            print("##CURRENT##")
            print(current_text)
            print("##NEW##")
            print(supported_text)

        new_contents = contents[:start_index]
        end_contents = contents[end_index:]
        new_contents.append(supported_text)
        new_contents.extend(end_contents)

        with open(filename, "w") as f:
            new_contents_text = "".join(new_contents)
            f.write(new_contents_text)
        return True
    return False


def _supported_summary(supported):
    return _supported_text(
        supported,
        "### Supported $brand$auth devices\n\n$types\n",
        "- **$type_$type_asterix**: $models\n",
    )


def _supported_detail(supported):
    return _supported_text(
        supported,
        "## $brand devices\n\n$preamble\n\n$types\n",
        "### $type_\n\n$models\n",
        "- **$model**\n$versions",
        "  - Hardware: $hw$region / Firmware: $fw$auth_flag\n",
    )


def _supported_text(
    supported, brand_template, types_template, model_template="", version_template=""
):
    brandt = Template(brand_template)
    typest = Template(types_template)
    modelt = Template(model_template)
    versst = Template(version_template)
    brands = ""
    version: SupportedVersion
    for brand, types in supported.items():
        preamble_text = (
            "Some newer Kasa devices require authentication. "
            + "These are marked with [^1] in the list below."
            if brand == "kasa"
            else "All Tapo devices require authentication."
        )
        preamble_text += (
            "<br>Hub-Connected Devices may work across TAPO/KASA branded "
            + "hubs even if they don't work across the native apps."
        )
        brand_text = brand.capitalize()
        brand_auth = r"[^1]" if brand == "tapo" else ""
        types_text = ""
        for supported_type, models in sorted(
            # Sort by device type order in the enum
            types.items(),
            key=lambda st: list(DEVICE_TYPE_TO_PRODUCT_GROUP.values()).index(st[0]),
        ):
            models_list = []
            models_text = ""
            for model, versions in sorted(models.items()):
                auth_count = 0
                versions_text = ""
                for version in sorted(versions):
                    region_text = f" ({version.region})" if version.region else ""
                    auth_count += 1 if version.auth else 0
                    vauth_flag = r"[^1]" if version.auth and brand == "kasa" else ""
                    if version_template:
                        versions_text += versst.substitute(
                            hw=version.hw,
                            fw=version.fw,
                            region=region_text,
                            auth_flag=vauth_flag,
                        )
                if brand == "kasa" and auth_count > 0:
                    auth_flag = r"[^1]" if auth_count == len(versions) else r"[^2]"
                else:
                    auth_flag = ""
                if model_template:
                    models_text += modelt.substitute(
                        model=model, versions=versions_text, auth_flag=auth_flag
                    )
                else:
                    models_list.append(f"{model}{auth_flag}")
            models_text = models_text if models_text else ", ".join(models_list)
            type_asterix = r"[^3]" if supported_type == "Hub-Connected Devices" else ""
            types_text += typest.substitute(
                type_=supported_type, type_asterix=type_asterix, models=models_text
            )
        brands += brandt.substitute(
            brand=brand_text, types=types_text, auth=brand_auth, preamble=preamble_text
        )
    return brands


def _get_supported_devices(
    supported: dict[str, Any],
    fixture_location: str,
    device_cls: type[IotDevice | SmartDevice | SmartCamDevice],
):
    for file in Path(fixture_location).glob("*.json"):
        with file.open() as f:
            fixture_data = json.load(f)

        model_info = device_cls._get_device_info(
            fixture_data, fixture_data.get("discovery_result", {}).get("result")
        )

        supported_type = DEVICE_TYPE_TO_PRODUCT_GROUP[model_info.device_type]

        stype = supported[model_info.brand].setdefault(supported_type, {})
        smodel = stype.setdefault(model_info.long_name, [])
        smodel.append(
            SupportedVersion(
                region=model_info.region if model_info.region else "",
                hw=model_info.hardware_version,
                fw=model_info.firmware_version,
                auth=model_info.requires_auth,
            )
        )


def main():
    """Entry point to module."""
    generate_supported(sys.argv[1:])


if __name__ == "__main__":
    generate_supported(sys.argv[1:])
