"""Discover TPLink Smart Home devices.

The main entry point for this library is :func:`Discover.discover()`,
which returns a dictionary of the found devices. The key is the IP address
of the device and the value contains ready-to-use, SmartDevice-derived
device object.

:func:`discover_single()` can be used to initialize a single device given its
IP address. If the :class:`DeviceConfig` of the device is already known,
you can initialize the corresponding device class directly without discovery.

The protocol uses UDP broadcast datagrams on port 9999 and 20002 for discovery.
Legacy devices support discovery on port 9999 and newer devices on 20002.

Newer devices that respond on port 20002 will most likely require TP-Link cloud
credentials to be passed if queries or updates are to be performed on the returned
devices.

Discovery returns a dict of {ip: discovered devices}:

>>> from kasa import Discover, Credentials
>>>
>>> found_devices = await Discover.discover()
>>> [dev.model for dev in found_devices.values()]
['KP303', 'HS110', 'L530E', 'KL430', 'HS220', 'H200']

You can pass username and password for devices requiring authentication:

>>> devices = await Discover.discover(
>>>     username="user@example.com",
>>>     password="great_password",
>>> )
>>> print(len(devices))
6

You can also pass a :class:`kasa.Credentials`:

>>> creds = Credentials("user@example.com", "great_password")
>>> devices = await Discover.discover(credentials=creds)
>>> print(len(devices))
6

.. include:: ../creds_hashing.md
   :parser: myst_parser.sphinx_

Discovery can also be targeted to a specific broadcast address instead of
the default 255.255.255.255:

>>> found_devices = await Discover.discover(target="127.0.0.255", credentials=creds)
>>> print(len(found_devices))
6

Basic information is available on the device from the discovery broadcast response
but it is important to call device.update() after discovery if you want to access
all the attributes without getting errors or None.

>>> dev = found_devices["127.0.0.3"]
>>> dev.alias
None
>>> await dev.update()
>>> dev.alias
'Living Room Bulb'

It is also possible to pass a coroutine to be executed for each found device:

>>> async def print_dev_info(dev):
>>>     await dev.update()
>>>     print(f"Discovered {dev.alias} (model: {dev.model})")
>>>
>>> devices = await Discover.discover(on_discovered=print_dev_info, credentials=creds)
Discovered Bedroom Power Strip (model: KP303)
Discovered Bedroom Lamp Plug (model: HS110)
Discovered Living Room Bulb (model: L530)
Discovered Bedroom Lightstrip (model: KL430)
Discovered Living Room Dimmer Switch (model: HS220)
Discovered Tapo Hub (model: H200)

Discovering a single device returns a kasa.Device object.

>>> device = await Discover.discover_single("127.0.0.1", credentials=creds)
>>> device.model
'KP303'

"""

from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import logging
import secrets
import socket
import struct
from asyncio import timeout as asyncio_timeout
from asyncio.transports import DatagramTransport
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pprint import pformat as pf
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NamedTuple,
    TypedDict,
    cast,
)

from aiohttp import ClientSession
from mashumaro.config import BaseConfig
from mashumaro.types import Alias

from kasa import Device
from kasa.credentials import Credentials
from kasa.device_factory import (
    get_device_class_from_family,
    get_device_class_from_sys_info,
    get_protocol,
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
)
from kasa.exceptions import (
    KasaException,
    TimeoutError,
    UnsupportedDeviceError,
)
from kasa.iot.iotdevice import IotDevice, _extract_sys_info
from kasa.json import DataClassJSONMixin
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.protocols.iotprotocol import REDACTORS as IOT_REDACTORS
from kasa.protocols.protocol import mask_mac, redact_data
from kasa.transports.aestransport import AesEncyptionSession, KeyPair
from kasa.transports.xortransport import XorEncryption

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from kasa import BaseProtocol
    from kasa.transports import BaseTransport


class ConnectAttempt(NamedTuple):
    """Try to connect attempt."""

    protocol: type
    transport: type
    device: type
    https: bool


class DiscoveredMeta(TypedDict):
    """Meta info about discovery response."""

    ip: str
    port: int


class DiscoveredRaw(TypedDict):
    """Try to connect attempt."""

    meta: DiscoveredMeta
    discovery_response: dict


