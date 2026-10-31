import asyncio
import subprocess
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig
from cbltest.configparser import SyncGatewayInfo
from cbltest.schemathesis import run_schemathesis

SPEC_REPO = "https://github.com/couchbase/sync_gateway.git"
DB_NAME = "openapi_db"
CONFIG_FILE = Path(__file__).parent / "schemathesis.toml"

# A non-destructive slice of the admin API; {keyspace} resolves to the default collection.
# Not covered: POST _changes (a body feed cannot be pinned, so longpoll runs hang), and
# PUT /{keyspace}/{docid}/{attach} (the spec names its media type `Attachment content type`).
OPERATIONS = [
    "GET /",
    "GET /_all_dbs",
    "GET /{db}/",
    "GET /{db}/_user/",
    "PUT /{db}/_user/{name}",
    "GET /{db}/_user/{name}",
    "DELETE /{db}/_user/{name}",
    "PUT /{db}/_role/{name}",
    "GET /{db}/_role/{name}",
    "PUT /{keyspace}/{docid}",
    "GET /{keyspace}/{docid}",
    "GET /{keyspace}/_all_docs",
    "POST /{keyspace}/",
    "DELETE /{keyspace}/{docid}",
    "POST /{keyspace}/_all_docs",
    "POST /{keyspace}/_bulk_docs",
    "POST /{keyspace}/_bulk_get",
    "POST /{keyspace}/_revs_diff",
    "GET /{keyspace}/_raw/{docid}",
    "GET /{keyspace}/_revtree/{docid}",
    "GET /{keyspace}/_changes",
    "PUT /{keyspace}/_local/{docid}",
    "GET /{keyspace}/_local/{docid}",
    "DELETE /{keyspace}/_local/{docid}",
    "GET /{keyspace}/{docid}/{attach}",
    "DELETE /{keyspace}/{docid}/{attach}",
    "GET /{db}/_config",
    "POST /{db}/_user/",
    "GET /{db}/_user/{name}/_access_history",
    "DELETE /{db}/_user/{name}/_session",
    "GET /{db}/_role/",
    "POST /{db}/_role/",
    "DELETE /{db}/_role/{name}",
    "POST /{db}/_session",
    "GET /{db}/_session/{sessionid}",
    "DELETE /{db}/_session/{sessionid}",
]


def fetch_admin_spec(version: str, dest: Path) -> Path:
    """
    Sparse-checks out Sync Gateway's docs/api, which splits admin.yaml across many $ref'd files,
    from the release tag for `version`, or from main for a development build with no tag.
    """
    for ref in (version, "main"):
        clone = subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "--branch", ref, "--filter=blob:none", "--sparse"]
            + [SPEC_REPO, str(dest)],
            capture_output=True,
        )
        if clone.returncode == 0:
            break
    else:
        raise RuntimeError(f"Could not clone {SPEC_REPO}: {clone.stderr.decode()}")

    subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", "docs/api"], check=True)
    return dest / "docs" / "api" / "admin.yaml"


@pytest.mark.openapi
@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
class TestAdminApiSchema(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_api_conforms_to_spec(self, cblpytest: CBLPyTest, tmp_path: Path) -> None:
        self.mark_test_step("Fetch the admin API spec for the Sync Gateway version under test")
        sg = cblpytest.sync_gateways[0]
        version = (await sg.get_version()).version
        spec = await asyncio.to_thread(fetch_admin_spec, version, tmp_path / "sync_gateway")

        self.mark_test_step("Create a database that uses the default collection")
        if not cblpytest.config.couchbase_servers and not await sg.using_rosmar:
            pytest.skip("Sync Gateway is not on rosmar, so the database needs a Couchbase Server")
        await cblpytest.clusters[0].create_database(
            DB_NAME, DatabaseConfig(bucket=DB_NAME, index=IndexConfig(num_replicas=0))
        )

        self.mark_test_step("Run schemathesis against the admin API operations in scope")
        sgw = SyncGatewayInfo(cblpytest.config.sync_gateways[0])
        auth = f"{sgw.rbac_user}:{sgw.rbac_password}" if await sg.admin_interface_authentication else None
        returncode, output = await run_schemathesis(
            spec,
            CONFIG_FILE,
            sg.http_url,
            OPERATIONS,
            auth=auth,
            env={"SGW_OPENAPI_DB": DB_NAME},
        )

        self.mark_test_step("Check that schemathesis found no failures")
        assert returncode == 0, output
