from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock, patch

from cbltest.api import syncgateway


def bootstrap_response(server: str = "rosmar") -> Mock:
    """
    Stands in for the response to the synchronous ``GET /_config`` that SyncGateway.__init__
    reads.

    :param server: The bootstrap server the fake config names
    """
    body = {"bootstrap": {"server": server}}
    return Mock(json=Mock(return_value=body), raise_for_status=Mock(return_value=None))


@contextmanager
def patch_bootstrap(server: str = "rosmar") -> Iterator[None]:
    """Answers the bootstrap read SyncGateway.__init__ makes, so it needs no live node."""
    with patch("cbltest.api.syncgateway.requests.get", return_value=bootstrap_response(server)):
        yield


@contextmanager
def fake_sync_gateways(count: int) -> Iterator[list[syncgateway.SyncGateway]]:
    with (
        patch("cbltest.api.syncgateway.ClientSession", autospec=True),
        patch("cbltest.api.caddy.ClientSession", autospec=True),
        patch_bootstrap(),
    ):
        yield [
            syncgateway.SyncGateway(
                url="https://example.com",
                username="user",
                password="pass",
            )
            for _ in range(count)
        ]
