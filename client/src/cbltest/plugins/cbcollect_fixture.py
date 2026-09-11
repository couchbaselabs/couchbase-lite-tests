import asyncio
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_error, cbl_info


async def run_cbcollects(couchbase_servers: Sequence[CouchbaseServer], output_dir: Path) -> list[Path]:
    """
    Runs cbcollect_info on every given Couchbase Server node in parallel, downloading each
    resulting archive into output_dir, and logs a summary of what was collected.

    A node that fails costs only its own archive, since one unreachable host should not cost
    the diagnostics from the rest. Losing every node is different: it means the run produced
    no diagnostics at all, so that raises.

    :param couchbase_servers: The Couchbase Server nodes to collect from
    :param output_dir: Local directory to download the resulting archives into
    :return: The local paths of the archives that were successfully collected
    :raises ExceptionGroup: If every node failed, holding one exception per node
    """

    async def _collect_one(cbs: CouchbaseServer) -> Path | Exception:
        try:
            return await cbs.collect_logs(output_dir)
        except Exception as e:
            cbl_error(f"cbcollect: failed to collect logs from {cbs}: {e}", include_stack=False)
            return e

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(_collect_one(cbs)) for cbs in couchbase_servers]

    results = [task.result() for task in tasks]
    collected = [result for result in results if isinstance(result, Path)]
    failures = [result for result in results if isinstance(result, Exception)]
    cbl_info(
        f"cbcollect: collected {len(collected)}/{len(results)} node(s) to {output_dir}: {[str(p) for p in collected]}"
    )
    if failures:
        cbl_error(
            f"cbcollect: {len(failures)}/{len(results)} node(s) failed to collect logs, see errors above",
            include_stack=False,
        )
    if failures and not collected:
        raise ExceptionGroup("cbcollect collected nothing: every Couchbase Server node failed", failures)
    return collected


@pytest_asyncio.fixture(scope="session", autouse=True)
async def cbcollect_session(cblpytest: CBLPyTest) -> AsyncGenerator[None]:
    yield
    # CBG-5733 sets this flag from CouchbaseCluster.create_database the moment its Sync
    # Gateway call times out; collection itself waits until here, session end, so that a
    # test hitting this doesn't stall behind a multi-minute cbcollect_info run of its own --
    # the same reason sgcollect/es_collect wait for teardown instead of collecting inline.
    if CBLPyTestGlobal.cbcollect_needed:
        servers = [cbs for cluster in cblpytest.clusters for cbs in cluster.couchbase_servers]
        try:
            await run_cbcollects(servers, Path.cwd())
        except* Exception as eg:
            # A diagnostics-collection attempt must never fail the session teardown itself --
            # e.g. a local --server cbs run has a real Couchbase Server but no AWS
            # shell2http/Caddy sidecar for collect_logs to reach, and any other transient
            # infra failure deserves the same treatment.  run_cbcollects already logged each
            # node's own error; this is just the last-resort backstop.
            cbl_error(
                f"cbcollect: giving up, no logs collected from any node: {eg.exceptions}",
                include_stack=False,
            )
