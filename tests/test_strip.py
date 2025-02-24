from datetime import datetime

import pytest

from kasa import Device, KasaException, Module
from kasa.iot import IotStrip

from .conftest import handle_turn_on, strip, strip_iot, turn_on


@strip
@turn_on
async def test_children_change_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    for plug in dev.children:
        orig_state = plug.is_on
        if orig_state:
            await plug.turn_off()
            await dev.update()
            assert plug.is_on is False
            assert plug.is_off is True

            await plug.turn_on()
            await dev.update()
            assert plug.is_on is True
            assert plug.is_off is False
        else:
            await plug.turn_on()
            await dev.update()
            assert plug.is_on is True
            assert plug.is_off is False

            await plug.turn_off()
            await dev.update()
            assert plug.is_on is False
            assert plug.is_off is True


@strip
async def test_children_alias(dev):
    test_alias = "TEST1234"
    for plug in dev.children:
        original = plug.alias
        await plug.set_alias(alias=test_alias)
        await dev.update()  # TODO: set_alias does not call parent's update()..
        assert plug.alias == test_alias

        await plug.set_alias(alias=original)
        await dev.update()  # TODO: set_alias does not call parent's update()..
        assert plug.alias == original


@strip
async def test_children_on_since(dev):
    on_sinces = []
    for plug in dev.children:
        if plug.is_on:
            on_sinces.append(plug.on_since)
            assert isinstance(plug.on_since, datetime)
        else:
            assert plug.on_since is None

    if dev.is_off:
        assert dev.on_since is None
    # TODO: testing this would require some mocking utcnow which is not
    # very straightforward.
    # else:
    #    assert dev.on_since == max(on_sinces)


@strip
async def test_get_plug_by_name(dev: IotStrip):
    name = dev.children[0].alias
    assert dev.get_plug_by_name(name) == dev.children[0]  # type: ignore[arg-type]

    with pytest.raises(KasaException):
        dev.get_plug_by_name("NONEXISTING NAME")


@strip
async def test_get_plug_by_index(dev: IotStrip):
    assert dev.get_plug_by_index(0) == dev.children[0]

    with pytest.raises(KasaException):
        dev.get_plug_by_index(-1)

    with pytest.raises(KasaException):
        dev.get_plug_by_index(len(dev.children))


@strip
async def test_plug_features(dev: IotStrip):
    """Test the child plugs have default features."""
    for child in dev.children:
        assert "state" in child.features
        assert "on_since" in child.features


@pytest.mark.skip("this test will wear out your relays")
async def test_all_binary_states(dev):
    # test every binary state
    # TODO: this needs to be fixed, dev.plugs is not available for each device..
    for state in range(2 ** len(dev.children)):
        # create binary state map
        state_map = {}
        for plug_index in range(len(dev.children)):
            state_map[plug_index] = bool((state >> plug_index) & 1)

            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

        # check state map applied
        for index, state in dev.is_on.items():
            assert state_map[index] == state

        # toggle each outlet with state map applied
        for plug_index in range(len(dev.children)):
            # toggle state
            if state_map[plug_index]:
                await dev.turn_off(index=plug_index)
            else:
                await dev.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in dev.is_on.items():
                if index == plug_index:
                    assert state != state_map[index]
                else:
                    assert state == state_map[index]

            # reset state
            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

            # original state map should be restored
            for index, state in dev.is_on.items():
                assert state == state_map[index]


@strip
def test_children_api(dev):
    """Test the child device API."""
    first = dev.children[0]
    first_by_get_child_device = dev.get_child_device(first.device_id)
    assert first == first_by_get_child_device


@strip_iot
async def test_children_energy(dev: Device):
    if Module.Energy not in dev.modules:
        pytest.skip(f"skipping device {dev.model} does not support energy")

    for plug in dev.children:
        # For now all known strips with energy support these
        energy = plug.modules[Module.Energy]
        assert "voltage" in energy._module_features
        assert "current" in energy._module_features
        assert "power" in energy._module_features
