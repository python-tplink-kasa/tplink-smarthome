"""Device creation via DeviceConfig."""

from __future__ import annotations

import logging
import time
from typing import Any

from .device import Device
from .device_type import DeviceType
from .deviceconfig import DeviceConfig, DeviceEncryptionType, DeviceFamily
from .exceptions import KasaException, UnsupportedDeviceError
from .iot import (
    IotBulb,
    IotCamera,
    IotDevice,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from .protocols import (
    BaseProtocol,
    IotProtocol,
    SmartProtocol,
)
from .protocols.smartcamprotocol import SmartCamProtocol
from .smart import SmartDevice
from .smartcam import SmartCamDevice
from .transports import (
    AesTransport,
    BaseTransport,
    KlapTransport,
    KlapTransportV2,
    LinkieTransportV2,
    SslTransport,
    XorTransport,
)
from .transports.sslaestransport import SslAesTransport

_LOGGER = logging.getLogger(__name__)

GET_SYSINFO_QUERY: dict[str, dict[str, dict]] = {
    "system": {"get_sysinfo": {}},
}


async def connect(*, host: str | None = None, config: DeviceConfig) -> Device:
    """Connect to a single device by the given hostname or device configuration.

    This method avoids the UDP based discovery process and
    will connect directly to the device.

    It is generally preferred to avoid :func:`discover_single()` and
    use this function instead as it should perform better when
    the WiFi network is congested or the device is not responding
    to discovery requests.

    Do not use this function directly, use SmartDevice.connect()

    :param host: Hostname of device to query
    :param config: Connection parameters to ensure the correct protocol
        and connection options are used.
    :rtype: SmartDevice
    :return: Object for querying/controlling found device.
    """
    if host and config or (not host and not config):
        raise KasaException("One of host or config must be provded and not both")
    if host:
        config = DeviceConfig(host=host)

    if (protocol := get_protocol(config=config)) is None:
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}",
            host=config.host,
        )

    try:
        return await _connect(config, protocol)
    except:
        await protocol.close()
        raise


async def _connect(config: DeviceConfig, protocol: BaseProtocol) -> Device:
    debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
    if debug_enabled:
        start_time = time.perf_counter()

    def _perf_log(has_params: bool, perf_type: str) -> None:
        nonlocal start_time
        if debug_enabled:
            end_time = time.perf_counter()
            _LOGGER.debug(
                "Device %s with connection params %s took %.2f seconds to %s",
                config.host,
                has_params,
                end_time - start_time,
                perf_type,
            )
            start_time = time.perf_counter()

    device_class: type[Device] | None
    device: Device | None = None

    if isinstance(protocol, IotProtocol) and isinstance(
        protocol._transport, XorTransport
    ):
        info = await protocol.query(GET_SYSINFO_QUERY)
        _perf_log(True, "get_sysinfo")
        device_class = get_device_class_from_sys_info(info)
        device = device_class(config.host, protocol=protocol)
        device.update_from_discover_info(info)
        await device.update()
        _perf_log(True, "update")
        return device
    elif device_class := get_device_class_from_family(
        config.connection_type.device_family.value, https=config.connection_type.https
    ):
        device = device_class(host=config.host, protocol=protocol)
        await device.update()
        _perf_log(True, "update")
        return device
    else:
        raise UnsupportedDeviceError(
            f"Unsupported device for {config.host}: "
            + f"{config.connection_type.device_family.value}",
            host=config.host,
        )


def get_device_class_from_sys_info(sysinfo: dict[str, Any]) -> type[IotDevice]:
    """Find SmartDevice subclass for device described by passed data."""
    TYPE_TO_CLASS = {
        DeviceType.Bulb: IotBulb,
        DeviceType.Plug: IotPlug,
        DeviceType.Dimmer: IotDimmer,
        DeviceType.Strip: IotStrip,
        DeviceType.WallSwitch: IotWallSwitch,
        DeviceType.LightStrip: IotLightStrip,
        DeviceType.Camera: IotCamera,
    }
    return TYPE_TO_CLASS[IotDevice._get_device_type_from_sys_info(sysinfo)]


