import copy
import logging

from kasa.deviceconfig import DeviceConfig
from kasa.protocols import IotProtocol
from kasa.transports.basetransport import BaseTransport

_LOGGER = logging.getLogger(__name__)


def get_realtime(obj, x, *args):
    return {
        "current": 0.268587,
        "voltage": 125.836131,
        "power": 33.495623,
        "total": 0.199000,
    }


def get_monthstat(obj, x, *args):
    if x["year"] < 2016:
        return {"month_list": []}

    return {
        "month_list": [
            {"year": 2016, "month": 11, "energy": 1.089000},
            {"year": 2016, "month": 12, "energy": 1.582000},
        ]
    }


def get_daystat(obj, x, *args):
    if x["year"] < 2016:
        return {"day_list": []}

    return {
        "day_list": [
            {"year": 2016, "month": 11, "day": 24, "energy": 0.026000},
            {"year": 2016, "month": 11, "day": 25, "energy": 0.109000},
        ]
    }


emeter_support = {
    "get_realtime": get_realtime,
    "get_monthstat": get_monthstat,
    "get_daystat": get_daystat,
}


def get_realtime_units(obj, x, *args):
    return {"power_mw": 10800}


def get_monthstat_units(obj, x, *args):
    if x["year"] < 2016:
        return {"month_list": []}

    return {
        "month_list": [
            {"year": 2016, "month": 11, "energy_wh": 32},
            {"year": 2016, "month": 12, "energy_wh": 16},
        ]
    }


def get_daystat_units(obj, x, *args):
    if x["year"] < 2016:
        return {"day_list": []}

    return {
        "day_list": [
            {"year": 2016, "month": 11, "day": 24, "energy_wh": 20},
            {"year": 2016, "month": 11, "day": 25, "energy_wh": 32},
        ]
    }


emeter_units_support = {
    "get_realtime": get_realtime_units,
    "get_monthstat": get_monthstat_units,
    "get_daystat": get_daystat_units,
}


emeter_commands = {
    "emeter": emeter_support,
    "smartlife.iot.common.emeter": emeter_units_support,
}


def error(msg="default msg"):
    return {"err_code": -1323, "msg": msg}


def success(res):
    if res:
        res.update({"err_code": 0})
    else:
        res = {"err_code": 0}
    return res


# plugs and bulbs use a different module for time information,
# so we define the contents here to avoid repeating ourselves
TIME_MODULE = {
    "get_time": {
        "year": 2017,
        "month": 1,
        "mday": 2,
        "hour": 3,
        "min": 4,
        "sec": 5,
    },
    "get_timezone": {
        "zone_str": "test",
        "dst_offset": -1,
        "index": 12,
        "tz_str": "test2",
    },
}

CLOUD_MODULE = {
    "get_info": {
        "username": "",
        "server": "devs.tplinkcloud.com",
        "binded": 0,
        "err_code": 0,
        "cld_connection": 0,
        "illegalType": -1,
        "stopConnect": -1,
        "tcspStatus": -1,
        "fwDlPage": "",
        "tcspInfo": "",
        "fwNotifyType": 0,
    }
}

SCHEDULE_MODULE = {
    "get_next_action": {
        "action": 1,
        "err_code": 0,
        "id": "0794F4729DB271627D1CF35A9A854030",
        "schd_time": 68927,
        "type": 2,
    },
    "get_rules": {
        "enable": 1,
        "err_code": 0,
        "rule_list": [
            {
                "eact": -1,
                "enable": 1,
                "id": "8AA75A50A8440B17941D192BD9E01FFA",
                "name": "name",
                "repeat": 1,
                "sact": 1,
                "smin": 1027,
                "soffset": 0,
                "stime_opt": 2,
                "wday": [1, 1, 1, 1, 1, 1, 1],
            },
        ],
        "version": 2,
    },
}

