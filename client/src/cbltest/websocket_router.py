import json
import socket
import webbrowser
from asyncio import Future, Semaphore, wait_for
from typing import cast
from urllib.parse import urlencode

import netifaces
from aiohttp import web

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_error, cbl_info


class WebSocketRouter:
    def __init__(self, server_urls: list[str]) -> None:
        self.__app = web.Application()
        self.__app.router.add_get("/", self._websocket_handler)
        self.__pending: dict[int, Future] = {}
        self.__server_urls = server_urls
        self.__conn_sem = Semaphore(0)
        self.__connections: dict[str, web.WebSocketResponse] = {}
        self.__runner = web.AppRunner(self.__app)
        self.__stopping = False

    async def start(self) -> None:
        self.__stopping = False
        await self.__runner.setup()
        site = web.TCPSite(self.__runner, port=10000)
        await site.start()

        for url in self.__server_urls:
            local_ip = self._lookup_ip(url)
            cbl_info(f"Connecting to test server at {url}...")
            params = {
                "tdkURL": f"ws://{local_ip}:10000",
                "autostart": "true",
                "device": "foo",
            }
            query = urlencode(params)
            timeout = 30
            if CBLPyTestGlobal.auto_start_tdk_page:
                webbrowser.open_new_tab(f"{url}/tdk.html?{query}")
                timeout = 10

            await wait_for(self.__conn_sem.acquire(), timeout=timeout)
            cbl_info(f"Connected to test server at {url}!")

    async def stop(self) -> None:
        self.__stopping = True

        for ws in list(self.__connections.values()):
            if not ws.closed:
                try:
                    await ws.close(code=1001, message=b"Server shutting down")
                except Exception:
                    pass

        if self.__runner:
            await self.__runner.cleanup()

        for fut in self.__pending.values():
            if not fut.done():
                fut.set_exception(
                    RuntimeError("WebSocket router stopped before response received")
                )

        self.__pending.clear()

    def get_websocket_for_write(self, url: str) -> web.WebSocketResponse:
        if not self.is_known_ws_url(url):
            raise IndexError(f"No WebSocket connection for the given URL ({url})")

        return self.__connections[url]

    def is_known_ws_url(self, url: str) -> bool:
        return url in self.__connections

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(
            protocols=request.headers.getall("Sec-WebSocket-Protocol", [])
        )
        await ws.prepare(request)

        peer = (
            request.transport.get_extra_info("peername") if request.transport else None
        )
        if peer is not None:
            remote_ip = peer[0]
        else:
            remote_ip = request.remote or "unknown"

        if remote_ip == "127.0.0.1" or remote_ip == "::1":
            remote_ip = "localhost"

        cbl_info(f"WebSocket connection established from {remote_ip}")
        self.__connections[f"http://{remote_ip}:5173"] = ws
        self.__conn_sem.release()

        async for msg in ws:
            if self.__stopping:
                break

            if msg.type == web.WSMsgType.TEXT:
                data = cast(dict, json.loads(msg.data))
                ts_id = data.get("ts_id")
                if ts_id is not None and ts_id in self.__pending:
                    future = self.__pending.pop(ts_id)
                    future.set_result(data)
            elif msg.type == web.WSMsgType.ERROR:
                cbl_error(
                    f"WebSocket connection closed with exception {ws.exception()}"
                )

        return ws

    def register(self, ts_id: int) -> Future[dict]:
        future: Future[dict] = Future()
        self.__pending[ts_id] = future
        return future

    def _lookup_ip(self, remote_url: str) -> str:
        if "localhost" in remote_url:
            return "localhost"

        for interface in netifaces.interfaces():
            if interface == "lo":
                continue

            addr = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addr:
                if "addr" not in addr[netifaces.AF_INET][0]:
                    continue

                ip = addr[netifaces.AF_INET][0]["addr"]
                if ip.startswith("169.254"):
                    continue

                if not WebSocketRouter._reachable(
                    ip, remote_url.split("/")[2].split(":")[0], 5173
                ):
                    continue

                return ip

        raise RuntimeError("No valid network interface found!")

    @staticmethod
    def _reachable(
        local_ip: str, remote_host: str, remote_port: int, timeout: float = 0.5
    ) -> bool:
        """Bind to local_ip and attempt a TCP connect; returns True if succeeds or gets a
        connection refused (host reachable), False on timeout / network unreachable."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.bind((local_ip, 0))
                s.connect((remote_host, remote_port))
                return True
        except ConnectionRefusedError:
            return True
        except OSError:
            return False