def get_device_class_from_family(
    device_type: str, *, https: bool, require_exact: bool = False
) -> type[Device] | None:
    """Return the device class from the type name."""
    supported_device_types: dict[str, type[Device]] = {
        "SMART.TAPOPLUG": SmartDevice,
        "SMART.TAPOBULB": SmartDevice,
        "SMART.TAPOSWITCH": SmartDevice,
        "SMART.KASAPLUG": SmartDevice,
        "SMART.TAPOHUB": SmartDevice,
        "SMART.TAPOHUB.HTTPS": SmartCamDevice,
        "SMART.KASAHUB": SmartDevice,
        "SMART.KASASWITCH": SmartDevice,
        "SMART.IPCAMERA.HTTPS": SmartCamDevice,
        "SMART.TAPOROBOVAC.HTTPS": SmartDevice,
        "IOT.SMARTPLUGSWITCH": IotPlug,
        "IOT.SMARTBULB": IotBulb,
        "IOT.IPCAMERA": IotCamera,
    }
    lookup_key = f"{device_type}{'.HTTPS' if https else ''}"
    if (
        (cls := supported_device_types.get(lookup_key)) is None
        and device_type.startswith("SMART.")
        and not require_exact
    ):
        _LOGGER.debug("Unknown SMART device with %s, using SmartDevice", device_type)
        cls = SmartDevice

    if cls is not None:
        _LOGGER.debug("Using %s for %s", cls.__name__, device_type)

    return cls


def get_protocol(config: DeviceConfig, *, strict: bool = False) -> BaseProtocol | None:
    """Return the protocol from the device config.

    For cameras and vacuums the device family is a simple mapping to
    the protocol/transport. For other device types the transport varies
    based on the discovery information.

    :param config: Device config to derive protocol
    :param strict: Require exact match on encrypt type
    """
    _LOGGER.debug("Finding protocol for %s", config.host)
    ctype = config.connection_type
    protocol_name = ctype.device_family.value.split(".")[0]
    _LOGGER.debug("Finding protocol for %s", ctype.device_family)

    if ctype.device_family is DeviceFamily.SmartIpCamera:
        if strict and ctype.encryption_type is not DeviceEncryptionType.Aes:
            return None
        return SmartCamProtocol(transport=SslAesTransport(config=config))

    if ctype.device_family is DeviceFamily.IotIpCamera:
        if strict and ctype.encryption_type is not DeviceEncryptionType.Xor:
            return None
        return IotProtocol(transport=LinkieTransportV2(config=config))

    # Older FW used a different transport
        if strict and ctype.encryption_type is not DeviceEncryptionType.Aes:
            return None
        and ctype.encryption_type is DeviceEncryptionType.Aes
    ):
        return SmartProtocol(transport=SslTransport(config=config))

    protocol_transport_key = (
        protocol_name
        + "."
        + ctype.encryption_type.value
        + (".HTTPS" if ctype.https else "")
    )

    _LOGGER.debug("Finding transport for %s", protocol_transport_key)
    supported_device_protocols: dict[
        str, tuple[type[BaseProtocol], type[BaseTransport]]
    ] = {
        "IOT.XOR": (IotProtocol, XorTransport),
        "IOT.KLAP": (IotProtocol, KlapTransport),
        "SMART.AES": (SmartProtocol, AesTransport),
        "SMART.KLAP": (SmartProtocol, KlapTransportV2),
        "SMART.KLAP.HTTPS": (SmartProtocol, KlapTransportV2),
        # H200 is device family SMART.TAPOHUB and uses SmartCamProtocol so use
        # https to distuingish from SmartProtocol devices
        "SMART.AES.HTTPS": (SmartCamProtocol, SslAesTransport),
    }
    if not (prot_tran_cls := supported_device_protocols.get(protocol_transport_key)):
        return None
    protocol_cls, transport_cls = prot_tran_cls
    return protocol_cls(transport=transport_cls(config=config))
