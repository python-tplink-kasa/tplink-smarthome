"""Module for SmartCamera Protocol."""

from __future__ import annotations

import logging
from pprint import pformat as pf
from typing import Any

from ..exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    _RetryableError,
)
from ..json import dumps as json_dumps
from ..smartprotocol import SmartProtocol
from .sslaestransport import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    SmartErrorCode,
)

_LOGGER = logging.getLogger(__name__)

# List of getMethodNames that should be sent as {"method":"do"}
# https://md.depau.eu/s/r1Ys_oWoP#Modules
GET_METHODS_AS_DO = {
    "getSdCardFormatStatus",
    "getConnectionType",
    "getUserID",
    "getP2PSharePassword",
    "getAESEncryptKey",
    "getFirmwareAFResult",
    "getWhitelampStatus",
}


class SmartCameraProtocol(SmartProtocol):
    """Class for SmartCamera Protocol."""

    async def _handle_response_lists(
        self, response_result: dict[str, Any], method, retry_count
    ):
        pass

    def _handle_response_error_code(self, resp_dict: dict, method, raise_on_error=True):
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR

        if error_code is SmartErrorCode.SUCCESS:
            return

        if not raise_on_error:
            resp_dict["result"] = error_code
            return

        msg = (
            f"Error querying device: {self._host}: "
            + f"{error_code.name}({error_code.value})"
            + f" for method: {method}"
        )
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()

    @staticmethod
    def _get_smart_camera_single_request(
        request: dict[str, dict[str, Any]],
    ) -> tuple[str, str, str, dict]:
        method = next(iter(request))
        if method == "multipleRequest":
            method_type = "multi"
            params = request["multipleRequest"]
            req = {"method": "multipleRequest", "params": params}
            return "multi", "multipleRequest", "", req

        if (short_method := method[:3]) and short_method in {"get", "set"}:
            method_type = short_method
            param = next(iter(request[method]))
            if method in GET_METHODS_AS_DO:
                method_type = "do"
            req = {
                "method": method_type,
                param: request[method][param],
            }
        else:
            method_type = "do"
            param = next(iter(request[method]))
            req = {
                "method": method_type,
                param: request[method][param],
            }
        return method_type, method, param, req

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        if isinstance(request, dict):
            if len(request) == 1:
                method_type, method, param, single_request = (
                    self._get_smart_camera_single_request(request)
                )
            else:
                return await self._execute_multiple_query(request, retry_count)
        else:
            # If method like getSomeThing then module will be some_thing
            method = request
            method_type = request[:3]
            snake_name = "".join(
                ["_" + i.lower() if i.isupper() else i for i in request]
            ).lstrip("_")
            param = snake_name[4:]
            if (short_method := method[:3]) and short_method in {"get", "set"}:
                method_type = short_method
                param = snake_name[4:]
            else:
                method_type = "do"
                param = snake_name
            single_request = {"method": method_type, param: {}}

        smart_request = json_dumps(single_request)
        if debug_enabled:
            _LOGGER.debug(
                "%s >> %s",
                self._host,
                pf(smart_request),
            )
        response_data = await self._transport.send(smart_request)

        if debug_enabled:
            _LOGGER.debug(
                "%s << %s",
                self._host,
                pf(response_data),
            )

        if "error_code" in response_data:
            # H200 does not return an error code
            self._handle_response_error_code(response_data, method)
        # Requests that are invalid and raise PROTOCOL_FORMAT_ERROR when sent
        # as a multipleRequest will return {} when sent as a single request.
        if method_type == "get" and (
            not (section := next(iter(response_data))) or response_data[section] == {}
        ):
            raise DeviceError(f"No results for get request {single_request}")

        # TODO need to update handle response lists

        if method_type == "do":
            return {method: response_data}
        if method_type == "set":
            return {}
        if method_type == "multi":
            return {method: response_data["result"]}
        return {method: {param: response_data[param]}}


class _ChildCameraProtocolWrapper(SmartProtocol):
    """Protocol wrapper for controlling child devices.

    This is an internal class used to communicate with child devices,
    and should not be used directly.

    This class overrides query() method of the protocol to modify all
    outgoing queries to use ``controlChild`` command, and unwraps the
    device responses before returning to the caller.
    """

    def __init__(self, device_id: str, base_protocol: SmartProtocol):
        self._device_id = device_id
        self._protocol = base_protocol
        self._transport = base_protocol._transport

    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Wrap request inside controlChild envelope."""
        return await self._query(request, retry_count)

    async def _query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Wrap request inside controlChild envelope."""
        if not isinstance(request, dict):
            raise KasaException("Child requests must be dictionaries.")
        requests = []
        methods = []
        for key, val in request.items():
            request = {
                "method": "controlChild",
                "params": {
                    "childControl": {
                        "device_id": self._device_id,
                        "request_data": {"method": key, "params": val},
                    }
                },
            }
            methods.append(key)
            requests.append(request)

        multipleRequest = {"multipleRequest": {"requests": requests}}

        response = await self._protocol.query(multipleRequest, retry_count)

        responses = response["multipleRequest"]["responses"]
        response_dict = {}
        for index_id, response in enumerate(responses):
            response_data = response["result"]["response_data"]
            method = methods[index_id]
            self._handle_response_error_code(
                response_data, method, raise_on_error=False
            )
            response_dict[method] = response_data.get("result")

        return response_dict

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""
