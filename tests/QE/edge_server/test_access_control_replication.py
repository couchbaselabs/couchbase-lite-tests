from datetime import timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorStatus,
    ReplicatorType,
)

SCRIPT_DIR = Path(__file__).parent
CONFIG = str(SCRIPT_DIR / "config" / "test_access_control.json")
USERS = SCRIPT_DIR / "config" / "test_access_control_users.json"
USERS_FILE = "/home/ec2-user/user/access_control_users.json"
PASSWORD = "password"
HOTELS = "travel.hotels"
AIRLINES = "travel.airlines"


async def _write_local(db: Database, collection: str, doc_ids: list[str]) -> None:
    """Create `doc_ids` in `collection` of the local database."""
    async with db.batch_updater() as updater:
        for doc_id in doc_ids:
            updater.upsert_document(collection, doc_id, [{"origin": "cbl"}])


async def _es_ids(edge_server: EdgeServer, collection: str) -> set[str]:
    """Document IDs in `collection` (scope.collection) of `travel` on Edge Server."""
    scope, name = collection.split(".")
    return {row.id for row in (await edge_server.get_all_documents("travel", scope, name)).rows}


async def _local_ids(db: Database, collection: str) -> set[str]:
    """Document IDs in `collection` of the local database."""
    return {doc.id for doc in (await db.get_all_documents(collection))[collection]}


