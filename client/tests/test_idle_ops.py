"""
Tests for cbltest.api.idleops, which compares Sync Gateway's idle_kv_ops and idle_query_ops stats with Couchbase
Server's commands and query requests.
"""

import itertools
from collections import Counter
from collections.abc import Iterable
from unittest.mock import MagicMock, create_autospec

import pytest
from cbltest.api.couchbaseserver import CouchbaseServer, OpCounts
from cbltest.api.error import CblTimeoutError
from cbltest.api.idleops import (
    IdleOpSnapshot,
    document_commands,
    is_document_command,
    read_idle_op_snapshot,
    take_quiet_idle_op_snapshot,
)
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaystats import SyncGatewayStats

# Commands that Couchbase Server 7.6 and 8.0 nodes ran while idle, or with an idle Sync Gateway against them,
# that are not KV operations on a document.
NON_DOCUMENT_COMMANDS = [
    ("", "HELLO"),
    ("", "SASL_AUTH"),
    ("", "STAT"),
    ("", "SELECT_BUCKET"),
    ("", "GET_CLUSTER_CONFIG"),
    ("probe", "COLLECTIONS_GET_MANIFEST"),
    ("probe", "COLLECTIONS_SET_MANIFEST"),
    ("probe", "COMPACT_DB"),
    ("probe", "DCP_BUFFER_ACKNOWLEDGEMENT"),
    ("probe", "GET_ALL_VB_SEQNOS"),
    ("probe", "GET_CLUSTER_CONFIG"),
    ("probe", "SELECT_BUCKET"),
    ("probe", "SET_VBUCKET"),
    ("probe", "STAT"),
]

DOCUMENT_COMMANDS = [
    ("probe", "GET"),
    ("probe", "GET_META"),
    ("probe", "REPLACE"),
    ("probe", "TOUCH"),
    ("probe", "SUBDOC_MULTI_LOOKUP"),
]


@pytest.mark.parametrize(("bucket", "opcode"), NON_DOCUMENT_COMMANDS)
def test_non_document_command(bucket: str, opcode: str) -> None:
    assert not is_document_command(bucket, opcode)


@pytest.mark.parametrize(("bucket", "opcode"), DOCUMENT_COMMANDS)
def test_document_command(bucket: str, opcode: str) -> None:
    assert is_document_command(bucket, opcode)


def test_document_command_needs_a_bucket() -> None:
    # A command sent before its connection selects a bucket only sets up the connection, whatever its opcode.
    assert not is_document_command("", "GET")


def test_document_commands_keeps_only_document_commands() -> None:
    commands = Counter({("probe", "GET"): 3, ("probe", "STAT"): 40, ("", "HELLO"): 2, ("other", "TOUCH"): 1})
    assert document_commands(commands) == Counter({("probe", "GET"): 3, ("other", "TOUCH"): 1})


def _stats(idle_kv_ops: int, idle_query_ops: int = 0) -> SyncGatewayStats:
    return SyncGatewayStats.from_expvar(
        {
            "syncgateway": {
                "global": {"resource_utilization": {"idle_kv_ops": idle_kv_ops, "idle_query_ops": idle_query_ops}},
                "per_db": {},
                "per_replication": {},
            }
        }
    )


def _sync_gateway(idle_kv_ops: Iterable[int], idle_query_ops: Iterable[int] | None = None) -> MagicMock:
    """A Sync Gateway whose idle_kv_ops and idle_query_ops stats read each value in turn."""
    sg = create_autospec(SyncGateway, instance=True)
    sg.get_stats.side_effect = (
        _stats(kv, query) for kv, query in zip(idle_kv_ops, idle_query_ops or itertools.repeat(0), strict=False)
    )
    return sg


def _counts(
    commands: dict[tuple[str, str], int], kv_ops: dict[tuple[str, str], int] | None = None, query_requests: int = 0
) -> OpCounts:
    return OpCounts(commands, kv_ops or {}, query_requests)


def _couchbase_server(readings: Iterable[OpCounts]) -> MagicMock:
    """A Couchbase Server node whose counts read each value in turn."""
    cbs = create_autospec(CouchbaseServer, instance=True)
    cbs.get_op_counts.side_effect = iter(readings)
    return cbs


@pytest.mark.asyncio
async def test_read_sums_every_node() -> None:
    sync_gateways = [_sync_gateway([3], [1]), _sync_gateway([4], [2])]
    couchbase_servers = [
        _couchbase_server([_counts({("probe", "GET"): 10, ("probe", "STAT"): 1}, {("probe", "get"): 10}, 3)]),
        _couchbase_server(
            [_counts({("probe", "GET"): 5, ("other", "GET"): 2}, {("probe", "get"): 5, ("other", "get"): 2})]
        ),
    ]

    snapshot = await read_idle_op_snapshot(sync_gateways, couchbase_servers)

    assert snapshot == IdleOpSnapshot(
        7,
        3,
        Counter({("probe", "GET"): 15, ("probe", "STAT"): 1, ("other", "GET"): 2}),
        Counter({("probe", "get"): 15, ("other", "get"): 2}),
        3,
    )


