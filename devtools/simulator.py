"""Minimalistic, fixture-powered device simulator."""

import asyncio
import json
import logging
import ssl

import asyncclick as click

from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads

_LOGGER = logging.getLogger(__name__)

HDR = b"\x02\x00\x00\x01\x01\xe5\x11\x00"
RESP_HDR = bytearray(16)


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """Simplified discovery protocol implementation."""

    def __init__(self, fixture):
        self.disco_data = fixture

    def connection_made(self, transport):
        """Set transport and log incoming connections."""
        peer = transport.get_extra_info("peername")
        _LOGGER.info("[UDP] Connection from %s", peer)
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        """Respond to discovery requests."""
        _LOGGER.info("[UDP] %s << %s", addr, data)
        if not data.startswith(HDR):
            _LOGGER.debug("[UDP] Unexpected datagram from %s: %r", addr, data)

        resp_data = {"error_code": 0, "result": self.disco_data}
        resp = json_dumps(resp_data).encode()
        _LOGGER.info("[UDP] %s >> %s", addr, resp)
        self.transport.sendto(RESP_HDR + resp, addr)


class AppProtocol(asyncio.Protocol):
    """App protocol implementation."""

    def connection_made(self, transport):
        """Set the transport on incoming connections."""
        peer = transport.get_extra_info("peername")
        _LOGGER.info("[APP] Connection from %s", peer)
        self.transport = transport

    def data_received(self, data: bytes):
        """Handle received requests."""
        message = data
        _LOGGER.info("[APP] << %r", message)

        resp = {"error_code": 0}

        _LOGGER.info("[APP] >> %r", resp)
        self.transport.write(json.dumps(resp).encode())

        # TODO: don't close after response?
        self.transport.close()


async def serve_udp(port, discovery_data):
    """Serve discovery protocol."""
    loop = asyncio.get_event_loop()
    _LOGGER.info("Serving discovery on port %s", port)
    await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(discovery_data),
        local_addr=("0.0.0.0", port),  # noqa: S104
    )
    while True:
        await asyncio.sleep(5)


async def serve_tcp(port):
    """Serve app communications protocol."""
    _LOGGER.info("Serving app on port %s", port)
    loop = asyncio.get_event_loop()

    # TODO: These settings are not enough to let openssl nor kasa cli to connect
    #       ssl.SSLError: [SSL: NO_SHARED_CIPHER] no shared cipher (_ssl.c:1000)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("ALL:@SECLEVEL=0")
    ctx.minimum_version = ssl.TLSVersion.TLSv1

    server = await loop.create_server(AppProtocol, host="0.0.0.0", port=port, ssl=ctx)  # noqa: S104
    async with server:
        await server.serve_forever()


@click.command()
@click.argument("fixture", type=click.File())
async def main(fixture):
    """Minimalistic, fixture-powered device simulator."""
    fixture_data = json_loads(fixture.read())
    disco_data = fixture_data["discovery_result"]
    _LOGGER.info(
        "Starting for %s (%s)", disco_data["device_model"], disco_data["device_type"]
    )

    async with asyncio.TaskGroup() as tg:
        tg.create_task(serve_udp(discovery_data=disco_data, port=20002))
        tg.create_task(serve_tcp(port=4433))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
