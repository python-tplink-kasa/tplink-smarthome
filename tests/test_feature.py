import logging
from unittest.mock import AsyncMock, patch

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Feature, KasaException
from kasa.iot import IotStrip

_LOGGER = logging.getLogger(__name__)


class DummyDevice:
    pass


@pytest.fixture
def dummy_feature() -> Feature:
    # create_autospec for device slows tests way too much, so we use a dummy here

    feat = Feature(
        device=DummyDevice(),  # type: ignore[arg-type]
        id="dummy_feature",
        name="dummy_feature",
        attribute_getter="dummygetter",
        attribute_setter="dummysetter",
        container=None,
        icon="mdi:dummy",
        type=Feature.Type.Switch,
        unit_getter=lambda: "dummyunit",
    )
    return feat


def test_feature_api(dummy_feature: Feature):
    """Test all properties of a dummy feature."""
    assert dummy_feature.device is not None
    assert dummy_feature.name == "dummy_feature"
    assert dummy_feature.attribute_getter == "dummygetter"
    assert dummy_feature.attribute_setter == "dummysetter"
    assert dummy_feature.container is None
    assert dummy_feature.icon == "mdi:dummy"
    assert dummy_feature.type == Feature.Type.Switch
    assert dummy_feature.unit == "dummyunit"


@pytest.mark.parametrize(
    "read_only_type", [Feature.Type.Sensor, Feature.Type.BinarySensor]
)
def test_feature_setter_on_sensor(read_only_type):
    """Test that creating a sensor feature with a setter causes an error."""
    with pytest.raises(ValueError, match="Invalid type for configurable feature"):
        Feature(
            device=DummyDevice(),  # type: ignore[arg-type]
            id="dummy_error",
            name="dummy error",
            attribute_getter="dummygetter",
            attribute_setter="dummysetter",
            type=read_only_type,
        )


def test_feature_value(dummy_feature: Feature):
    """Verify that property gets accessed on *value* access."""
    dummy_feature.attribute_getter = "test_prop"
    dummy_feature.device.test_prop = "dummy"  # type: ignore[attr-defined]
    assert dummy_feature.value == "dummy"


def test_feature_value_container(mocker, dummy_feature: Feature):
    """Test that container's attribute is accessed when expected."""

    class DummyContainer:
        @property
        def test_prop(self):
            return "dummy"

    dummy_feature.container = DummyContainer()
    dummy_feature.attribute_getter = "test_prop"

    mock_dev_prop = mocker.patch.object(
        dummy_feature, "test_prop", new_callable=mocker.PropertyMock, create=True
    )

    assert dummy_feature.value == "dummy"
    mock_dev_prop.assert_not_called()


def test_feature_value_callable(dev, dummy_feature: Feature):
    """Verify that callables work as *attribute_getter*."""
    dummy_feature.attribute_getter = lambda x: "dummy value"
    assert dummy_feature.value == "dummy value"


async def test_feature_setter(dev, mocker, dummy_feature: Feature):
    """Verify that *set_value* calls the defined method."""
    mock_set_dummy = mocker.patch.object(
        dummy_feature.device, "set_dummy", create=True, new_callable=AsyncMock
    )
    dummy_feature.attribute_setter = "set_dummy"
    await dummy_feature.set_value("dummy value")
    mock_set_dummy.assert_called_with("dummy value")


async def test_feature_setter_read_only(dummy_feature):
    """Verify that read-only feature raises an exception when trying to change it."""
    dummy_feature.attribute_setter = None
    with pytest.raises(ValueError, match="Tried to set read-only feature"):
        await dummy_feature.set_value("value for read only feature")


async def test_feature_action(mocker):
    """Test that setting value on button calls the setter."""
    feat = Feature(
        device=DummyDevice(),  # type: ignore[arg-type]
        id="dummy_feature",
        name="dummy_feature",
        attribute_setter="call_action",
        container=None,
        icon="mdi:dummy",
        type=Feature.Type.Action,
    )
    mock_call_action = mocker.patch.object(
        feat.device, "call_action", create=True, new_callable=AsyncMock
    )
    assert feat.value == "<Action>"
    await feat.set_value(1234)
    mock_call_action.assert_called()


@pytest.mark.xdist_group(name="caplog")
async def test_feature_choice_list(dummy_feature, caplog, mocker: MockerFixture):
    """Test the choice feature type."""
    dummy_feature.type = Feature.Type.Choice
    dummy_feature.choices_getter = lambda: ["first", "second"]

    mock_setter = mocker.patch.object(
        dummy_feature.device, "dummysetter", create=True, new_callable=AsyncMock
    )
    await dummy_feature.set_value("first")
    mock_setter.assert_called_with("first")
    mock_setter.reset_mock()

    with pytest.raises(ValueError, match="Unexpected value for dummy_feature: invalid"):  # noqa: PT012
        await dummy_feature.set_value("invalid")
        assert "Unexpected value" in caplog.text

    mock_setter.assert_not_called()


@pytest.mark.parametrize("precision_hint", [1, 2, 3])
async def test_precision_hint(dummy_feature, precision_hint):
    """Test that precision hint works as expected."""
    dummy_value = 3.141593
    dummy_feature.type = Feature.Type.Sensor
    dummy_feature.precision_hint = precision_hint

    dummy_feature.attribute_getter = lambda x: dummy_value
    assert dummy_feature.value == dummy_value
    assert f"{round(dummy_value, precision_hint)} dummyunit" in repr(dummy_feature)


async def test_feature_setters(dev: Device, mocker: MockerFixture):
    """Test that all feature setters query something."""
    # setters that do not call set on the device itself.
    internal_setters = {"pan_step", "tilt_step"}

    async def _test_feature(feat, query_mock):
        if feat.attribute_setter is None:
            return

        # IotStrip makes calls via it's children
        expecting_call = feat.id not in internal_setters and not isinstance(
            dev, IotStrip
        )

        if feat.type == Feature.Type.Number:
            await feat.set_value(feat.minimum_value)
        elif feat.type == Feature.Type.Switch:
            await feat.set_value(True)
        elif feat.type == Feature.Type.Action:
            await feat.set_value("dummyvalue")
        elif feat.type == Feature.Type.Choice:
            await feat.set_value(feat.choices[0])
        elif feat.type == Feature.Type.Unknown:
            _LOGGER.warning("Feature '%s' has no type, cannot test the setter", feat)
            expecting_call = False
        else:
            raise NotImplementedError(f"set_value not implemented for {feat.type}")

        if expecting_call:
            query_mock.assert_called()

    async def _test_features(dev):
        exceptions = []
        for feat in dev.features.values():
            try:
                with patch.object(feat.device.protocol, "query") as query:
                    await _test_feature(feat, query)
            # we allow our own exceptions to avoid mocking valid responses
            except KasaException:
                pass
            except Exception as ex:
                ex.add_note(f"Exception when trying to set {feat} on {dev}")
                exceptions.append(ex)

        return exceptions

    exceptions = await _test_features(dev)

    for child in dev.children:
        exceptions.extend(await _test_features(child))

    if exceptions:
        raise ExceptionGroup(
            "Got exceptions while testing attribute_setters", exceptions
        )
