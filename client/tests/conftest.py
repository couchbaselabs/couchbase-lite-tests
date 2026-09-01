from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from cbltest.api import syncgateway


@contextmanager
def fake_sync_gateways(count: int) -> Iterator[list[syncgateway.SyncGateway]]:
    with (
        patch("cbltest.api.syncgateway.ClientSession", autospec=True),
        patch("cbltest.api.syncgateway.requests.get", autospec=True),
    ):
        # A bare host, as the config supplies: SyncGateway builds its own URLs from this,
        # and a scheme here produces nonsense like "http://https://example.com:20001".
        yield [
            syncgateway.SyncGateway(
                url="sgw.example.com",
                username="user",
                password="pass",
            )
            for _ in range(count)
        ]