AMBIENT_MODULE = {
    "get_current_brt": {"value": 26, "err_code": 0},
    "get_config": {
        "devs": [
            {
                "hw_id": 0,
                "enable": 0,
                "dark_index": 1,
                "min_adc": 0,
                "max_adc": 2450,
                "level_array": [
                    {"name": "cloudy", "adc": 490, "value": 20},
                    {"name": "overcast", "adc": 294, "value": 12},
                    {"name": "dawn", "adc": 222, "value": 9},
                    {"name": "twilight", "adc": 222, "value": 9},
                    {"name": "total darkness", "adc": 111, "value": 4},
                    {"name": "custom", "adc": 2400, "value": 97},
                ],
            }
        ],
        "ver": "1.0",
        "err_code": 0,
    },
}


MOTION_MODULE = {
    "get_config": {
        "enable": 0,
        "version": "1.0",
        "trigger_index": 2,
        "cold_time": 60000,
        "min_adc": 0,
        "max_adc": 4095,
        "array": [80, 50, 20, 0],
        "err_code": 0,
    }
}

LIGHT_DETAILS = {
    "color_rendering_index": 80,
    "err_code": 0,
    "incandescent_equivalent": 60,
    "lamp_beam_angle": 150,
    "max_lumens": 800,
    "max_voltage": 120,
    "min_voltage": 110,
    "wattage": 10,
}

DEFAULT_BEHAVIOR = {
    "err_code": 0,
    "hard_on": {"mode": "circadian"},
    "soft_on": {"mode": "last_status"},
}


