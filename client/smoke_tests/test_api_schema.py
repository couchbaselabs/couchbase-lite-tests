import asyncio
import copy
import itertools
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
import requests
import schemathesis
import yaml
from cbltest import CBLPyTest
from cbltest.api.database import BASE_BLOB_URL
from cbltest.requests import RequestFactory
from cbltest.responses import ServerVariant, unwrap_ws_payload
from hypothesis import assume
from schemathesis import BaseSchema, Case, CheckContext, GenerationMode, Response
from schemathesis.checks import ignored_auth, positive_data_acceptance

SPEC_PATH = Path(__file__).parents[2] / "spec" / "api" / "api.yaml"

# newSession would replace the session that the cblpytest fixture opened, and the multipeer
# replicator needs Wi-Fi or Bluetooth peers
EXCLUDED_PATHS = [
    "/newSession",
    "/startMultipeerReplicator",
    "/stopMultipeerReplicator",
    "/getMultipeerReplicatorStatus",
]

# The database and collections that the examples in the spec name
EXAMPLE_DATABASES = {"db1": {"collections": ["store.cloths", "store.shoes", "catalog.cloths", "catalog.shoes"]}}

# The API is stateful, so a schema-valid request for a database, replicator or listener that does
# not exist gets 400. The spec has no security schemes, so ignored_auth has nothing to check.
EXCLUDED_CHECKS = [positive_data_acceptance, ignored_auth]

# The JS and React Native test servers cannot accept connections, and lite-js only compacts
UNSUPPORTED_PATHS = {
    ServerVariant.JS: {"/startListener", "/stopListener", "/performMaintenance"},
    ServerVariant.REACT_NATIVE: {"/startListener", "/stopListener"},
}

DATASET_BASE_URL = (
    "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/dbs/"
)

# The datasets that every platform has, and the small blobs
DATASET_NAMES = ["names", "posts", "todo", "travel"]
BLOB_NAMES = [f"s{i}.jpg" for i in range(1, 11)]

REQUEST_ARGS = {"method", "url", "headers", "params", "cookies", "data", "json"}

# Far above the message numbers that the request factory gives its own WebSocket requests
_ws_message_ids = itertools.count(1_000_000)

type Sender = Callable[[requests.Request], Response]


@pytest.fixture(scope="session")
def test_server_url(cblpytest: CBLPyTest) -> str:
    return cblpytest.config.test_servers[0]["url"]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def session_loop() -> asyncio.AbstractEventLoop:
    """The loop that the WebSocket router of the cblpytest fixture runs on."""
    return asyncio.get_running_loop()


async def _send_ws(factory: RequestFactory, url: str, request: requests.PreparedRequest) -> Response:
    """Sends a request the way that the WebSocket transport does, with the headers as ts_* fields."""
    message_id = next(_ws_message_ids)
    message = {
        **(json.loads(request.body) if request.body else {}),
        "ts_id": message_id,
        "ts_command": urlsplit(request.url).path,
        "ts_clientID": str(factory.uuid),
        "ts_apiVersion": factory.version,
    }

    router = factory.ws_router
    start = time.monotonic()
    future = router.register(message_id)
    await router.get_websocket_for_write(url).send_str(json.dumps(message))
    try:
        payload = await asyncio.wait_for(future, timeout=120)
    finally:
        router.unregister(message_id)

    status, body = unwrap_ws_payload(payload)
    headers = {"Content-Type": ["application/json"]}
    for header, field in (("CBLTest-API-Version", "ts_apiVersion"), ("CBLTest-Server-ID", "ts_serverID")):
        if field in payload:
            headers[header] = [str(payload[field])]

    return Response(
        status_code=status,
        headers=headers,
        content=json.dumps(body).encode(),
        request=request,
        elapsed=time.monotonic() - start,
        verify=True,
    )


@pytest.fixture(scope="session")
def send(cblpytest: CBLPyTest, session_loop: asyncio.AbstractEventLoop) -> Sender:
    """Sends a request with the headers of the session that the cblpytest fixture opened."""
    factory = cblpytest.request_factory
    session = requests.Session()
    session.headers.update({"CBLTest-API-Version": str(factory.version), "CBLTest-Client-ID": str(factory.uuid)})
    test_server = cblpytest.config.test_servers[0]
    if test_server.get("transport", "http") == "http":
        return lambda request: Response.from_requests(session.send(session.prepare_request(request)), verify=True)

    return lambda request: session_loop.run_until_complete(
        _send_ws(factory, test_server["url"], session.prepare_request(request))
    )


