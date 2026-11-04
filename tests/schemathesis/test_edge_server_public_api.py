"""
Checks the Edge Server public API against its published OpenAPI spec with the schemathesis pytest
integration. Each run below is one keyspace and one generation mode, and pytest makes one test per run and
operation. schemathesis.toml holds the settings that every run shares.
"""

import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import schemathesis
import yaml
from cbltest import CBLPyTest
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.plugins.cluster_cleanup import perform_cleanup, reset_all_edge_servers
from hypothesis import HealthCheck, settings
from schemathesis import GenerationMode
from schemathesis.config import SchemathesisConfig

SPEC_URL = (
    "https://docs.couchbase.com/couchbase-edge-server/current/public-api-reference/_attachments/public.bundle.yaml"
)
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "schemathesis.toml"
DATASET_CONFIG = SCRIPT_DIR / "config" / "edge_server.json"
DB = "names"

# A port that nothing listens on, on the Edge Server host, so the replications stay listed and send nothing
# off the host.
UNREACHABLE_TARGET = "ws://127.0.0.1:1/names"

# The documents that schemathesis.toml pins as {docid}, copied into each named collection.
PINNED_DOC_IDS = ["name_1", "name_2", "name_3"]


@dataclass(frozen=True)
class Run:
    keyspace: str
    mode: GenerationMode


# The keyspace is pinned, so negative mode runs only against the default collection.
RUNS = {
    "names-positive": Run("names", GenerationMode.POSITIVE),
    "names-negative": Run("names", GenerationMode.NEGATIVE),
    "schema_coll-positive": Run("names.schema_coll", GenerationMode.POSITIVE),
    "schema_scope.schema_coll-positive": Run("names.schema_scope.schema_coll", GenerationMode.POSITIVE),
}


def fetch_spec() -> dict[str, Any]:
    """Download the bundled public API spec, which describes only the current Edge Server release."""
    with urllib.request.urlopen(SPEC_URL, timeout=60) as response:
        return yaml.safe_load(response.read())


def schema_for(spec: dict[str, Any], run: Run) -> schemathesis.BaseSchema:
    """The spec, with schemathesis.toml plus the keyspace and generation mode of one run."""
    config = SchemathesisConfig.from_path(str(CONFIG_FILE))
    project = config.projects.default
    project.parameters["keyspace"] = run.keyspace
    project.generation.update(modes=[run.mode])
    return schemathesis.openapi.from_dict(spec, config=config)


SPEC = fetch_spec()
SPEC_VERSION = str(SPEC["info"]["version"])


@dataclass
class EdgeServerRun:
    name: str
    base_url: str
    auth: tuple[str, str]
    read_task: int
    stop_task: int


_current: EdgeServerRun | None = None


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def cluster_cleanup(cblpytest: CBLPyTest) -> None:
    """Clean up once for the module. edge_server sets Edge Server up again for each run."""
    await reset_all_edge_servers(cblpytest.edge_servers)
    await perform_cleanup(cblpytest)


def major_minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


@pytest_asyncio.fixture(loop_scope="session")
async def edge_server(cblpytest: CBLPyTest, request: pytest.FixtureRequest) -> EdgeServerRun:
    """
    The Edge Server for the run that the current test belongs to. Edge Server starts again with the names
    dataset at the first test of each run, so that each run starts from the same data, like a separate
    schemathesis CLI run.
    """
    global _current
    match = re.search(r"\[([^\]]+)\]\[", request.node.name)
    assert match is not None, f"No run name in {request.node.name}"
    name = match.group(1)
    if _current is not None and _current.name == name:
        return _current

    keyspace = RUNS[name].keyspace
    manager = cblpytest.edge_servers[0]
    edge_server = await manager.configure_dataset(db_name=DB, config_file=str(DATASET_CONFIG))

    server_version = (await edge_server.get_version()).version
    if major_minor(server_version) != major_minor(SPEC_VERSION):
        pytest.skip(f"The published spec is for Edge Server {SPEC_VERSION}, but the server is {server_version}")

    if keyspace != DB:
        # new_edits=False keeps the dataset revisions that the {key} pins in schemathesis.toml use.
        docs = [await edge_server.get_document(DB, doc_id) for doc_id in PINNED_DOC_IDS]
        await edge_server.bulk_doc_op(
            [BulkDocOperation(doc.body, _id=doc.id, rev=doc.revid, optype="update") for doc in docs],
            keyspace,
            new_edits=False,
        )

    read_task, stop_task = [
        await edge_server.start_replication(
            DB, UNREACHABLE_TARGET, user=None, password=None, bidirectional=False, continuous=True
        )
        for _ in range(2)
    ]
    _current = EdgeServerRun(
        name, edge_server.base_url, (manager.admin_user, manager.admin_password), read_task, stop_task
    )
    return _current


@pytest.mark.openapi
@pytest.mark.min_edge_servers(1)
@schemathesis.pytest.parametrize(**{name: schema_for(SPEC, run) for name, run in RUNS.items()})
# The fixture sets up Edge Server once per run, and every generated request in the run shares it.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_public_api(case: schemathesis.Case, edge_server: EdgeServerRun) -> None:
    if case.path_parameters and "taskid" in case.path_parameters:
        # schemathesis.toml pins a placeholder, because the task IDs change on every run.
        is_read = case.operation.method.upper() == "GET"
        case.path_parameters["taskid"] = edge_server.read_task if is_read else edge_server.stop_task
    case.call_and_validate(base_url=edge_server.base_url, auth=edge_server.auth, verify=False)