OnDiscoveredCallable = Callable[[Device], Coroutine]
OnDiscoveredRawCallable = Callable[[DiscoveredRaw], None]
OnUnsupportedCallable = Callable[[UnsupportedDeviceError], Coroutine]
OnConnectAttemptCallable = Callable[[ConnectAttempt, bool], None]
DeviceDict = dict[str, Device]

DECRYPTED_REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "connect_ssid": lambda x: "#MASKED_SSID#" if x else "",
    "device_id": lambda x: "REDACTED_" + x[9::],
    "owner": lambda x: "REDACTED_" + x[9::],
}

NEW_DISCOVERY_REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "device_id": lambda x: "REDACTED_" + x[9::],
    "device_name": lambda x: "#MASKED_NAME#" if x else "",
    "owner": lambda x: "REDACTED_" + x[9::],
    "mac": mask_mac,
    "master_device_id": lambda x: "REDACTED_" + x[9::],
    "group_id": lambda x: "REDACTED_" + x[9::],
    "group_name": lambda x: "I01BU0tFRF9TU0lEIw==",
    "encrypt_info": lambda x: {**x, "key": "", "data": ""},
    "ip": lambda x: x,  # don't redact but keep listed here for dump_devinfo
    "decrypted_data": lambda x: redact_data(x, DECRYPTED_REDACTORS),
}


class _AesDiscoveryQuery:
    keypair: KeyPair | None = None

    @classmethod
    def generate_query(cls) -> bytearray:
        if not cls.keypair:
            cls.keypair = KeyPair.create_key_pair(key_size=2048)
        secret = secrets.token_bytes(4)

        key_payload = {"params": {"rsa_key": cls.keypair.get_public_pem().decode()}}

        key_payload_bytes = json_dumps(key_payload).encode()
        # https://labs.withsecure.com/advisories/tp-link-ac1750-pwn2own-2019
        version = 2  # version of tdp
        msg_type = 0
        op_code = 1  # probe
        msg_size = len(key_payload_bytes)
        flags = 17
        padding_byte = 0  # blank byte
        device_serial = int.from_bytes(secret, "big")
        initial_crc = 0x5A6B7C8D

        disco_header = struct.pack(
            ">BBHHBBII",
            version,
            msg_type,
            op_code,
            msg_size,
            flags,
            padding_byte,
            device_serial,
            initial_crc,
        )

        query = bytearray(disco_header + key_payload_bytes)
        crc = binascii.crc32(query).to_bytes(length=4, byteorder="big")
        query[12:16] = crc
        return query


