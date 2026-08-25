from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from cbltest.api import syncgateway
from cbltest.utils import basic_auth_headers


@contextmanager
def fake_sync_gateways(count: int) -> Iterator[list[syncgateway.SyncGateway]]:
    with (
        patch("cbltest.api.syncgateway.ClientSession", autospec=True),
        patch("cbltest.api.syncgateway.requests.get", autospec=True),
    ):
        yield [
            syncgateway.SyncGateway(
                url="https://example.com",
                headers=basic_auth_headers("user", "pass"),
            )
            for _ in range(count)
        ]
