"""Tests for reading per-command, kv_ops and query request counts out of a node's GET /metrics output."""

from unittest.mock import AsyncMock, patch

import pytest
from cbltest.api.couchbaseserver import (
    CouchbaseServer,
    OpCounts,
    parse_kv_command_counts,
    parse_kv_op_counts,
    parse_query_request_count,
)

# Trimmed from a Couchbase Server 8.0 node: the _bucket and _sum series and other metrics sit next to
# the _count series and must be left out. The n1ql_requests_* series are by duration, and must not be added to
# n1ql_requests.
METRICS = """\
# HELP kv_cmd_duration_seconds Per-opcode histogram of time taken to execute operations
# TYPE kv_cmd_duration_seconds histogram
kv_cmd_duration_seconds_bucket{bucket="",opcode="HELLO",le="0.001"} 13
kv_cmd_duration_seconds_sum{bucket="",opcode="HELLO"} 0.0021
kv_cmd_duration_seconds_count{bucket="",opcode="HELLO"} 13
kv_cmd_duration_seconds_count{bucket="probe",opcode="GET"} 102
kv_cmd_duration_seconds_count{bucket="probe",opcode="GET_META"} 204
kv_cmd_duration_seconds_count{opcode="GET_META",bucket="other"} 7
kv_ops{bucket="probe",op="get_meta"} 17
kv_ops{bucket="probe",op="set_meta"} 0
kv_ops{bucket="probe",op="set"} 117
kv_ops{bucket="probe",op="get",result="hit"} 35268
kv_ops{bucket="probe",op="get",result="miss"} 31489
kv_ops{bucket="probe",op="cas",result="hit"} 4360
kv_ops{bucket="probe",op="cas",result="badval"} 139
kv_curr_connections 42
n1ql_requests 31
n1ql_requests_250ms 4
n1ql_selects 29
"""


def test_parse_kv_command_counts() -> None:
    assert parse_kv_command_counts(METRICS) == {
        ("", "HELLO"): 13,
        ("probe", "GET"): 102,
        ("probe", "GET_META"): 204,
        ("other", "GET_META"): 7,
    }


def test_parse_kv_command_counts_no_commands() -> None:
    assert parse_kv_command_counts("kv_curr_connections 42\n") == {}


def test_parse_kv_op_counts_sums_results() -> None:
    assert parse_kv_op_counts(METRICS) == {
        ("probe", "get_meta"): 17,
        ("probe", "set_meta"): 0,
        ("probe", "set"): 117,
        ("probe", "get"): 35268 + 31489,
        ("probe", "cas"): 4360 + 139,
    }


def test_parse_kv_op_counts_no_ops() -> None:
    assert parse_kv_op_counts("kv_curr_connections 42\n") == {}


def test_parse_query_request_count() -> None:
    assert parse_query_request_count(METRICS) == 31


def test_parse_query_request_count_with_labels() -> None:
    assert parse_query_request_count('n1ql_requests{instance="n1ql"} 7\n') == 7


def test_parse_query_request_count_no_query_service() -> None:
    # A node that does not run the Query Service has no n1ql series.
    assert parse_query_request_count("kv_curr_connections 42\n") == 0


def test_parse_kv_command_counts_needs_bucket_label() -> None:
    # Every count line has a bucket label, so one without it means the format changed.
    with pytest.raises(KeyError, match="bucket"):
        parse_kv_command_counts('kv_cmd_duration_seconds_count{opcode="GET"} 1\n')


@pytest.mark.asyncio
async def test_get_op_counts_reads_metrics_once() -> None:
    with (
        patch("cbltest.api.couchbaseserver.Cluster", autospec=True),
        patch("cbltest.api.couchbaseserver.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.caddy.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.couchbaseserver.Shell2HttpClient", autospec=True),
    ):
        server = CouchbaseServer(url="https://cbs.example.com", username="user", password="pass")
    send = AsyncMock(return_value=METRICS)
    with patch.object(CouchbaseServer, "_CouchbaseServer__send_request", send):
        counts = await server.get_op_counts()

    send.assert_awaited_once_with("get", "/metrics")
    assert counts == OpCounts(parse_kv_command_counts(METRICS), parse_kv_op_counts(METRICS), 31)
