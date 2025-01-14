import copy
from json import loads as json_loads
from warnings import warn

import pytest

from kasa import Credentials, DeviceConfig, SmartProtocol
from kasa.exceptions import SmartErrorCode
from kasa.smart import SmartChildDevice
from kasa.smartcam import SmartCamChild
from kasa.smartcam.smartcamchild import CHILD_INFO_FROM_PARENT
from kasa.transports.basetransport import BaseTransport


class FakeSmartProtocol(SmartProtocol):
    def __init__(self, info, fixture_name, *, is_child=False, verbatim=False):
        super().__init__(
            transport=FakeSmartTransport(
                info, fixture_name, is_child=is_child, verbatim=verbatim
            ),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so can still patch SmartProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeSmartTransport(BaseTransport):
    def __init__(
        self,
        info,
        fixture_name,
        *,
        list_return_size=10,
        component_nego_not_included=False,
        warn_fixture_missing_methods=True,
        fix_incomplete_fixture_lists=True,
        is_child=False,
        get_child_fixtures=True,
        verbatim=False,
    ):
        super().__init__(
            config=DeviceConfig(
                "127.0.0.123",
                credentials=Credentials(
                    username="dummy_user",
                    password="dummy_password",  # noqa: S106
                ),
            ),
        )
        self.fixture_name = fixture_name

        # When True verbatim will bypass any extra processing of missing
        # methods and is used to test the fixture creation itself.
        self.verbatim = verbatim

        # Don't copy the dict if the device is a child so that updates on the
        # child are then still reflected on the parent's lis of child device in
        if not is_child:
            self.info = copy.deepcopy(info)
            if get_child_fixtures:
                self.child_protocols = self._get_child_protocols(
                    self.info, self.fixture_name, "get_child_device_list", self.verbatim
                )
        else:
            self.info = info
        if not component_nego_not_included:
            self.components = {
                comp["id"]: comp["ver_code"]
                for comp in self.info["component_nego"]["component_list"]
            }
        self.list_return_size = list_return_size
        self.warn_fixture_missing_methods = warn_fixture_missing_methods
        self.fix_incomplete_fixture_lists = fix_incomplete_fixture_lists

        if verbatim:
            self.warn_fixture_missing_methods = False
            self.fix_incomplete_fixture_lists = False

    @property
    def default_port(self):
        """Default port for the transport."""
        return 80

    @property
    def credentials_hash(self):
        """The hashed credentials used by the transport."""
        return self._credentials.username + self._credentials.password + "hash"

    FIXTURE_MISSING_MAP = {
        "get_wireless_scan_info": ("wireless", {"ap_list": [], "wep_supported": False}),
        "get_auto_off_config": ("auto_off", {"delay_min": 10, "enable": False}),
        "get_led_info": (
            "led",
            {
                "led_rule": "never",
                "led_status": False,
                "night_mode": {
                    "end_time": 420,
                    "night_mode_type": "sunrise_sunset",
                    "start_time": 1140,
                    "sunrise_offset": 0,
                    "sunset_offset": 0,
                },
            },
        ),
        "get_latest_fw": (
            "firmware",
            {
                "fw_size": 0,
                "fw_ver": "1.0.5 Build 230801 Rel.095702",
                "hw_id": "",
                "need_to_upgrade": False,
                "oem_id": "",
                "release_date": "",
                "release_note": "",
                "type": 0,
            },
        ),
        "get_homekit_info": (
            "homekit",
            {
                "mfi_setup_code": "000-00-000",
                "mfi_setup_id": "0000",
                "mfi_token_token": "000000000000000000000000000000000",
                "mfi_token_uuid": "00000000-0000-0000-0000-000000000000",
            },
        ),
        "get_auto_update_info": (
            ("firmware", 2),
            {"enable": True, "random_range": 120, "time": 180},
        ),
        "get_alarm_configure": (
            "alarm",
            {
                "duration": 10,
                "type": "Doorbell Ring 2",
                "volume": "low",
            },
        ),
        "get_support_alarm_type_list": (
            "alarm",
            {
                "alarm_type_list": [
                    "Doorbell Ring 1",
                ]
            },
        ),
        "get_device_usage": ("device", {}),
        "get_connect_cloud_state": ("cloud_connect", {"status": 0}),
        "get_emeter_data": (
            "energy_monitoring",
            {
                "current_ma": 33,
                "energy_wh": 971,
                "power_mw": 1003,
                "voltage_mv": 121215,
            },
        ),
        "get_emeter_vgain_igain": (
            "energy_monitoring",
            {"igain": 10861, "vgain": 118657},
        ),
        "get_matter_setup_info": (
            "matter",
            {
                "setup_code": "00000000000",
                "setup_payload": "00:0000000-0000.00.000",
            },
        ),
    }

    def _missing_result(self, method):
        """Check the FIXTURE_MISSING_MAP for responses.

        Fixtures generated prior to a query being supported by dump_devinfo
        do not have the response so this method checks whether the component
        is supported and fills in the missing response.
        If the first value of the lookup value is a tuple it will also check
        the version, i.e. (component_name, component_version).
        """
        if not (missing := self.FIXTURE_MISSING_MAP.get(method)):
            return None
        condition = missing[0]
        if (
            isinstance(condition, tuple)
            and (version := self.components.get(condition[0]))
            and version >= condition[1]
        ):
            return copy.deepcopy(missing[1])

        if condition in self.components:
            return copy.deepcopy(missing[1])

        return None

    async def send(self, request: str):
        request_dict = json_loads(request)
        method = request_dict["method"]

        if method == "multipleRequest":
            params = request_dict["params"]
            responses = []
            for request in params["requests"]:
                response = await self._send_request(request)  # type: ignore[arg-type]
                # Devices do not continue after error
                if response["error_code"] != 0:
                    break
                response["method"] = request["method"]  # type: ignore[index]
                responses.append(response)
            return {"result": {"responses": responses}, "error_code": 0}
        else:
            return await self._send_request(request_dict)

    @staticmethod
    def _get_child_protocols(
        parent_fixture_info, parent_fixture_name, child_devices_key, verbatim
    ):
        child_infos = parent_fixture_info.get(child_devices_key, {}).get(
            "child_device_list", []
        )
        if not child_infos:
            return
        found_child_fixture_infos = []
        child_protocols = {}
        # imported here to avoid circular import
        from .conftest import filter_fixtures

        def try_get_child_fixture_info(child_dev_info, protocol):
            hw_version = child_dev_info["hw_ver"]
            sw_version = child_dev_info.get("sw_ver", child_dev_info.get("fw_ver"))
            sw_version = sw_version.split(" ")[0]
            model = child_dev_info.get("device_model", child_dev_info.get("model"))
            assert sw_version
            assert model

            region = child_dev_info.get("specs", child_dev_info.get("region"))
            region = f"({region})" if region else ""
            child_fixture_name = f"{model}{region}_{hw_version}_{sw_version}"
            child_fixtures = filter_fixtures(
                "Child fixture",
                protocol_filter={protocol},
                model_filter={child_fixture_name},
            )
            if child_fixtures:
                return next(iter(child_fixtures))
            return None

        for child_info in child_infos:
            if (  # Is SMART protocol
                (device_id := child_info.get("device_id"))
                and (category := child_info.get("category"))
                and category in SmartChildDevice.CHILD_DEVICE_TYPE_MAP
            ):
                if fixture_info_tuple := try_get_child_fixture_info(
                    child_info, "SMART.CHILD"
                ):
                    child_fixture = copy.deepcopy(fixture_info_tuple.data)
                    child_fixture["get_device_info"]["device_id"] = device_id
                    found_child_fixture_infos.append(child_fixture["get_device_info"])
                    child_protocols[device_id] = FakeSmartProtocol(
                        child_fixture,
                        fixture_info_tuple.name,
                        is_child=True,
                        verbatim=verbatim,
                    )
                # Look for fixture inline
                elif (child_fixtures := parent_fixture_info.get("child_devices")) and (
                    child_fixture := child_fixtures.get(device_id)
                ):
                    found_child_fixture_infos.append(child_fixture["get_device_info"])
                    child_protocols[device_id] = FakeSmartProtocol(
                        child_fixture,
                        f"{parent_fixture_name}-{device_id}",
                        is_child=True,
                        verbatim=verbatim,
                    )
                else:
                    pytest.fixtures_missing_methods.setdefault(  # type: ignore[attr-defined]
                        parent_fixture_name, set()
                    ).add("child_devices")
            elif (
                (device_id := child_info.get("device_id"))
                and (category := child_info.get("category"))
                and category in SmartCamChild.CHILD_DEVICE_TYPE_MAP
                and (
                    fixture_info_tuple := try_get_child_fixture_info(
                        child_info, "SMARTCAM.CHILD"
                    )
                )
            ):
                from .fakeprotocol_smartcam import FakeSmartCamProtocol

                child_fixture = copy.deepcopy(fixture_info_tuple.data)
                child_fixture["getDeviceInfo"]["device_info"]["basic_info"][
                    "dev_id"
                ] = device_id
                child_fixture[CHILD_INFO_FROM_PARENT]["device_id"] = device_id
                # We copy the child device info to the parent getChildDeviceInfo
                # list for smartcam children in order for updates to work.
                found_child_fixture_infos.append(child_fixture[CHILD_INFO_FROM_PARENT])
                child_protocols[device_id] = FakeSmartCamProtocol(
                    child_fixture,
                    fixture_info_tuple.name,
                    is_child=True,
                    verbatim=verbatim,
                )
            else:
                warn(
                    f"Child is a protocol which needs to be implemented {child_info}",
                    stacklevel=2,
                )
        # Replace parent child infos with the infos from the child fixtures so
        # that updates update both
        if not verbatim and child_infos and found_child_fixture_infos:
            parent_fixture_info[child_devices_key]["child_device_list"] = (
                found_child_fixture_infos
            )
        return child_protocols

    async def _handle_control_child(self, params: dict):
        """Handle control_child command."""
        device_id = params.get("device_id")
        if device_id not in self.child_protocols:
            # no need to warn as the warning was raised during protocol init
            return self._handle_control_child_missing(params)

        child_protocol: SmartProtocol = self.child_protocols[device_id]

        request_data = params.get("requestData", {})

        child_method = request_data.get("method")
        child_params = request_data.get("params")  # noqa: F841

        resp = await child_protocol.query({child_method: child_params})
        resp["error_code"] = 0
        for val in resp.values():
            return {
                "result": {"responseData": {"result": val, "error_code": 0}},
                "error_code": 0,
            }

    def _handle_control_child_missing(self, params: dict):
        """Handle control_child command.

        Used for older fixtures where child info wasn't stored in the fixture.
        TODO: Should be removed somehow for future maintanability.
        """
        device_id = params.get("device_id")
        request_data = params.get("requestData", {})

        child_method = request_data.get("method")
        child_params = request_data.get("params")

        info = self.info
        children = info["get_child_device_list"]["child_device_list"]

        for child in children:
            if child["device_id"] == device_id:
                info = child
                break
        # Create the child_devices fixture section for fixtures generated before it was added
        if "child_devices" not in self.info:
            self.info["child_devices"] = {}
        # Get the method calls made directly on the child devices
        child_device_calls = self.info["child_devices"].setdefault(device_id, {})

        # We only support get & set device info in this method for missing.
        if child_method == "get_device_info":
            result = copy.deepcopy(info)
            return {"result": result, "error_code": 0}
        elif child_method == "set_device_info":
            info.update(child_params)
            return {"error_code": 0}
        elif child_method == "set_preset_rules":
            return self._set_child_preset_rules(info, child_params)
        elif child_method == "set_on_off_gradually_info":
            return self._set_on_off_gradually_info(info, child_params)
        elif child_method in child_device_calls:
            result = copy.deepcopy(child_device_calls[child_method])
            return {"result": result, "error_code": 0}
        elif missing_result := self._missing_result(child_method):
            # FIXTURE_MISSING is for service calls not in place when
            # SMART fixtures started to be generated
            # Copy to info so it will work with update methods
            child_device_calls[child_method] = missing_result
            result = copy.deepcopy(info[child_method])
            retval = {"result": result, "error_code": 0}
            return retval
        elif child_method[:3] == "set":
            target_method = f"get{child_method[3:]}"
            if target_method not in child_device_calls:
                raise RuntimeError(
                    f"No {target_method} in child info, calling set before get not supported."
                )
            child_device_calls[target_method].update(child_params)
            return {"error_code": 0}
        else:
            # PARAMS error returned for KS240 when get_device_usage called
            # on parent device.  Could be any error code though.
            # TODO: Try to figure out if there's a way to prevent the KS240 smartdevice
            # calling the unsupported device in the first place.
            retval = {
                "error_code": SmartErrorCode.PARAMS_ERROR.value,
                "method": child_method,
            }
            return retval

        raise NotImplementedError(f"Method {child_method} not implemented for children")

    def _get_on_off_gradually_info(self, info, params):
        if self.components["on_off_gradually"] == 1:
            info["get_on_off_gradually_info"] = {"enable": True}
        else:
            info["get_on_off_gradually_info"] = {
                "off_state": {"duration": 5, "enable": False, "max_duration": 60},
                "on_state": {"duration": 5, "enable": False, "max_duration": 60},
            }
        return copy.deepcopy(info["get_on_off_gradually_info"])

    def _set_on_off_gradually_info(self, info, params):
        # Child devices can have the required properties directly in info

        # the _handle_control_child_missing directly passes in get_device_info
        sys_info = info.get("get_device_info", info)

        if self.components["on_off_gradually"] == 1:
            info["get_on_off_gradually_info"] = {"enable": params["enable"]}
        elif on_state := params.get("on_state"):
            if "fade_on_time" in sys_info and "gradually_on_mode" in sys_info:
                sys_info["gradually_on_mode"] = 1 if on_state["enable"] else 0
                if "duration" in on_state:
                    sys_info["fade_on_time"] = on_state["duration"]
            if "get_on_off_gradually_info" in info:
                info["get_on_off_gradually_info"]["on_state"]["enable"] = on_state[
                    "enable"
                ]
                if "duration" in on_state:
                    info["get_on_off_gradually_info"]["on_state"]["duration"] = (
                        on_state["duration"]
                    )
        elif off_state := params.get("off_state"):
            if "fade_off_time" in sys_info and "gradually_off_mode" in sys_info:
                sys_info["gradually_off_mode"] = 1 if off_state["enable"] else 0
                if "duration" in off_state:
                    sys_info["fade_off_time"] = off_state["duration"]
            if "get_on_off_gradually_info" in info:
                info["get_on_off_gradually_info"]["off_state"]["enable"] = off_state[
                    "enable"
                ]
                if "duration" in off_state:
                    info["get_on_off_gradually_info"]["off_state"]["duration"] = (
                        off_state["duration"]
                    )
        return {"error_code": 0}

    def _set_dynamic_light_effect(self, info, params):
        """Set or remove values as per the device behaviour."""
        info["get_device_info"]["dynamic_light_effect_enable"] = params["enable"]
        info["get_dynamic_light_effect_rules"]["enable"] = params["enable"]
        if params["enable"]:
            info["get_device_info"]["dynamic_light_effect_id"] = params["id"]
            info["get_dynamic_light_effect_rules"]["current_rule_id"] = params["id"]
        else:
            if "dynamic_light_effect_id" in info["get_device_info"]:
                del info["get_device_info"]["dynamic_light_effect_id"]
            if "current_rule_id" in info["get_dynamic_light_effect_rules"]:
                del info["get_dynamic_light_effect_rules"]["current_rule_id"]

    def _set_edit_dynamic_light_effect_rule(self, info, params):
        """Edit dynamic light effect rule."""
        rules = info["get_dynamic_light_effect_rules"]["rule_list"]
        for rule in rules:
            if rule["id"] == params["id"]:
                rule.update(params)
                return

        raise Exception("Unable to find rule with id")

    def _set_light_strip_effect(self, info, params):
        """Set or remove values as per the device behaviour."""
        # Brightness is not always available
        if (brightness := params.get("brightness")) is not None:
            info["get_device_info"]["lighting_effect"]["brightness"] = brightness
        if "enable" in params:
            info["get_device_info"]["lighting_effect"]["enable"] = params["enable"]
            info["get_device_info"]["lighting_effect"]["name"] = params["name"]
            info["get_device_info"]["lighting_effect"]["id"] = params["id"]
            info["get_lighting_effect"] = copy.deepcopy(params)

    def _set_led_info(self, info, params):
        """Set or remove values as per the device behaviour."""
        info["get_led_info"]["led_status"] = params["led_rule"] != "never"
        info["get_led_info"]["led_rule"] = params["led_rule"]

    def _set_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        if "brightness" not in info["get_preset_rules"]:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["get_preset_rules"]["brightness"] = params["brightness"]
        # So far the only child device with light preset (KS240) also has the
        # data available to read in the device_info.
        device_info = info["get_device_info"]
        if "preset_state" in device_info:
            device_info["preset_state"] = [
                {"brightness": b} for b in params["brightness"]
            ]
        return {"error_code": 0}

    def _set_child_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        # So far the only child device with light preset (KS240) has the
        # data available to read in the device_info.  If a child device
        # appears that doesn't have this this will need to be extended.
        if "preset_state" not in info:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["preset_state"] = [{"brightness": b} for b in params["brightness"]]
        return {"error_code": 0}

    def _edit_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        if "states" not in info["get_preset_rules"] is None:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["get_preset_rules"]["states"][params["index"]] = params["state"]
        return {"error_code": 0}

    def _set_temperature_unit(self, info, params):
        """Set or remove values as per the device behaviour."""
        unit = params["temp_unit"]
        if unit not in {"celsius", "fahrenheit"}:
            raise ValueError(f"Invalid value for temperature unit {unit}")
        if "temp_unit" not in info["get_device_info"]:
            return {"error_code": SmartErrorCode.UNKNOWN_METHOD_ERROR}
        else:
            info["get_device_info"]["temp_unit"] = unit
            return {"error_code": 0}

    def _update_sysinfo_key(self, info: dict, key: str, value: str) -> dict:
        """Update a single key in the main system info.

        This is used to implement child device setters that change the main sysinfo state.
        """
        sys_info = info.get("get_device_info", info)
        sys_info[key] = value

        return {"error_code": 0}

    async def _send_request(self, request_dict: dict):
        method = request_dict["method"]

        info = self.info
        if method == "control_child":
            return await self._handle_control_child(request_dict["params"])

        params = request_dict.get("params", {})
        if method in {"component_nego", "qs_component_nego"} or method[:3] == "get":
            if method in info:
                result = copy.deepcopy(info[method])
                if result and "start_index" in result and "sum" in result:
                    list_key = next(
                        iter([key for key in result if isinstance(result[key], list)])
                    )
                    start_index = (
                        start_index
                        if (params and (start_index := params.get("start_index")))
                        else 0
                    )
                    # Fixtures generated before _handle_response_lists was implemented
                    # could have incomplete lists.
                    if (
                        len(result[list_key]) < result["sum"]
                        and self.fix_incomplete_fixture_lists
                    ):
                        result["sum"] = len(result[list_key])
                        if self.warn_fixture_missing_methods:
                            pytest.fixtures_missing_methods.setdefault(  # type: ignore[attr-defined]
                                self.fixture_name, set()
                            ).add(f"{method} (incomplete '{list_key}' list)")

                    result[list_key] = result[list_key][
                        start_index : start_index + self.list_return_size
                    ]
                return {"result": result, "error_code": 0}

            if self.verbatim:
                return {
                    "error_code": SmartErrorCode.PARAMS_ERROR.value,
                    "method": method,
                }

            if missing_result := self._missing_result(method):
                # FIXTURE_MISSING is for service calls not in place when
                # SMART fixtures started to be generated
                # Copy to info so it will work with update methods
                info[method] = missing_result
                result = copy.deepcopy(info[method])
                retval = {"result": result, "error_code": 0}
            elif (
                method == "get_on_off_gradually_info"
                and "on_off_gradually" in self.components
            ):
                # Need to call a method here to determine which version schema to return
                result = self._get_on_off_gradually_info(info, params)
                return {"result": result, "error_code": 0}
            else:
                # PARAMS error returned for KS240 when get_device_usage called
                # on parent device.  Could be any error code though.
                # TODO: Try to figure out if there's a way to prevent the KS240 smartdevice
                # calling the unsupported device in the first place.
                retval = {
                    "error_code": SmartErrorCode.PARAMS_ERROR.value,
                    "method": method,
                }
            # Reduce warning spam by consolidating and reporting at the end of the run
            if self.warn_fixture_missing_methods:
                pytest.fixtures_missing_methods.setdefault(  # type: ignore[attr-defined]
                    self.fixture_name, set()
                ).add(method)
            return retval
        elif method in ["set_qs_info", "fw_download", "play_alarm", "stop_alarm"]:
            return {"error_code": 0}
        elif method == "set_dynamic_light_effect_rule_enable":
            self._set_dynamic_light_effect(info, params)
            return {"error_code": 0}
        elif method == "edit_dynamic_light_effect_rule":
            self._set_edit_dynamic_light_effect_rule(info, params)
            return {"error_code": 0}
        elif method == "set_lighting_effect":
            self._set_light_strip_effect(info, params)
            return {"error_code": 0}
        elif method == "set_led_info":
            self._set_led_info(info, params)
            return {"error_code": 0}
        elif method == "set_preset_rules":
            return self._set_preset_rules(info, params)
        elif method == "edit_preset_rules":
            return self._edit_preset_rules(info, params)
        elif method == "set_temperature_unit":
            return self._set_temperature_unit(info, params)
        elif method == "set_on_off_gradually_info":
            return self._set_on_off_gradually_info(info, params)
        elif method == "set_child_protection":
            return self._update_sysinfo_key(info, "child_protection", params["enable"])
        # Vacuum special actions
        elif method in ["playSelectAudio"]:
            return {"error_code": 0}
        elif method[:3] == "set":
            target_method = f"get{method[3:]}"
            # Some vacuum commands do not have a getter
            if method in [
                "setRobotPause",
                "setSwitchClean",
                "setSwitchCharge",
                "setSwitchDustCollection",
            ]:
                return {"error_code": 0}

            info[target_method].update(params)

            return {"error_code": 0}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