class _DiscoverProtocol(asyncio.DatagramProtocol):
    """Implementation of the discovery protocol handler.

    This is internal class, use :func:`Discover.discover`: instead.
    """

    DISCOVERY_START_TIMEOUT = 1

    discovered_devices: DeviceDict

    def __init__(
        self,
        *,
        on_discovered: OnDiscoveredCallable | None = None,
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        target: str = "255.255.255.255",
        discovery_packets: int = 3,
        discovery_timeout: int = 5,
        interface: str | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        port: int | None = None,
        credentials: Credentials | None = None,
        timeout: int | None = None,
    ) -> None:
        self.transport: DatagramTransport | None = None
        self.discovery_packets = discovery_packets
        self.interface = interface
        self.on_discovered = on_discovered

        self.port = port
        self.discovery_port = port or Discover.DISCOVERY_PORT
        self.target = target
        self.target_1 = (target, self.discovery_port)
        self.target_2 = (target, Discover.DISCOVERY_PORT_2)

        self.discovered_devices = {}
        self.unsupported_device_exceptions: dict = {}
        self.invalid_device_exceptions: dict = {}
        self.on_unsupported = on_unsupported
        self.on_discovered_raw = on_discovered_raw
        self.credentials = credentials
        self.timeout = timeout
        self.discovery_timeout = discovery_timeout
        self.seen_hosts: set[str] = set()
        self.discover_task: asyncio.Task | None = None
        self.callback_tasks: list[asyncio.Task] = []
        self.target_discovered: bool = False
        self._started_event = asyncio.Event()

    def _run_callback_task(self, coro: Coroutine) -> None:
        task: asyncio.Task = asyncio.create_task(coro)
        self.callback_tasks.append(task)

    async def wait_for_discovery_to_complete(self) -> None:
        """Wait for the discovery task to complete."""
        # Give some time for connection_made event to be received
        async with asyncio_timeout(self.DISCOVERY_START_TIMEOUT):
            await self._started_event.wait()
        try:
            if TYPE_CHECKING:
                assert isinstance(self.discover_task, asyncio.Task)

            await self.discover_task
        except asyncio.CancelledError:
            # if target_discovered then cancel was called internally
            if not self.target_discovered:
                raise
        # Wait for any pending callbacks to complete
        await asyncio.gather(*self.callback_tasks)

    def connection_made(self, transport: DatagramTransport) -> None:  # type: ignore[override]
        """Set socket options for broadcasting."""
        self.transport = cast(DatagramTransport, transport)

        sock = self.transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError as ex:  # WSL does not support SO_REUSEADDR, see #246
            _LOGGER.debug("Unable to set SO_REUSEADDR: %s", ex)

        # windows does not support SO_BINDTODEVICE
        if self.interface is not None and hasattr(socket, "SO_BINDTODEVICE"):
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode()
            )

        self.discover_task = asyncio.create_task(self.do_discover())
        self._started_event.set()

    async def do_discover(self) -> None:
        """Send number of discovery datagrams."""
        req = json_dumps(Discover.DISCOVERY_QUERY)
        _LOGGER.debug("[DISCOVERY] %s >> %s", self.target, Discover.DISCOVERY_QUERY)
        encrypted_req = XorEncryption.encrypt(req)
        sleep_between_packets = self.discovery_timeout / self.discovery_packets

        aes_discovery_query = _AesDiscoveryQuery.generate_query()
        for _ in range(self.discovery_packets):
            if self.target in self.seen_hosts:  # Stop sending for discover_single
                break
            self.transport.sendto(encrypted_req[4:], self.target_1)  # type: ignore
            self.transport.sendto(aes_discovery_query, self.target_2)  # type: ignore
            await asyncio.sleep(sleep_between_packets)

    def datagram_received(
        self,
        data: bytes,
        addr: tuple[str, int],
    ) -> None:
        """Handle discovery responses."""
        if TYPE_CHECKING:
            assert _AesDiscoveryQuery.keypair

        ip, port = addr
        # Prevent multiple entries due multiple broadcasts
        if ip in self.seen_hosts:
            return
        self.seen_hosts.add(ip)

        device: Device | None = None

        config = DeviceConfig(host=ip, port_override=self.port)
        if self.credentials:
            config.credentials = self.credentials
        if self.timeout:
            config.timeout = self.timeout
        try:
            if port == self.discovery_port:
                json_func = Discover._get_discovery_json_legacy
                device_func = Discover._get_device_instance_legacy
            elif port == Discover.DISCOVERY_PORT_2:
                json_func = Discover._get_discovery_json
                device_func = Discover._get_device_instance
            else:
                return
            info = json_func(data, ip)
            if self.on_discovered_raw is not None:
                self.on_discovered_raw(
                    {
                        "discovery_response": info,
                        "meta": {"ip": ip, "port": port},
                    }
                )
            device = device_func(info, config)
        except UnsupportedDeviceError as udex:
            _LOGGER.debug("Unsupported device found at %s << %s", ip, udex)
            self.unsupported_device_exceptions[ip] = udex
            if self.on_unsupported is not None:
                self._run_callback_task(self.on_unsupported(udex))
            self._handle_discovered_event()
            return
        except KasaException as ex:
            _LOGGER.debug("[DISCOVERY] Unable to find device type for %s: %s", ip, ex)
            self.invalid_device_exceptions[ip] = ex
            self._handle_discovered_event()
            return

        self.discovered_devices[ip] = device

        if self.on_discovered is not None:
            self._run_callback_task(self.on_discovered(device))

        self._handle_discovered_event()

    def _handle_discovered_event(self) -> None:
        """If target is in seen_hosts cancel discover_task."""
        if self.target in self.seen_hosts:
            self.target_discovered = True
            if self.discover_task:
                self.discover_task.cancel()

    def error_received(self, ex: Exception) -> None:
        """Handle asyncio.Protocol errors."""
        _LOGGER.error("Got error: %s", ex)

    def connection_lost(self, ex: Exception | None) -> None:  # pragma: no cover
        """Cancel the discover task if running."""
        if self.discover_task:
            self.discover_task.cancel()