def _load_spec(dataset_version: str) -> dict[str, Any]:
    """Loads the spec with dataset and blob URLs limited to ones that exist, so that their v1 names exist too."""
    spec = yaml.safe_load(SPEC_PATH.read_text())
    schemas = spec["components"]["schemas"]
    database = schemas["ResetConfiguration"]["properties"]["databases"]["additionalProperties"]
    database["properties"]["dataset"]["enum"] = [
        f"{DATASET_BASE_URL}{dataset_version}/{name}.cblite2.zip" for name in DATASET_NAMES
    ]
    updated_blobs = schemas["DatabaseUpdateItem"]["properties"]["updatedBlobs"]
    updated_blobs["additionalProperties"]["enum"] = [f"{BASE_BLOB_URL}{name}" for name in BLOB_NAMES]
    return spec


def _file_name(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1]


def _to_v1_body(path: str, body: Any) -> None:
    """Replaces dataset and blob URLs with the names that API v1 takes, as the v1 request bodies of cbltest do."""
    if not isinstance(body, dict):
        return

    if path == "/reset":
        for entry in (body.get("databases") or {}).values():
            if entry and "dataset" in entry:
                entry["dataset"] = _file_name(entry["dataset"]).removesuffix(".cblite2.zip")
    elif path in ("/updateDatabase", "/verifyDocuments"):
        for item in body.get("updates" if path == "/updateDatabase" else "changes") or []:
            blobs = item.get("updatedBlobs") or {}
            for keypath, url in blobs.items():
                blobs[keypath] = _file_name(url)


@pytest.fixture(scope="session")
def api_schema(cblpytest: CBLPyTest, test_server_url: str) -> BaseSchema:
    schema = schemathesis.openapi.from_dict(_load_spec(cblpytest.test_servers[0].dataset_version))
    schema.config.update(base_url=test_server_url)
    schema.config.generation.update(modes=[GenerationMode.POSITIVE], max_examples=25)
    return schema


schema = schemathesis.pytest.from_fixture("api_schema").exclude(path=EXCLUDED_PATHS)


@schemathesis.check
def cbltest_response_headers(ctx: CheckContext, response: Response, case: Case) -> bool | None:
    present = {name.lower() for name in response.headers}
    missing = [h for h in ("CBLTest-API-Version", "CBLTest-Server-ID") if h.lower() not in present]
    if missing:
        raise AssertionError(f"Missing response headers: {', '.join(missing)}")
    return None


@schema.parametrize()
def test_api_conforms_to_spec(case: Case, cblpytest: CBLPyTest, test_server_url: str, send: Sender) -> None:
    variant = cblpytest.request_factory.variant(0)
    if case.path in UNSUPPORTED_PATHS.get(variant, set()):
        pytest.skip(f"The {variant} test server does not implement {case.path}")

    # CBL .NET does not send replicator headers, so it cannot present a bearer token
    if variant == ServerVariant.DOTNET and case.path == "/startReplicator" and isinstance(case.body, dict):
        authenticator = case.body["config"].get("authenticator") or {}
        assume(str(authenticator.get("type", "")).upper() != "BEARER")

    # cbl-reactnative has no custom conflict resolvers: https://couchbasecloud.atlassian.net/browse/IDEA-1106
    if variant == ServerVariant.REACT_NATIVE and case.path == "/startReplicator" and isinstance(case.body, dict):
        assume(not any(c.get("conflictResolver") for c in case.body["config"].get("collections") or []))

    # JAK creates databases only for a reset that names a test
    reset_body = {"test": "test_api_conforms_to_spec", "databases": EXAMPLE_DATABASES}
    reset = send(requests.Request("POST", f"{test_server_url}/reset", json=reset_body))
    assert reset.status_code == 200, f"Reset failed: {reset.status_code} {reset.text}"
    kwargs = {k: v for k, v in case.as_transport_kwargs().items() if k in REQUEST_ARGS}
    # The case keeps the v2 body, which the checks compare to the spec
    if cblpytest.request_factory.version == 1 and "json" in kwargs:
        kwargs["json"] = copy.deepcopy(kwargs["json"])
        _to_v1_body(case.path, kwargs["json"])

    case.validate_response(send(requests.Request(**kwargs)), excluded_checks=EXCLUDED_CHECKS)
