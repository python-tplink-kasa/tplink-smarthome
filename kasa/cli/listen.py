"""Module for cli listen commands."""

import asyncio
from contextlib import suppress
from typing import cast

import asyncclick as click

from kasa import (
    Credentials,
    Device,
)
from kasa.eventtype import EventType

from .common import echo, error, pass_dev_or_child


async def wait_on_keyboard_interrupt(msg: str):
    """Non loop blocking get input."""
    echo(msg + ", press Ctrl-C to cancel\n")

    with suppress(asyncio.CancelledError):
        await asyncio.Event().wait()


@click.command()
@click.option(
    "--cam-username",
    required=True,
    envvar="KASA_CAMERA_USERNAME",
    help="Camera account username address to authenticate to device.",
)
@click.option(
    "--cam-password",
    required=True,
    envvar="KASA_CAMERA_PASSWORD",
    help="Camera account password to use to authenticate to device.",
)
@click.option(
    "--listen-port",
    default=None,
    required=False,
    envvar="KASA_LISTEN_PORT",
    help="Port to listen on for onvif notifications.",
)
@click.option(
    "--listen-ip",
    default=None,
    required=False,
    envvar="KASA_LISTEN_IP",
    help="Ip address to listen on for onvif notifications.",
)
@click.option(
    "-et",
    "--event-types",
    default=None,
    required=False,
    multiple=True,
    type=click.Choice([et for et in EventType], case_sensitive=False),
    help="Event types to listen to.",
)
@pass_dev_or_child
async def listen(
    dev: Device,
    cam_username: str,
    cam_password: str,
    listen_port: int | None,
    listen_ip: str | None,
    event_types: list[EventType] | None,
) -> None:
    """Listen for events like motion, triggers or alarms."""
    try:
        import onvif  # type: ignore[import-untyped] # noqa: F401
    except ImportError:
        error("python-kasa must be installed with onvif extra for listen.")

    from kasa.smartcam.modules.onviflisten import OnvifListen

    listen: OnvifListen = cast(OnvifListen, dev.modules.get(OnvifListen._module_name()))
    if not listen:
        error(f"Device {dev.host} does not support listening for events.")

    def on_event(event: EventType) -> None:
        echo(f"Device {dev.host} received event {event}")

    creds = Credentials(cam_username, cam_password)
    await listen.listen(
        on_event,
        creds,
        listen_ip=listen_ip,
        listen_port=listen_port,
        event_types=event_types,
    )

    msg = f"Listening for events on {listen.listening_address}"

    await wait_on_keyboard_interrupt(msg)

    echo("\nStopping listener")
    await listen.stop()