class Discover:
    """Class for discovering devices."""

    DISCOVERY_PORT = 9999

    DISCOVERY_QUERY: dict[str, dict[str, dict]] = {
        "system": {"get_sysinfo": {}},
    }

    DISCOVERY_PORT_2 = 20002
    DISCOVERY_QUERY_2 = binascii.unhexlify("020000010000000000000000463cb5d3")

    _redact_data = True

    @staticmethod
    async def discover(
        *,
        target: str = "255.255.255.255",
        on_discovered: OnDiscoveredCallable | None = None,
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        discovery_timeout: int = 5,
        discovery_packets: int = 3,
        interface: str | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
        credentials: Credentials | None = None,
        username: str | None = None,
        password: str | None = None,
        port: int | None = None,
        timeout: int | None = None,
    ) -> DeviceDict:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 and
        255.255.255.255:20002 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.
        If you have multiple interfaces,
        you can use *target* parameter to specify the network for discovery.

        If given, `on_discovered` coroutine will get awaited with
        a :class:`Device`-derived object as parameter.

        The results of the discovery are returned as a dict of
        :class:`Device`-derived objects keyed with IP addresses.
        The devices are already initialized and all but emeter-related properties
        can be accessed directly.

        :param target: The target address where to send the broadcast discovery
         queries if multi-homing (e.g. 192.168.xxx.255).
        :param on_discovered: coroutine to execute on discovery
        :param on_discovered_raw: Optional callback once discovered json is loaded
            before any attempt to deserialize it and create devices
        :param discovery_timeout: Seconds to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets to broadcast
        :param interface: Bind to specific interface
        :param on_unsupported: Optional callback when unsupported devices are discovered
        :param credentials: Credentials for devices that require authentication.
            username and password are ignored if provided.
        :param username: Username for devices that require authentication
        :param password: Password for devices that require authentication
        :param port: Override the discovery port for devices listening on 9999
        :param timeout: Query timeout in seconds for devices returned by discovery
        :return: dictionary with discovered devices
        """
        if not credentials and username and password:
            credentials = Credentials(username, password)
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=target,
                on_discovered=on_discovered,
                discovery_packets=discovery_packets,
                interface=interface,
                on_unsupported=on_unsupported,
                on_discovered_raw=on_discovered_raw,
                credentials=credentials,
                timeout=timeout,
                discovery_timeout=discovery_timeout,
                port=port,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug("Waiting %s seconds for responses...", discovery_timeout)
            await protocol.wait_for_discovery_to_complete()
        except (KasaException, asyncio.CancelledError) as ex:
            for device in protocol.discovered_devices.values():
                await device.protocol.close()
            raise ex
        finally:
            transport.close()

        _LOGGER.debug("Discovered %s devices", len(protocol.discovered_devices))

        return protocol.discovered_devices

    @staticmethod
    async def discover_single(
        host: str,
        *,
        discovery_timeout: int = 5,
        port: int | None = None,
        timeout: int | None = None,
        credentials: Credentials | None = None,
        username: str | None = None,
        password: str | None = None,
        on_discovered_raw: OnDiscoveredRawCallable | None = None,
        on_unsupported: OnUnsupportedCallable | None = None,
    ) -> Device | None:
        """Discover a single device by the given IP address.

        It is generally preferred to avoid :func:`discover_single()` and
        use :meth:`Device.connect()` instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param discovery_timeout: Timeout in seconds for discovery
        :param port: Optionally set a different port for legacy devices using port 9999
        :param timeout: Timeout in seconds device for devices queries
        :param credentials: Credentials for devices that require authentication.
            username and password are ignored if provided.
        :param username: Username for devices that require authentication
        :param password: Password for devices that require authentication
        :param on_discovered_raw: Optional callback once discovered json is loaded
            before any attempt to deserialize it and create devices
        :param on_unsupported: Optional callback when unsupported devices are discovered
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        if not credentials and username and password:
            credentials = Credentials(username, password)
        loop = asyncio.get_event_loop()

        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            try:
                adrrinfo = await loop.getaddrinfo(
                    host,
                    0,
                    type=socket.SOCK_DGRAM,
                    family=socket.AF_INET,
                )
                # getaddrinfo returns a list of 5 tuples with the following structure:
                # (family, type, proto, canonname, sockaddr)
                # where sockaddr is 2 tuple (ip, port).
                # hence [0][4][0] is a stable array access because if no socket
                # address matches the host for SOCK_DGRAM AF_INET the gaierror
                # would be raised.
                # https://docs.python.org/3/library/socket.html#socket.getaddrinfo
                ip = adrrinfo[0][4][0]
            except socket.gaierror as gex:
                raise KasaException(f"Could not resolve hostname {host}") from gex

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=ip,
                port=port,
                credentials=credentials,
                timeout=timeout,
                discovery_timeout=discovery_timeout,
                on_discovered_raw=on_discovered_raw,
            ),
            local_addr=("0.0.0.0", 0),  # noqa: S104
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug(
                "Waiting a total of %s seconds for responses...", discovery_timeout
            )
            await protocol.wait_for_discovery_to_complete()
        finally:
            transport.close()

        if ip in protocol.discovered_devices:
            dev = protocol.discovered_devices[ip]
            dev.host = host
            return dev
        elif ip in protocol.unsupported_device_exceptions:
            if on_unsupported:
                await on_unsupported(protocol.unsupported_device_exceptions[ip])
                return None
            else:
                raise protocol.unsupported_device_exceptions[ip]
        elif ip in protocol.invalid_device_exceptions:
            raise protocol.invalid_device_exceptions[ip]
        else:
            raise TimeoutError(f"Timed out getting discovery response for {host}")

    @staticmethod
    async def try_connect_all(
        host: str,
        *,
        port: int | None = None,
        timeout: int | None = None,
        credentials: Credentials | None = None,
        http_client: ClientSession | None = None,
        on_attempt: OnConnectAttemptCallable | None = None,
    ) -> Device | None:
        """Try to connect directly to a device with all possible parameters.

        This method can be used when udp is not working due to network issues.
        After succesfully connecting use the device config and
        :meth:`Device.connect()` for future connections.

        :param host: Hostname of device to query
        :param port: Optionally set a different port for legacy devices using port 9999
        :param timeout: Timeout in seconds device for devices queries
        :param credentials: Credentials for devices that require authentication.
        :param http_client: Optional client session for devices that use http.
            username and password are ignored if provided.
        """
        from .device_factory import _connect

        main_device_families = {
            Device.Family.SmartTapoPlug,
            Device.Family.IotSmartPlugSwitch,
            Device.Family.SmartIpCamera,
            Device.Family.SmartTapoRobovac,
            Device.Family.IotIpCamera,
        }
        candidates: dict[
            tuple[type[BaseProtocol], type[BaseTransport], type[Device], bool],
            tuple[BaseProtocol, DeviceConfig],
        ] = {
            (type(protocol), type(protocol._transport), device_class, https): (
                protocol,
                config,
            )
            for encrypt in Device.EncryptionType
            for device_family in main_device_families
            for https in (True, False)
            for login_version in (None, 2)
            if (
                conn_params := DeviceConnectionParameters(
                    device_family=device_family,
                    encryption_type=encrypt,
                    login_version=login_version,
                    https=https,
                )
            )
            and (
                config := DeviceConfig(
                    host=host,
                    connection_type=conn_params,
                    timeout=timeout,
                    port_override=port,
                    credentials=credentials,
                    http_client=http_client,
                )
            )
            and (protocol := get_protocol(config, strict=True))
            and (
                device_class := get_device_class_from_family(
                    device_family.value, https=https, require_exact=True
                )
            )
        }
        for key, val in candidates.items():
            try:
                prot, config = val
                _LOGGER.debug("Trying to connect with %s", prot.__class__.__name__)
                dev = await _connect(config, prot)
            except Exception as ex:
                _LOGGER.debug(
                    "Unable to connect with %s: %s",
                    prot.__class__.__name__,
                    ex,
                )
                if on_attempt:
                    ca = tuple.__new__(ConnectAttempt, key)
                    on_attempt(ca, False)
            else:
                if on_attempt:
                    ca = tuple.__new__(ConnectAttempt, key)
                    on_attempt(ca, True)
                _LOGGER.debug("Found working protocol %s", prot.__class__.__name__)
                return dev
            finally:
                await prot.close()
        return None

    @staticmethod
    def _get_device_class(info: dict) -> type[Device]:
        """Find SmartDevice subclass for device described by passed data."""
        if "result" in info:
            discovery_result = DiscoveryResult.from_dict(info["result"])
            https = (
                discovery_result.mgt_encrypt_schm.is_support_https
                if discovery_result.mgt_encrypt_schm
                else False
            )
            dev_class = get_device_class_from_family(
                discovery_result.device_type, https=https
            )
            if not dev_class:
                raise UnsupportedDeviceError(
                    f"Unknown device type: {discovery_result.device_type}",
                    discovery_result=info,
                )
            return dev_class
        else:
            return get_device_class_from_sys_info(info)

    @staticmethod
    def _get_discovery_json_legacy(data: bytes, ip: str) -> dict:
        """Get discovery json from legacy 9999 response."""
        try:
            info = json_loads(XorEncryption.decrypt(data))
        except Exception as ex:
            raise KasaException(
                f"Unable to read response from device: {ip}: {ex}"
            ) from ex
        return info

    @staticmethod
    def _get_device_instance_legacy(info: dict, config: DeviceConfig) -> Device:
        """Get IotDevice from legacy 9999 response."""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            data = redact_data(info, IOT_REDACTORS) if Discover._redact_data else info
            _LOGGER.debug("[DISCOVERY] %s << %s", config.host, pf(data))

        device_class = cast(type[IotDevice], Discover._get_device_class(info))
        device = device_class(config.host, config=config)
        sys_info = _extract_sys_info(info)
        device_type = sys_info.get("mic_type", sys_info.get("type"))
        login_version = (
            sys_info.get("stream_version") if device_type == "IOT.IPCAMERA" else None
        )
        config.connection_type = DeviceConnectionParameters.from_values(
            device_family=device_type,
            encryption_type=DeviceEncryptionType.Xor.value,
            https=device_type == "IOT.IPCAMERA",
            login_version=login_version,
        )
        device.protocol = get_protocol(config)  # type: ignore[assignment]
        device.update_from_discover_info(info)
        return device

    @staticmethod
    def _decrypt_discovery_data(discovery_result: DiscoveryResult) -> None:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        if TYPE_CHECKING:
            assert discovery_result.encrypt_info
            assert _AesDiscoveryQuery.keypair
        encryped_key = discovery_result.encrypt_info.key
        encrypted_data = discovery_result.encrypt_info.data

        key_and_iv = _AesDiscoveryQuery.keypair.decrypt_discovery_key(
            base64.b64decode(encryped_key.encode())
        )

        key, iv = key_and_iv[:16], key_and_iv[16:]

        session = AesEncyptionSession(key, iv)
        decrypted_data = session.decrypt(encrypted_data)

        result = json_loads(decrypted_data)
        if debug_enabled:
            data = (
                redact_data(result, DECRYPTED_REDACTORS)
                if Discover._redact_data
                else result
            )
            _LOGGER.debug(
                "Decrypted encrypt_info for %s: %s",
                discovery_result.ip,
                pf(data),
            )
        discovery_result.decrypted_data = result

    @staticmethod
    def _get_discovery_json(data: bytes, ip: str) -> dict:
        """Get discovery json from the new 20002 response."""
        try:
            info = json_loads(data[16:])
        except Exception as ex:
            _LOGGER.debug("Got invalid response from device %s: %s", ip, data)
            raise KasaException(
                f"Unable to read response from device: {ip}: {ex}"
            ) from ex
        return info

    @staticmethod
    def _get_connection_parameters(
        discovery_result: DiscoveryResult,
    ) -> DeviceConnectionParameters:
        """Get connection parameters from the discovery result."""
        type_ = discovery_result.device_type
        if (encrypt_schm := discovery_result.mgt_encrypt_schm) is None:
            raise UnsupportedDeviceError(
                f"Unsupported device {discovery_result.ip} of type {type_} "
                "with no mgt_encrypt_schm",
                discovery_result=discovery_result.to_dict(),
                host=discovery_result.ip,
            )

        if not (encrypt_type := encrypt_schm.encrypt_type) and (
            encrypt_info := discovery_result.encrypt_info
        ):
            encrypt_type = encrypt_info.sym_schm

        if not (login_version := encrypt_schm.lv) and (
            et := discovery_result.encrypt_type
        ):
            # Known encrypt types are ["1","2"] and ["3"]
            # Reuse the login_version attribute to pass the max to transport
            login_version = max([int(i) for i in et])

        if not encrypt_type:
            raise UnsupportedDeviceError(
                f"Unsupported device {discovery_result.ip} of type {type_} "
                + "with no encryption type",
                discovery_result=discovery_result.to_dict(),
                host=discovery_result.ip,
            )
        return DeviceConnectionParameters.from_values(
            type_,
            encrypt_type,
            login_version=login_version,
            https=encrypt_schm.is_support_https,
            http_port=encrypt_schm.http_port,
        )

    @staticmethod
    def _get_device_instance(
        info: dict,
        config: DeviceConfig,
    ) -> Device:
        """Get SmartDevice from the new 20002 response."""
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        try:
            discovery_result = DiscoveryResult.from_dict(info["result"])
        except Exception as ex:
            if debug_enabled:
                data = (
                    redact_data(info, NEW_DISCOVERY_REDACTORS)
                    if Discover._redact_data
                    else info
                )
                _LOGGER.debug(
                    "Unable to parse discovery from device %s: %s",
                    config.host,
                    pf(data),
                )
            raise UnsupportedDeviceError(
                f"Unable to parse discovery from device: {config.host}: {ex}",
                host=config.host,
            ) from ex

        # Decrypt the data
        if (
            encrypt_info := discovery_result.encrypt_info
        ) and encrypt_info.sym_schm == "AES":
            try:
                Discover._decrypt_discovery_data(discovery_result)
            except Exception:
                _LOGGER.exception(
                    "Unable to decrypt discovery data %s: %s",
                    config.host,
                    redact_data(info, NEW_DISCOVERY_REDACTORS),
                )
        type_ = discovery_result.device_type
        try:
            conn_params = Discover._get_connection_parameters(discovery_result)
            config.connection_type = conn_params
        except KasaException as ex:
            if isinstance(ex, UnsupportedDeviceError):
                raise
            raise UnsupportedDeviceError(
                f"Unsupported device {config.host} of type {type_} "
                + f"with encrypt_scheme {discovery_result.mgt_encrypt_schm}",
                discovery_result=discovery_result.to_dict(),
                host=config.host,
            ) from ex

        if (
            device_class := get_device_class_from_family(type_, https=conn_params.https)
        ) is None:
            _LOGGER.debug("Got unsupported device type: %s", type_)
            raise UnsupportedDeviceError(
                f"Unsupported device {config.host} of type {type_}: {info}",
                discovery_result=discovery_result.to_dict(),
                host=config.host,
            )

        if (protocol := get_protocol(config)) is None:
            _LOGGER.debug(
                "Got unsupported connection type: %s", config.connection_type.to_dict()
            )
            raise UnsupportedDeviceError(
                f"Unsupported encryption scheme {config.host} of "
                + f"type {config.connection_type.to_dict()}: {info}",
                discovery_result=discovery_result.to_dict(),
                host=config.host,
            )

        if debug_enabled:
            data = (
                redact_data(info, NEW_DISCOVERY_REDACTORS)
                if Discover._redact_data
                else info
            )
            _LOGGER.debug("[DISCOVERY] %s << %s", config.host, pf(data))

        device = device_class(config.host, protocol=protocol)

        di = discovery_result.to_dict()
        di["model"], _, _ = discovery_result.device_model.partition("(")
        device.update_from_discover_info(di)
        return device


