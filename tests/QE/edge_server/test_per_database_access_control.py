import json
from collections.abc import Awaitable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorStatus,
    ReplicatorType,
)
from cbltest.api.syncgateway import get_basic_auth_headers
from cbltest.asyncfile import read_json_file, write_json_file
from cbltest.utils import async_retry_assert

SCRIPT_DIR = str(Path(__file__).parent)
ROOT_TRUE_CONFIG = f"{SCRIPT_DIR}/config/test_per_db_access_control.json"
ROOT_FALSE_CONFIG = f"{SCRIPT_DIR}/config/test_per_db_access_control_root_false.json"
OPT_IN_CONFIG = f"{SCRIPT_DIR}/config/test_per_db_access_control_opt_in.json"
TRAVEL_CONFIG = f"{SCRIPT_DIR}/config/test_per_db_access_control_travel.json"

# Every config here reads this file, so the provisioned users.json is never touched.
USERS_FILE = "/home/ec2-user/user/per_db_access_users.json"
EDGE_LOG = "/home/ec2-user/log/edge.log"
FLAG = "enable_user_access_control"

PASSWORD = "pass"
PASSWORD_HASH = "$2b$05$IcP5FQp9n229unPK9VLwAOrSmNO8dFT1EcUlMFc4h4l76YXefElwu"  # bcrypt of PASSWORD

WARN_EXEMPT_DB = "access control is not enabled for that database; those rules will be ignored"


def _user(access: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """A users-file entry with the shared password, and `access` as its access block (None omits it)."""
    entry: dict[str, Any] = {"password": PASSWORD_HASH}
    if access is not None:
        entry["access"] = access
    return entry


# The users for every config with `enforced` (flag true), `exempt` (flag false) and `inherits` (no flag).
USERS = {
    "no_block": _user(),
    "ruled": _user({"enforced": ["read"], "exempt": ["read"]}),
    "writer": _user({"enforced": ["read", "write"]}),
    "write_only": _user({"enforced": ["write"], "exempt": ["write"]}),
    "star": _user({"*": ["read"]}),
    "restricted": _user({}),
}


async def _config(flags: dict[str, bool | None]) -> dict[str, Any]:
    """
    A config with no root flag and one empty database per entry of `flags`.

    :param flags: Database name to its flag, where None omits the key
    """
    config = await read_json_file(OPT_IN_CONFIG)
    block = dict(config["databases"]["inherits"])
    config["databases"] = {}
    for name, flag in flags.items():
        config["databases"][name] = {**block, "path": f"/home/ec2-user/database/{name}.cblite2"}
        if flag is not None:
            config["databases"][name][FLAG] = flag
    return config


async def _status(request: Awaitable[Any]) -> int:
    """The HTTP status a REST request was answered with, reporting any success as 200."""
    try:
        await request
        return 200
    except CblEdgeServerBadResponseError as e:
        return e.code


async def _allowed(request: Awaitable[Any]) -> bool:
    """Whether a REST request succeeds.  A 403 is a denial; any other failure is a test error."""
    status = await _status(request)
    assert status in (200, 403), f"Expected success or 403, got {status}"
    return status == 200


async def _check(client: EdgeServer, who: str, keyspace: str, *, read: bool, write: bool) -> None:
    """Assert whether `client` can read (`_all_docs`) and write (`PUT`) `keyspace` ("db" or "db.scope.collection")."""
    db, _, rest = keyspace.partition(".")
    scope, _, collection = rest.partition(".")
    can_read = await _allowed(client.get_all_documents(db, scope, collection))
    can_write = await _allowed(client.put_document_with_id({"by": who}, f"{who}_{uuid4().hex}", db, scope, collection))
    assert (can_read, can_write) == (read, write), (
        f"{who} on {keyspace}: (read, write) expected {(read, write)}, got {(can_read, can_write)}"
    )


async def _doc_ids(client: EdgeServer, db: str) -> set[str]:
    """The ids of every document in `db`."""
    return {row.id for row in (await client.get_all_documents(db)).rows}


async def _wait_for_docs(client: EdgeServer, db: str, doc_ids: set[str]) -> None:
    """Wait until every id in `doc_ids` is in `db`."""

    async def _poll() -> None:
        present = await _doc_ids(client, db)
        assert doc_ids <= present, f"Not in {db}: {sorted(doc_ids - present)}"

    await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(90))


