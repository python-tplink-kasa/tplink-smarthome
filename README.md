# python-kasa

[![PyPI version](https://badge.fury.io/py/python-kasa.svg)](https://badge.fury.io/py/python-kasa)
[![Build Status](https://github.com/python-kasa/python-kasa/actions/workflows/ci.yml/badge.svg)](https://github.com/python-kasa/python-kasa/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/python-kasa/python-kasa/branch/master/graph/badge.svg?token=5K7rtN5OmS)](https://codecov.io/gh/python-kasa/python-kasa)
[![Documentation Status](https://readthedocs.org/projects/python-kasa/badge/?version=latest)](https://python-kasa.readthedocs.io/en/latest/?badge=latest)

python-kasa is a Python library to control TPLink's smart home devices (plugs, wall switches, power strips, and bulbs).

This is a voluntary, community-driven effort and is not affiliated, sponsored, or endorsed by TPLink.

**Contributions in any form (adding missing features, reporting issues, fixing or triaging existing ones, improving the documentation, or device donations) are more than welcome!**

---

## Getting started

You can install the most recent release using pip:
```
pip install python-kasa
```

Alternatively, you can clone this repository and use `uv` to install the development version:
```
git clone https://github.com/python-kasa/python-kasa.git
cd python-kasa/
uv sync --all-extras
uv run kasa
```

If you have not yet provisioned your device, [you can do so using the cli tool](https://python-kasa.readthedocs.io/en/latest/cli.html#provisioning).

## Discovering devices

Running `kasa discover` will send discovery packets to the default broadcast address (`255.255.255.255`) to discover supported devices.
If your device requires authentication to control it,
you need to pass the credentials using `--username` and `--password` options or define `KASA_USERNAME` and `KASA_PASSWORD` environment variables.

> [!NOTE]
> If your system has multiple network interfaces, you can specify the broadcast address using the `--target` option.

The `discover` command will automatically execute the `state` command on all the discovered devices:

```
$ kasa discover
Discovering devices on 255.255.255.255 for 3 seconds

== Bulb McBulby - L530 ==
Host: 192.0.2.123
Port: 80
Device state: False
Time:         2024-06-22 15:42:15+02:00 (tz: {'timezone': 'CEST'}
Hardware:     3.0
Software:     1.1.6 Build 240130 Rel.173828
MAC (rssi):   5C:E9:31:aa:bb:cc (-50)
== Primary features ==
State (state): False
Brightness (brightness): 11 (range: 0-100)
Color temperature (color_temperature): 0 (range: 2500-6500)
Light effect (light_effect): *Off* Party Relax

== Information ==
Signal Level (signal_level): 2
Overheated (overheated): False
Cloud connection (cloud_connection): False
Update available (update_available): None
Device time (device_time): 2024-06-22 15:42:15+02:00

== Configuration ==
HSV (hsv): HSV(hue=35, saturation=70, value=11)
Auto update enabled (auto_update_enabled): False
Light preset (light_preset): *Not set* Light preset 1 Light preset 2 Light preset 3 Light preset 4 Light preset 5 Light preset 6 Light preset 7
Smooth transition on (smooth_transition_on): 2 (range: 0-60)
Smooth transition off (smooth_transition_off): 20 (range: 0-60)

== Debug ==
Device ID (device_id): soneuniqueidentifier
RSSI (rssi): -50 dBm
SSID (ssid): HomeNet
Current firmware version (current_firmware_version): 1.1.6 Build 240130 Rel.173828
Available firmware version (available_firmware_version): None
```


## Command line usage

All devices support a variety of common commands (like `on`, `off`, and `state`).
The syntax to control device is `kasa --host <host> <command>`:

```
$ kasa --host 192.0.2.123 on
```

Use `kasa --help` ([or consult the documentation](https://python-kasa.readthedocs.io/en/latest/cli.html#kasa-help)) to get a list of all available commands and options.
Some examples of available options include JSON output (`--json`), more verbose output (`--verbose`), and defining timeouts (`--timeout` and `--discovery-timeout`).
Refer [the documentation](https://python-kasa.readthedocs.io/en/latest/cli.html) for more details.

> [!NOTE]
> Each individual command may also have additional options, which are shown when called with the `--help` option.


### Feature interface

All devices are also controllable through a generic feature-based interface.
The available features differ from device to device and are accessible using `kasa feature` command:

```
$ kasa --host 192.0.2.123 feature
== Primary features ==
State (state): False
Brightness (brightness): 11 (range: 0-100)
Color temperature (color_temperature): 0 (range: 2500-6500)
Light effect (light_effect): *Off* Party Relax

== Information ==
Signal Level (signal_level): 2
Overheated (overheated): False
Cloud connection (cloud_connection): False
Update available (update_available): None
Device time (device_time): 2024-06-22 15:39:44+02:00

== Configuration ==
HSV (hsv): HSV(hue=35, saturation=70, value=11)
Auto update enabled (auto_update_enabled): False
Light preset (light_preset): *Not set* Light preset 1 Light preset 2 Light preset 3 Light preset 4 Light preset 5 Light preset 6 Light preset 7
Smooth transition on (smooth_transition_on): 2 (range: 0-60)
Smooth transition off (smooth_transition_off): 20 (range: 0-60)

== Debug ==
Device ID (device_id): soneuniqueidentifier
RSSI (rssi): -50 dBm
SSID (ssid): HomeNet
Current firmware version (current_firmware_version): 1.1.6 Build 240130 Rel.173828
Available firmware version (available_firmware_version): None
```

Some features present configuration that can be changed:
```
kasa --host 192.0.2.123 feature color_temperature 2500
Changing color_temperature from 0 to 2500
New state: 2500
```

> [!NOTE]
> When controlling hub-connected devices, you need to pass the device ID of the connected device as an option: `kasa --host 192.0.2.200 feature --child someuniqueidentifier target_temperature 21`


## Library usage

```
import asyncio
from kasa import Discover

async def main():
    dev = await Discover.discover_single("192.0.2.123", username="un@example.com", password="pw")
    await dev.turn_on()
    await dev.update()

if __name__ == "__main__":
    asyncio.run(main())
```

If you want to use this library in your own project, a good starting point is [the tutorial in the documentation](https://python-kasa.readthedocs.io/en/latest/tutorial.html).

You can find several code examples in the API documentation [How to guides](https://python-kasa.readthedocs.io/en/latest/guides.html).

Information about the library design and the way the devices work can be found in the [topics section](https://python-kasa.readthedocs.io/en/latest/topics.html).

## Contributing

Contributions are very welcome! The easiest way to contribute is by [creating a fixture file](https://python-kasa.readthedocs.io/en/latest/contribute.html#contributing-fixture-files) for the automated test suite if your device hardware and firmware version is not currently listed as supported.
Please refer to [our contributing guidelines](https://python-kasa.readthedocs.io/en/latest/contribute.html).

## Supported devices

The following devices have been tested and confirmed as working. If your device is unlisted but working, please consider [contributing a fixture file](https://python-kasa.readthedocs.io/en/latest/contribute.html#contributing-fixture-files).

> [!NOTE]
> The hub attached Tapo buttons S200B and S200D do not currently support alerting when the button is pressed.

> [!NOTE]
> Some firmware versions of Tapo Cameras will not authenticate unless you enable "Tapo Lab" > "Third-Party Compatibility" in the native Tapo app.
> Alternatively, you can factory reset and then prevent the device from accessing the internet.

<!--Do not edit text inside the SUPPORTED section below -->
<!--SUPPORTED_START-->
### Supported Kasa devices

- **Plugs**: EP10, EP25[^1], HS100[^2], HS103, HS105, HS110, KP100, KP105, KP115, KP125, KP125M[^1], KP401
- **Power Strips**: EP40, EP40M[^1], HS107, HS300, KP200, KP303, KP400
- **Wall Switches**: ES20M, HS200[^2], HS210, HS220[^2], KP405, KS200, KS200M, KS205[^1], KS220, KS220M, KS225[^1], KS230, KS240[^1]
- **Bulbs**: KL110, KL120, KL125, KL130, KL135, KL50, KL60, LB110
- **Light Strips**: KL400L5, KL420L5, KL430
- **Hubs**: KH100[^1]
- **Hub-Connected Devices[^3]**: KE100[^1]

### Supported Tapo[^1] devices

- **Plugs**: P100, P110, P110M, P115, P125M, P135, TP15
- **Power Strips**: P210M, P300, P304M, P306, TP25
- **Wall Switches**: S210, S220, S500D, S505, S505D
- **Bulbs**: L510B, L510E, L530B, L530E, L630
- **Light Strips**: L900-10, L900-5, L920-5, L930-5
- **Cameras**: C100, C110, C210, C220, C225, C325WB, C520WS, C720, TC65, TC70
- **Doorbells and chimes**: D100C, D130, D230
- **Vacuums**: RV20 Max Plus, RV20 Mop Plus, RV30 Max
- **Hubs**: H100, H200
- **Hub-Connected Devices[^3]**: S200B, S200D, T100, T110, T300, T310, T315

<!--SUPPORTED_END-->
[^1]: Model requires authentication
[^2]: Newer versions require authentication
[^3]: Devices may work across TAPO/KASA branded hubs

See [supported devices in our documentation](SUPPORTED.md) for more detailed information about tested hardware and software versions.

## Resources

### Developer Resources

* [softScheck's github contains lot of information and wireshark dissector](https://github.com/softScheck/tplink-smartplug)
* [TP-Link Smart Home Device Simulator](https://github.com/plasticrake/tplink-smarthome-simulator)
* [Unofficial API documentation](https://github.com/plasticrake/tplink-smarthome-api)
* [Another unofficial API documentation](https://github.com/whitslack/kasa)
* [pyHS100](https://github.com/GadgetReactor/pyHS100) provides synchronous interface and is the unmaintained predecessor of this library.


### Library Users

* [Home Assistant](https://www.home-assistant.io/integrations/tplink/)
* [MQTT access to TP-Link devices, using python-kasa](https://github.com/flavio-fernandes/mqtt2kasa)
* [Homebridge Kasa Python Plug-In](https://github.com/ZeliardM/homebridge-kasa-python)

### Other related projects

* [PyTapo - Python library for communication with Tapo Cameras](https://github.com/JurajNyiri/pytapo)
  * [Home Assistant integration](https://github.com/JurajNyiri/HomeAssistant-Tapo-Control)
* [Tapo P100 (Tapo plugs, Tapo bulbs)](https://github.com/fishbigger/TapoP100)
  * [Home Assistant integration](https://github.com/fishbigger/HomeAssistant-Tapo-P100-Control)
* [plugp100, another tapo library](https://github.com/petretiandrea/plugp100)
  * [Home Assistant integration](https://github.com/petretiandrea/home-assistant-tapo-p100)
* [rust and python implementation for tapo devices](https://github.com/mihai-dinculescu/tapo/)
