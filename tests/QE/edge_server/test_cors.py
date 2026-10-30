import json
from datetime import timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.responses import ServerVariant

SCRIPT_DIR = Path(__file__).parent
CONFIG = SCRIPT_DIR / "config" / "test_cors.json"
CORS_HEADERS = ["Authorization", "Content-Type"]


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestCors(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "origin, pull_allowed",
        [
            (["http://localhost:5173"], True),
            (["*"], False),
            (["https://app.example.com"], False),
            (None, False),
        ],
        ids=["test_server_origin", "wildcard_origin", "other_origin_only", "cors_off"],
    )
    async def test_cbl_js_replication_needs_cors(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, origin: list[str] | None, pull_allowed: bool
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_es_not(cblpytest.edge_servers[0].get_admin_client(), ">= 1.1")

        self.mark_test_step("Start Edge Server with the case's CORS origins, and seed a doc in `travel.hotels`")
        config = json.loads(CONFIG.read_text())
        if origin is None:
            config.pop("cors")
        else:
            config["cors"] = {"origin": origin, "headers": CORS_HEADERS, "max_age": 600}
        config_path = tmp_path / "cors_config.json"
        config_path.write_text(json.dumps(config))
        admin = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=str(config_path))
        await admin.put_document_with_id({"origin": "es"}, "cors_seed", "travel", "travel", "hotels")

        self.mark_test_step("Pull the seed doc from the browser as the admin")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.hotels"]))[0]
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
        pulled = {doc.id for doc in (await db.get_all_documents("travel.hotels"))["travel.hotels"]}

        self.mark_test_step("Verify the pull succeeds only when CORS allows the test server's origin")
        if pull_allowed:
            assert status.error is None, (
                f"Pull failed: {status.error.domain}/{status.error.code}: {status.error.message}"
            )
            assert "cors_seed" in pulled, "The seed doc was not pulled"
        else:
            assert status.error is not None, (
                "A browser replicated with Edge Server although CORS does not allow its origin"
            )
            assert "cors_seed" not in pulled, "A browser pulled a doc although CORS does not allow its origin"