class _DiscoveryBaseMixin(DataClassJSONMixin):
    """Base class for serialization mixin."""

    class Config(BaseConfig):
        """Serialization config."""

        omit_none = True
        omit_default = True
        serialize_by_alias = True


@dataclass
class EncryptionScheme(_DiscoveryBaseMixin):
    """Base model for encryption scheme of discovery result."""

    is_support_https: bool
    encrypt_type: str | None = None
    http_port: int | None = None
    lv: int | None = None


@dataclass
class EncryptionInfo(_DiscoveryBaseMixin):
    """Base model for encryption info of discovery result."""

    sym_schm: str
    key: str
    data: str


@dataclass
class DiscoveryResult(_DiscoveryBaseMixin):
    """Base model for discovery result."""

    device_type: str
    device_model: str
    device_id: str
    ip: str
    mac: str
    mgt_encrypt_schm: EncryptionScheme | None = None
    device_name: str | None = None
    encrypt_info: EncryptionInfo | None = None
    encrypt_type: list[str] | None = None
    decrypted_data: dict | None = None
    is_reset_wifi: Annotated[bool | None, Alias("isResetWiFi")] = None

    firmware_version: str | None = None
    hardware_version: str | None = None
    hw_ver: str | None = None
    owner: str | None = None
    is_support_iot_cloud: bool | None = None
    obd_src: str | None = None
    factory_default: bool | None = None
