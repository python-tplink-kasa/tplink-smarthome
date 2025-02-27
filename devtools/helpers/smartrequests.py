"""SmartRequest helper classes and functions for new SMART/TAPO devices.

List of known requests with associated parameter classes.

Other requests that are known but not currently implemented
or tested are:

get_child_device_component_list
get_child_device_list
control_child
get_device_running_info - seems to be a subset of get_device_info

get_tss_info
get_raw_dvi
get_homekit_info

fw_download

sync_env
account_sync

device_reset
close_device_ble
heart_beat

"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

_LOGGER = logging.getLogger(__name__)


class SmartRequest:
    """Class to represent a smart protocol request."""

    def __init__(self, method_name: str, params: SmartRequestParams | None = None):
        self.method_name = method_name
        if params:
            self.params = params.to_dict()
        else:
            self.params = None

    def __repr__(self):
        return f"SmartRequest({self.method_name})"

    def to_dict(self):
        """Return the request as a dict suitable for passing to query()."""
        return {self.method_name: self.params}

    @dataclass
    class SmartRequestParams:
        """Base class for Smart request params.

        The to_dict() method of this class omits null values which
        is required by the devices.
        """

        def to_dict(self):
            """Return the params as a dict with values of None ommited."""
            return asdict(
                self, dict_factory=lambda x: {k: v for (k, v) in x if v is not None}
            )

    @dataclass
    class DeviceOnParams(SmartRequestParams):
        """Get Rules Params."""

        device_on: bool

    @dataclass
    class GetRulesParams(SmartRequestParams):
        """Get Rules Params."""

        start_index: int = 0

    @dataclass
    class GetScheduleRulesParams(SmartRequestParams):
        """Get Rules Params."""

        start_index: int = 0
        schedule_mode: str = ""

    @dataclass
    class GetTriggerLogsParams(SmartRequestParams):
        """Trigger Logs params."""

        page_size: int = 5
        start_id: int = 0

    @dataclass
    class LedStatusParams(SmartRequestParams):
        """LED Status params."""

        led_rule: str | None = None

        @staticmethod
        def from_bool(state: bool):
            """Set the led_rule from the state."""
            rule = "always" if state else "never"
            return SmartRequest.LedStatusParams(led_rule=rule)

    @dataclass
    class LightInfoParams(SmartRequestParams):
        """LightInfo params."""

        brightness: int | None = None
        color_temp: int | None = None
        hue: int | None = None
        saturation: int | None = None

    @dataclass
    class DynamicLightEffectParams(SmartRequestParams):
        """LightInfo params."""

        enable: bool
        id: str | None = None

    @dataclass
    class GetCleanAttrParams(SmartRequestParams):
        """CleanAttr params.

        Decides which cleaning settings are requested
        """

        #: type can be global or pose
        type: str = "global"

    @staticmethod
    def get_raw_request(
        method: str, params: SmartRequestParams | None = None
    ) -> SmartRequest:
        """Send a raw request to the device."""
        return SmartRequest(method, params)

    @staticmethod
    def component_nego() -> SmartRequest:
        """Get quick setup component info."""
        return SmartRequest("component_nego")

    @staticmethod
    def get_device_info() -> SmartRequest:
        """Get device info."""
        return SmartRequest("get_device_info")

    @staticmethod
    def get_device_usage() -> SmartRequest:
        """Get device usage."""
        return SmartRequest("get_device_usage")

    @staticmethod
    def device_info_list(ver_code) -> list[SmartRequest]:
        """Get device info list."""
        if ver_code == 1:
            return [SmartRequest.get_device_info()]
        return [
            SmartRequest.get_device_info(),
            SmartRequest.get_device_usage(),
            SmartRequest.get_auto_update_info(),
        ]

    @staticmethod
    def get_auto_update_info() -> SmartRequest:
        """Get auto update info."""
        return SmartRequest("get_auto_update_info")

    @staticmethod
    def firmware_info_list() -> list[SmartRequest]:
        """Get info list."""
        return [
            SmartRequest.get_raw_request("get_fw_download_state"),
            SmartRequest.get_raw_request("get_latest_fw"),
        ]

    @staticmethod
    def qs_component_nego() -> SmartRequest:
        """Get quick setup component info."""
        return SmartRequest("qs_component_nego")

    @staticmethod
    def get_device_time() -> SmartRequest:
        """Get device time."""
        return SmartRequest("get_device_time")

    @staticmethod
    def get_child_device_list() -> SmartRequest:
        """Get child device list."""
        return SmartRequest("get_child_device_list")

    @staticmethod
    def get_child_device_component_list() -> SmartRequest:
        """Get child device component list."""
        return SmartRequest("get_child_device_component_list")

    @staticmethod
    def get_wireless_scan_info(
        params: GetRulesParams | None = None,
    ) -> SmartRequest:
        """Get wireless scan info."""
        return SmartRequest(
            "get_wireless_scan_info", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_schedule_rules(params: GetRulesParams | None = None) -> SmartRequest:
        """Get schedule rules."""
        return SmartRequest(
            "get_schedule_rules", params or SmartRequest.GetScheduleRulesParams()
        )

    @staticmethod
    def get_next_event(params: GetRulesParams | None = None) -> SmartRequest:
        """Get next scheduled event."""
        return SmartRequest("get_next_event", params or SmartRequest.GetRulesParams())

    @staticmethod
    def schedule_info_list() -> list[SmartRequest]:
        """Get schedule info list."""
        return [
            SmartRequest.get_schedule_rules(),
            SmartRequest.get_next_event(),
        ]

    @staticmethod
    def get_countdown_rules(params: GetRulesParams | None = None) -> SmartRequest:
        """Get countdown rules."""
        return SmartRequest(
            "get_countdown_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_antitheft_rules(params: GetRulesParams | None = None) -> SmartRequest:
        """Get antitheft rules."""
        return SmartRequest(
            "get_antitheft_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_led_info(params: LedStatusParams | None = None) -> SmartRequest:
        """Get led info."""
        return SmartRequest("get_led_info", params or SmartRequest.LedStatusParams())

    @staticmethod
    def get_auto_off_config(params: GetRulesParams | None = None) -> SmartRequest:
        """Get auto off config."""
        return SmartRequest(
            "get_auto_off_config", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_delay_action_info() -> SmartRequest:
        """Get delay action info."""
        return SmartRequest("get_delay_action_info")

    @staticmethod
    def auto_off_list() -> list[SmartRequest]:
        """Get energy usage."""
        return [
            SmartRequest.get_auto_off_config(),
            SmartRequest.get_delay_action_info(),  # May not live here
        ]

    @staticmethod
    def get_energy_usage() -> SmartRequest:
        """Get energy usage."""
        return SmartRequest("get_energy_usage")

    @staticmethod
    def energy_monitoring_list() -> list[SmartRequest]:
        """Get energy usage."""
        return [
            SmartRequest("get_energy_usage"),
            SmartRequest("get_emeter_data"),
            SmartRequest("get_emeter_vgain_igain"),
            SmartRequest.get_raw_request("get_electricity_price_config"),
        ]

    @staticmethod
    def get_current_power() -> SmartRequest:
        """Get current power."""
        return SmartRequest("get_current_power")

    @staticmethod
    def power_protection_list() -> list[SmartRequest]:
        """Get power protection info list."""
        return [
            SmartRequest.get_current_power(),
            SmartRequest.get_raw_request("get_max_power"),
            SmartRequest.get_raw_request("get_protection_power"),
        ]

    @staticmethod
    def get_preset_rules(params: GetRulesParams | None = None) -> SmartRequest:
        """Get preset rules."""
        return SmartRequest("get_preset_rules", params or SmartRequest.GetRulesParams())

    @staticmethod
    def get_on_off_gradually_info(
        params: SmartRequestParams | None = None,
    ) -> SmartRequest:
        """Get preset rules."""
        return SmartRequest(
            "get_on_off_gradually_info", params or SmartRequest.SmartRequestParams()
        )

    @staticmethod
    def get_dimmer_calibration(
        params: SmartRequestParams | None = None,
    ) -> list[SmartRequest]:
        """Get dimmer calibration."""
        return [
            # Not certain if the get_calibration is used anywhere...
            SmartRequest(
                "get_calibration", params or SmartRequest.SmartRequestParams()
            ),
            # The brightness calibration is used, however.
            SmartRequest(
                "get_calibrate_brightness", params or SmartRequest.SmartRequestParams()
            ),
        ]

    @staticmethod
    def get_auto_light_info() -> SmartRequest:
        """Get auto light info."""
        return SmartRequest("get_auto_light_info")

    @staticmethod
    def get_dynamic_light_effect_rules(
        params: GetRulesParams | None = None,
    ) -> SmartRequest:
        """Get dynamic light effect rules."""
        return SmartRequest(
            "get_dynamic_light_effect_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def set_device_on(params: DeviceOnParams) -> SmartRequest:
        """Set device on state."""
        return SmartRequest("set_device_info", params)

    @staticmethod
    def set_light_info(params: LightInfoParams) -> SmartRequest:
        """Set color temperature."""
        return SmartRequest("set_device_info", params)

    @staticmethod
    def set_dynamic_light_effect_rule_enable(
        params: DynamicLightEffectParams,
    ) -> SmartRequest:
        """Enable dynamic light effect rule."""
        return SmartRequest("set_dynamic_light_effect_rule_enable", params)

    @staticmethod
    def get_component_info_requests(component_nego_response) -> list[SmartRequest]:
        """Get a list of requests based on the component info response."""
        request_list: list[SmartRequest] = []
        for component in component_nego_response["component_list"]:
            if (
                requests := get_component_requests(
                    component["id"], int(component["ver_code"])
                )
            ) is not None:
                request_list.extend(requests)
        return request_list

    @staticmethod
    def _create_request_dict(
        smart_request: SmartRequest | list[SmartRequest],
    ) -> dict:
        """Create request dict to be passed to SmartProtocol.query()."""
        if isinstance(smart_request, list):
            request = {}
            for sr in smart_request:
                request[sr.method_name] = sr.params
        else:
            request = smart_request.to_dict()
        return request


def get_component_requests(component_id, ver_code):
    """Get the requests supported by the component and version."""
    if (cr := COMPONENT_REQUESTS.get(component_id)) is None:
        return None
    if callable(cr):
        return SmartRequest._create_request_dict(cr(ver_code))
    return SmartRequest._create_request_dict(cr)


COMPONENT_REQUESTS = {
    "device": SmartRequest.device_info_list,
    "firmware": SmartRequest.firmware_info_list(),
    "quick_setup": [SmartRequest.qs_component_nego()],
    "inherit": [SmartRequest.get_raw_request("get_inherit_info")],
    "time": [SmartRequest.get_device_time()],
    "wireless": [SmartRequest.get_wireless_scan_info()],
    "schedule": SmartRequest.schedule_info_list(),
    "countdown": [SmartRequest.get_countdown_rules()],
    "antitheft": [SmartRequest.get_antitheft_rules()],
    "account": [],
    "synchronize": [],  # sync_env
    "sunrise_sunset": [],  # for schedules
    "led": [SmartRequest.get_led_info()],
    "cloud_connect": [SmartRequest.get_raw_request("get_connect_cloud_state")],
    "iot_cloud": [],
    "device_local_time": [],
    "default_states": [],  # in device_info
    "auto_off": [SmartRequest.get_auto_off_config()],
    "localSmart": [],
    "energy_monitoring": SmartRequest.energy_monitoring_list(),
    "power_protection": SmartRequest.power_protection_list(),
    "current_protection": [],  # overcurrent in device_info
    "matter": [SmartRequest.get_raw_request("get_matter_setup_info")],
    "preset": [SmartRequest.get_preset_rules()],
    "brightness": [],  # in device_info
    "color": [],  # in device_info
    "color_temperature": [],  # in device_info
    "auto_light": [SmartRequest.get_auto_light_info()],
    "light_effect": [SmartRequest.get_dynamic_light_effect_rules()],
    "bulb_quick_control": [],
    "on_off_gradually": [SmartRequest.get_on_off_gradually_info()],
    "light_strip": [],
    "light_strip_lighting_effect": [
        SmartRequest.get_raw_request("get_lighting_effect")
    ],
    "music_rhythm": [],  # music_rhythm_enable in device_info
    "segment": [SmartRequest.get_raw_request("get_device_segment")],
    "segment_effect": [SmartRequest.get_raw_request("get_segment_effect_rule")],
    "device_load": [SmartRequest.get_raw_request("get_device_load_info")],
    "child_quick_setup": [
        SmartRequest.get_raw_request("get_support_child_device_category")
    ],
    "alarm": [
        SmartRequest.get_raw_request("get_support_alarm_type_list"),
        SmartRequest.get_raw_request("get_alarm_configure"),
    ],
    "alarm_logs": [SmartRequest.get_raw_request("get_alarm_triggers")],
    "trigger_log": [
        SmartRequest.get_raw_request(
            "get_trigger_logs", SmartRequest.GetTriggerLogsParams()
        )
    ],
    "temp_humidity_record": [SmartRequest.get_raw_request("get_temp_humidity_records")],
    "double_click": [SmartRequest.get_raw_request("get_double_click_info")],
    "child_device": [
        SmartRequest.get_raw_request("get_child_device_list"),
        SmartRequest.get_raw_request("get_child_device_component_list"),
    ],
    "control_child": [],
    "homekit": [SmartRequest.get_raw_request("get_homekit_info")],
    "dimmer_calibration": SmartRequest.get_dimmer_calibration(),
    "fan_control": [],
    "overheat_protection": [],
    # Vacuum components
    "clean": [
        SmartRequest.get_raw_request("getCarpetClean"),
        SmartRequest.get_raw_request("getCleanRecords"),
        SmartRequest.get_raw_request("getVacStatus"),
        SmartRequest.get_raw_request("getAreaUnit"),
        SmartRequest.get_raw_request("getCleanInfo"),
        SmartRequest.get_raw_request("getCleanStatus"),
        SmartRequest("getCleanAttr", SmartRequest.GetCleanAttrParams()),
    ],
    "battery": [SmartRequest.get_raw_request("getBatteryInfo")],
    "consumables": [SmartRequest.get_raw_request("getConsumablesInfo")],
    "direction_control": [],
    "button_and_led": [SmartRequest.get_raw_request("getChildLockInfo")],
    "speaker": [
        SmartRequest.get_raw_request("getSupportVoiceLanguage"),
        SmartRequest.get_raw_request("getCurrentVoiceLanguage"),
        SmartRequest.get_raw_request("getVolume"),
    ],
    "map": [
        SmartRequest.get_raw_request("getMapInfo"),
        SmartRequest.get_raw_request("getMapData"),
    ],
    "auto_change_map": [SmartRequest.get_raw_request("getAutoChangeMap")],
    "dust_bucket": [
        SmartRequest.get_raw_request("getAutoDustCollection"),
        SmartRequest.get_raw_request("getDustCollectionInfo"),
    ],
    "mop": [SmartRequest.get_raw_request("getMopState")],
    "do_not_disturb": [SmartRequest.get_raw_request("getDoNotDisturb")],
    "charge_pose_clean": [],
    "continue_breakpoint_sweep": [],
    "goto_point": [],
}
