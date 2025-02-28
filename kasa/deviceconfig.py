"""Configuration for connecting directly to a device without discovery.

If you are connecting to a newer KASA or TAPO device you can get the device
via discovery or connect directly with :class:`DeviceConfig`.

Discovery returns a list of discovered devices:

>>> from kasa import Discover, Device
>>> device = await Discover.discover_single(
>>>     "127.0.0.3",
>>>     username="user@example.com",
>>>     password="great_password",
>>> )
>>> print(device.alias)  # Alias is None because update() has not been called
None

.. include:: ../creds_hashing.md
   :parser: myst_parser.sphinx_

>>> config_dict = device.config.to_dict()
>>> # DeviceConfig.to_dict() can be used to store for later
>>> print(config_dict)
{'host': '127.0.0.3', 'timeout': 5, 'credentials': {'username': 'user@example.com', \
'password': 'great_password'}, 'connection_type'\
: {'device_family': 'SMART.TAPOBULB', 'encryption_type': 'KLAP', 'login_version': 2, \
'https': False, 'http_port': 80}}

>>> later_device = await Device.connect(config=Device.Config.from_dict(config_dict))
>>> print(later_device.alias)  # Alias is available as connect() calls update()
Living Room Bulb

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, TypedDict

from aiohttp import ClientSession
from mashumaro import field_options, pass_through
from mashumaro.config import BaseConfig

from .credentials import Credentials
from .exceptions import KasaException
from .json import DataClassJSONMixin

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


class KeyPairDict(TypedDict):
    """Class to represent a public/private key pair."""

    private: str
    public: str


class DeviceEncryptionType(Enum):
    """Encrypt type enum."""

    Klap = "KLAP"
    Aes = "AES"
    Xor = "XOR"


class DeviceFamily(Enum):
    """Encrypt type enum."""

    IotSmartPlugSwitch = "IOT.SMARTPLUGSWITCH"
    IotSmartBulb = "IOT.SMARTBULB"
    IotIpCamera = "IOT.IPCAMERA"
    SmartKasaPlug = "SMART.KASAPLUG"
    SmartKasaSwitch = "SMART.KASASWITCH"
    SmartTapoPlug = "SMART.TAPOPLUG"
    SmartTapoBulb = "SMART.TAPOBULB"
    SmartTapoSwitch = "SMART.TAPOSWITCH"
    SmartTapoHub = "SMART.TAPOHUB"
    SmartKasaHub = "SMART.KASAHUB"
    SmartIpCamera = "SMART.IPCAMERA"
    SmartTapoRobovac = "SMART.TAPOROBOVAC"
    SmartTapoChime = "SMART.TAPOCHIME"
    SmartTapoDoorbell = "SMART.TAPODOORBELL"


class _DeviceConfigBaseMixin(DataClassJSONMixin):
    """Base class for serialization mixin."""

    class Config(BaseConfig):
        """Serialization config."""

        omit_none = True


@dataclass
class DeviceConnectionParameters(_DeviceConfigBaseMixin):
    """Class to hold the the parameters determining connection type."""

    device_family: DeviceFamily
    encryption_type: DeviceEncryptionType
    login_version: int | None = None
    https: bool = False
    http_port: int | None = None

    @staticmethod
    def from_values(
        device_family: str,
        encryption_type: str,
        *,
        login_version: int | None = None,
        https: bool | None = None,
        http_port: int | None = None,
    ) -> DeviceConnectionParameters:
        """Return connection parameters from string values."""
        try:
            if https is None:
                https = False
            return DeviceConnectionParameters(
                DeviceFamily(device_family),
                DeviceEncryptionType(encryption_type),
                login_version,
                https,
                http_port=http_port,
            )
        except (ValueError, TypeError) as ex:
            raise KasaException(
                f"Invalid connection parameters for {device_family}."
                + f"{encryption_type}.{login_version}"
            ) from ex


@dataclass
class DeviceConfig(_DeviceConfigBaseMixin):
    """Class to represent paramaters that determine how to connect to devices."""

    DEFAULT_TIMEOUT = 5
    #: IP address or hostname
    host: str
    #: Timeout for querying the device
    timeout: int | None = DEFAULT_TIMEOUT
    #: Override the default 9999 port to support port forwarding
    port_override: int | None = None
    #: Credentials for devices requiring authentication
    credentials: Credentials | None = None
    #: Credentials hash for devices requiring authentication.
    #: If credentials are also supplied they take precendence over credentials_hash.
    #: Credentials hash can be retrieved from :attr:`Device.credentials_hash`
    credentials_hash: str | None = None
    #: The protocol specific type of connection.  Defaults to the legacy type.
    batch_size: int | None = None
    #: The batch size for protoools supporting multiple request batches.
    connection_type: DeviceConnectionParameters = field(
        default_factory=lambda: DeviceConnectionParameters(
            DeviceFamily.IotSmartPlugSwitch, DeviceEncryptionType.Xor
        )
    )

    @property
    def uses_http(self) -> bool:
        """True if the device uses http."""
        ctype = self.connection_type
        return ctype.encryption_type is not DeviceEncryptionType.Xor or ctype.https

    #: Set a custom http_client for the device to use.
    http_client: ClientSession | None = field(
        default=None,
        compare=False,
        metadata=field_options(serialize="omit", deserialize=pass_through),
    )

    aes_keys: KeyPairDict | None = None

    def __post_init__(self) -> None:
        if self.connection_type is None:
            self.connection_type = DeviceConnectionParameters(
                DeviceFamily.IotSmartPlugSwitch, DeviceEncryptionType.Xor
            )

    def to_dict_control_credentials(
        self,
        *,
        credentials_hash: str | None = None,
        exclude_credentials: bool = False,
    ) -> dict[str, dict[str, str]]:
        """Convert deviceconfig to dict controlling how to serialize credentials.

        If credentials_hash is provided credentials will be None.
        If credentials_hash is '' credentials_hash and credentials will be None.
        exclude credentials controls whether to include credentials.
        The defaults are the same as calling to_dict().
        """
        if credentials_hash is None:
            if not exclude_credentials:
                return self.to_dict()
            else:
                return replace(self, credentials=None).to_dict()

        return replace(
            self,
            credentials_hash=credentials_hash if credentials_hash else None,
            credentials=None,
        ).to_dict()
