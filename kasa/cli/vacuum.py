"""Module for cli vacuum commands.."""

from __future__ import annotations

import asyncclick as click
from PIL import ImageShow

from kasa import (
    Device,
    Module,
)

from .common import (
    error,
    pass_dev_or_child,
)


@click.group(invoke_without_command=True)
@click.pass_context
async def vacuum(ctx: click.Context) -> None:
    """Vacuum commands."""


@vacuum.group(invoke_without_command=True, name="map")
@pass_dev_or_child
async def map_group(dev: Device):
    """Return map."""
    if not (map := dev.modules.get(Module.Map)):
        error("This device does not support maps.")
        return

    click.echo(map.map_info)
    click.echo(map.map_data)

    click.echo("Use `kasa vacuum map show` to display the map")


@map_group.command()
@pass_dev_or_child
async def show(dev: Device):
    """Show current map."""
    if not (map := dev.modules.get(Module.Map)):
        error("This device does not support maps.")
        return

    img = map.get_map_image()

    img = img.resize((4 * img.width, 4 * img.height))
    ImageShow.show(img)


@map_group.command()
@pass_dev_or_child
async def path(dev: Device):
    """Show current path."""
    if not (map := dev.modules.get(Module.Map)):
        error("This device does not support maps.")
        return

    data = map.get_path()
    print(data)
