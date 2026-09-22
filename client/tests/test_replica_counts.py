"""
Cover how a bucket and its indexes get their replica count.  Buckets are reused between tests,
so the count the first caller picks is the one every later caller lives with.
"""

from typing import Any
from unittest.mock import patch

import pytest
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblTestError
from couchbase.diagnostics import ServiceType


def node(services: list[str], membership: str = "active", status: str = "healthy") -> dict[str, Any]:
    return {"services": services, "clusterMembership": membership, "status": status}


ONE_NODE = [node(["kv", "index", "n1ql"])]
TWO_NODES = ONE_NODE * 2
SPLIT_SERVICES = [node(["kv"]), node(["kv"]), node(["index", "n1ql"])]
FAILED_OVER = [node(["kv", "index", "n1ql"]), node(["kv", "index", "n1ql"], membership="inactiveFailed")]


def make_server(nodes: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> CouchbaseServer:
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        server = CouchbaseServer("cbs.example.com", "user", "pass")
    monkeypatch.setattr(server, "_get_cluster_info", lambda: {"nodes": nodes})
    return server


def test_single_node_cluster_has_nowhere_to_put_a_replica(monkeypatch: pytest.MonkeyPatch) -> None:
    server = make_server(ONE_NODE, monkeypatch)
    assert server.replica_count(ServiceType.KeyValue) == 0
    assert server.replica_count(ServiceType.Query) == 0


def test_multi_node_cluster_keeps_a_second_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    server = make_server(TWO_NODES, monkeypatch)
    assert server.replica_count(ServiceType.KeyValue) == 1
    assert server.replica_count(ServiceType.Query) == 1


def test_each_service_is_counted_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """A service can run on fewer nodes than the cluster has, and only its own count decides."""
    server = make_server(SPLIT_SERVICES, monkeypatch)
    assert server.node_count(ServiceType.KeyValue) == 2
    assert server.node_count(ServiceType.Query) == 1
    assert server.replica_count(ServiceType.KeyValue) == 1
    assert server.replica_count(ServiceType.Query) == 0


def test_a_failed_over_node_cannot_hold_a_replica(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node a failover left behind is still listed, but nothing can be placed on it."""
    server = make_server(FAILED_OVER, monkeypatch)
    assert server.node_count(ServiceType.KeyValue) == 1
    assert server.replica_count(ServiceType.KeyValue) == 0


def test_a_service_no_node_reports_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A silent zero would read as a real topology."""
    server = make_server(TWO_NODES, monkeypatch)
    with pytest.raises(CblTestError):
        server.node_count(ServiceType.Management)
