"""Shared aiohttp client setup."""

import asyncio
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from aiohttp import ClientHandlerType, ClientRequest, ClientResponse, ClientSession
from yarl import URL

from cbltest.api.error import CblTimeoutError


def get_client_session(base_url: str | URL | None = None, **kwargs: Any) -> ClientSession:
    """
    Create a `ClientSession` whose timeouts name the request that timed out.

    :param base_url: Base URL that relative request paths resolve against
    :param kwargs: Passed through to `ClientSession`
    """
    return ClientSession(base_url, middlewares=(_describe_timeouts,), response_class=_DescribedResponse, **kwargs)


def describe_transfer(received: int, expected: int | None) -> str:
    """
    Describes how much of a response body arrived, for error messages on a transfer that
    did not finish.

    :param received: Bytes actually read so far
    :param expected: Bytes the response promised via Content-Length, or None if it did not say
    :return: Something like "12.3 MiB of 40.0 MiB (31%)", or "12.3 MiB of unknown total"
    """

    def size(n: int) -> str:
        value = float(n)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{n} B"
            value /= 1024
        raise AssertionError("unreachable")

    if expected is None:
        return f"{size(received)} of unknown total"
    if expected == 0:
        return f"{size(received)} of 0 B"
    return f"{size(received)} of {size(expected)} ({received * 100 // expected}%)"


@contextmanager
def _describe_timeout(method: str, url: URL, start: float, phase: Callable[[], str]) -> Iterator[None]:
    """
    Raise aiohttp's bare TimeoutError, which stringifies to "", as a `CblTimeoutError` naming
    the request and `phase()`, the step it was on.
    """
    try:
        yield
    except CblTimeoutError:
        raise
    except TimeoutError as e:
        detail = f": {e}" if str(e) else ""
        raise CblTimeoutError(
            f"{method} {url} timed out after {time.monotonic() - start:.1f}s {phase()}{detail}"
        ) from e


class _DescribedResponse(ClientResponse):
    """Covers the body read, which happens after the middleware returns."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__start = time.monotonic()

    async def read(self) -> bytes:
        with _describe_timeout(self.method, self.url, self.__start, self.__body_progress):
            return await super().read()

    def __body_progress(self) -> str:
        return f"reading the body, received {describe_transfer(self.content.total_raw_bytes, self.content_length)}"


async def _describe_timeouts(request: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
    start = time.monotonic()
    try:
        with _describe_timeout(request.method, request.url, start, lambda: "waiting for the response"):
            return await handler(request)
    except asyncio.CancelledError as e:
        # A timeout during connect is raised outside this middleware, from this cancellation
        e.add_note(f"{request.method} {request.url} was cancelled after {time.monotonic() - start:.1f}s")
        raise
