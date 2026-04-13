import asyncio
import json
import os
import socket
import sys
import time
import webbrowser
from asyncio import Future, Semaphore, wait_for
from typing import cast
from urllib.parse import urlencode, urlparse

import netifaces
from aiohttp import web

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_error, cbl_info, cbl_warning


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
        if len(self.__server_urls) == 0:
            cbl_info("No WS test servers to connect to; skipping router start")
            return

        self.__stopping = False
        await self.__runner.setup()

        # For ws:// URLs, bind to the port from the first URL so that
        # native apps (e.g. React Native) can connect to a known port.
        # For browser-based servers the random port is communicated via
        # the tdkURL query parameter, so a random port works fine.
        bind_port = 0
        first_url = self.__server_urls[0]
        parsed = urlparse(first_url)
        if parsed.scheme == "ws" and parsed.port:
            bind_port = parsed.port

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", bind_port))
        sock.listen(128)
        site = web.SockSite(self.__runner, sock)
        chosen_port = sock.getsockname()[1]
        await site.start()
        print(
            f"[cbltest] WebSocket router listening on port {chosen_port}", flush=True
        )
        cbl_info(f"WebSocket router listening on port {chosen_port}")

        # If a relaunch script is configured, run it now — the port is bound
        # and the server is ready to accept connections.  Launching native WS
        # apps (e.g. React Native) here guarantees their very first connection
        # attempt hits a listening port, instead of getting ECONNREFUSED and
        # relying on a retry window that may expire before pytest starts.
        relaunch_script = os.environ.get("CBL_NATIVE_WS_RELAUNCH_SCRIPT")
        has_native_ws = any(urlparse(u).scheme == "ws" for u in self.__server_urls)
        if has_native_ws and not relaunch_script:
            print(
                "[cbltest] WARNING: native WS test server detected but "
                "CBL_NATIVE_WS_RELAUNCH_SCRIPT is not set; "
                "relying on the app's built-in reconnect logic",
                flush=True,
            )
            cbl_warning(
                "Native WS test server detected but CBL_NATIVE_WS_RELAUNCH_SCRIPT "
                "is not set; relying on the app's built-in reconnect logic"
            )
        if relaunch_script:
            print(
                f"[cbltest] Relaunching native WS app via: {relaunch_script}",
                flush=True,
            )
            cbl_info(f"Relaunching native WS app via: {relaunch_script}")
            # Use asyncio subprocess so the event loop stays responsive while
            # the relaunch script runs (captures stdout/stderr for diagnostics).
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                relaunch_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            if stdout_bytes:
                print(
                    f"[cbltest] relaunch stdout:\n{stdout_bytes.decode(errors='replace')}",
                    flush=True,
                )
            if proc.returncode != 0:
                err_text = stderr_bytes.decode(errors="replace")
                print(
                    f"[cbltest] ERROR: relaunch script failed (exit {proc.returncode}):\n{err_text}",
                    flush=True,
                )
                raise RuntimeError(
                    f"Native WS relaunch script exited with code {proc.returncode}:\n{err_text}"
                )
            print("[cbltest] Native WS app relaunch complete", flush=True)
            cbl_info("Native WS app relaunch complete")

        ws_index = 0
        for url in self.__server_urls:
            local_ip = self._lookup_ip(url)
            cbl_info(f"Connecting to test server at {url}...")
            print(f"[cbltest] Waiting for test server to connect at {url}…", flush=True)
            params = {
                "tdkURL": f"ws://{local_ip}:{chosen_port}/",
                "autostart": "true",
                "device": f"ws{ws_index}",
            }
            query = urlencode(params)
            parsed_url = urlparse(url)
            is_native_ws = parsed_url.scheme == "ws"
            # Native WS apps (React Native) are (re)launched by the relaunch
            # hook above, right after this port was bound, so they should
            # connect quickly.  90 s gives ample margin for app startup.
            timeout = 90 if is_native_ws else 30
            if not is_native_ws and CBLPyTestGlobal.auto_start_tdk_page:
                webbrowser.open_new_tab(f"{url}/tdk.html?{query}")
                timeout = 10

            t0 = time.monotonic()
            try:
                await self._wait_for_connection(timeout)
            except TimeoutError:
                elapsed = time.monotonic() - t0
                print(
                    f"[cbltest] TIMEOUT: no connection from {url} after {elapsed:.1f}s "
                    f"(limit={timeout}s)",
                    flush=True,
                )
                raise
            elapsed = time.monotonic() - t0
            print(f"[cbltest] Test server connected at {url} (took {elapsed:.1f}s)", flush=True)
            cbl_info(f"Connected to test server at {url}!")

    async def _wait_for_connection(self, timeout: float) -> None:
        """Acquire the connection semaphore, printing a heartbeat every 10 s."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            chunk = min(10.0, remaining)
            try:
                await wait_for(self.__conn_sem.acquire(), timeout=chunk)
                return
            except TimeoutError:
                elapsed = timeout - (deadline - time.monotonic())
                print(
                    f"[cbltest] … still waiting for app to connect "
                    f"({elapsed:.0f}s elapsed, {timeout - elapsed:.0f}s remaining)",
                    flush=True,
                )

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

        async for msg in ws:
            if self.__stopping:
                break

            if msg.type == web.WSMsgType.TEXT:
                data = cast(dict, json.loads(msg.data))
                ts_id = data.get("ts_id")
                if ts_id is not None and ts_id in self.__pending:
                    future = self.__pending.pop(ts_id)
                    future.set_result(data)
                else:
                    device = data.get("device")
                    if device is not None:
                        try:
                            url_index = int(device[2:])
                            self.__connections[self.__server_urls[url_index]] = ws
                            self.__conn_sem.release()
                        except (ValueError, IndexError):
                            cbl_error(
                                f"Unknown or invalid device ID received: {device}"
                            )
                            await ws.close(message=b"Unknown or invalid device ID")
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
