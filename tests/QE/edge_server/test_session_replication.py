import secrets
from datetime import timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.error_types import ErrorResponseBody
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorAuthenticator,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorSessionAuthenticator,
    ReplicatorStatus,
    ReplicatorType,
)
from cbltest.api.syncgateway import get_basic_auth_headers

SCRIPT_DIR = Path(__file__).parent
CONFIG = str(SCRIPT_DIR / "config" / "test_session.json")
USERS = SCRIPT_DIR / "config" / "test_session_users.json"
USERS_FILE = "/home/ec2-user/user/session_users.json"
DB = "travel"
OTHER_DB = "names"
PASSWORD = "password"
HOTELS = "travel.hotels"
AIRLINES = "travel.airlines"
DEFAULT = "_default._default"


def _is_auth_rejection(error: ErrorResponseBody | None) -> bool:
    """
    Whether a replicator error is the WebSocket upgrade being refused for want of credentials.
    A browser cannot see the status of a refused upgrade, so CBL-JS reports only "Failed to connect".
    """
    if error is None:
        return False
    if error.domain == "CBL-JS" and "Failed to connect" in error.message:
        return True
    return error.code in (401, 10401) or "401" in error.message or "unauthorized" in error.message.lower()


def _describe(error: ErrorResponseBody | None) -> str:
    """A replicator error as ``domain/code: message``, for assertion messages."""
    return "no error" if error is None else f"{error.domain}/{error.code}: {error.message}"


async def _write_local(db: Database, collection: str, doc_ids: list[str]) -> None:
    """Create `doc_ids` in `collection` of the local database."""
    async with db.batch_updater() as updater:
        for doc_id in doc_ids:
            updater.upsert_document(collection, doc_id, [{"origin": "cbl"}])


async def _es_ids(edge_server: EdgeServer, collection: str | None = HOTELS, db: str = DB) -> set[str]:
    """Document IDs in `collection` (scope.collection, or None for the default collection) of `db` on Edge Server."""
    scope, name = collection.split(".") if collection else ("", "")
    return {row.id for row in (await edge_server.get_all_documents(db, scope=scope, collection=name)).rows}


async def _local_ids(db: Database, collection: str = HOTELS) -> set[str]:
    """Document IDs in `collection` of the local database."""
    return {doc.id for doc in (await db.get_all_documents(collection))[collection]}


