import json
import re
import socket
from asyncio import Future, Semaphore, wait_for
from contextlib import AsyncExitStack
from logging import FileHandler, Formatter, getLogger
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

import netifaces
from aiohttp import web
from playwright.async_api import Browser, ConsoleMessage, async_playwright

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_error, cbl_info, cbl_warning


def _format_console(msg: ConsoleMessage) -> str:
    """Applies console.log style substitutions to LogTape output, dropping the CSS that %c consumes"""
    args = [str(arg) for arg in msg.args]
    # LogTape's format string always starts with %c; other first arguments may not be strings
    if not args or not args[0].startswith("%c"):
        return msg.text

    remaining = iter(args[1:])

    def substitute(match: re.Match[str]) -> str:
        spec = match.group(1)
        if spec == "%":
            return "%"

        value = next(remaining, None)
        if value is None:
            return match.group(0)

        return "" if spec == "c" else value

    formatted = re.sub(r"%([%csdifoO])", substitute, args[0])
    return " ".join([formatted, *remaining])


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
        self.__browser_cleanup = AsyncExitStack()
        self.__browser_log_path = Path("browser_log")

    async def _open_tdk_page(self, browser: Browser, url: str, device: str, query: str) -> None:
        self.__browser_log_path.mkdir(exist_ok=True)
        handler = FileHandler(self.__browser_log_path / f"{device}.log", mode="w", encoding="utf-8")
        handler.setFormatter(Formatter("%(asctime)s %(message)s"))
        browser_log = getLogger(f"CBL.browser.{device}")
        browser_log.propagate = False
        browser_log.addHandler(handler)
        self.__browser_cleanup.callback(handler.close)
        self.__browser_cleanup.callback(browser_log.removeHandler, handler)

        def write_log(level: str, text: str) -> None:
            browser_log.info(f"[{level}] {text}")
            if level in ("error", "pageerror", "crash"):
                cbl_error(f"[{url}] {text}", include_stack=False)

        # A context per device keeps each test server's browser storage separate
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        page.on("console", lambda msg: write_log(msg.type, _format_console(msg)))
        page.on("pageerror", lambda err: write_log("pageerror", str(err)))
        page.on("crash", lambda _: write_log("crash", "TDK page crashed"))
        # The WebSocket connect timeout in start() decides success, not the page load
        await page.goto(f"{url}/tdk.html?{query}", wait_until="commit")

    async def start(self) -> None:
        if len(self.__server_urls) == 0:
            cbl_info("No WS test servers to connect to; skipping router start")
            return

        self.__stopping = False
        await self.__runner.setup()

        # Create a socket so that I can use an OS provided port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("", 0))
        sock.listen(128)
        site = web.SockSite(self.__runner, sock)
        chosen_port = sock.getsockname()[1]
        await site.start()

        try:
            browser: Browser | None = None
            if CBLPyTestGlobal.auto_start_tdk_page:
                playwright = await self.__browser_cleanup.enter_async_context(async_playwright())
                browser = await playwright.chromium.launch()
                self.__browser_cleanup.push_async_callback(browser.close)

            for ws_index, url in enumerate(self.__server_urls):
                local_ip = self._lookup_ip(url)
                cbl_info(f"Connecting to test server at {url}...")
                params = {
                    "tdkURL": f"ws://{local_ip}:{chosen_port}/",
                    "autostart": "true",
                    "device": f"ws{ws_index}",
                }
                query = urlencode(params)
                timeout = 30
                if browser is not None:
                    await self._open_tdk_page(browser, url, params["device"], query)

                await wait_for(self.__conn_sem.acquire(), timeout=timeout)
                cbl_info(f"Connected to test server at {url}!")
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        self.__stopping = True

        # Close the pages first, so that they do not report the shutdown of the sockets as an error
        try:
            await self.__browser_cleanup.aclose()
        except Exception as e:
            cbl_warning(f"Failed to shut down the TDK browser ({e})")

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

    def get_websocket_for_write(self, url: str) -> web.WebSocketResponse:
        if not self.is_known_ws_url(url):
            raise IndexError(f"No WebSocket connection for the given URL ({url})")

        return self.__connections[url]

    def is_known_ws_url(self, url: str) -> bool:
        return url in self.__connections

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=request.headers.getall("Sec-WebSocket-Protocol", []))
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
                            cbl_error(f"Unknown or invalid device ID received: {device}")
                            await ws.close(message=b"Unknown or invalid device ID")
            elif msg.type == web.WSMsgType.ERROR:
                cbl_error(f"WebSocket connection closed with exception {ws.exception()}")

        return ws

    def register(self, ts_id: int) -> Future[dict]:
        future: Future[dict] = Future()
        self.__pending[ts_id] = future
        return future

    def unregister(self, ts_id: int) -> None:
        self.__pending.pop(ts_id, None)

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
