"""Unit tests for SyncGatewayStats, the model of the ``syncgateway`` section of ``GET /_expvar``"""

import pytest
from cbltest.api.error import CblTestError
from cbltest.api.syncgatewaystats import StatNotPresentError, SyncGatewayStats


def _expvar(**per_db: dict) -> dict:
    return {
        "syncgateway": {
            "global": {"resource_utilization": {"error_count": 2}},
            "per_db": per_db,
            "per_replication": {},
        }
    }


@pytest.fixture
def stats() -> SyncGatewayStats:
    return SyncGatewayStats.from_expvar(
        _expvar(
            travel={
                "database": {"doc_reads_bytes_blip": 10, "doc_writes_bytes_blip": 20},
                "delta_sync": {"deltas_sent": 3},
                "per_collection": {"inventory.hotel": {"import_count": 4}},
                "replications": {"rep1": {"sgr_deltas_sent": 5}},
            },
            posts={"database": {}},
        )
    )


class TestParsing:
    def test_reads_reported_stats(self, stats: SyncGatewayStats) -> None:
        travel = stats.db("travel")
        assert travel.database.doc_reads_bytes_blip == 10
        assert travel.database.doc_writes_bytes_blip == 20
        assert travel.delta_sync.deltas_sent == 3
        assert travel.collection("inventory", "hotel").import_count == 4
        assert travel.replications["rep1"].sgr_deltas_sent == 5

    def test_global_alias(self, stats: SyncGatewayStats) -> None:
        assert stats.global_stats.resource_utilization.error_count == 2

    def test_keeps_unknown_keys_as_extras(self) -> None:
        stats = SyncGatewayStats.from_expvar(_expvar(db={"database": {"new_stat": 7}, "new_group": {"x": 1}}))
        db = stats.db("db")
        assert db.database.model_extra == {"new_stat": 7}
        assert db.model_extra == {"new_group": {"x": 1}}


class TestMissingStats:
    def test_missing_stat_names_its_path(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(
            StatNotPresentError,
            match=r"^Sync Gateway did not report syncgateway\.per_db\.posts\.database\.doc_reads_bytes_blip$",
        ):
            _ = stats.db("posts").database.doc_reads_bytes_blip

    def test_missing_group_names_its_path(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(StatNotPresentError, match=r"syncgateway\.per_db\.posts\.delta_sync$"):
            _ = stats.db("posts").delta_sync

    def test_aliased_group_path_uses_expvar_key(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(StatNotPresentError, match=r"syncgateway\.global\.config$"):
            _ = stats.global_stats.config

    def test_dict_child_path_includes_key(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(
            StatNotPresentError, match=r"syncgateway\.per_db\.travel\.replications\.rep1\.sgr_deltas_recv$"
        ):
            _ = stats.db("travel").replications["rep1"].sgr_deltas_recv

    def test_is_attribute_error_and_cbl_test_error(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(AttributeError):
            _ = stats.db("posts").delta_sync
        with pytest.raises(CblTestError):
            _ = stats.db("posts").delta_sync

    def test_hasattr_and_getattr_default(self, stats: SyncGatewayStats) -> None:
        posts = stats.db("posts")
        assert not hasattr(posts, "delta_sync")
        assert getattr(posts, "shared_bucket_import", None) is None
        assert hasattr(stats.db("travel"), "delta_sync")

    def test_unknown_attribute_is_plain_attribute_error(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(AttributeError) as exc_info:
            _ = stats.db("travel").not_a_stat
        assert not isinstance(exc_info.value, StatNotPresentError)

    def test_unknown_database_lists_reported_ones(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(StatNotPresentError, match=r"'missing', it reports: travel, posts$"):
            stats.db("missing")

    def test_unknown_collection_lists_reported_ones(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(
            StatNotPresentError,
            match=r"'inventory\.route' in syncgateway\.per_db\.travel, it reports: inventory\.hotel$",
        ):
            stats.db("travel").collection("inventory", "route")

    def test_no_collections_reports_none(self, stats: SyncGatewayStats) -> None:
        with pytest.raises(StatNotPresentError, match=r"it reports: none$"):
            stats.db("posts").collection("_default", "_default")