async def _replicate(
    db: Database,
    edge_server: EdgeServer,
    authenticator: ReplicatorAuthenticator | None,
    replicator_type: ReplicatorType = ReplicatorType.PUSH_AND_PULL,
    collections: list[str] | None = None,
    db_name: str = DB,
    continuous: bool = False,
    wait_for: ReplicatorActivityLevel = ReplicatorActivityLevel.STOPPED,
) -> tuple[Replicator, ReplicatorStatus]:
    """Run a replicator against `db_name` on Edge Server until it reaches `wait_for`."""
    replicator = Replicator(
        db,
        edge_server.replication_url(db_name),
        replicator_type=replicator_type,
        continuous=continuous,
        authenticator=authenticator,
        collections=[ReplicatorCollectionEntry(collections or [HOTELS])],
    )
    await replicator.start()
    return replicator, await replicator.wait_for(wait_for, timeout=timedelta(seconds=60))


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestEdgeServerSessionReplication(CBLTestClass):
    async def _setup(self, cblpytest: CBLPyTest, prefix: str) -> tuple[EdgeServer, Database, Database]:
        """
        Start Edge Server on the session config, seed `<prefix>_es_hotels` and `<prefix>_es_airlines`,
        and reset local databases `db1` and `db2` in one call (a second reset closes the first).
        """
        es = cblpytest.edge_servers[0]
        await es.write_file(USERS_FILE, USERS.read_text())
        admin = await es.configure_dataset(db_name=DB, config_file=CONFIG)
        await admin.put_document_with_id({"origin": "es"}, f"{prefix}_es_hotels", DB, "travel", "hotels")
        await admin.put_document_with_id({"origin": "es"}, f"{prefix}_es_airlines", DB, "travel", "airlines")
        db1, db2 = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1", "db2"], collections=[HOTELS, AIRLINES, DEFAULT]
        )
        return admin, db1, db2

    async def _mint_as(self, cblpytest: CBLPyTest, user: str, db: str = DB) -> str:
        """Mint a one-time session for `db` as `user`."""
        async with cblpytest.edge_servers[0].get_user_client(get_basic_auth_headers(user, PASSWORD)) as client:
            return (await client.create_session(db))["one_time_session_id"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_auth_push_pull(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "basic")

        self.mark_test_step("Create 5 local docs, and replicate as `rw` with basic auth")
        pushed = [f"basic_cbl_{i}" for i in range(5)]
        await _write_local(db, HOTELS, pushed)
        _, status = await _replicate(db, admin, ReplicatorBasicAuthenticator("rw", PASSWORD))
        assert status.error is None, f"Basic auth replication failed: {_describe(status.error)}"

        self.mark_test_step("Verify the 5 docs are on Edge Server and the seeded doc was pulled")
        assert set(pushed) <= await _es_ids(admin), "Local docs did not reach Edge Server"
        assert "basic_es_hotels" in await _local_ids(db), "The seeded doc was not pulled"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_auth_push_pull(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "sess")

        self.mark_test_step("Create 5 local docs, and replicate with a session as `rw`")
        pushed = [f"sess_cbl_{i}" for i in range(5)]
        await _write_local(db, HOTELS, pushed)
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "rw")))
        assert status.error is None, f"Session auth replication failed: {_describe(status.error)}"

        self.mark_test_step("Verify the 5 docs are on Edge Server and the seeded doc was pulled")
        assert set(pushed) <= await _es_ids(admin), "Local docs did not reach Edge Server"
        assert "sess_es_hotels" in await _local_ids(db), "The seeded doc was not pulled"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_auth_continuous_live_changes(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "live")

        self.mark_test_step("Start a continuous replicator with a session as `rw`, and wait for idle")
        replicator, status = await _replicate(
            db,
            admin,
            ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "rw")),
            continuous=True,
            wait_for=ReplicatorActivityLevel.IDLE,
        )
        assert status.error is None, f"Continuous session replication did not go idle: {_describe(status.error)}"

        self.mark_test_step("Write a doc on Edge Server and a doc locally")
        await admin.put_document_with_id({"origin": "es"}, "live_es_after", DB, "travel", "hotels")
        await _write_local(db, HOTELS, ["live_cbl_after"])

        self.mark_test_step("Verify both docs cross while the replicator stays error-free")
        for _ in range(10):
            status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
            assert status.error is None, f"Continuous session replication errored: {_describe(status.error)}"
            if "live_es_after" in await _local_ids(db) and "live_cbl_after" in await _es_ids(admin):
                break
        assert "live_es_after" in await _local_ids(db), "The live Edge Server change was not pulled"
        assert "live_cbl_after" in await _es_ids(admin), "The live local change was not pushed"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_one_time_false_gives_no_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "otf")

        self.mark_test_step("Verify POST /travel/_session?one_time=false as `rw` is rejected with 400")
        async with cblpytest.edge_servers[0].get_user_client(get_basic_auth_headers("rw", PASSWORD)) as client:
            with pytest.raises(CblEdgeServerBadResponseError) as e:
                await client.create_session(DB, one_time=False)
        assert e.value.code == 400, f"one_time=false: expected 400, got {e.value.code}"

        self.mark_test_step("Create a local doc, and replicate with no credentials")
        await _write_local(db, HOTELS, ["otf_cbl_0"])
        _, status = await _replicate(db, admin, None)

        self.mark_test_step("Verify the replicator is refused and nothing crossed in either direction")
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"
        assert "otf_cbl_0" not in await _es_ids(admin), "A doc was pushed without credentials"
        assert "otf_es_hotels" not in await _local_ids(db), "A doc was pulled without credentials"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reused_session_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset local databases `db1` and `db2`")
        admin, db, db2 = await self._setup(cblpytest, "reuse")

        self.mark_test_step("Replicate `db1` with a session as `rw`")
        session_id = await self._mint_as(cblpytest, "rw")
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(session_id))
        assert status.error is None, f"The first replication with the session failed: {_describe(status.error)}"

        self.mark_test_step("Create a local doc in `db2`, and replicate `db2` with the same session")
        await _write_local(db2, HOTELS, ["reuse_cbl_db2"])
        _, status = await _replicate(db2, admin, ReplicatorSessionAuthenticator(session_id))

        self.mark_test_step("Verify the replicator is refused and nothing crossed in either direction")
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"
        assert "reuse_cbl_db2" not in await _es_ids(admin), "A doc was pushed with a consumed session"
        assert "reuse_es_hotels" not in await _local_ids(db2), "A doc was pulled with a consumed session"

        self.mark_test_step("Verify `db2` replicates with a new session, and its doc is pushed")
        _, status = await _replicate(db2, admin, ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "rw")))
        assert status.error is None, f"Replication with a new session failed: {_describe(status.error)}"
        assert "reuse_cbl_db2" in await _es_ids(admin), "The doc was not pushed with a new session"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_for_other_database_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "xdb")

        self.mark_test_step("Replicate `travel` with a session for `names` as `admin_user`")
        session_id = await self._mint_as(cblpytest, "admin_user", OTHER_DB)
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(session_id))

        self.mark_test_step("Verify the replicator is refused and nothing was pulled")
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"
        assert "xdb_es_hotels" not in await _local_ids(db), "A doc was pulled with another database's session"

        self.mark_test_step("Create a local doc, and push it to `names` with the same session")
        await _write_local(db, DEFAULT, ["xdb_cbl_0"])
        _, status = await _replicate(
            db, admin, ReplicatorSessionAuthenticator(session_id), ReplicatorType.PUSH, [DEFAULT], OTHER_DB
        )

        self.mark_test_step("Verify the push succeeded")
        assert status.error is None, f"The session on its own database failed: {_describe(status.error)}"
        assert "xdb_cbl_0" in await _es_ids(admin, None, OTHER_DB), f"The doc was not pushed to `{OTHER_DB}`"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("session_id", [secrets.token_hex(16), "not-a-session"], ids=["unknown", "malformed"])
    async def test_invalid_session_rejected(self, cblpytest: CBLPyTest, dataset_path: Path, session_id: str) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "bad")

        self.mark_test_step("Create a local doc, and replicate with the case's session")
        await _write_local(db, HOTELS, ["bad_cbl_0"])
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(session_id))

        self.mark_test_step("Verify the replicator is refused and nothing crossed in either direction")
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"
        assert "bad_cbl_0" not in await _es_ids(admin), "A doc was pushed with an unissued session"
        assert "bad_es_hotels" not in await _local_ids(db), "A doc was pulled with an unissued session"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_restart_revokes_sessions(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        _, db, _ = await self._setup(cblpytest, "restart")

        self.mark_test_step("Mint a session as `rw`, then restart Edge Server")
        session_id = await self._mint_as(cblpytest, "rw")
        await es.kill_server()
        admin = await es.start_server()

        self.mark_test_step("Verify a replicator with the session is refused and nothing was pulled")
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(session_id))
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"
        assert "restart_es_hotels" not in await _local_ids(db), (
            "A doc was pulled with a session from before the restart"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_second_replicator_needs_its_own_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset local databases `db1` and `db2`")
        admin, db, db2 = await self._setup(cblpytest, "two")

        self.mark_test_step("Start a continuous replicator on `db1` with a session as `rw`, and wait for idle")
        session_id = await self._mint_as(cblpytest, "rw")
        first, status = await _replicate(
            db,
            admin,
            ReplicatorSessionAuthenticator(session_id),
            continuous=True,
            wait_for=ReplicatorActivityLevel.IDLE,
        )
        assert status.error is None, f"The continuous replicator failed: {_describe(status.error)}"

        self.mark_test_step("Verify a replicator on `db2` with the same session is refused")
        _, status = await _replicate(db2, admin, ReplicatorSessionAuthenticator(session_id))
        assert _is_auth_rejection(status.error), f"Expected a refusal, got {_describe(status.error)}"

        self.mark_test_step("Write a doc on Edge Server, and verify the first replicator still pulls it without error")
        await admin.put_document_with_id({"origin": "es"}, "two_es_after", DB, "travel", "hotels")
        for _ in range(10):
            status = await first.wait_for(ReplicatorActivityLevel.IDLE)
            assert status.error is None, f"The first replicator errored: {_describe(status.error)}"
            if "two_es_after" in await _local_ids(db):
                break
        assert "two_es_after" in await _local_ids(db), "The first replicator stopped pulling"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_read_only_session_cannot_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "ro")

        self.mark_test_step("Create 3 local docs, and push and pull with a session as read-only `ro`")
        pushed = [f"ro_cbl_{i}" for i in range(3)]
        await _write_local(db, HOTELS, pushed)
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "ro")))

        self.mark_test_step(
            "Verify the replicator is refused as pull-only (403) and none of the docs reached Edge Server"
        )
        assert status.error is not None and status.error.code == 403, f"Expected 403, got {_describe(status.error)}"
        assert not set(pushed) & await _es_ids(admin), "A read-only session wrote to Edge Server"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_read_only_session_can_pull(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "rop")

        self.mark_test_step("Pull with a session as read-only `ro`")
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "ro"))
        _, status = await _replicate(db, admin, session, ReplicatorType.PULL)

        self.mark_test_step("Verify the pull succeeded and the seeded doc was pulled")
        assert status.error is None, f"Read-only pull failed: {_describe(status.error)}"
        assert "rop_es_hotels" in await _local_ids(db), "The seeded doc was not pulled"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_collection_grants_apply_to_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "coll")

        self.mark_test_step("Pull both collections with a session as `coll`, and verify both seeded docs arrive")
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "coll"))
        _, status = await _replicate(db, admin, session, ReplicatorType.PULL, [HOTELS, AIRLINES])
        assert status.error is None, f"Pulling both readable collections failed: {_describe(status.error)}"
        assert "coll_es_hotels" in await _local_ids(db, HOTELS), "travel.hotels was not pulled"
        assert "coll_es_airlines" in await _local_ids(db, AIRLINES), "travel.airlines was not pulled"

        self.mark_test_step("Push a doc to `travel.hotels` with a new session, and verify it lands")
        await _write_local(db, HOTELS, ["coll_cbl_hotels"])
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "coll"))
        _, status = await _replicate(db, admin, session, ReplicatorType.PUSH, [HOTELS])
        assert status.error is None, f"Pushing to the writable travel.hotels failed: {_describe(status.error)}"
        assert "coll_cbl_hotels" in await _es_ids(admin, HOTELS), "travel.hotels did not accept the push"

        self.mark_test_step("Push a doc to `travel.airlines` with a new session, and verify it does not land")
        await _write_local(db, AIRLINES, ["coll_cbl_airlines"])
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "coll"))
        await _replicate(db, admin, session, ReplicatorType.PUSH, [AIRLINES])
        assert "coll_cbl_airlines" not in await _es_ids(admin, AIRLINES), (
            "The read-only travel.airlines accepted a push"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_session_has_full_access(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "adm")

        self.mark_test_step("Create a local doc in each collection, and replicate both with a session as `admin_user`")
        await _write_local(db, HOTELS, ["adm_cbl_hotels"])
        await _write_local(db, AIRLINES, ["adm_cbl_airlines"])
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "admin_user"))
        _, status = await _replicate(db, admin, session, collections=[HOTELS, AIRLINES])

        self.mark_test_step("Verify the replicator succeeded and both collections synced both ways")
        assert status.error is None, f"Admin session replication failed: {_describe(status.error)}"
        assert "adm_es_hotels" in await _local_ids(db, HOTELS), "travel.hotels was not pulled"
        assert "adm_es_airlines" in await _local_ids(db, AIRLINES), "travel.airlines was not pulled"
        assert "adm_cbl_hotels" in await _es_ids(admin, HOTELS), "travel.hotels was not pushed"
        assert "adm_cbl_airlines" in await _es_ids(admin, AIRLINES), "travel.airlines was not pushed"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_limited_to_granted_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "own")

        self.mark_test_step("Verify `other_db` is refused a session for `travel` with 403")
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await self._mint_as(cblpytest, "other_db")
        assert e.value.code == 403, f"Session on an ungranted database: expected 403, got {e.value.code}"

        self.mark_test_step("Create a local doc, and push it to `names` with a session as `other_db`")
        await _write_local(db, DEFAULT, ["own_cbl_0"])
        session = ReplicatorSessionAuthenticator(await self._mint_as(cblpytest, "other_db", OTHER_DB))
        _, status = await _replicate(db, admin, session, ReplicatorType.PUSH, [DEFAULT], OTHER_DB)

        self.mark_test_step("Verify the push succeeded, and the doc is on `names` and not on `travel`")
        assert status.error is None, f"The session on the granted database failed: {_describe(status.error)}"
        assert "own_cbl_0" in await _es_ids(admin, None, OTHER_DB), f"The doc was not pushed to `{OTHER_DB}`"
        assert "own_cbl_0" not in await _es_ids(admin), f"The doc leaked into `{DB}`"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_no_access_user_gets_no_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "none")

        self.mark_test_step("Verify `none` is refused a session for `travel` with 403")
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await self._mint_as(cblpytest, "none")
        assert e.value.code == 403, f"Session for a user with no grants: expected 403, got {e.value.code}"

        self.mark_test_step("Verify replicating as `none` with basic auth fails, and nothing was pulled")
        _, status = await _replicate(db, admin, ReplicatorBasicAuthenticator("none", PASSWORD))
        assert status.error is not None, "A user with no grants replicated with basic auth"
        assert "none_es_hotels" not in await _local_ids(db), "A user with no grants pulled a doc"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_write_only_session_cannot_sync(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server, seed one doc per collection, and reset the local database")
        admin, db, _ = await self._setup(cblpytest, "wo")

        self.mark_test_step("Mint a session as write-only `wo`, which may be refused with 403")
        try:
            session_id = await self._mint_as(cblpytest, "wo")
        except CblEdgeServerBadResponseError as e:
            assert e.code == 403, f"Session for a write-only user: expected a session or 403, got {e.code}"
            return

        self.mark_test_step("Create a local doc, and push and pull with the session")
        await _write_local(db, HOTELS, ["wo_cbl_0"])
        _, status = await _replicate(db, admin, ReplicatorSessionAuthenticator(session_id))

        self.mark_test_step("Verify the replicator is refused and nothing crossed in either direction")
        assert status.error is not None, "A write-only session replicated without an error"
        assert "wo_cbl_0" not in await _es_ids(admin), "A write-only session pushed"
        assert "wo_es_hotels" not in await _local_ids(db), "A write-only session pulled"
