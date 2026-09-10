"""Tests for the CouchbaseServer client, whose sidecar has to answer without the SDK."""

from unittest.mock import patch

import pytest
from cbltest.api.couchbaseserver import CouchbaseServer


@pytest.mark.asyncio
async def test_the_sidecar_answers_without_a_connection() -> None:
    """start_server() is for a node whose service is stopped, which the SDK cannot connect to."""
    with patch("cbltest.api.sidecar.ClientSession", autospec=True):
        cbs = CouchbaseServer("cbs.example.com", "Administrator", "password")

        sidecar = cbs._shell2http
        assert sidecar is cbs._shell2http, "one sidecar per client, opened once and kept"

        with pytest.raises(AssertionError, match="not connected"):
            _ = cbs._cluster

        await cbs.close()