async def _replicate(
    db: Database,
    edge_server: EdgeServer,
    user: str,
    replicator_type: ReplicatorType = ReplicatorType.PUSH_AND_PULL,
    collections: list[str] | None = None,
) -> ReplicatorStatus:
    """Run a one-shot replicator against `travel` on Edge Server as `user`, until it stops."""
    replicator = Replicator(
        db,
        edge_server.replication_url("travel"),
        replicator_type=replicator_type,
        continuous=False,
        authenticator=ReplicatorBasicAuthenticator(user, PASSWORD),
        collections=[ReplicatorCollectionEntry(collections or [HOTELS])],
    )
    await replicator.start()
    return await replicator.wait_for(ReplicatorActivityLevel.STOPPED, timeout=timedelta(seconds=60))


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestAccessControlReplication(CBLTestClass):
    async def _setup(self, cblpytest: CBLPyTest, prefix: str) -> tuple[EdgeServer, Database]:
        """
        Start Edge Server with access control on, seed `<prefix>_es_hotels` and `<prefix>_es_airlines`,
        and reset local database `db1` with both collections.
        """
        es = cblpytest.edge_servers[0]
        await es.write_file(USERS_FILE, USERS.read_text())
        admin = await es.configure_dataset(db_name="travel", config_file=CONFIG)
        await admin.put_document_with_id({"origin": "es"}, f"{prefix}_es_hotels", "travel", "travel", "hotels")
        await admin.put_document_with_id({"origin": "es"}, f"{prefix}_es_airlines", "travel", "travel", "airlines")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[HOTELS, AIRLINES])
        return admin, dbs[0]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_read_write_user_syncs_both_ways(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, "rw")

        self.mark_test_step("Create 3 local docs, and push and pull as `rw` (`travel.*`: read, write)")
        pushed = [f"rw_cbl_{i}" for i in range(3)]
        await _write_local(db, HOTELS, pushed)
        status = await _replicate(db, admin, "rw")

        self.mark_test_step(
            "Verify the replicator stopped without error, the docs were pushed, and the seed was pulled"
        )
        assert status.error is None, f"Read-write replication failed: {status.error}"
        assert set(pushed) <= await _es_ids(admin, HOTELS), "The local docs did not reach Edge Server"
        assert "rw_es_hotels" in await _local_ids(db, HOTELS), "The seeded doc was not pulled"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_read_only_user_can_pull(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, "ro")

        self.mark_test_step("Pull as `ro` (`travel.*`: read)")
        status = await _replicate(db, admin, "ro", ReplicatorType.PULL)

        self.mark_test_step("Verify the pull stopped without error and the seed was pulled")
        assert status.error is None, f"Read-only pull failed: {status.error}"
        assert "ro_es_hotels" in await _local_ids(db, HOTELS), "The seeded doc was not pulled"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_read_only_user_cannot_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, "rop")

        self.mark_test_step("Create 3 local docs, and push and pull as `ro`")
        pushed = [f"rop_cbl_{i}" for i in range(3)]
        await _write_local(db, HOTELS, pushed)
        status = await _replicate(db, admin, "ro")

        self.mark_test_step(
            "Verify the replicator is refused as pull-only (403), and none of the docs reached Edge Server"
        )
        assert status.error is not None and status.error.code == 403, f"Expected a pull-only 403, got {status.error}"
        assert not set(pushed) & await _es_ids(admin, HOTELS), "A read-only user wrote to Edge Server"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_syncs_every_collection(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, "adm")

        self.mark_test_step("Create a local doc in each collection, and push and pull both as `admin_user`")
        await _write_local(db, HOTELS, ["adm_cbl_hotels"])
        await _write_local(db, AIRLINES, ["adm_cbl_airlines"])
        status = await _replicate(db, admin, "admin_user", collections=[HOTELS, AIRLINES])

        self.mark_test_step("Verify the replicator stopped without error and both collections synced both ways")
        assert status.error is None, f"Admin replication failed: {status.error}"
        assert "adm_es_hotels" in await _local_ids(db, HOTELS), "travel.hotels was not pulled"
        assert "adm_es_airlines" in await _local_ids(db, AIRLINES), "travel.airlines was not pulled"
        assert "adm_cbl_hotels" in await _es_ids(admin, HOTELS), "travel.hotels was not pushed"
        assert "adm_cbl_airlines" in await _es_ids(admin, AIRLINES), "travel.airlines was not pushed"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_collection_grants_apply_to_sync(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, "mix")

        self.mark_test_step("Pull both collections as `mixed`, and verify both seeded docs arrive")
        status = await _replicate(db, admin, "mixed", ReplicatorType.PULL, [HOTELS, AIRLINES])
        assert status.error is None, f"Pulling both readable collections failed: {status.error}"
        assert "mix_es_hotels" in await _local_ids(db, HOTELS), "The readable travel.hotels was not pulled"
        assert "mix_es_airlines" in await _local_ids(db, AIRLINES), "The readable travel.airlines was not pulled"

        self.mark_test_step("Push a doc to `travel.hotels` as `mixed`, and verify it lands")
        await _write_local(db, HOTELS, ["mix_cbl_hotels"])
        status = await _replicate(db, admin, "mixed", ReplicatorType.PUSH, [HOTELS])
        assert status.error is None, f"Pushing to the writable travel.hotels failed: {status.error}"
        assert "mix_cbl_hotels" in await _es_ids(admin, HOTELS), "The writable travel.hotels did not accept the push"

        self.mark_test_step("Push a doc to `travel.airlines` as `mixed`, and verify it does not land")
        await _write_local(db, AIRLINES, ["mix_cbl_airlines"])
        await _replicate(db, admin, "mixed", ReplicatorType.PUSH, [AIRLINES])
        assert "mix_cbl_airlines" not in await _es_ids(admin, AIRLINES), "The read-only travel.airlines accepted a push"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("user", ["none", "wo", "names_rw"], ids=["no_access", "write_only", "other_database"])
    async def test_user_without_read_access_is_refused(
        self, cblpytest: CBLPyTest, dataset_path: Path, user: str
    ) -> None:
        self.mark_test_step("Start Edge Server with access control on, seed one doc per collection, and reset `db1`")
        admin, db = await self._setup(cblpytest, user)

        self.mark_test_step("Create a local doc, and push and pull `travel` as the user")
        await _write_local(db, HOTELS, [f"{user}_cbl_0"])
        status = await _replicate(db, admin, user)

        self.mark_test_step("Verify the replicator is refused and nothing crossed in either direction")
        assert status.error is not None, f"`{user}` replicated with `travel` without an error"
        assert f"{user}_es_hotels" not in await _local_ids(db, HOTELS), f"`{user}` pulled from `travel`"
        assert f"{user}_cbl_0" not in await _es_ids(admin, HOTELS), f"`{user}` pushed to `travel`"
