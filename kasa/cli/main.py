"""Main module for cli tool."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncclick as click

if TYPE_CHECKING:
    from kasa import Device

from kasa.deviceconfig import DeviceEncryptionType

from .common import (
    SKIP_UPDATE_COMMANDS,
    CatchAllExceptions,
    echo,
    error,
    invoke_subcommand,
    json_formatter_cb,
    pass_dev_or_child,
)
from .lazygroup import LazyGroup

TYPES = [
    "plug",
    "switch",
    "bulb",
    "dimmer",
    "strip",
    "lightstrip",
    "smart",
    "camera",
]

ENCRYPT_TYPES = [encrypt_type.value for encrypt_type in DeviceEncryptionType]
DEFAULT_TARGET = "255.255.255.255"


def _legacy_type_to_class(_type: str) -> Any:
    from kasa.iot import (
        IotBulb,
        IotDimmer,
        IotLightStrip,
        IotPlug,
        IotStrip,
        IotWallSwitch,
    )

    TYPE_TO_CLASS = {
        "plug": IotPlug,
        "switch": IotWallSwitch,
        "bulb": IotBulb,
        "dimmer": IotDimmer,
        "strip": IotStrip,
        "lightstrip": IotLightStrip,
    }
    return TYPE_TO_CLASS[_type]


@click.group(
    invoke_without_command=True,
    cls=CatchAllExceptions(LazyGroup),
    lazy_subcommands={
        "discover": None,
        "device": None,
        "feature": None,
        "light": None,
        "wifi": None,
        "time": None,
        "schedule": None,
        "usage": None,
        "energy": "usage",
        # device commands runnnable at top level
        "state": "device",
        "on": "device",
        "off": "device",
        "toggle": "device",
        "led": "device",
        "alias": "device",
        "reboot": "device",
        "update_credentials": "device",
        "sysinfo": "device",
        # light commands runnnable at top level
        "presets": "light",
        "brightness": "light",
        "hsv": "light",
        "temperature": "light",
        "effect": "light",
        "vacuum": "vacuum",
    },
    result_callback=json_formatter_cb,
)
@click.option(
    "--host",
    envvar="KASA_HOST",
    required=False,
    help="The host name or IP address of the device to connect to.",
)
@click.option(
    "--port",
    envvar="KASA_PORT",
    required=False,
    type=int,
    help="The port of the device to connect to.",
)
@click.option(
    "--alias",
    envvar="KASA_NAME",
    required=False,
    help="The device name, or alias, of the device to connect to.",
)
@click.option(
    "--target",
    envvar="KASA_TARGET",
    default=DEFAULT_TARGET,
    required=False,
    show_default=True,
    help="The broadcast address to be used for discovery.",
)
@click.option(
    "-v",
    "--verbose",
    envvar="KASA_VERBOSE",
    required=False,
    default=False,
    is_flag=True,
    help="Be more verbose on output",
)
@click.option(
    "-d",
    "--debug",
    envvar="KASA_DEBUG",
    default=False,
    is_flag=True,
    help="Print debug output",
)
@click.option(
    "--type",
    envvar="KASA_TYPE",
    default=None,
    type=click.Choice(TYPES, case_sensitive=False),
    help="The device type in order to bypass discovery. Use `smart` for newer devices",
)
@click.option(
    "--json/--no-json",
    envvar="KASA_JSON",
    default=False,
    is_flag=True,
    help="Output raw device response as JSON.",
)
@click.option(
    "-e",
    "--encrypt-type",
    envvar="KASA_ENCRYPT_TYPE",
    default=None,
    type=click.Choice(ENCRYPT_TYPES, case_sensitive=False),
)
@click.option(
    "-df",
    "--device-family",
    envvar="KASA_DEVICE_FAMILY",
    default="SMART.TAPOPLUG",
    help="Device family type, e.g. `SMART.KASASWITCH`. Deprecated use `--type smart`",
)
@click.option(
    "-lv",
    "--login-version",
    envvar="KASA_LOGIN_VERSION",
    default=2,
    type=int,
    help="The login version for device authentication. Defaults to 2",
)
@click.option(
    "--https/--no-https",
    envvar="KASA_HTTPS",
    default=False,
    is_flag=True,
    type=bool,
    help="Set flag if the device encryption uses https.",
)
@click.option(
    "--timeout",
    envvar="KASA_TIMEOUT",
    default=5,
    required=False,
    show_default=True,
    help="Timeout for device communications.",
)
@click.option(
    "--discovery-timeout",
    envvar="KASA_DISCOVERY_TIMEOUT",
    default=10,
    required=False,
    show_default=True,
    help="Timeout for discovery.",
)
@click.option(
    "--username",
    default=None,
    required=False,
    envvar="KASA_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    default=None,
    required=False,
    envvar="KASA_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.option(
    "--credentials-hash",
    default=None,
    required=False,
    envvar="KASA_CREDENTIALS_HASH",
    help="Hashed credentials used to authenticate to the device.",
)
@click.version_option(package_name="python-kasa")
@click.pass_context
async def cli(
    ctx,
    host,
    port,
    alias,
    target,
    verbose,
    debug,
    type,
    encrypt_type,
    https,
    device_family,
    login_version,
    json,
    timeout,
    discovery_timeout,
    username,
    password,
    credentials_hash,
):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    # no need to perform any checks if we are just displaying the help
    if "--help" in sys.argv:
        # Context object is required to avoid crashing on sub-groups
        ctx.obj = object()
        return

    if target != DEFAULT_TARGET and host:
        error("--target is not a valid option for single host discovery")

    logging_config: dict[str, Any] = {
        "level": logging.DEBUG if debug > 0 else logging.INFO
    }
    try:
        from rich.logging import RichHandler

        rich_config = {
            "show_time": False,
        }
        logging_config["handlers"] = [RichHandler(**rich_config)]
        logging_config["format"] = "%(message)s"
    except ImportError:
        pass

    # The configuration should be converted to use dictConfig,
    # but this keeps mypy happy for now
    logging.basicConfig(**logging_config)  # type: ignore

    if ctx.invoked_subcommand == "discover":
        return

    if alias is not None and host is not None:
        raise click.BadOptionUsage("alias", "Use either --alias or --host, not both.")

    if bool(password) != bool(username):
        raise click.BadOptionUsage(
            "username", "Using authentication requires both --username and --password"
        )

    if username:
        from kasa.credentials import Credentials

        credentials = Credentials(username=username, password=password)
    else:
        credentials = None

    if host is None and alias is None:
        if ctx.invoked_subcommand and ctx.invoked_subcommand != "discover":
            error("Only discover is available without --host or --alias")

        echo("No host name given, trying discovery..")
        from .discover import discover

        return await invoke_subcommand(discover, ctx)

    device_updated = False
    device_discovered = False

    if type is not None and type not in {"smart", "camera"}:
        from kasa.deviceconfig import DeviceConfig

        config = DeviceConfig(host=host, port_override=port, timeout=timeout)
        dev = _legacy_type_to_class(type)(host, config=config)
    elif type in {"smart", "camera"} or (device_family and encrypt_type):
        if type == "camera":
            encrypt_type = "AES"
            https = True
            login_version = 2
            device_family = "SMART.IPCAMERA"

        from kasa.device import Device
        from kasa.deviceconfig import (
            DeviceConfig,
            DeviceConnectionParameters,
            DeviceEncryptionType,
            DeviceFamily,
        )

        if not encrypt_type:
            encrypt_type = "KLAP"

        ctype = DeviceConnectionParameters(
            DeviceFamily(device_family),
            DeviceEncryptionType(encrypt_type),
            login_version,
            https,
        )
        config = DeviceConfig(
            host=host,
            port_override=port,
            credentials=credentials,
            credentials_hash=credentials_hash,
            timeout=timeout,
            connection_type=ctype,
        )
        dev = await Device.connect(config=config)
        device_updated = True
    elif alias:
        echo(f"Alias is given, using discovery to find host {alias}")

        from .discover import find_dev_from_alias

        dev = await find_dev_from_alias(
            alias=alias, target=target, credentials=credentials
        )
        if not dev:
            echo(f"No device with name {alias} found")
            return
        echo(f"Found hostname by alias: {dev.host}")
        device_updated = True
    else:  # host will be set
        from .discover import discover

        discovered = await invoke_subcommand(discover, ctx)
        if not discovered:
            error(f"Unable to create device for {host}")
        dev = discovered[host]
        device_discovered = True

    # Skip update on specific commands, or if device factory,
    # that performs an update was used for the device.
    if ctx.invoked_subcommand not in SKIP_UPDATE_COMMANDS and not device_updated:
        await dev.update()

    @asynccontextmanager
    async def async_wrapped_device(device: Device):
        try:
            yield device
        finally:
            await device.disconnect()

    ctx.obj = await ctx.with_async_resource(async_wrapped_device(dev))

    # discover command has already invoked state
    if ctx.invoked_subcommand is None and not device_discovered:
        from .device import state

        return await ctx.invoke(state)

    return dev


@cli.command()
@pass_dev_or_child
async def shell(dev: Device) -> None:
    """Open interactive shell."""
    echo(f"Opening shell for {dev}")
    from ptpython.repl import embed

    logging.getLogger("parso").setLevel(logging.WARNING)  # prompt parsing
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    loop = asyncio.get_event_loop()
    try:
        await embed(  # type: ignore[func-returns-value]
            globals=globals(),
            locals=locals(),
            return_asyncio_coroutine=True,
            patch_stdout=True,
        )
    except EOFError:
        loop.stop()


@cli.command()
@click.pass_context
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(ctx, module, command, parameters):
    """Run a raw command on the device."""
    logging.warning("Deprecated, use 'kasa command --module %s %s'", module, command)
    return await ctx.forward(cmd_command)


@cli.command(name="command")
@click.option("--module", required=False, help="Module for IOT protocol.")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
@pass_dev_or_child
async def cmd_command(dev: Device, module, command, parameters):
    """Run a raw command on the device."""
    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    from kasa import KasaException
    from kasa.iot import IotDevice
    from kasa.smart import SmartDevice

    if isinstance(dev, IotDevice):
        res = await dev._query_helper(module, command, parameters)
    elif isinstance(dev, SmartDevice):
        res = await dev._query_helper(command, parameters)
    else:
        raise KasaException("Unexpected device type %s.", dev)
    echo(json.dumps(res))
    return res
