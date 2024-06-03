"""Implementation of the TP-Link cleartext transport.

This transport does not encrypt the payloads at all, but requires login to function.
This has been seen on some devices (like robovacs) with self-signed HTTPS certificates.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, cast

from yarl import URL

from .credentials import Credentials
from .deviceconfig import DeviceConfig
from .exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from .httpclient import HttpClient
from .json import dumps as json_dumps
from .json import loads as json_loads
from .protocol import DEFAULT_CREDENTIALS, BaseTransport, get_default_credentials

_LOGGER = logging.getLogger(__name__)


ONE_DAY_SECONDS = 86400
SESSION_EXPIRE_BUFFER_SECONDS = 60 * 20


def _md5(payload: bytes) -> str:
    algo = hashlib.md5()  # noqa: S324
    algo.update(payload)
    return algo.hexdigest()


class TransportState(Enum):
    """Enum for transport state."""

    LOGIN_REQUIRED = auto()  # Login needed
    ESTABLISHED = auto()  # Ready to send requests


class CleartextTransport(BaseTransport):
    """Implementation of the cleartext transport protocol.

    This transport uses HTTPS without any further payload encryption.
    """

    DEFAULT_PORT: int = 4433
    COMMON_HEADERS = {
        "Content-Type": "application/json",
    }
    BACKOFF_SECONDS_AFTER_LOGIN_ERROR = 1

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        super().__init__(config=config)

        if (
            not self._credentials or self._credentials.username is None
        ) and not self._credentials_hash:
            self._credentials = Credentials()
        if self._credentials:
            self._login_params = self._get_login_params(self._credentials)
        else:
            # TODO: Figure out how to handle credential hash
            self._login_params = json_loads(
                base64.b64decode(self._credentials_hash.encode()).decode()  # type: ignore[union-attr]
            )
        self._default_credentials: Credentials | None = None
        self._http_client: HttpClient = HttpClient(config)

        self._state = TransportState.LOGIN_REQUIRED
        self._session_expire_at: float | None = None

        self._app_url = URL(f"https://{self._host}:{self._port}/app")
        self._token_url: URL | None = None

        _LOGGER.debug("Created cleartext transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""
        return base64.b64encode(json_dumps(self._login_params).encode()).decode()

    def _get_login_params(self, credentials: Credentials) -> dict[str, str]:
        """Get the login parameters based on the login_version."""
        un, pw = self.hash_credentials(credentials)
        # The password hash needs to be upper-case
        return {"password": pw.upper(), "username": un}

    @staticmethod
    def hash_credentials(credentials: Credentials) -> tuple[str, str]:
        """Hash the credentials."""
        un = credentials.username
        pw = _md5(credentials.password.encode())
        return un, pw

    def _handle_response_error_code(self, resp_dict: Any, msg: str) -> None:
        """Handle response errors to request reauth etc.

        TODO: This should probably be moved to the base class as
         it's common for all smart protocols?
        """
        error_code = SmartErrorCode(resp_dict.get("error_code"))  # type: ignore[arg-type]
        if error_code == SmartErrorCode.SUCCESS:
            return

        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"

        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)

        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.LOGIN_REQUIRED
            raise AuthenticationError(msg, error_code=error_code)

        raise DeviceError(msg, error_code=error_code)

    async def send_cleartext_request(self, request: str) -> dict[str, Any]:
        """Send encrypted message as passthrough."""
        if self._state is TransportState.ESTABLISHED and self._token_url:
            url = self._token_url
        else:
            url = self._app_url

        _LOGGER.debug("Sending %s", request)

        status_code, resp = await self._http_client.post(
            url,
            data=request.encode(),
            headers=self.COMMON_HEADERS,
        )
        _LOGGER.debug("Response with %s: %r", status_code, resp)
        resp_dict = json_loads(resp)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        if TYPE_CHECKING:
            resp_dict = cast(Dict[str, Any], resp_dict)

        return resp_dict  # type: ignore[return-value]

    async def perform_login(self):
        """Login to the device."""
        try:
            await self.try_login(self._login_params)
        except AuthenticationError as aex:
            try:
                if aex.error_code is not SmartErrorCode.LOGIN_ERROR:
                    raise aex
                if self._default_credentials is None:
                    self._default_credentials = get_default_credentials(
                        DEFAULT_CREDENTIALS["TAPO"]
                    )
                    await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_LOGIN_ERROR)
                await self.try_login(self._get_login_params(self._default_credentials))
                _LOGGER.debug(
                    "%s: logged in with default credentials",
                    self._host,
                )
            except AuthenticationError:
                raise
            except Exception as ex:
                raise KasaException(
                    "Unable to login and trying default "
                    + f"login raised another exception: {ex}",
                    ex,
                ) from ex

    async def try_login(self, login_params: dict[str, Any]) -> None:
        """Try to login with supplied login_params."""
        login_request = {
            "method": "login",
            "params": login_params,
        }
        request = json_dumps(login_request)
        _LOGGER.debug("Going to send login request")

        resp_dict = await self.send_cleartext_request(request)
        self._handle_response_error_code(resp_dict, "Error logging in")

        login_token = resp_dict["result"]["token"]
        self._token_url = self._app_url.with_query(f"token={login_token}")
        self._state = TransportState.ESTABLISHED
        self._session_expire_at = (
            time.time() + ONE_DAY_SECONDS - SESSION_EXPIRE_BUFFER_SECONDS
        )

    def _session_expired(self):
        """Return true if session has expired."""
        return (
            self._session_expire_at is None
            or self._session_expire_at - time.time() <= 0
        )

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        _LOGGER.info("Going to send %s", request)
        if self._state is not TransportState.ESTABLISHED or self._session_expired():
            _LOGGER.debug("Transport not established or session expired, logging in")
            await self.perform_login()

        return await self.send_cleartext_request(request)

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal login state."""
        self._state = TransportState.LOGIN_REQUIRED
