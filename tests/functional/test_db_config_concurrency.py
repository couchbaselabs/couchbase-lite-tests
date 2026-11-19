import asyncio
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info

DB_NAME = "posts"

# App Services times out requests after 30 seconds, so a request that takes longer counts as a hang.
REQUEST_TIMEOUT_SECONDS = 30

# A run picks a new seed unless its --test-props file sets this key, to replay the operations a logged run picked.
SEED_PROP = "db_config_concurrency_seed"

WRITER_COUNT = 4
OPERATIONS_PER_WRITER = 15


@dataclass(frozen=True)
class _Operation:
    name: str
    method: str
    path: str
    allowed: frozenset[int]
    sends_config: bool
    # Only writers pick by weight.  Readers send every operation in turn.
    weight: int = 1


@dataclass(frozen=True)
class _Violation:
    operation: str
    node: SyncGateway
    status: int | None
    seconds: float
    detail: str

    def __str__(self) -> str:
        status = self.status if self.status is not None else "no response"
        return f"{self.operation} on {self.node}: {status} after {self.seconds:.1f}s {self.detail}"


# With admin API authentication on, as it is on AWS, Sync Gateway answers a request for a database it does not serve
# with 403.  Without it (rosmar) the answer would be 404, which this test does not allow.  An upsert can still get 404
# "missing": the node serves the database, but another node has already deleted its config from the bucket.

# Writers pick from these by weight.  Remove a row to turn that operation off.
WRITE_OPERATIONS: list[_Operation] = [
    _Operation("upsert config", "post", f"/{DB_NAME}/_config", frozenset({201, 403, 404}), True, weight=4),
    _Operation("recreate database", "put", f"/{DB_NAME}/", frozenset({201, 412}), True, weight=2),
    _Operation("delete database", "delete", f"/{DB_NAME}/", frozenset({200, 403}), False, weight=1),
]

# Readers send each of these to their node in turn.  Remove a row to turn that operation off.
READ_OPERATIONS: list[_Operation] = [
    _Operation("get database", "get", f"/{DB_NAME}/", frozenset({200, 403}), False),
    _Operation("get all databases", "get", "/_all_dbs", frozenset({200}), False),
]


@dataclass
class _ConcurrencyRun:
    """The requests of one run: what they send, the requests that broke the rules, and the slowest request of each
    operation."""

    sg_cluster: SyncGatewayCluster
    config: DatabaseConfig
    seed: int
    violations: list[_Violation] = field(default_factory=list)
    slowest: dict[str, float] = field(default_factory=dict)

    async def send(self, sg: SyncGateway, operation: _Operation) -> None:
        """Send one operation to a node, and record it as a violation if it took 30 seconds or longer, or returned a
        status the operation does not allow.  A 500 is never allowed."""
        start = time.monotonic()
        status: int | None = None
        detail = ""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                _, resp = await sg._send_request_with_response(
                    operation.method, operation.path, self.config if operation.sends_config else None
                )
            status = resp.status
        except CblSyncGatewayBadResponseError as e:
            status = e.code
            detail = e.body
        except TimeoutError:
            detail = f"(no response within {REQUEST_TIMEOUT_SECONDS}s)"
        except Exception as e:
            # A node that crashed or stopped listening, which is the failure this test exists to catch.
            detail = f"({e!r})"

        seconds = time.monotonic() - start
        self.slowest[operation.name] = max(self.slowest.get(operation.name, 0.0), seconds)
        if status not in operation.allowed:
            self.violations.append(_Violation(operation.name, sg, status, seconds, detail))

    async def read_until(self, sg: SyncGateway, writers_done: asyncio.Event) -> None:
        """Send every read operation to one node in turn, until the writers are done."""
        while not writers_done.is_set():
            for operation in READ_OPERATIONS:
                await self.send(sg, operation)

    async def write(self, writer: int) -> None:
        """Send OPERATIONS_PER_WRITER write operations, each picked by weight and sent to a random node.  The seed
        replays the operations a writer picks, not the nodes they go to or the order the requests run in."""
        rng = random.Random(self.seed + writer)
        weights = [operation.weight for operation in WRITE_OPERATIONS]
        for _ in range(OPERATIONS_PER_WRITER):
            operation = rng.choices(WRITE_OPERATIONS, weights)[0]
            await self.send(self.sg_cluster.random_node, operation)


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestDbConfigConcurrency(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_db_config_operations(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure the `posts` dataset on the Sync Gateway cluster")
        cloud = cblpytest.clusters[0]
        await cloud.configure_dataset(dataset_path, DB_NAME)
        sg_cluster = cloud.sync_gateway_cluster

        self.mark_test_step(
            "Read the config of the database, to send with the upsert config and recreate database operations"
        )
        config = await sg_cluster.sync_gateways[0].get_database_config(DB_NAME)

        seed = int(cblpytest.extra_props.get(SEED_PROP, random.randrange(2**32)))
        run = _ConcurrencyRun(sg_cluster, config, seed)
        cbl_info(f"Seed {run.seed}, {len(sg_cluster.sync_gateways)} Sync Gateway nodes")
        writers_done = asyncio.Event()

        async with asyncio.TaskGroup() as readers:
            self.mark_test_step(
                "On every node, start a reader that sends the reader operations until the writers finish"
            )
            for sg in sg_cluster.sync_gateways:
                readers.create_task(run.read_until(sg, writers_done))

            self.mark_test_step(
                f"Start {WRITER_COUNT} writers, each sending {OPERATIONS_PER_WRITER} operations to random nodes"
            )
            async with asyncio.TaskGroup() as writers:
                for writer in range(WRITER_COUNT):
                    writers.create_task(run.write(writer))

            self.mark_test_step("Wait for the writers to finish, then stop the readers")
            writers_done.set()

        cbl_info(
            "Slowest request of each operation: "
            + ", ".join(f"{name} {seconds:.1f}s" for name, seconds in sorted(run.slowest.items()))
        )

        self.mark_test_step(
            "Leave the database online with the config it started with, and wait for every node to run that config"
        )
        try:
            await sg_cluster.create_database(DB_NAME, config)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise
            await sg_cluster.update_database_config(DB_NAME, config)

        self.mark_test_step(
            "Check that every request returned within 30 seconds with a status its operation allows, "
            "and that none returned a 500"
        )
        assert not run.violations, f"{len(run.violations)} requests broke the rules (seed {run.seed}):\n" + "\n".join(
            str(v) for v in run.violations
        )
