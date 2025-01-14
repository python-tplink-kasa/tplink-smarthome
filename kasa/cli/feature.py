"""Module for cli feature commands."""

from __future__ import annotations

import ast

import asyncclick as click

from kasa import Device, Feature

from .common import (
    echo,
    error,
    pass_dev_or_child,
)


def _echo_features(
    features: dict[str, Feature],
    title: str,
    category: Feature.Category | None = None,
    verbose: bool = False,
    indent: str = "\t",
) -> None:
    """Print out a listing of features and their values."""
    if category is not None:
        features = {
            id_: feat for id_, feat in features.items() if feat.category == category
        }

    echo(f"{indent}[bold]{title}[/bold]")
    for _, feat in features.items():
        try:
            echo(f"{indent}{feat}")
            if verbose:
                echo(f"{indent}\tType: {feat.type}")
                echo(f"{indent}\tCategory: {feat.category}")
                echo(f"{indent}\tIcon: {feat.icon}")
        except Exception as ex:
            echo(f"{indent}{feat.name} ({feat.id}): [red]got exception ({ex})[/red]")


def _echo_all_features(
    features, *, verbose=False, title_prefix=None, indent=""
) -> None:
    """Print out all features by category."""
    if title_prefix is not None:
        echo(f"[bold]\n{indent}== {title_prefix} ==[/bold]")
        echo()
    _echo_features(
        features,
        title="== Primary features ==",
        category=Feature.Category.Primary,
        verbose=verbose,
        indent=indent,
    )
    echo()
    _echo_features(
        features,
        title="== Information ==",
        category=Feature.Category.Info,
        verbose=verbose,
        indent=indent,
    )
    echo()
    _echo_features(
        features,
        title="== Configuration ==",
        category=Feature.Category.Config,
        verbose=verbose,
        indent=indent,
    )
    echo()
    _echo_features(
        features,
        title="== Debug ==",
        category=Feature.Category.Debug,
        verbose=verbose,
        indent=indent,
    )


@click.command(name="feature")
@click.argument("name", required=False)
@click.argument("value", required=False)
@pass_dev_or_child
@click.pass_context
async def feature(
    ctx: click.Context,
    dev: Device,
    name: str,
    value,
):
    """Access and modify features.

    If no *name* is given, lists available features and their values.
    If only *name* is given, the value of named feature is returned.
    If both *name* and *value* are set, the described setting is changed.
    """
    verbose = ctx.parent.params.get("verbose", False) if ctx.parent else False

    if not name:
        _echo_all_features(dev.features, verbose=verbose, indent="")

        if dev.children:
            for child_dev in dev.children:
                _echo_all_features(
                    child_dev.features,
                    verbose=verbose,
                    title_prefix=f"Child {child_dev.alias}",
                    indent="\t",
                )

        return

    if name not in dev.features:
        error(f"No feature by name '{name}'")
        return

    feat = dev.features[name]

    if value is None and feat.type is Feature.Type.Action:
        echo(f"Executing action {name}")
        response = await dev.features[name].set_value(value)
        echo(response)
        return response

    if value is None:
        unit = f" {feat.unit}" if feat.unit else ""
        echo(f"{feat.name} ({name}): {feat.value}{unit}")
        return feat.value

    try:
        # Attempt to parse as python literal.
        value = ast.literal_eval(value)
    except ValueError:
        # The value is probably an unquoted string, so we'll raise an error,
        # and tell the user to quote the string.
        raise click.exceptions.BadParameter(
            f'{repr(value)} for {name} (Perhaps you forgot to "quote" the value?)'
        ) from SyntaxError
    except SyntaxError:
        # There are likely miss-matched quotes or odd characters in the input,
        # so abort and complain to the user.
        raise click.exceptions.BadParameter(
            f"{repr(value)} for {name}"
        ) from SyntaxError

    echo(f"Changing {name} from {feat.value} to {value}")
    response = await dev.features[name].set_value(value)
    await dev.update()
    echo(f"New state: {feat.value}")

    return response
