from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from conftest import fake_sync_gateways


def test_round_robin_node_cycles_through_all_nodes():
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        picks = [cluster.round_robin_node for _ in range(7)]
        assert picks == [
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
        ]


def test_round_robin_node_single_node():
    with fake_sync_gateways(1) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(3):
            assert cluster.round_robin_node is sync_gateways[0]


def test_random_node_returns_a_cluster_member():
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(20):
            assert cluster.random_node in sync_gateways
