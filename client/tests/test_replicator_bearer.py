"""Only CBL JS has a bearer authenticator, so Replicator sends a bearer token to every other
platform as the Authorization header.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from cbltest.api.database import Database
from cbltest.api.error import CblTestError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorBearerAuthenticator
from cbltest.configparser import ParsedConfig
from cbltest.requests import RequestFactory
from cbltest.responses import ServerVariant


def replicator(variant: ServerVariant, **kwargs: Any) -> Replicator:
    """A Replicator for a database on a fake test server that runs `variant`."""
    factory = SimpleNamespace(variant=lambda index: variant)
    db = cast(Database, SimpleNamespace(_index=0, _request_factory=factory, name="db1"))
    return Replicator(db, "wss://sg:4984/travel", **kwargs)


@pytest.mark.parametrize("variant", [ServerVariant.C, ServerVariant.DOTNET, ServerVariant.IOS, ServerVariant.JVM])
def test_bearer_becomes_authorization_header(variant: ServerVariant) -> None:
    r = replicator(variant, authenticator=ReplicatorBearerAuthenticator("tok"), headers={"X-Other": "1"})
    assert r._request_auth() == (None, {"X-Other": "1", "Authorization": "Bearer tok"})
    assert r.headers == {"X-Other": "1"}


def test_js_keeps_bearer_authenticator() -> None:
    authenticator = ReplicatorBearerAuthenticator("tok")
    r = replicator(ServerVariant.JS, authenticator=authenticator)
    assert r._request_auth() == (authenticator, None)


def test_other_authenticators_pass_through() -> None:
    authenticator = ReplicatorBasicAuthenticator("user", "pass")
    r = replicator(ServerVariant.C, authenticator=authenticator, headers={"X-Other": "1"})
    assert r._request_auth() == (authenticator, {"X-Other": "1"})


def test_authenticator_changes_before_start_apply() -> None:
    r = replicator(ServerVariant.C, authenticator=ReplicatorBearerAuthenticator("a"))
    r.authenticator = ReplicatorBearerAuthenticator("b")
    assert r._request_auth() == (None, {"Authorization": "Bearer b"})

    r.authenticator = None
    assert r._request_auth() == (None, None)


@pytest.mark.parametrize("name", ["Authorization", "authorization"])
def test_bearer_with_authorization_header_fails(name: str) -> None:
    r = replicator(ServerVariant.C, authenticator=ReplicatorBearerAuthenticator("tok"), headers={name: "x"})
    with pytest.raises(CblTestError, match="Authorization"):
        r._request_auth()


@pytest.mark.asyncio
async def test_variant_is_unknown_before_it_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    factory = RequestFactory(ParsedConfig({"test-servers": [{"url": "http://localhost:8080"}]}))
    with pytest.raises(CblTestError, match="not known"):
        factory.variant(0)

    factory.set_variant(0, ServerVariant.C)
    assert factory.variant(0) == ServerVariant.C
    await factory.close()
