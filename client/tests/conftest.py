from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from cbltest.api import syncgateway


@contextmanager
def fake_sync_gateways(count: int) -> Iterator[list[syncgateway.SyncGateway]]:
    with (
        patch("cbltest.api.syncgateway.ClientSession", autospec=True),
        patch("cbltest.api.caddy.ClientSession", autospec=True),
        patch("cbltest.api.syncgateway.requests.get", autospec=True),
    ):
        yield [
            syncgateway.SyncGateway(
                url="https://example.com",
                username="user",
                password="pass",
            )
            for _ in range(count)
        ]
