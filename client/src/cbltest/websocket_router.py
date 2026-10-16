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
        self.__connected_events: dict[str, asyncio.Event] = {url: asyncio.Event() for url in server_urls}
        self.__reconnect_lock = asyncio.Lock()

    async def start(self) -> None:
        if len(self.__server_urls) == 0:
            cbl_info("No WS test servers to connect to; skipping router start")
            return

        self.__stopping = False
        await self.__runner.setup()

        # Native WebSocket test servers (ws:// URLs, e.g. React Native) connect back to a
        # fixed port given in their URL. Otherwise let the OS choose one.
        bind_port = next(
            (urlparse(u).port or 0 for u in self.__server_urls if urlparse(u).scheme == "ws"),
            0,
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", bind_port))
        sock.listen(128)
        site = web.SockSite(self.__runner, sock)
        chosen_port = sock.getsockname()[1]
        await site.start()
        cbl_info(f"WebSocket router listening on port {chosen_port}")

        relaunch_script = os.environ.get("CBL_NATIVE_WS_RELAUNCH_SCRIPT")
        has_native_ws = any(urlparse(u).scheme == "ws" for u in self.__server_urls)
        if has_native_ws and not relaunch_script:
            cbl_warning(
                "Native WS test server detected but CBL_NATIVE_WS_RELAUNCH_SCRIPT "
                "is not set; relying on the app's built-in reconnect logic"
            )
        if relaunch_script:
            cbl_info(f"Relaunching native WS app via: {relaunch_script}")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                relaunch_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            if stdout_bytes:
                cbl_info(f"Relaunch script output:\n{stdout_bytes.decode(errors='replace')}")
            if proc.returncode != 0:
                err_text = stderr_bytes.decode(errors="replace")
                raise RuntimeError(f"Native WS relaunch script exited with code {proc.returncode}:\n{err_text}")
            cbl_info("Native WS app relaunch complete")

        for ws_index, url in enumerate(self.__server_urls):
            local_ip = self._lookup_ip(url)
            cbl_info(f"Connecting to test server at {url}...")
            params = {
                "tdkURL": f"ws://{local_ip}:{chosen_port}/",
                "autostart": "true",
                "device": f"ws{ws_index}",
            }
            query = urlencode(params)
            parsed_url = urlparse(url)
            is_native_ws = parsed_url.scheme == "ws"
            timeout = 90 if is_native_ws else 30
            if not is_native_ws and CBLPyTestGlobal.auto_start_tdk_page:
                webbrowser.open_new_tab(f"{url}/tdk.html?{query}")

            t0 = time.monotonic()
            try:
                await self._wait_for_connection(timeout)
            except TimeoutError:
                cbl_error(f"No connection from {url} after {time.monotonic() - t0:.1f}s (limit {timeout}s)")
                raise
            cbl_info(f"Connected to test server at {url} (took {time.monotonic() - t0:.1f}s)")

    async def _wait_for_connection(self, timeout: float) -> None:
        """Acquire the connection semaphore, logging a heartbeat every 10 s."""
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
                cbl_info(
                    f"Still waiting for test server to connect ({elapsed:.0f}s elapsed, "
                    f"{timeout - elapsed:.0f}s remaining)"
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
                fut.set_exception(RuntimeError("WebSocket router stopped before response received"))

        self.__pending.clear()

    async def ensure_connected(self, url: str, timeout: float = 120.0) -> None:
        """Wait until a live WebSocket connection for *url* is available.

        Returns immediately if already connected; blocks while a reconnect
        is in progress.
        """
        event = self.__connected_events.get(url)
        if event is None or event.is_set():
            return
        cbl_info(f"Waiting up to {timeout:.0f}s for test server to reconnect at {url}")
        try:
            await wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            raise ConnectionError(f"Device at {url} did not reconnect within {timeout:.0f} s") from None

    def get_websocket_for_write(self, url: str) -> web.WebSocketResponse:
        if not self.is_known_ws_url(url):
            raise IndexError(f"No WebSocket connection for the given URL ({url})")

        return self.__connections[url]

    def is_known_ws_url(self, url: str) -> bool:
        return url in self.__connections

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=request.headers.getall("Sec-WebSocket-Protocol", []))
        await ws.prepare(request)

        current_url: str | None = None

        async for msg in ws:
            if self.__stopping:
                break

            if msg.type == web.WSMsgType.TEXT:
                data = cast(dict, json.loads(msg.data))
                ts_id = data.get("ts_id")
                if ts_id is not None and ts_id in self.__pending:
                    future = self.__pending.pop(ts_id)
                    if not future.done():
                        future.set_result(data)
                else:
                    device = data.get("device")
                    if device is not None:
                        try:
                            url_index = int(device[2:])
                            current_url = self.__server_urls[url_index]
                            self.__connections[current_url] = ws
                            self.__connected_events[current_url].set()
                            self.__conn_sem.release()
                        except (ValueError, IndexError):
                            cbl_error(f"Unknown or invalid device ID received: {device}")
                            await ws.close(message=b"Unknown or invalid device ID")
            elif msg.type == web.WSMsgType.ERROR:
                cbl_error(f"WebSocket connection closed with exception {ws.exception()}")

        # ── Connection closed ──────────────────────────────────────────────
        # Only act if this ws is still THE active connection for the URL.
        # begin_reconnect() may have already claimed ownership and scheduled
        # its own _close_and_reconnect, in which case we must not interfere
        # (especially: we must not clear the connected event after a
        # successful reconnect has already set it).
        if current_url is not None and not self.__stopping and self.__connections.get(current_url) is ws:
            cbl_warning(f"WebSocket connection from {current_url} dropped")

            del self.__connections[current_url]
            self.__connected_events[current_url].clear()

            self._fail_pending_futures(current_url)

            relaunch_script = os.environ.get("CBL_NATIVE_WS_RELAUNCH_SCRIPT")
            if relaunch_script:
                asyncio.ensure_future(self._reconnect(current_url, relaunch_script))

        return ws

    # ── Timeout-triggered reconnect (called from send()) ───────────────

    def unregister(self, ts_id: int) -> None:
        self.__pending.pop(ts_id, None)

    def begin_reconnect(self, url: str) -> None:
        """Mark *url* as disconnected and schedule WS close + app relaunch.

        This is called **synchronously** from send() after a per-request
        timeout.  Clearing the connected event HERE (before send() raises
        ConnectionError) guarantees the next test's ensure_connected() will
        wait for the reconnect to finish instead of hitting the stale WS.
        """
        self.__connected_events[url].clear()

        ws = self.__connections.pop(url, None)
        cbl_warning(f"Request timeout on {url}; closing the connection and relaunching the test server")

        self._fail_pending_futures(url)

        asyncio.ensure_future(self._close_and_reconnect(url, ws))

    def register(self, ts_id: int) -> Future[dict]:
        future: Future[dict] = Future()
        self.__pending[ts_id] = future
        return future

    # ── Internal helpers ───────────────────────────────────────────────

    def _fail_pending_futures(self, url: str) -> None:
        pending_ids = list(self.__pending.keys())
        if pending_ids:
            cbl_warning(f"Failing {len(pending_ids)} in-flight request(s) for {url}")
        for ts_id in pending_ids:
            fut = self.__pending.pop(ts_id)
            if not fut.done():
                fut.set_exception(ConnectionError(f"WebSocket connection to {url} lost while waiting for response"))

    async def _close_and_reconnect(self, url: str, ws: web.WebSocketResponse | None) -> None:
        """Close *ws* (if still open) and relaunch the native app."""
        if ws is not None and not ws.closed:
            try:
                await ws.close(
                    code=1011,
                    message=b"Request timed out forcing reconnect",
                )
            except Exception:
                pass

        relaunch_script = os.environ.get("CBL_NATIVE_WS_RELAUNCH_SCRIPT")
        if relaunch_script:
            await self._reconnect(url, relaunch_script)

    async def _reconnect(self, url: str, relaunch_script: str) -> None:
        """Re-launch the native app and wait for it to reconnect."""
        async with self.__reconnect_lock:
            if self.__connected_events[url].is_set():
                return

            cbl_info(f"Reconnecting {url}: running relaunch script")
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    relaunch_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await proc.communicate()
                if stdout_bytes:
                    cbl_info(f"Relaunch script output:\n{stdout_bytes.decode(errors='replace')}")
                if proc.returncode != 0:
                    err_text = stderr_bytes.decode(errors="replace")
                    cbl_error(f"Relaunch script failed (exit {proc.returncode}):\n{err_text}", include_stack=False)
                    return

                cbl_info(f"Test server relaunched; waiting up to 90s for it to reconnect at {url}")
                await wait_for(self.__connected_events[url].wait(), timeout=90)
                cbl_info(f"Test server reconnected at {url}")
            except TimeoutError:
                cbl_error(f"Test server at {url} did not reconnect within 90s after relaunch")
            except Exception as exc:
                cbl_error(f"Error during reconnect for {url}: {exc}")

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

                if not WebSocketRouter._reachable(ip, remote_url.split("/")[2].split(":")[0], 5173):
                    continue

                return ip

        raise RuntimeError("No valid network interface found!")

    @staticmethod
    def _reachable(local_ip: str, remote_host: str, remote_port: int, timeout: float = 0.5) -> bool:
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