class FakeIotProtocol(IotProtocol):
    def __init__(self, info, fixture_name=None, *, verbatim=False):
        super().__init__(
            transport=FakeIotTransport(info, fixture_name, verbatim=verbatim),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so tests can still patch IotProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeIotTransport(BaseTransport):
    def __init__(self, info, fixture_name=None, *, verbatim=False):
        super().__init__(config=DeviceConfig("127.0.0.123"))
        info = copy.deepcopy(info)
        self.discovery_data = info
        self.fixture_name = fixture_name
        self.writer = None
        self.reader = None
        self.verbatim = verbatim

        # When True verbatim will bypass any extra processing of missing
        # methods and is used to test the fixture creation itself.
        if verbatim:
            self.proto = copy.deepcopy(info)
        else:
            self.proto = self._build_fake_proto(info)

    @staticmethod
    def _build_fake_proto(info):
        """Create an internal protocol with extra data not in the fixture."""
        proto = copy.deepcopy(FakeIotTransport.baseproto)

        for target in info:
            if target != "discovery_result":
                for cmd in info[target]:
                    # Use setdefault in case the fixture has modules not yet
                    # part of the baseproto.
                    proto.setdefault(target, {})[cmd] = info[target][cmd]

        # if we have emeter support, we need to add the missing pieces
        for module in ["emeter", "smartlife.iot.common.emeter"]:
            if (
                module in info
                and "err_code" in info[module]
                and info[module]["err_code"] != 0
            ):
                proto[module] = info[module]
            else:
                for etype in ["get_realtime", "get_daystat", "get_monthstat"]:
                    if (
                        module in info and etype in info[module]
                    ):  # if the fixture has the data, use it
                        # print("got %s %s from fixture: %s" % (module, etype, info[module][etype]))
                        proto[module][etype] = info[module][etype]
                    else:  # otherwise fall back to the static one
                        dummy_data = emeter_commands[module][etype]
                        # print("got %s %s from dummy: %s" % (module, etype, dummy_data))
                        proto[module][etype] = dummy_data
        return proto

    @property
    def default_port(self) -> int:
        return 9999

    @property
    def credentials_hash(self) -> None:
        return None

    def set_alias(self, x, child_ids=None):
        if child_ids is None:
            child_ids = []
        _LOGGER.debug("Setting alias to %s, child_ids: %s", x["alias"], child_ids)
        if child_ids:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                if child["id"] in child_ids:
                    child["alias"] = x["alias"]
        else:
            self.proto["system"]["get_sysinfo"]["alias"] = x["alias"]

    def set_relay_state(self, x, child_ids=None):
        if child_ids is None:
            child_ids = []
        _LOGGER.debug("Setting relay state to %s", x["state"])

        _LOGGER.info("child_ids: %s", child_ids)
        if child_ids:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                if child["id"] in child_ids:
                    _LOGGER.info("Found %s, turning to %s", child, x["state"])
                    child["state"] = x["state"]
        else:
            self.proto["system"]["get_sysinfo"]["relay_state"] = x["state"]

    def set_led_off(self, x, *args):
        _LOGGER.debug("Setting led off to %s", x)
        self.proto["system"]["get_sysinfo"]["led_off"] = x["off"]

    def set_mac(self, x, *args):
        _LOGGER.debug("Setting mac to %s", x)
        self.proto["system"]["get_sysinfo"]["mac"] = x["mac"]

    def set_hs220_brightness(self, x, *args):
        _LOGGER.debug("Setting brightness to %s", x)
        self.proto["system"]["get_sysinfo"]["brightness"] = x["brightness"]

    def set_hs220_dimmer_transition(self, x, *args):
        _LOGGER.debug("Setting dimmer transition to %s", x)
        brightness = x["brightness"]
        if brightness == 0:
            self.proto["system"]["get_sysinfo"]["relay_state"] = 0
        else:
            self.proto["system"]["get_sysinfo"]["relay_state"] = 1
            self.proto["system"]["get_sysinfo"]["brightness"] = x["brightness"]

    def set_lighting_effect(self, effect, *args):
        _LOGGER.debug("Setting light effect to %s", effect)
        self.proto["system"]["get_sysinfo"]["lighting_effect_state"] = dict(effect)

    def transition_light_state(self, state_changes, *args):
        # Setting the light state on a device will turn off any active lighting effects.
        # Unless it's just the brightness in which case it will update the brightness for
        # the lighting effect
        if lighting_effect_state := self.proto["system"]["get_sysinfo"].get(
            "lighting_effect_state"
        ):
            if (
                "hue" in state_changes
                or "saturation" in state_changes
                or "color_temp" in state_changes
            ):
                lighting_effect_state["enable"] = 0
            elif (
                lighting_effect_state["enable"] == 1
                and state_changes.get("on_off") != 0
                and (brightness := state_changes.get("brightness"))
            ):
                lighting_effect_state["brightness"] = brightness
                return

        _LOGGER.debug("Setting light state to %s", state_changes)
        light_state = self.proto["system"]["get_sysinfo"]["light_state"]

        _LOGGER.debug("Current light state: %s", light_state)
        new_state = light_state

        # turn on requested, if we were off, use the dft_on_state as a base
        if state_changes["on_off"] == 1 and not light_state["on_off"]:
            _LOGGER.debug("Bulb was off, using dft_on_state")
            new_state = light_state["dft_on_state"]

        # override the existing settings
        new_state.update(state_changes)

        if (
            not state_changes["on_off"] and "dft_on_state" not in light_state
        ):  # if not already off, pack the data inside dft_on_state
            _LOGGER.debug(
                "Bulb was on and turn_off was requested, saving to dft_on_state"
            )
            new_state = {"dft_on_state": light_state, "on_off": 0}

        _LOGGER.debug("New light state: %s", new_state)
        self.proto["system"]["get_sysinfo"]["light_state"] = new_state

    def set_preferred_state(self, new_state, *args):
        """Implement set_preferred_state."""
        self.proto["system"]["get_sysinfo"]["preferred_state"][new_state["index"]] = (
            new_state
        )

    def light_state(self, x, *args):
        light_state = self.proto["system"]["get_sysinfo"]["light_state"]
        # Our tests have light state off, so we simply return the dft_on_state when device is on.
        _LOGGER.debug("reporting light state: %s", light_state)
        # TODO: hack to go around KL430 fixture differences
        if light_state["on_off"] and "dft_on_state" in light_state:
            return light_state["dft_on_state"]
        else:
            return light_state

    def set_time(self, new_state: dict, *args):
        """Implement set_time."""
        mods = [
            v
            for k, v in self.proto.items()
            if k in {"time", "smartlife.iot.common.timesetting"}
        ]
        index = new_state.pop("index", None)
        for mod in mods:
            mod["get_time"] = new_state
            if index is not None:
                mod["get_timezone"]["index"] = index

    baseproto = {
        "system": {
            "set_relay_state": set_relay_state,
            "set_dev_alias": set_alias,
            "set_led_off": set_led_off,
            "get_dev_icon": {"icon": None, "hash": None},
            "set_mac_addr": set_mac,
            "get_sysinfo": None,
        },
        "emeter": {
            "get_realtime": None,
            "get_daystat": None,
            "get_monthstat": None,
            "erase_emeter_state": None,
        },
        "smartlife.iot.common.emeter": {
            "get_realtime": None,
            "get_daystat": None,
            "get_monthstat": None,
            "erase_emeter_state": None,
        },
        "smartlife.iot.smartbulb.lightingservice": {
            "get_light_state": light_state,
            "get_light_details": LIGHT_DETAILS,
            "get_default_behavior": DEFAULT_BEHAVIOR,
            "transition_light_state": transition_light_state,
            "set_preferred_state": set_preferred_state,
        },
        "smartlife.iot.lighting_effect": {
            "set_lighting_effect": set_lighting_effect,
        },
        # lightstrip follows the same payloads but uses different module & method
        "smartlife.iot.lightStrip": {
            "set_light_state": transition_light_state,
            "get_light_state": light_state,
            "get_light_details": LIGHT_DETAILS,
            "get_default_behavior": DEFAULT_BEHAVIOR,
            "set_preferred_state": set_preferred_state,
        },
        "smartlife.iot.common.system": {
            "set_dev_alias": set_alias,
        },
        "time": {**TIME_MODULE, "set_time": set_time, "set_timezone": set_time},
        "smartlife.iot.common.timesetting": {
            **TIME_MODULE,
            "set_time": set_time,
            "set_timezone": set_time,
        },
        # HS220 brightness, different setter and getter
        "smartlife.iot.dimmer": {
            "set_brightness": set_hs220_brightness,
            "set_dimmer_transition": set_hs220_dimmer_transition,
        },
        "smartlife.iot.LAS": AMBIENT_MODULE,
        "smartlife.iot.PIR": MOTION_MODULE,
        "cnCloud": CLOUD_MODULE,
        "smartlife.iot.common.cloud": CLOUD_MODULE,
        "schedule": SCHEDULE_MODULE,
        "smartlife.iot.common.schedule": SCHEDULE_MODULE,
    }

    async def send(self, request, port=9999):
        if not self.verbatim:
            return await self._send(request, port)

        # Simply return whatever is in the fixture
        response = {}
        for target in request:
            if target in self.proto:
                response.update({target: self.proto[target]})
            else:
                response.update({"err_msg": "module not support"})
        return copy.deepcopy(response)

    async def _send(self, request, port=9999):
        proto = self.proto
        # collect child ids from context
        try:
            child_ids = request["context"]["child_ids"]
            request.pop("context", None)
        except KeyError:
            child_ids = []

        def get_response_for_module(target):
            if target not in proto:
                return error(msg="target not found")
            if "err_code" in proto[target] and proto[target]["err_code"] != 0:
                return {target: proto[target]}

            def get_response_for_command(cmd):
                if cmd not in proto[target]:
                    return error(msg=f"command {cmd} not found")

                params = request[target][cmd]
                _LOGGER.debug(
                    "Going to execute %s.%s (params: %s).. ", target, cmd, params
                )

                if callable(proto[target][cmd]):
                    res = proto[target][cmd](self, params, child_ids)
                    _LOGGER.debug("[callable] %s.%s: %s", target, cmd, res)
                    return success(res)
                elif isinstance(proto[target][cmd], dict):
                    res = proto[target][cmd]
                    _LOGGER.debug("[static] %s.%s: %s", target, cmd, res)
                    return success(res)
                else:
                    raise NotImplementedError(f"target {target} cmd {cmd}")

            from collections import defaultdict

            cmd_responses = defaultdict(dict)
            for cmd in request[target]:
                cmd_responses[target][cmd] = get_response_for_command(cmd)

            return cmd_responses

        response = {}
        for target in request:
            response.update(get_response_for_module(target))

        return copy.deepcopy(response)

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
