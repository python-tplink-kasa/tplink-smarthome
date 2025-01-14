"""Module for cli wifi commands."""

from __future__ import annotations

import asyncclick as click

from kasa import (
    Device,
)

from .common import (
    echo,
    pass_dev,
)


@click.group()
@pass_dev
def wifi(dev) -> None:
    """Commands to control wifi settings."""


@wifi.command()
@pass_dev
async def scan(dev):
    """Scan for available wifi networks."""
    echo("Scanning for wifi networks, wait a second..")
    devs = await dev.wifi_scan()
    echo(f"Found {len(devs)} wifi networks!")
    for dev in devs:
        echo(f"\t {dev}")

    return devs


@wifi.command()
@click.argument("ssid")
@click.option("--keytype", prompt=True, default="3")
@click.option("--password", prompt=True, hide_input=True)
@pass_dev
async def join(dev: Device, ssid: str, password: str, keytype: str):
    """Join the given wifi network."""
    echo(f"Asking the device to connect to {ssid}..")
    res = await dev.wifi_join(ssid, password, keytype=keytype)
    echo(
        f"Response: {res} - if the device is not able to join the network, "
        f"it will revert back to its previous state."
    )

    return res
