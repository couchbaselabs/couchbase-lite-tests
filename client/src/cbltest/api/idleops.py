"""
Compares Sync Gateway's ``idle_kv_ops`` stat with the document commands Couchbase Server ran, and with
Couchbase Server's ``kv_ops``, the series Capella's idle-cluster hibernation check subtracts the stat from.
Also compares Sync Gateway's ``idle_query_ops`` stat with the query requests Couchbase Server ran.
"""

import asyncio
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblTimeoutError
from cbltest.api.syncgateway import SyncGateway

# Commands that set up connections, stream DCP, manage collections, or report state, rather than reading or
# writing a document. Sync Gateway does not count these as KV operations, and Couchbase Server sends some of them
# itself, such as STAT.
NON_DOCUMENT_OPCODE_PREFIXES = ("COLLECTIONS_", "DCP_", "SASL_")
NON_DOCUMENT_OPCODES = frozenset(
    {
        "COMPACT_DB",
        "DEL_VBUCKET",
        "DISABLE_TRAFFIC",
        "ENABLE_TRAFFIC",
        "GET_ALL_VB_SEQNOS",
        "GET_CLUSTER_CONFIG",
        "GET_ERROR_MAP",
        "GET_FAILOVER_LOG",
        "GET_VBUCKET",
        "HELLO",
        "NOOP",
        "SELECT_BUCKET",
        "SET_BUCKET_DATA_LIMIT_EXCEEDED",
        "SET_CLUSTER_CONFIG",
        "SET_PARAM",
        "SET_VBUCKET",
        "STAT",
    }
)

CommandCounts = Counter[tuple[str, str]]


def is_document_command(bucket: str, opcode: str) -> bool:
    """
    Whether a Couchbase Server command is a KV operation on a document. A command run before its connection
    selected a bucket has an empty bucket name, and only ever sets up the connection.
    """
    return bucket != "" and opcode not in NON_DOCUMENT_OPCODES and not opcode.startswith(NON_DOCUMENT_OPCODE_PREFIXES)


def document_commands(commands: CommandCounts) -> CommandCounts:
    """The counts of the commands that are KV operations on a document, keyed by (bucket, opcode)."""
    return Counter({key: count for key, count in commands.items() if is_document_command(*key)})


@dataclass(frozen=True)
class IdleOpSnapshot:
    idle_kv_ops: int
    """The sum of the idle_kv_ops stat over every Sync Gateway node"""

    idle_query_ops: int
    """The sum of the idle_query_ops stat over every Sync Gateway node"""

    commands: CommandCounts
    """The commands every Couchbase Server node has run, by (bucket, opcode)"""

    kv_ops: CommandCounts
    """The kv_ops series of every Couchbase Server node, by (bucket, op)"""

    query_requests: int
    """The query requests every Couchbase Server node has run"""

    @property
    def unmatched_commands(self) -> int:
        """The document commands Couchbase Server has run beyond what Sync Gateway counted as idle"""
        return document_commands(self.commands).total() - self.idle_kv_ops


async def read_idle_op_snapshot(
    sync_gateways: Sequence[SyncGateway], couchbase_servers: Sequence[CouchbaseServer]
) -> IdleOpSnapshot:
    """Reads the counters once, Sync Gateway's first."""
    idle_kv_ops = 0
    idle_query_ops = 0
    for sg in sync_gateways:
        resource_utilization = (await sg.get_stats()).global_stats.resource_utilization
        idle_kv_ops += resource_utilization.idle_kv_ops
        idle_query_ops += resource_utilization.idle_query_ops
    commands: CommandCounts = Counter()
    kv_ops: CommandCounts = Counter()
    query_requests = 0
    for cbs in couchbase_servers:
        counts = await cbs.get_op_counts()
        commands.update(counts.commands)
        kv_ops.update(counts.ops)
        query_requests += counts.query_requests
    return IdleOpSnapshot(idle_kv_ops, idle_query_ops, commands, kv_ops, query_requests)


def _is_still(before: IdleOpSnapshot, after: IdleOpSnapshot) -> bool:
    return (
        before.idle_kv_ops == after.idle_kv_ops
        and before.idle_query_ops == after.idle_query_ops
        and document_commands(before.commands) == document_commands(after.commands)
        and before.kv_ops == after.kv_ops
        and before.query_requests == after.query_requests
    )


async def take_quiet_idle_op_snapshot(
    sync_gateways: Sequence[SyncGateway],
    couchbase_servers: Sequence[CouchbaseServer],
    quiet_window: float = 0.1,
    timeout: float = 120,
    samples: int = 1,
    sample_interval: float = 0.5,
) -> IdleOpSnapshot:
    """
    Reads the counters at a moment when none of them is moving. Sync Gateway counts the operations of a background
    task when the task ends, so a reading taken in the middle of one has operations that Couchbase Server has run
    but Sync Gateway has not counted yet. The counters are read twice, quiet_window seconds apart, and the reading
    is kept only if none moved in between. Commands that are not document commands may move. Watching kv_ops as
    well also covers the moment by which it trails the command counts in each read.

    A task that pauses for longer than quiet_window between its last operation and its end still looks quiet. To
    get past that, samples quiet readings are taken, sample_interval seconds apart, and the one with the fewest
    unmatched commands is kept, since a task Sync Gateway has not counted yet can only add to them.

    :raises CblTimeoutError: If the counters did not stay still for quiet_window seconds, samples times, within
        timeout seconds
    """
    deadline = time.monotonic() + timeout
    kept: list[IdleOpSnapshot] = []
    while time.monotonic() < deadline:
        before = await read_idle_op_snapshot(sync_gateways, couchbase_servers)
        await asyncio.sleep(quiet_window)
        after = await read_idle_op_snapshot(sync_gateways, couchbase_servers)
        if not _is_still(before, after):
            continue
        kept.append(before)
        if len(kept) == samples:
            return min(kept, key=lambda snapshot: snapshot.unmatched_commands)
        await asyncio.sleep(sample_interval)

    raise CblTimeoutError(
        f"The idle operation counters stayed still for {quiet_window}s only {len(kept)} of {samples} times "
        f"within {timeout}s"
    )
