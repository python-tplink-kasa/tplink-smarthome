"""Module for cli vacuum commands.."""

from __future__ import annotations

import asyncclick as click

from kasa import (
    Device,
    Module,
)

from .common import (
    error,
    pass_dev_or_child,
)


@click.group(invoke_without_command=False)
@click.pass_context
async def vacuum(ctx: click.Context) -> None:
    """Vacuum commands."""


@vacuum.group(invoke_without_command=True, name="records")
@pass_dev_or_child
async def records_group(dev: Device) -> None:
    """Access cleaning records."""
    if not (rec := dev.modules.get(Module.VacuumRecords)):
        error("This device does not support records.")

    data = rec.parsed_data
    latest = data.latest_clean
    click.echo(
        f"Totals: {rec.total_clean_area} {rec.area_unit} in {rec.total_clean_time} "
        f"(cleaned {rec.total_clean_count} times)"
    )
    click.echo(f"Last clean: {latest.clean_area} {rec.area_unit} @ {latest.clean_time}")
    click.echo("Execute `kasa vacuum records list` to list all records.")


@records_group.command(name="list")
@pass_dev_or_child
async def records_list(dev: Device) -> None:
    """List all cleaning records."""
    if not (rec := dev.modules.get(Module.VacuumRecords)):
        error("This device does not support records.")

    data = rec.parsed_data
    for record in data.records:
        click.echo(f"* {record}")