def test_unmatched_commands_leaves_out_other_commands() -> None:
    snapshot = IdleOpSnapshot(7, 0, Counter({("probe", "GET"): 10, ("probe", "STAT"): 40}), Counter(), 0)
    assert snapshot.unmatched_commands == 3


@pytest.mark.asyncio
async def test_quiet_snapshot_kept_when_nothing_moved() -> None:
    sg = _sync_gateway([5, 5])
    cbs = _couchbase_server([_counts({("probe", "GET"): 10}, {("probe", "get"): 10})] * 2)

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot == IdleOpSnapshot(5, 0, Counter({("probe", "GET"): 10}), Counter({("probe", "get"): 10}), 0)
    assert sg.get_stats.await_count == 2
    assert cbs.get_op_counts.await_count == 2


@pytest.mark.asyncio
async def test_quiet_snapshot_retried_when_sync_gateway_moved() -> None:
    sg = _sync_gateway([5, 6, 6, 6])
    cbs = _couchbase_server([_counts({("probe", "GET"): 10})] * 4)

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.idle_kv_ops == 6
    assert sg.get_stats.await_count == 4


@pytest.mark.asyncio
async def test_quiet_snapshot_retried_when_document_command_ran() -> None:
    sg = _sync_gateway([5] * 4)
    cbs = _couchbase_server(
        [
            _counts({("probe", "GET"): 10}),
            _counts({("probe", "GET"): 11}),
            _counts({("probe", "GET"): 11}),
            _counts({("probe", "GET"): 11}),
        ]
    )

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.commands == Counter({("probe", "GET"): 11})
    assert cbs.get_op_counts.await_count == 4


@pytest.mark.asyncio
async def test_quiet_snapshot_retried_when_kv_ops_moved() -> None:
    # A node reads kv_ops a moment before its command counts, so kv_ops can still be catching up.
    sg = _sync_gateway([5] * 4)
    cbs = _couchbase_server(
        [
            _counts({("probe", "GET"): 10}, {("probe", "get"): 8}),
            _counts({("probe", "GET"): 10}, {("probe", "get"): 10}),
            _counts({("probe", "GET"): 10}, {("probe", "get"): 10}),
            _counts({("probe", "GET"): 10}, {("probe", "get"): 10}),
        ]
    )

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.kv_ops == Counter({("probe", "get"): 10})
    assert cbs.get_op_counts.await_count == 4


@pytest.mark.asyncio
async def test_quiet_snapshot_retried_when_idle_query_ops_moved() -> None:
    sg = _sync_gateway([5] * 4, [1, 2, 2, 2])
    cbs = _couchbase_server([_counts({("probe", "GET"): 10}, query_requests=2)] * 4)

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.idle_query_ops == 2
    assert sg.get_stats.await_count == 4


@pytest.mark.asyncio
async def test_quiet_snapshot_retried_when_query_ran() -> None:
    sg = _sync_gateway([5] * 4, [2] * 4)
    cbs = _couchbase_server(
        [
            _counts({("probe", "GET"): 10}, query_requests=1),
            _counts({("probe", "GET"): 10}, query_requests=2),
            _counts({("probe", "GET"): 10}, query_requests=2),
            _counts({("probe", "GET"): 10}, query_requests=2),
        ]
    )

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.query_requests == 2
    assert cbs.get_op_counts.await_count == 4


@pytest.mark.asyncio
async def test_quiet_snapshot_kept_when_only_other_commands_ran() -> None:
    # Couchbase Server runs STAT on its own all the time, so it must not stop a reading being kept.
    sg = _sync_gateway([5, 5])
    cbs = _couchbase_server(
        [_counts({("probe", "GET"): 10, ("probe", "STAT"): 1}), _counts({("probe", "GET"): 10, ("probe", "STAT"): 9})]
    )

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0)

    assert snapshot.commands == Counter({("probe", "GET"): 10, ("probe", "STAT"): 1})


@pytest.mark.asyncio
async def test_quiet_snapshot_keeps_sample_with_fewest_unmatched_commands() -> None:
    # The first and last quiet readings land while a task Sync Gateway has not counted yet is paused: Couchbase
    # Server has run its 3 commands, but the stat does not have them. Only the middle reading is settled.
    sg = _sync_gateway([10, 10, 13, 13, 13, 13])
    cbs = _couchbase_server(
        [_counts({("probe", "GET"): 23})] * 4 + [_counts({("probe", "GET"): 26})] * 2,
    )

    snapshot = await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0, samples=3, sample_interval=0)

    assert snapshot.idle_kv_ops == 13
    assert snapshot.commands == Counter({("probe", "GET"): 23})
    assert sg.get_stats.await_count == 6


@pytest.mark.asyncio
async def test_quiet_snapshot_times_out_when_counters_never_still() -> None:
    sg = _sync_gateway(itertools.count())
    cbs = _couchbase_server(itertools.repeat(_counts({("probe", "GET"): 10})))

    with pytest.raises(CblTimeoutError, match="idle operation counters stayed still for 0s only 0 of 1 times"):
        await take_quiet_idle_op_snapshot([sg], [cbs], quiet_window=0, timeout=0.05)
