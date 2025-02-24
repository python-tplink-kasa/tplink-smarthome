"""Implementation of the TP-Link SSL AES transport."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import socket
import ssl
from contextlib import suppress
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

from yarl import URL

from ..credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from ..httpclient import HttpClient
from ..json import dumps as json_dumps
from ..json import loads as json_loads
from . import AesEncyptionSession, BaseTransport

_LOGGER = logging.getLogger(__name__)


ONE_DAY_SECONDS = 86400
SESSION_EXPIRE_BUFFER_SECONDS = 60 * 20


def _sha256(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()  # noqa: S324


def _md5_hash(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest().upper()  # noqa: S324


def _sha256_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()  # noqa: S324


class TransportState(Enum):
    """Enum for AES state."""

    HANDSHAKE_REQUIRED = auto()  # Handshake needed
    ESTABLISHED = auto()  # Ready to send requests


class SslAesTransport(BaseTransport):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT: int = 443
    COMMON_HEADERS = {
        "Content-Type": "application/json; charset=UTF-8",
        "requestByApp": "true",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "Tapo CameraClient Android",
    }
    CIPHERS = ":".join(
        [
            "AES256-GCM-SHA384",
            "AES256-SHA256",
            "AES128-GCM-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
        ]
    )
    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        super().__init__(config=config)

        self._login_version = config.connection_type.login_version
        if (
            not self._credentials or self._credentials.username is None
        ) and not self._credentials_hash:
            self._credentials = Credentials()
        self._default_credentials: Credentials = get_default_credentials(
            DEFAULT_CREDENTIALS["TAPOCAMERA"]
        )
        self._http_client: HttpClient = HttpClient(config)

        self._state = TransportState.HANDSHAKE_REQUIRED

        self._encryption_session: AesEncyptionSession | None = None
        self._session_expire_at: float | None = None

        self._host_port = f"{self._host}:{self._port}"
        self._app_url = URL(f"https://{self._host_port}")
        self._token_url: URL | None = None
        self._ssl_context: ssl.SSLContext | None = None
        self._headers: dict | None = None
        self._seq: int | None = None
        self._pwd_hash: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        if self._credentials != Credentials() and self._credentials:
            self._username = self._credentials.username
            self._password = self._credentials.password
        elif self._credentials_hash:
            ch = json_loads(base64.b64decode(self._credentials_hash.encode()))
            self._password = ch["pwd"]
            self._username = ch["un"]
        self._local_nonce: str | None = None
        self._send_secure = True

        _LOGGER.debug("Created AES transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @staticmethod
    def _create_b64_credentials(credentials: Credentials) -> str:
        ch = {"un": credentials.username, "pwd": credentials.password}
        return base64.b64encode(json_dumps(ch).encode()).decode()

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""
        if self._credentials == Credentials():
            return None
        if not self._credentials and self._credentials_hash:
            return self._credentials_hash
        if (cred := self._credentials) and cred.password and cred.username:
            return self._create_b64_credentials(cred)
        return None

    def _get_response_error(self, resp_dict: Any) -> SmartErrorCode:
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR
        return error_code

    def _get_response_inner_error(self, resp_dict: Any) -> SmartErrorCode | None:
        # Device blocked errors have 'data' element at the root level, other inner
        # errors are inside 'result'
        error_code_raw = resp_dict.get("data", {}).get("code")

        if error_code_raw is None:
            error_code_raw = resp_dict.get("result", {}).get("data", {}).get("code")

        if error_code_raw is None:
            return None
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR
        return error_code

    def _handle_response_error_code(self, resp_dict: Any, msg: str) -> None:
        error_code = self._get_response_error(resp_dict)
        if error_code is SmartErrorCode.SUCCESS:
            return
        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.HANDSHAKE_REQUIRED
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def _get_ssl_context(self) -> ssl.SSLContext:
        if not self._ssl_context:
            loop = asyncio.get_running_loop()
            self._ssl_context = await loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    async def _get_host_ip(self) -> str:
        def get_ip() -> str:
            #  From https://stackoverflow.com/a/28950776
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            try:
                # doesn't even have to be reachable
                s.connect(("10.254.254.254", 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, get_ip)

    async def _get_headers(self) -> dict:
        if not self._headers:
            this_ip = await self._get_host_ip()
            self._headers = {
                **self.COMMON_HEADERS,
                "Referer": f"https://{this_ip}/",
                "Host": self._host_port,
            }
        return self._headers

    async def send_secure_passthrough(self, request: str) -> dict[str, Any]:
        """Send encrypted message as passthrough."""
        if self._state is TransportState.ESTABLISHED and self._token_url:
            url = self._token_url
        else:
            url = self._app_url

        _LOGGER.debug(
            "Sending secure passthrough from %s",
            self._host,
        )
        encrypted_payload = self._encryption_session.encrypt(request.encode())  # type: ignore
        passthrough_request = {
            "method": "securePassthrough",
            "params": {"request": encrypted_payload.decode()},
        }
        passthrough_request_str = json_dumps(passthrough_request)
        if TYPE_CHECKING:
            assert self._pwd_hash
            assert self._local_nonce
            assert self._seq
        tag = self.generate_tag(
            passthrough_request_str, self._local_nonce, self._pwd_hash, self._seq
        )
        headers = {**await self._get_headers(), "Seq": str(self._seq), "Tapo_tag": tag}
        self._seq += 1
        status_code, resp_dict = await self._http_client.post(
            url,
            json=passthrough_request_str,
            headers=headers,
            ssl=await self._get_ssl_context(),
        )

        if TYPE_CHECKING:
            assert self._encryption_session is not None

        # Devices can respond with 500 if another session is created from
        # the same host. Decryption may not succeed after that
        if status_code == 500:
            msg = (
                f"Device {self._host} replied with status 500 after handshake, "
                f"response: "
            )
            decrypted = None
            if isinstance(resp_dict, dict) and (
                response := resp_dict.get("result", {}).get("response")
            ):
                with suppress(Exception):
                    decrypted = self._encryption_session.decrypt(response.encode())

            if decrypted:
                msg += decrypted
            else:
                msg += str(resp_dict)

            _LOGGER.debug(msg)
            raise _RetryableError(msg)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        if TYPE_CHECKING:
            resp_dict = cast(dict[str, Any], resp_dict)

        if "result" in resp_dict and "response" in resp_dict["result"]:
            raw_response: str = resp_dict["result"]["response"]
        else:
            # Tapo Cameras respond unencrypted to single requests.
            return resp_dict

        try:
            response = self._encryption_session.decrypt(raw_response.encode())
            ret_val = json_loads(response)
        except Exception as ex:
            try:
                ret_val = json_loads(raw_response)
                _LOGGER.debug(
                    "Received unencrypted response over secure passthrough from %s",
                    self._host,
                )
            except Exception:
                raise KasaException(
                    f"Unable to decrypt response from {self._host}, "
                    + f"error: {ex}, response: {raw_response}",
                    ex,
                ) from ex
        return ret_val  # type: ignore[return-value]

    async def send_unencrypted(self, request: str) -> dict[str, Any]:
        """Send encrypted message as passthrough."""
        url = cast(URL, self._token_url)

        _LOGGER.debug(
            "Sending unencrypted to %s",
            self._host,
        )

        status_code, resp_dict = await self._http_client.post(
            url,
            json=request,
            headers=self._headers,
            ssl=await self._get_ssl_context(),
        )

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to unencrypted send"
            )

        self._handle_response_error_code(resp_dict, "Error sending message")

        if TYPE_CHECKING:
            resp_dict = cast(dict[str, Any], resp_dict)
        return resp_dict

    @staticmethod
    def generate_confirm_hash(
        local_nonce: str, server_nonce: str, pwd_hash: str
    ) -> str:
        """Generate an auth hash for the protocol on the supplied credentials."""
        expected_confirm_bytes = _sha256_hash(
            local_nonce.encode() + pwd_hash.encode() + server_nonce.encode()
        )
        return expected_confirm_bytes + server_nonce + local_nonce

    @staticmethod
    def generate_digest_password(
        local_nonce: str, server_nonce: str, pwd_hash: str
    ) -> str:
        """Generate an auth hash for the protocol on the supplied credentials."""
        digest_password_hash = _sha256_hash(
            pwd_hash.encode() + local_nonce.encode() + server_nonce.encode()
        )
        return (
            digest_password_hash.encode() + local_nonce.encode() + server_nonce.encode()
        ).decode()

    @staticmethod
    def generate_encryption_token(
        token_type: str, local_nonce: str, server_nonce: str, pwd_hash: str
    ) -> bytes:
        """Generate encryption token."""
        hashedKey = _sha256_hash(
            local_nonce.encode() + pwd_hash.encode() + server_nonce.encode()
        )
        return _sha256(
            token_type.encode()
            + local_nonce.encode()
            + server_nonce.encode()
            + hashedKey.encode()
        )[:16]

    @staticmethod
    def generate_tag(request: str, local_nonce: str, pwd_hash: str, seq: int) -> str:
        """Generate the tag header from the request for the header."""
        pwd_nonce_hash = _sha256_hash(pwd_hash.encode() + local_nonce.encode())
        tag = _sha256_hash(
            pwd_nonce_hash.encode() + request.encode() + str(seq).encode()
        )
        return tag

    async def perform_handshake(self) -> None:
        """Perform the handshake."""
        result = await self.perform_handshake1()
        if result:
            local_nonce, server_nonce, pwd_hash = result
            await self.perform_handshake2(local_nonce, server_nonce, pwd_hash)

    async def try_perform_less_secure_login(self, username: str, password: str) -> bool:
        """Perform the md5 login."""
        _LOGGER.debug("Performing less secure login...")

        pwd_hash = _md5_hash(password.encode())
        body = {
            "method": "login",
            "params": {
                "hashed": True,
                "password": pwd_hash,
                "username": username,
            },
        }

        status_code, resp_dict = await self._http_client.post(
            self._app_url,
            json=body,
            headers=self._headers,
            ssl=await self._get_ssl_context(),
        )
        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to login"
            )
        resp_dict = cast(dict, resp_dict)
        if resp_dict.get("error_code") == 0 and (
            stok := resp_dict.get("result", {}).get("stok")
        ):
            _LOGGER.debug(
                "Succesfully logged in to %s with less secure passthrough", self._host
            )
            self._send_secure = False
            self._token_url = URL(f"{str(self._app_url)}/stok={stok}/ds")
            self._pwd_hash = pwd_hash
            return True

        _LOGGER.debug("Unable to log in to %s with less secure login", self._host)
        return False

    async def perform_handshake2(
        self, local_nonce: str, server_nonce: str, pwd_hash: str
    ) -> None:
        """Perform the handshake."""
        _LOGGER.debug("Performing handshake2 ...")
        digest_password = self.generate_digest_password(
            local_nonce, server_nonce, pwd_hash
        )
        body = {
            "method": "login",
            "params": {
                "cnonce": local_nonce,
                "encrypt_type": "3",
                "digest_passwd": digest_password,
                "username": self._username,
            },
        }
        http_client = self._http_client
        status_code, resp_dict = await http_client.post(
            self._app_url,
            json=body,
            headers=await self._get_headers(),
            ssl=await self._get_ssl_context(),
        )
        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake2"
            )
        resp_dict = cast(dict, resp_dict)
        if (
            error_code := self._get_response_error(resp_dict)
        ) and error_code is SmartErrorCode.INVALID_NONCE:
            raise AuthenticationError(
                f"Invalid password hash in handshake2 for {self._host}"
            )

        self._handle_response_error_code(resp_dict, "Error in handshake2")

        self._seq = resp_dict["result"]["start_seq"]
        stok = resp_dict["result"]["stok"]
        self._token_url = URL(f"{str(self._app_url)}/stok={stok}/ds")
        self._pwd_hash = pwd_hash
        self._local_nonce = local_nonce
        lsk = self.generate_encryption_token("lsk", local_nonce, server_nonce, pwd_hash)
        ivb = self.generate_encryption_token("ivb", local_nonce, server_nonce, pwd_hash)
        self._encryption_session = AesEncyptionSession(lsk, ivb)
        self._state = TransportState.ESTABLISHED
        _LOGGER.debug("Handshake2 complete ...")

    def _pwd_to_hash(self) -> str:
        """Return the password to hash."""
        if self._credentials and self._credentials != Credentials():
            return self._credentials.password

        if self._username and self._password:
            return self._password

        return self._default_credentials.password

    def _is_less_secure_login(self, resp_dict: dict[str, Any]) -> bool:
        result = (
            self._get_response_error(resp_dict) is SmartErrorCode.SESSION_EXPIRED
            and (data := resp_dict.get("result", {}).get("data", {}))
            and (encrypt_type := data.get("encrypt_type"))
            and (encrypt_type != ["3"])
        )
        if result:
            _LOGGER.debug(
                "Received encrypt_type %s for %s, trying less secure login",
                encrypt_type,
                self._host,
            )
        return result

    async def perform_handshake1(self) -> tuple[str, str, str] | None:
        """Perform the handshake1."""
        resp_dict = None
        if self._username:
            local_nonce = secrets.token_bytes(8).hex().upper()
            resp_dict = await self.try_send_handshake1(self._username, local_nonce)

        if (
            resp_dict
            and self._is_less_secure_login(resp_dict)
            and self._get_response_inner_error(resp_dict)
            is not SmartErrorCode.BAD_USERNAME
            and await self.try_perform_less_secure_login(
                cast(str, self._username), self._pwd_to_hash()
            )
        ):
            self._state = TransportState.ESTABLISHED
            return None

        # Try the default username. If it fails raise the original error_code
        if (
            not resp_dict
            or (error_code := self._get_response_error(resp_dict))
            is not SmartErrorCode.INVALID_NONCE
            or "nonce" not in resp_dict["result"].get("data", {})
        ):
            _LOGGER.debug("Trying default credentials to %s", self._host)
            local_nonce = secrets.token_bytes(8).hex().upper()
            default_resp_dict = await self.try_send_handshake1(
                self._default_credentials.username, local_nonce
            )
            # INVALID_NONCE means device should perform secure login
            if (
                default_error_code := self._get_response_error(default_resp_dict)
            ) is SmartErrorCode.INVALID_NONCE and "nonce" in default_resp_dict[
                "result"
            ].get("data", {}):
                _LOGGER.debug("Connected to %s with default username", self._host)
                self._username = self._default_credentials.username
                error_code = default_error_code
                resp_dict = default_resp_dict
            # Otherwise could be less secure login
            elif self._is_less_secure_login(
                default_resp_dict
            ) and await self.try_perform_less_secure_login(
                self._default_credentials.username, self._pwd_to_hash()
            ):
                self._username = self._default_credentials.username
                self._state = TransportState.ESTABLISHED
                return None

        # If the default login worked it's ok not to provide credentials but if
        # it didn't raise auth error here.
        if not self._username:
            raise AuthenticationError(
                f"Credentials must be supplied to connect to {self._host}"
            )

        # Device responds with INVALID_NONCE and a "nonce" to indicate ready
        # for secure login. Otherwise error.
        if error_code is not SmartErrorCode.INVALID_NONCE or (
            resp_dict and "nonce" not in resp_dict.get("result", {}).get("data", {})
        ):
            if (
                resp_dict
                and self._get_response_inner_error(resp_dict)
                is SmartErrorCode.DEVICE_BLOCKED
            ):
                sec_left = resp_dict.get("data", {}).get("sec_left")
                msg = "Device blocked" + (
                    f" for {sec_left} seconds" if sec_left else ""
                )
                raise DeviceError(msg, error_code=SmartErrorCode.DEVICE_BLOCKED)

            raise AuthenticationError(f"Error trying handshake1: {resp_dict}")

        if TYPE_CHECKING:
            resp_dict = cast(dict[str, Any], resp_dict)

        server_nonce = resp_dict["result"]["data"]["nonce"]
        device_confirm = resp_dict["result"]["data"]["device_confirm"]

        pwd_hash = _sha256_hash(self._pwd_to_hash().encode())

        expected_confirm_sha256 = self.generate_confirm_hash(
            local_nonce, server_nonce, pwd_hash
        )
        if device_confirm == expected_confirm_sha256:
            _LOGGER.debug("Credentials match")
            return local_nonce, server_nonce, pwd_hash

        if TYPE_CHECKING:
            assert self._credentials
            assert self._credentials.password

        pwd_hash = _md5_hash(self._pwd_to_hash().encode())

        expected_confirm_md5 = self.generate_confirm_hash(
            local_nonce, server_nonce, pwd_hash
        )
        if device_confirm == expected_confirm_md5:
            _LOGGER.debug("Credentials match")
            return local_nonce, server_nonce, pwd_hash

        msg = (
            f"Device response did not match our challenge on ip {self._host}, "
            f"check that your e-mail and password (both case-sensitive) are correct. "
        )
        _LOGGER.debug(msg)

        raise AuthenticationError(msg)

    async def try_send_handshake1(self, username: str, local_nonce: str) -> dict:
        """Perform the handshake."""
        _LOGGER.debug("Sending handshake1...")

        body = {
            "method": "login",
            "params": {
                "cnonce": local_nonce,
                "encrypt_type": "3",
                "username": username,
            },
        }
        http_client = self._http_client

        status_code, resp_dict = await http_client.post(
            self._app_url,
            json=body,
            headers=await self._get_headers(),
            ssl=await self._get_ssl_context(),
        )

        _LOGGER.debug("Device responded with status %s: %s", status_code, resp_dict)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake1"
            )

        return cast(dict, resp_dict)

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        if self._state is TransportState.HANDSHAKE_REQUIRED:
            await self.perform_handshake()

        if self._send_secure:
            return await self.send_secure_passthrough(request)

        return await self.send_unencrypted(request)

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal handshake state."""
        self._state = TransportState.HANDSHAKE_REQUIRED
        self._encryption_session = None
        self._seq = 0
        self._pwd_hash = None
        self._local_nonce = None