async def _cbl_doc_ids(db: Database) -> set[str]:
    """The ids of every document in `db`'s default collection."""
    return {d.id for d in (await db.get_all_documents("_default._default"))["_default._default"]}


async def _cbl_sync(
    db: Database, url: str, user: str, replicator_type: ReplicatorType = ReplicatorType.PUSH_AND_PULL
) -> ReplicatorStatus:
    """Write one document to `db`, then replicate once against `url` as `user`."""
    async with db.batch_updater() as updater:
        updater.upsert_document("_default._default", f"cbl_{user}_{db.name}", [{"by": user}])
    replicator = Replicator(
        db,
        url,
        collections=[ReplicatorCollectionEntry(["_default._default"])],
        replicator_type=replicator_type,
        continuous=False,
        authenticator=ReplicatorBasicAuthenticator(user, PASSWORD),
    )
    await replicator.start()
    return await replicator.wait_for(ReplicatorActivityLevel.STOPPED)


@pytest.mark.min_edge_servers(1)
class TestPerDatabaseAccessControl(CBLTestClass):
    async def _start(
        self,
        es: EdgeServerManager,
        tmp_path: Path,
        users: dict[str, Any],
        config: dict[str, Any] | str,
        dataset: str = "enforced",
    ) -> None:
        """Write `users` (plus `qe_admin`) as the users file, and restart Edge Server on `config`."""
        users_file = {"qe_admin": {"password": PASSWORD_HASH, "roles": ["admin"]}, **users}
        await es.write_file(USERS_FILE, json.dumps(users_file, indent=2))
        if isinstance(config, dict):
            config_path = tmp_path / f"{es}_{uuid4().hex[:8]}.json"
            await write_json_file(str(config_path), config)
            config = str(config_path)
        await es.configure_dataset(db_name=dataset, config_file=config)

    def _client(self, es: EdgeServerManager, user: str) -> AbstractAsyncContextManager[EdgeServer]:
        """A client signed in as `user` with the shared password."""
        return es.get_user_client(get_basic_auth_headers(user, PASSWORD))

    async def _assert_exempt_warning(self, es: EdgeServerManager, tmp_path: Path, database: str) -> None:
        """Assert Edge Server warned at startup that rules for `database` are ignored."""
        log = await es.get_admin_client().download_log_file(EDGE_LOG, tmp_path / f"edge_{uuid4().hex[:8]}.log")
        lines = [line for line in log.read_text(errors="replace").splitlines() if WARN_EXEMPT_DB in line]
        assert any(f"database '{database}'" in line for line in lines), (
            f"No exemption warning for '{database}' in Edge Server's output: {lines}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unset_database_inherits_root_true(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true and `inherits` setting no flag")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("Verify `restricted` and anonymous are denied `inherits`")
        async with self._client(es, "restricted") as restricted, es.get_anonymous_client() as anonymous:
            await _check(restricted, "restricted", "inherits", read=False, write=False)
            await _check(anonymous, "anonymous", "inherits", read=False, write=False)

        self.mark_test_step("Verify `star` (`*`: read) is read-only on `inherits`")
        async with self._client(es, "star") as star:
            await _check(star, "star", "inherits", read=True, write=False)

        self.mark_test_step("Verify `no_block` has full access to `inherits`")
        async with self._client(es, "no_block") as no_block:
            await _check(no_block, "no_block", "inherits", read=True, write=True)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_database_set_true_enforces_rules(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true and `enforced` setting true")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("Verify the admin and `no_block` have full access to `enforced`")
        for who in ("qe_admin", "no_block"):
            async with self._client(es, who) as client:
                await _check(client, who, "enforced", read=True, write=True)

        self.mark_test_step("Verify `ruled` is read-only and `writer` has full access to `enforced`")
        for who, read, write in (("ruled", True, False), ("writer", True, True)):
            async with self._client(es, who) as client:
                await _check(client, who, "enforced", read=read, write=write)

        self.mark_test_step("Verify `write_only` can create with POST, but cannot read or PUT with an ID")
        async with self._client(es, "write_only") as client:
            assert await _allowed(client.add_document_auto_id({"by": "write_only"}, "enforced")), (
                "write_only could not POST to enforced"
            )
            await _check(client, "write_only", "enforced", read=False, write=False)

        self.mark_test_step("Verify `restricted` and anonymous are denied `enforced`")
        async with self._client(es, "restricted") as restricted, es.get_anonymous_client() as anonymous:
            await _check(restricted, "restricted", "enforced", read=False, write=False)
            await _check(anonymous, "anonymous", "enforced", read=False, write=False)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_database_set_false_ignores_rules(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true and `exempt` setting false")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("Verify every user, including anonymous, has full access to `exempt`")
        for who in ("ruled", "write_only", "restricted"):
            async with self._client(es, who) as client:
                await _check(client, who, "exempt", read=True, write=True)
        async with es.get_anonymous_client() as anonymous:
            await _check(anonymous, "anonymous", "exempt", read=True, write=True)

        self.mark_test_step("Verify Edge Server warned that rules for `exempt` are ignored")
        await self._assert_exempt_warning(es, tmp_path, "exempt")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_root_false_enforces_only_databases_set_true(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step(
            "Start Edge Server with root flag false, `enforced` true, `exempt` false and `inherits` unset"
        )
        await self._start(es, tmp_path, USERS, ROOT_FALSE_CONFIG)

        self.mark_test_step("Verify only `enforced` restricts `restricted`")
        async with self._client(es, "restricted") as client:
            await _check(client, "restricted", "enforced", read=False, write=False)
            await _check(client, "restricted", "exempt", read=True, write=True)
            await _check(client, "restricted", "inherits", read=True, write=True)

        self.mark_test_step("Verify `ruled` is read-only on `enforced`")
        async with self._client(es, "ruled") as client:
            await _check(client, "ruled", "enforced", read=True, write=False)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_access_does_not_leak_between_databases(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("Verify full access to `exempt` grants `restricted` nothing on `enforced` or `inherits`")
        async with self._client(es, "restricted") as client:
            await _check(client, "restricted", "exempt", read=True, write=True)
            await _check(client, "restricted", "enforced", read=False, write=False)
            await _check(client, "restricted", "inherits", read=False, write=False)

        self.mark_test_step("Verify `writer`'s rule for `enforced` grants nothing on `inherits`")
        async with self._client(es, "writer") as client:
            await _check(client, "writer", "enforced", read=True, write=True)
            await _check(client, "writer", "inherits", read=False, write=False)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_missing_collection_status_follows_database_flag(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        async with self._client(es, "restricted") as client:
            self.mark_test_step("Verify a missing collection on `exempt` is 404")
            status = await _status(client.get_all_documents("exempt", collection="nosuchcollection"))
            assert status == 404, f"Missing collection on an open database returned {status}"

            self.mark_test_step("Verify a missing collection on `enforced` is 403")
            status = await _status(client.get_all_documents("enforced", collection="nosuchcollection"))
            assert status == 403, f"Missing collection on an enforcing database returned {status}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_all_dbs_follows_database_flag(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with root flag true")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("Verify `restricted` sees only `exempt`")
        async with self._client(es, "restricted") as client:
            dbs = set(await client.get_all_dbs())
        assert "exempt" in dbs and dbs.isdisjoint({"enforced", "inherits"}), f"restricted sees {dbs}"

        self.mark_test_step("Verify `ruled` sees `enforced` and `exempt`, but not `inherits`")
        async with self._client(es, "ruled") as client:
            dbs = set(await client.get_all_dbs())
        assert {"enforced", "exempt"} <= dbs and "inherits" not in dbs, f"ruled sees {dbs}"

        self.mark_test_step("Verify the admin sees every database")
        async with self._client(es, "qe_admin") as client:
            dbs = set(await client.get_all_dbs())
        assert {"enforced", "exempt", "inherits"} <= dbs, f"admin sees {dbs}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_collections_and_queries(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        users = {
            "hotel_reader": _user({"travel.travel.hotels": ["read"], "names._default._default": ["read"]}),
            "restricted": _user({}),
        }

        self.mark_test_step("Start Edge Server with `travel` enforcing and `names` exempt, both with named queries")
        await self._start(es, tmp_path, users, TRAVEL_CONFIG, dataset="travel")

        self.mark_test_step(
            "Verify `hotel_reader` can only read `travel.hotels` in `travel`, and has full access to `names`"
        )
        async with self._client(es, "hotel_reader") as client:
            await _check(client, "hotel_reader", "travel.travel.hotels", read=True, write=False)
            await _check(client, "hotel_reader", "travel.travel.airlines", read=False, write=False)
            await _check(client, "hotel_reader", "names", read=True, write=True)

        self.mark_test_step("Verify `restricted` is denied `travel.hotels` and has full access to `names`")
        async with self._client(es, "restricted") as client:
            await _check(client, "restricted", "travel.travel.hotels", read=False, write=False)
            await _check(client, "restricted", "names", read=True, write=True)

        self.mark_test_step("Verify the admin can run both `travel` named queries")
        async with self._client(es, "qe_admin") as client:
            assert await _allowed(client.named_query("travel", name="hotel_ids")), "admin denied hotel_ids"
            assert await _allowed(client.named_query("travel", name="airline_ids")), "admin denied airline_ids"

        self.mark_test_step(
            "Verify `hotel_reader` can run `hotel_ids` through `travel.travel.hotels`, but not `airline_ids`"
        )
        async with self._client(es, "hotel_reader") as client:
            assert await _allowed(client.named_query("travel", "travel", "hotels", name="hotel_ids")), (
                "hotel_reader denied hotel_ids"
            )
            assert not await _allowed(client.named_query("travel", "travel", "hotels", name="airline_ids")), (
                "hotel_reader ran airline_ids without read access to travel.airlines"
            )

        self.mark_test_step("Verify `restricted` can run neither `travel` query, and can run `name_ids` on `names`")
        async with self._client(es, "restricted") as client:
            assert not await _allowed(client.named_query("travel", "travel", "hotels", name="hotel_ids")), (
                "restricted ran hotel_ids"
            )
            assert not await _allowed(client.named_query("travel", "travel", "hotels", name="airline_ids")), (
                "restricted ran airline_ids"
            )
            assert await _allowed(client.named_query("names", name="name_ids")), "restricted denied name_ids"

        self.mark_test_step("Verify Edge Server warned that rules for `names` are ignored")
        await self._assert_exempt_warning(es, tmp_path, "names")

    @pytest.mark.min_edge_servers(2)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_replication(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        provider_es, consumer_es = cblpytest.edge_servers[0], cblpytest.edge_servers[1]

        self.mark_test_step("Start the provider with `enforced` true and `exempt` false")
        await self._start(provider_es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        self.mark_test_step("As admin, write `seed_enforced` and `seed_exempt` on the provider")
        async with self._client(provider_es, "qe_admin") as provider:
            await provider.put_document_with_id({"seed": True}, "seed_enforced", "enforced")
            await provider.put_document_with_id({"seed": True}, "seed_exempt", "exempt")
            url = provider.replication_url

            def _replication(source: str, target: str, user: str) -> dict[str, Any]:
                return {
                    "source": source,
                    "target": target,
                    "continuous": True,
                    "auth": {"user": user, "password": PASSWORD},
                }

            replications = [
                _replication(url("enforced"), "pull_ruled", "ruled"),
                _replication(url("enforced"), "pull_restricted", "restricted"),
                _replication(url("exempt"), "pull_exempt", "restricted"),
                _replication("push_writer", url("enforced"), "writer"),
                _replication("push_ruled", url("enforced"), "ruled"),
                _replication("push_exempt", url("exempt"), "ruled"),
            ]
            local_dbs = {name: None for r in replications for name in (r["source"], r["target"]) if "://" not in name}

            self.mark_test_step("Start the consumer with three pull and three push replications")
            config = await _config(local_dbs)
            config["replications"] = replications
            await self._start(consumer_es, tmp_path, {}, config)

            async with self._client(consumer_es, "qe_admin") as consumer:
                self.mark_test_step("On the consumer, write one document to each push database")
                await consumer.put_document_with_id({"by": "ruled"}, "pushed_by_ruled", "push_ruled")
                await consumer.put_document_with_id({"by": "writer"}, "pushed_by_writer", "push_writer")
                await consumer.put_document_with_id({"by": "ruled"}, "pushed_to_exempt", "push_exempt")

                self.mark_test_step("Wait for the allowed pulls: `ruled` from `enforced`, `restricted` from `exempt`")
                await _wait_for_docs(consumer, "pull_ruled", {"seed_enforced"})
                await _wait_for_docs(consumer, "pull_exempt", {"seed_exempt"})

                self.mark_test_step("Wait for the allowed pushes: `writer` to `enforced`, `ruled` to `exempt`")
                await _wait_for_docs(provider, "enforced", {"pushed_by_writer"})
                await _wait_for_docs(provider, "exempt", {"pushed_to_exempt"})

                self.mark_test_step("Verify `restricted` pulled nothing from `enforced`")
                assert "seed_enforced" not in await _doc_ids(consumer, "pull_restricted"), (
                    "restricted pulled from enforced"
                )

            self.mark_test_step("Verify `ruled` (read only) pushed nothing to `enforced`")
            assert "pushed_by_ruled" not in await _doc_ids(provider, "enforced"), "ruled pushed to enforced"

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_cbl_replication(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        es = cblpytest.edge_servers[0]

        self.mark_test_step("Start Edge Server with `enforced` true and `exempt` false")
        await self._start(es, tmp_path, USERS, ROOT_TRUE_CONFIG)

        async with self._client(es, "qe_admin") as client:
            self.mark_test_step("As admin, write `seed_enforced` and `seed_exempt`")
            await client.put_document_with_id({"seed": True}, "seed_enforced", "enforced")
            await client.put_document_with_id({"seed": True}, "seed_exempt", "exempt")

            exempt_db, pull_db, push_db, denied_db = await cblpytest.test_servers[0].create_and_reset_db(
                ["ruled_exempt", "ruled_pull", "ruled_push", "restricted_enforced"]
            )

            self.mark_test_step("Push and pull `exempt` as `ruled`: its read-only rule is ignored")
            status = await _cbl_sync(exempt_db, client.replication_url("exempt"), "ruled")
            assert status.error is None, (
                f"ruled could not sync with exempt: ({status.error.domain} / {status.error.code}) {status.error.message}"
            )
            assert "seed_exempt" in await _cbl_doc_ids(exempt_db), "ruled did not pull from exempt"
            assert "cbl_ruled_ruled_exempt" in await _doc_ids(client, "exempt"), "ruled could not push to exempt"

            self.mark_test_step("Pull `enforced` as `ruled`: its read rule allows it")
            status = await _cbl_sync(pull_db, client.replication_url("enforced"), "ruled", ReplicatorType.PULL)
            assert status.error is None, (
                f"ruled could not pull enforced: ({status.error.domain} / {status.error.code}) {status.error.message}"
            )
            assert "seed_enforced" in await _cbl_doc_ids(pull_db), "ruled did not pull from enforced"

            self.mark_test_step("Push and pull `enforced` as `ruled`: refused as pull-only, and nothing is pushed")
            status = await _cbl_sync(push_db, client.replication_url("enforced"), "ruled")
            assert status.error is not None and status.error.code == 403, (
                f"ruled's push to enforced was not refused with 403: {status.error}"
            )
            assert "cbl_ruled_ruled_push" not in await _doc_ids(client, "enforced"), "ruled pushed to enforced"

            self.mark_test_step("Push and pull `enforced` as `restricted`: the replicator fails and nothing moves")
            status = await _cbl_sync(denied_db, client.replication_url("enforced"), "restricted")
            assert status.error is not None, "restricted replicated with enforced without an error"
            assert "seed_enforced" not in await _cbl_doc_ids(denied_db), "restricted pulled from enforced"
            assert "cbl_restricted_restricted_enforced" not in await _doc_ids(client, "enforced"), (
                "restricted pushed to enforced"
            )
