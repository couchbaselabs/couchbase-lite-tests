import urllib.request
from pathlib import Path

import pytest
import yaml
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.schemathesis import run_schemathesis

SCRIPT_DIR = Path(__file__).parent
SPEC_URL = (
    "https://docs.couchbase.com/couchbase-edge-server/current/public-api-reference/_attachments/public.bundle.yaml"
)
CONFIG = SCRIPT_DIR / "config" / "test_public_api_schema.json"
CONFIG_FILE = SCRIPT_DIR / "schemathesis.toml"

OPERATIONS = [
    "GET /",
    "GET /_all_dbs",
    "GET /_active_tasks",
    "GET /{keyspace}",
    "PUT /{keyspace}",
    "GET /{keyspace}/_all_docs",
    "POST /{keyspace}/_all_docs",
    "GET /{keyspace}/{docid}",
    "HEAD /{keyspace}/{docid}",
    "PUT /{keyspace}/{docid}",
    "DELETE /{keyspace}/{docid}",
    "POST /{keyspace}/_bulk_docs",
    "GET /{keyspace}/{docid}/{key}",
    "PUT /{keyspace}/{docid}/{key}",
    "DELETE /{keyspace}/{docid}/{key}",
    "POST /{keyspace}/_query",
    "GET /{keyspace}/_query/{name}",
    "POST /{keyspace}/_query/{name}",
    "GET /{keyspace}/_changes",
    "POST /{db}/_session",
    "GET /_replicate",
    "GET /_replicate/{taskid}",
    "DELETE /_replicate/{taskid}",
]

# A port that nothing listens on, on the Edge Server host, so the replications stay listed and send nothing
# off the host. POST /_replicate is not covered, because generated targets would be any host.
UNREACHABLE_TARGET = "ws://127.0.0.1:1/names"

# The documents that the config pins as {docid}.
PINNED_DOC_IDS = ["name_1", "name_2", "name_3"]


def fetch_public_spec(dest: Path) -> Path:
    """Download the bundled public API spec, which describes only the current Edge Server release."""
    with urllib.request.urlopen(SPEC_URL, timeout=60) as response:
        dest.write_bytes(response.read())
    return dest


@pytest.fixture(scope="module")
def public_spec(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """The downloaded spec and its Edge Server version, fetched once for every case."""
    spec = fetch_public_spec(tmp_path_factory.mktemp("edge_server_spec") / "public.bundle.yaml")
    return spec, str(yaml.safe_load(spec.read_text())["info"]["version"])


def major_minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


@pytest.mark.openapi
@pytest.mark.min_edge_servers(1)
class TestPublicApiSchema(CBLTestClass):
    # Positive mode sends only valid requests, and negative mode only invalid ones, which must get a 4xx.
    # The keyspace is pinned, so negative mode runs only against the default collection.
    @pytest.mark.parametrize(
        "keyspace, mode",
        [
            ("names", "positive"),
            ("names", "negative"),
            ("names.schema_coll", "positive"),
            ("names.schema_scope.schema_coll", "positive"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_public_api_conforms_to_spec(
        self, cblpytest: CBLPyTest, public_spec: tuple[Path, str], keyspace: str, mode: str
    ) -> None:
        self.mark_test_step("Start Edge Server with the names dataset, the admin user and a named query")
        manager = cblpytest.edge_servers[0]
        edge_server = await manager.configure_dataset(db_name="names", config_file=str(CONFIG))

        self.mark_test_step("Skip if the published spec is for another Edge Server release")
        spec, spec_version = public_spec
        server_version = (await edge_server.get_version()).version
        if major_minor(server_version) != major_minor(spec_version):
            pytest.skip(f"The published spec is for Edge Server {spec_version}, but the server is {server_version}")

        if keyspace != "names":
            self.mark_test_step(f"Copy the pinned documents into {keyspace}, with their dataset revisions")
            docs = [await edge_server.get_document("names", doc_id) for doc_id in PINNED_DOC_IDS]
            await edge_server.bulk_doc_op(
                [BulkDocOperation(doc.body, _id=doc.id, rev=doc.revid, optype="update") for doc in docs],
                keyspace,
                new_edits=False,
            )

        self.mark_test_step("Start two continuous replications to an unreachable target, one to read and one to stop")
        task_ids = [
            await edge_server.start_replication(
                "names", UNREACHABLE_TARGET, user=None, password=None, bidirectional=False, continuous=True
            )
            for _ in range(2)
        ]

        self.mark_test_step(f"Run schemathesis in {mode} mode against the public API operations in {keyspace}")
        returncode, output = await run_schemathesis(
            spec,
            CONFIG_FILE,
            edge_server.base_url,
            OPERATIONS,
            auth=f"{manager.admin_user}:{manager.admin_password}",
            env={
                "ES_OPENAPI_KEYSPACE": keyspace,
                "ES_OPENAPI_READ_TASK": str(task_ids[0]),
                "ES_OPENAPI_STOP_TASK": str(task_ids[1]),
            },
            mode=mode,
        )

        self.mark_test_step("Check that schemathesis found no failures")
        assert returncode == 0, output
