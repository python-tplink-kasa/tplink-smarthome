"""Implementation of motion detection module."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Callable, Iterable
from datetime import timedelta

import onvif  # type: ignore[import-untyped]
from aiohttp import web
from onvif.managers import NotificationManager  # type: ignore[import-untyped]

from ...credentials import Credentials
from ...eventtype import EventType
from ...exceptions import KasaException
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

DEFAULT_LISTEN_PORT = 28002


TOPIC_EVENT_TYPE = {
    "tns1:RuleEngine/CellMotionDetector/Motion": EventType.MOTION_DETECTED,
    "tns1:RuleEngine/CellMotionDetector/People": EventType.PERSON_DETECTED,
    "tns1:RuleEngine/TamperDetector/Tamper": EventType.TAMPER_DETECTED,
}


class OnvifListen(SmartCamModule):
    """Implementation of lens mask module."""

    manager: NotificationManager
    callback: Callable[[EventType], None]
    event_types: Iterable[EventType] | None
    listening = False
    site: web.TCPSite
    runner: web.AppRunner
    instance_id: str
    path: str
    _listening_address: str | None = None

    @property
    def listening_address(self) -> str | None:
        """Address the listener is receiving onvif notifications on.

        Or None if not listening.
        """
        return self._listening_address

    async def _invoke_callback(self, event: EventType) -> None:
        self.callback(event)

    async def _handle_event(self, request: web.Request) -> web.Response:
        content = await request.read()
        result = self.manager.process(content)
        for msg in result.NotificationMessage:
            _LOGGER.debug(
                "Received notification message for %s: %s",
                self._device.host,
                msg,
            )
            if (event := TOPIC_EVENT_TYPE.get(msg.Topic._value_1)) and (
                (not self.event_types or event in self.event_types)
                and (simple_items := msg.Message._value_1.Data.SimpleItem)
                and simple_items[0].Value == "true"
            ):
                asyncio.create_task(self._invoke_callback(event))
        return web.Response()

    async def listen(
        self,
        callback: Callable[[EventType], None],
        camera_credentials: Credentials,
        *,
        event_types: Iterable[EventType] | None = None,
        listen_ip: str | None = None,
        listen_port: int | None = None,
    ) -> None:
        """Start listening for events."""
        self.callback = callback
        self.event_types = event_types
        self.instance_id = str(uuid.uuid4())
        self.path = f"/{self._device.host}/{self.instance_id}/"

        if listen_port is None:
            listen_port = DEFAULT_LISTEN_PORT

        def subscription_lost() -> None:
            _LOGGER.debug("Notification subscription lost for %s", self._device.host)
            asyncio.create_task(self.stop())

        wsdl = f"{os.path.dirname(onvif.__file__)}/wsdl/"

        mycam = onvif.ONVIFCamera(
            self._device.host,
            2020,
            camera_credentials.username,
            camera_credentials.password,
            wsdl,
        )
        await mycam.update_xaddrs()

        host_port = await self._start_server(listen_ip, listen_port)

        self.manager = await mycam.create_notification_manager(
            address=host_port + self.path,
            interval=timedelta(minutes=10),
            subscription_lost_callback=subscription_lost,
        )

        self._listening_address = host_port
        self.listening = True
        _LOGGER.debug("Listener started for %s", self._device.host)

    async def stop(self) -> None:
        """Stop the listener."""
        if not self.listening:
            _LOGGER.debug("Listener for %s already stopped", self._device.host)
            return

        _LOGGER.debug("Stopping listener for %s", self._device.host)
        self.listening = False
        self._listening_address = None
        await self.site.stop()
        await self.runner.shutdown()

    async def _get_host_ip(self) -> str:
        def get_ip() -> str:
            #  From https://stackoverflow.com/a/28950776
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            try:
                # doesn't even have to be reachable
                s.connect(("10.254.254.254", 1))
                ip = s.getsockname()[0]
            finally:
                s.close()
            return ip

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, get_ip)

    async def _start_server(self, listen_ip: str | None, listen_port: int) -> str:
        app = web.Application()
        app.add_routes([web.post(self.path, self._handle_event)])

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        if not listen_ip:
            try:
                listen_ip = await self._get_host_ip()
            except Exception as ex:
                raise KasaException(
                    "Unable to determine listen ip starting "
                    f"listener for {self._device.host}",
                    ex,
                ) from ex

        self.site = web.TCPSite(self.runner, listen_ip, listen_port)
        try:
            await self.site.start()
        except Exception:
            _LOGGER.exception(
                "Error trying to start listener for %s: ", self._device.host
            )

        _LOGGER.debug(
            "Listen handler for %s running on %s:%s",
            self._device.host,
            listen_ip,
            listen_port,
        )

        return f"http://{listen_ip}:{listen_port}"
