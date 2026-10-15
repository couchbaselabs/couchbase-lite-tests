import json
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.syncgateway import get_basic_auth_headers
from cbltest.responses import ServerVariant

SCRIPT_DIR = Path(__file__).parent
CONFIG = SCRIPT_DIR / "config" / "test_cors.json"
ES_PORT = 59840
ALLOWED_ORIGIN = "http://localhost:5173"
OTHER_ALLOWED_ORIGIN = "https://app.example.com"
DISALLOWED_ORIGIN = "https://evil.example.com"
ADMIN = get_basic_auth_headers("admin_user", "password")
PREFLIGHT = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}


async def _send(
    cblpytest: CBLPyTest, method: str, path: str, headers: Mapping[str, str]
) -> tuple[int, Mapping[str, str]]:
    """Send a raw request to the Edge Server, and return its status and response headers."""
    url = f"http://{cblpytest.edge_servers[0]}:{ES_PORT}{path}"
    async with aiohttp.ClientSession() as session, session.request(method, url, headers=headers) as resp:
        return resp.status, resp.headers


@pytest.mark.min_edge_servers(1)
class TestCors(CBLTestClass):
    async def _start(self, cblpytest: CBLPyTest, tmp_path: Path, cors: dict | None = None) -> EdgeServer:
        """Start Edge Server on the CORS config, optionally with a different `cors` block (an empty one removes it)."""
        config = json.loads(CONFIG.read_text())
        if cors is not None:
            config.pop("cors")
            if cors:
                config["cors"] = cors
        config_path = tmp_path / "cors_config.json"
        config_path.write_text(json.dumps(config))
        return await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=str(config_path))

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("origin", [ALLOWED_ORIGIN, OTHER_ALLOWED_ORIGIN], ids=["first_origin", "second_origin"])
    async def test_preflight_from_allowed_origin(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, origin: str
    ) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing two origins")
        await self._start(cblpytest, tmp_path)

        self.mark_test_step("Send a preflight OPTIONS /travel/_all_docs from the allowed origin")
        status, headers = await _send(cblpytest, "OPTIONS", "/travel/_all_docs", {"Origin": origin, **PREFLIGHT})

        self.mark_test_step(
            "Verify the preflight allows the origin, the method and the Authorization header, with the max age"
        )
        assert status in (200, 204), f"Preflight returned {status}"
        assert headers.get("Access-Control-Allow-Origin") == origin, (
            f"Allow-Origin: {headers.get('Access-Control-Allow-Origin')}"
        )
        assert "GET" in headers.get("Access-Control-Allow-Methods", ""), (
            f"Allow-Methods: {headers.get('Access-Control-Allow-Methods')}"
        )
        assert "authorization" in headers.get("Access-Control-Allow-Headers", "").lower(), (
            f"Allow-Headers: {headers.get('Access-Control-Allow-Headers')}"
        )
        assert headers.get("Access-Control-Max-Age") == "600", f"Max-Age: {headers.get('Access-Control-Max-Age')}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_preflight_from_disallowed_origin(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing two origins")
        await self._start(cblpytest, tmp_path)

        self.mark_test_step("Send a preflight OPTIONS /travel/_all_docs from an origin that is not allowed")
        _, headers = await _send(cblpytest, "OPTIONS", "/travel/_all_docs", {"Origin": DISALLOWED_ORIGIN, **PREFLIGHT})

        self.mark_test_step("Verify the response does not allow the origin")
        assert "Access-Control-Allow-Origin" not in headers, (
            f"Allow-Origin: {headers.get('Access-Control-Allow-Origin')}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_request_from_allowed_origin(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing two origins")
        await self._start(cblpytest, tmp_path)

        self.mark_test_step("Send GET /travel/ as the admin from the allowed origin")
        status, headers = await _send(cblpytest, "GET", "/travel/", {"Origin": ALLOWED_ORIGIN, **ADMIN})

        self.mark_test_step("Verify the request succeeds and the response allows the origin")
        assert status == 200, f"GET /travel/ returned {status}"
        assert headers.get("Access-Control-Allow-Origin") == ALLOWED_ORIGIN, (
            f"Allow-Origin: {headers.get('Access-Control-Allow-Origin')}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_request_from_disallowed_origin(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing two origins")
        await self._start(cblpytest, tmp_path)

        self.mark_test_step("Send GET /travel/ as the admin from an origin that is not allowed")
        _, headers = await _send(cblpytest, "GET", "/travel/", {"Origin": DISALLOWED_ORIGIN, **ADMIN})

        self.mark_test_step("Verify the response does not allow the origin")
        assert "Access-Control-Allow-Origin" not in headers, (
            f"Allow-Origin: {headers.get('Access-Control-Allow-Origin')}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_cors_does_not_bypass_authentication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing two origins")
        await self._start(cblpytest, tmp_path)

        self.mark_test_step("Send GET /travel/ from the allowed origin with no credentials")
        status, headers = await _send(cblpytest, "GET", "/travel/", {"Origin": ALLOWED_ORIGIN})

        self.mark_test_step(
            "Verify the request is refused with 401, and the refusal allows the origin so a browser can read it"
        )
        assert status == 401, f"GET /travel/ without credentials returned {status}"
        assert headers.get("Access-Control-Allow-Origin") == ALLOWED_ORIGIN, (
            f"The 401 has no Allow-Origin ({headers.get('Access-Control-Allow-Origin')}), so a browser sees only a CORS failure"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_wildcard_origin_allows_any_origin(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("Start Edge Server with CORS allowing any origin")
        await self._start(
            cblpytest, tmp_path, {"origin": ["*"], "headers": ["Authorization", "Content-Type"], "max_age": 600}
        )

        self.mark_test_step("Send a preflight OPTIONS /travel/_all_docs from an arbitrary origin")
        status, headers = await _send(
            cblpytest, "OPTIONS", "/travel/_all_docs", {"Origin": DISALLOWED_ORIGIN, **PREFLIGHT}
        )

        self.mark_test_step("Verify the preflight allows the origin")
        assert status in (200, 204), f"Preflight returned {status}"
        assert headers.get("Access-Control-Allow-Origin") in ("*", DISALLOWED_ORIGIN), (
            f"Allow-Origin: {headers.get('Access-Control-Allow-Origin')}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_cors_is_off_without_config(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        self.mark_test_step("Start Edge Server with no `cors` block")
        await self._start(cblpytest, tmp_path, {})

        self.mark_test_step("Send a preflight and a GET /travel/ as the admin from an origin")
        _, preflight = await _send(cblpytest, "OPTIONS", "/travel/_all_docs", {"Origin": ALLOWED_ORIGIN, **PREFLIGHT})
        _, request = await _send(cblpytest, "GET", "/travel/", {"Origin": ALLOWED_ORIGIN, **ADMIN})

        self.mark_test_step("Verify neither response allows the origin")
        assert "Access-Control-Allow-Origin" not in preflight, "A preflight was allowed with CORS off"
        assert "Access-Control-Allow-Origin" not in request, "A request was allowed cross-origin with CORS off"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.min_test_servers(1)
    @pytest.mark.parametrize("cors_on", [True, False], ids=["with_cors", "without_cors"])
    async def test_cbl_js_replication_needs_cors(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, cors_on: bool
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Start Edge Server with or without CORS for the test server's origin, and seed a doc")
        admin = await self._start(cblpytest, tmp_path, None if cors_on else {})
        await admin.put_document_with_id({"origin": "es"}, "cors_seed", "travel", "travel", "hotels")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.hotels"]))[0]

        self.mark_test_step("Pull the seed doc from the browser as the admin")
        replicator = Replicator(
            db,
            admin.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("admin_user", "password"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"], document_ids=["cors_seed"])],
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED, timeout=timedelta(seconds=60))
        pulled = {d.id for d in (await db.get_all_documents("travel.hotels"))["travel.hotels"]}

        self.mark_test_step("Verify the pull succeeds with CORS, and fails with nothing pulled without it")
        if cors_on:
            assert status.error is None, (
                f"Pull with CORS failed: {status.error.domain}/{status.error.code}: {status.error.message}"
            )
            assert "cors_seed" in pulled, "The seed doc was not pulled"
        else:
            assert status.error is not None, "A browser replicated with Edge Server without CORS"
            assert "cors_seed" not in pulled, "A browser pulled a doc without CORS"