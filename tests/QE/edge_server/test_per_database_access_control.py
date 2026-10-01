import json
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import bcrypt
import pytest
import tenacity
from aiohttp import ClientConnectorError
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError, CblTimeoutError
from cbltest.asyncfile import read_json_file, write_json_file
from cbltest.utils import async_retry_assert

SCRIPT_DIR = str(Path(__file__).parent)
CONFIG_TEMPLATE = f"{SCRIPT_DIR}/config/test_per_database_access_control.json"

# A file of its own, so the provisioned users.json other tests sign in with is never touched.
REMOTE_USERS_FILE = "/home/ec2-user/user/qe_per_db_access_users.json"
REMOTE_DB_DIR = "/home/ec2-user/database"
# start-edgeserver.sh sends the Edge Server's console output here, fresh on every start.
EDGE_LOG = "/home/ec2-user/log/edge.log"
MIN_ES_VERSION = ">= 1.1.1"

FLAG = "enable_user_access_control"

# Message fragments from UserAuth.cc.
ERR_FLAG_NOWHERE = "requires setting 'enable_user_access_control: true'"
ERR_UNSET_DB = "access control is not enabled for that database. Set 'enable_user_access_control' on"
WARN_EXEMPT_DB = "access control is not enabled for that database; those rules will be ignored"

Outcome = str  # "allow", "deny", or "HTTP <code>" for anything else
ALLOW: tuple[Outcome, Outcome] = ("allow", "allow")
DENY: tuple[Outcome, Outcome] = ("deny", "deny")
READ_ONLY: tuple[Outcome, Outcome] = ("allow", "deny")


@dataclass(frozen=True)
class QeUser:
    """A user the test writes into its own users file."""

    name: str
    password: str
    access: dict[str, list[str]] | None = None
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationCase:
    """One startup-validation scenario."""

    root: bool | None
    databases: dict[str, bool | None]
    access: dict[str, list[str]]
    expect: Literal["error", "warning", "clean"]
    fragment: str = ""
    database: str = ""


def _hash(password: str) -> str:
    """A bcrypt hash of `password`, the only form Edge Server accepts in a users file."""
    # Cost 5 keeps a users file quick to build and verify; Edge Server reads the cost from the hash.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=5)).decode()


def _database(name: str, flag: bool | None) -> dict[str, Any]:
    """An empty, writable, syncable database block, with `flag` as its access-control key (None omits it)."""
    block: dict[str, Any] = {
        "path": f"{REMOTE_DB_DIR}/{name}.cblite2",
        "create": True,
        "enable_client_writes": True,
        "enable_client_sync": True,
    }
    if flag is not None:
        block[FLAG] = flag
    return block


async def _outcome(request: Awaitable[Any]) -> Outcome:
    """Await a REST request, and classify it as allowed, denied (403), or anything else."""
    try:
        await request
        return "allow"
    except CblEdgeServerBadResponseError as e:
        return "deny" if e.code == 403 else f"HTTP {e.code}"


@pytest.mark.min_edge_servers(1)
class TestPerDatabaseAccessControl(CBLTestClass):
    async def _skip_if_unsupported(self, manager: EdgeServerManager) -> None:
        """Skip on an Edge Server that predates the per-database flag."""
        await self.skip_if_es_not(manager.get_admin_client(), MIN_ES_VERSION)

    async def _write_users(self, manager: EdgeServerManager, users: list[QeUser]) -> None:
        """Write a users file holding the provisioned admin and `users` to the Edge Server host."""
        entries: dict[str, Any] = {manager.admin_user: {"password": _hash(manager.admin_password), "roles": ["admin"]}}
        for user in users:
            entry: dict[str, Any] = {"password": _hash(user.password)}
            if user.roles:
                entry["roles"] = list(user.roles)
            if user.access is not None:
                entry["access"] = user.access
            entries[user.name] = entry

        await manager.write_file(REMOTE_USERS_FILE, json.dumps(entries, indent=2))

    async def _start(
        self,
        manager: EdgeServerManager,
        tmp_path: Path,
        root: bool | None,
        databases: dict[str, bool | None],
        replications: list[dict[str, Any]] | None = None,
    ) -> EdgeServer:
        """
        Restart Edge Server on a config with the given root flag and databases, reading the
        users file :func:`_write_users` wrote.

        :param root: The root-level flag, or None to omit it
        :param databases: Database name to that database's flag, where None omits the key
        :param replications: Replications to run at startup, if any
        """
        config = await read_json_file(CONFIG_TEMPLATE)
        if root is not None:
            config[FLAG] = root
        config["users"] = REMOTE_USERS_FILE
        config["databases"] = {name: _database(name, flag) for name, flag in databases.items()}
        if replications:
            config["replications"] = replications

        config_path = str(tmp_path / f"{manager}_{uuid4().hex[:8]}.json")
        await write_json_file(config_path, config)
        await manager.kill_server()
        return await manager.start_server(config_path)

    async def _edge_log(self, manager: EdgeServerManager, tmp_path: Path) -> str:
        """The Edge Server's console output from its latest start, or "" if it wrote none."""
        client = manager.get_admin_client()
        try:
            local = await client.download_log_file(EDGE_LOG, tmp_path / f"edge_{uuid4().hex[:8]}.log")
        except FileNotFoundError:
            return ""
        return local.read_text(errors="replace")

    async def _probe(self, manager: EdgeServerManager, name: str, password: str, db: str) -> tuple[Outcome, Outcome]:
        """Read and write `db` as `name`, returning how each was answered."""
        async with manager.get_user_client(name, password) as client:
            read = await _outcome(client.get_all_documents(db))
            write = await _outcome(client.put_document_with_id({"probe": name}, f"probe_{name}_{uuid4().hex}", db))
        return read, write

    async def _probe_user(self, manager: EdgeServerManager, user: QeUser, db: str) -> tuple[Outcome, Outcome]:
        """:func:`_probe` as a :class:`QeUser`."""
        return await self._probe(manager, user.name, user.password, db)

    async def _probe_admin(self, manager: EdgeServerManager, db: str) -> tuple[Outcome, Outcome]:
        """:func:`_probe` as the provisioned admin user."""
        return await self._probe(manager, manager.admin_user, manager.admin_password, db)

    async def _wait_for_docs(self, edge_server: EdgeServer, db: str, doc_ids: set[str]) -> None:
        """Wait until every id in `doc_ids` is in `db`."""

        async def _poll() -> None:
            present = {row.id for row in (await edge_server.get_all_documents(db)).rows}
            assert doc_ids <= present, f"Not in {db}: {sorted(doc_ids - present)}"

        await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(90))

    @pytest.mark.parametrize(
        "root, db_flag, enforcing",
        [
            pytest.param(None, None, False, id="row1_root_absent_db_absent"),
            pytest.param(None, False, False, id="row2_root_absent_db_false"),
            pytest.param(None, True, True, id="row3_root_absent_db_true"),
            pytest.param(False, None, False, id="row4_root_false_db_absent"),
            pytest.param(False, False, False, id="row5_root_false_db_false"),
            pytest.param(False, True, True, id="row6_root_false_db_true"),
            pytest.param(True, None, True, id="row7_root_true_db_absent"),
            pytest.param(True, False, False, id="row8_root_true_db_false"),
            pytest.param(True, True, True, id="row9_root_true_db_true"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_flag_resolution(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        tmp_path: Path,
        root: bool | None,
        db_flag: bool | None,
        enforcing: bool,
    ) -> None:
        manager = cblpytest.edge_servers[0]
        await self._skip_if_unsupported(manager)
        prober = QeUser("prober", "proberpass", access={"anchor_db": ["read", "write"]})

        self.mark_test_step("Write a users file with the admin user and `prober`")
        await self._write_users(manager, [prober])

        self.mark_test_step(
            f"Start Edge Server with root flag {root}, `subject_db` flag {db_flag}, and `anchor_db` flag true"
        )
        await self._start(manager, tmp_path, root, {"subject_db": db_flag, "anchor_db": True})

        self.mark_test_step("Verify `prober` can read and write `anchor_db`")
        anchor = await self._probe_user(manager, prober, "anchor_db")
        assert anchor == ALLOW, f"prober was not granted its own rule on anchor_db: (read, write) = {anchor}"

        state = "enforcing" if enforcing else "open"
        self.mark_test_step(f"Verify `subject_db` resolved {state} for `prober`")
        subject = await self._probe_user(manager, prober, "subject_db")
        expected = DENY if enforcing else ALLOW
        assert subject == expected, (
            f"root={root}, subject_db={db_flag} should resolve {state}: prober (read, write) expected "
            f"{expected}, got {subject}"
        )

        self.mark_test_step("Verify the admin user can read and write `subject_db`")
        admin = await self._probe_admin(manager, "subject_db")
        assert admin == ALLOW, f"admin was restricted on subject_db: (read, write) = {admin}"

    @pytest.mark.parametrize("root", [pytest.param(None, id="root_absent"), pytest.param(True, id="root_true")])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_user_access_block_by_database(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, root: bool | None
    ) -> None:
        manager = cblpytest.edge_servers[0]
        await self._skip_if_unsupported(manager)
        no_block = QeUser("no_block", "noblockpass")
        ruled = QeUser("ruled", "ruledpass", access={"enforced_db": ["read"], "exempt_db": ["read"]})
        empty_block = QeUser("empty_block", "emptypass", access={})

        self.mark_test_step("Write a users file with the admin user, `no_block`, `ruled` and `empty_block`")
        await self._write_users(manager, [no_block, ruled, empty_block])

        self.mark_test_step(f"Start Edge Server with root flag {root} and the three databases")
        await self._start(manager, tmp_path, root, {"enforced_db": True, "exempt_db": False, "default_db": None})

        default_enforcing = root is True
        expected: list[tuple[str, str, tuple[Outcome, Outcome]]] = [
            ("admin", "enforced_db", ALLOW),
            ("admin", "exempt_db", ALLOW),
            ("admin", "default_db", ALLOW),
            ("no_block", "enforced_db", ALLOW),
            ("no_block", "exempt_db", ALLOW),
            ("no_block", "default_db", ALLOW),
            ("ruled", "enforced_db", READ_ONLY),
            ("ruled", "exempt_db", ALLOW),
            ("ruled", "default_db", DENY if default_enforcing else ALLOW),
            ("empty_block", "enforced_db", DENY),
            ("empty_block", "exempt_db", ALLOW),
            ("empty_block", "default_db", DENY if default_enforcing else ALLOW),
        ]
        users = {u.name: u for u in (no_block, ruled, empty_block)}

        self.mark_test_step("As each user, read and write each database, and compare against the expected table")
        mismatches: list[str] = []
        for name, db, want in expected:
            if name == "admin":
                got = await self._probe_admin(manager, db)
            else:
                got = await self._probe_user(manager, users[name], db)
            if got != want:
                mismatches.append(f"{name} on {db}: (read, write) expected {want}, got {got}")

        assert not mismatches, f"root={root}: " + "; ".join(mismatches)

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                ValidationCase(None, {"db1": None}, {"db1": ["read"]}, "error", ERR_FLAG_NOWHERE),
                id="access_block_flag_nowhere",
            ),
            pytest.param(
                ValidationCase(None, {"db1": None}, {}, "error", ERR_FLAG_NOWHERE),
                id="empty_access_block_flag_nowhere",
            ),
            pytest.param(
                ValidationCase(
                    None, {"db1": True, "db2": None}, {"db1": ["read"], "db2": ["read"]}, "error", ERR_UNSET_DB, "db2"
                ),
                id="rule_for_unset_db_root_absent",
            ),
            pytest.param(
                ValidationCase(
                    False, {"db1": True, "db2": None}, {"db1": ["read"], "db2": ["read"]}, "error", ERR_UNSET_DB, "db2"
                ),
                id="rule_for_unset_db_root_false",
            ),
            pytest.param(
                ValidationCase(
                    None, {"db1": True, "db2": None}, {"db1": ["read"], "db2.*": ["read"]}, "error", ERR_UNSET_DB, "db2"
                ),
                id="scoped_rule_for_unset_db",
            ),
            pytest.param(
                ValidationCase(
                    None,
                    {"db1": True, "db2": False},
                    {"db1": ["read"], "db2": ["read"]},
                    "warning",
                    WARN_EXEMPT_DB,
                    "db2",
                ),
                id="rule_for_exempt_db_root_absent",
            ),
            pytest.param(
                ValidationCase(
                    True,
                    {"db1": None, "db2": False},
                    {"db1": ["read"], "db2": ["read"]},
                    "warning",
                    WARN_EXEMPT_DB,
                    "db2",
                ),
                id="rule_for_exempt_db_root_true",
            ),
            pytest.param(
                ValidationCase(True, {"db1": None, "db2": None}, {"db1": ["read"], "db2": ["read"]}, "clean"),
                id="rule_for_inheriting_db_root_true",
            ),
            pytest.param(
                ValidationCase(None, {"db1": True, "db2": None}, {"*": ["read"]}, "clean"),
                id="wildcard_rule",
            ),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_startup_validation(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, case: ValidationCase
    ) -> None:
        manager = cblpytest.edge_servers[0]
        await self._skip_if_unsupported(manager)

        self.mark_test_step("Write a users file with the admin user and `subject`, holding the case's access block")
        await self._write_users(manager, [QeUser("subject", "subjectpass", access=case.access)])

        self.mark_test_step(f"Start Edge Server with root flag {case.root} and databases {case.databases}")
        if case.expect == "error":
            failure: Exception | None = None
            try:
                await self._start(manager, tmp_path, case.root, case.databases)
            except (CblEdgeServerBadResponseError, ClientConnectorError, CblTimeoutError) as e:
                failure = e

            self.mark_test_step("Verify startup fails and the Edge Server's output names the problem")
            assert failure is not None, f"Edge Server started with an access block it should refuse: {case.access}"
            body = failure.body if isinstance(failure, CblEdgeServerBadResponseError) else ""
            output = body + "\n" + await self._edge_log(manager, tmp_path)
            assert case.fragment in output, f"Startup failed, but not with '{case.fragment}':\n{output}"
            if case.database:
                assert f"database '{case.database}'" in output, (
                    f"Startup error does not name {case.database}:\n{output}"
                )
            return

        await self._start(manager, tmp_path, case.root, case.databases)

        self.mark_test_step("Verify startup succeeds and the admin user can read each database")
        for db in case.databases:
            read, _ = await self._probe_admin(manager, db)
            assert read == "allow", f"admin could not read {db} after startup: {read}"

        output = await self._edge_log(manager, tmp_path)
        if case.expect == "warning":
            self.mark_test_step("Verify the exemption warning appears in the Edge Server's output")
            matching = [line for line in output.splitlines() if case.fragment in line]
            assert matching, f"No '{case.fragment}' warning in the Edge Server's output:\n{output}"
            assert any(f"database '{case.database}'" in line for line in matching), (
                f"Exemption warning does not name {case.database}: {matching}"
            )
        else:
            self.mark_test_step("Verify the exemption warning does not appear in the Edge Server's output")
            assert WARN_EXEMPT_DB not in output, f"Unexpected exemption warning:\n{output}"

    @pytest.mark.min_edge_servers(2)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_respects_database_flag(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        provider_manager = cblpytest.edge_servers[0]
        consumer_manager = cblpytest.edge_servers[1]
        await self._skip_if_unsupported(provider_manager)
        await self._skip_if_unsupported(consumer_manager)
        syncer = QeUser("syncer", "syncerpass", access={})
        reader = QeUser("reader", "readerpass", access={"enforced_db": ["read"]})

        self.mark_test_step(
            "Start the provider with `syncer` ({}) and `reader` (enforced_db: [read]), "
            "`enforced_db` true and `open_db` unset"
        )
        await self._write_users(provider_manager, [syncer, reader])
        provider = await self._start(provider_manager, tmp_path, None, {"enforced_db": True, "open_db": None})

        self.mark_test_step("As admin, write 3 documents to each of `enforced_db` and `open_db` on the provider")
        enforced_ids = {f"enforced_doc_{i}" for i in range(3)}
        open_ids = {f"open_doc_{i}" for i in range(3)}
        for db, ids in (("enforced_db", enforced_ids), ("open_db", open_ids)):
            for doc_id in ids:
                await provider.put_document_with_id({"type": "seed", "db": db}, doc_id, db)

        self.mark_test_step("Start the consumer with the three pull replications")

        def _pull(db: str, target: str, user: QeUser) -> dict[str, Any]:
            return {
                "source": provider.replication_url(db),
                "target": target,
                "continuous": True,
                "auth": {"user": user.name, "password": user.password},
            }

        await self._write_users(consumer_manager, [])
        consumer = await self._start(
            consumer_manager,
            tmp_path,
            None,
            {"open_copy": None, "reader_copy": None, "denied_copy": None},
            replications=[
                _pull("open_db", "open_copy", syncer),
                _pull("enforced_db", "reader_copy", reader),
                _pull("enforced_db", "denied_copy", syncer),
            ],
        )

        self.mark_test_step("Wait for the `open_db` documents to reach `open_copy`")
        await self._wait_for_docs(consumer, "open_copy", open_ids)

        self.mark_test_step("Wait for the `enforced_db` documents to reach `reader_copy`")
        await self._wait_for_docs(consumer, "reader_copy", enforced_ids)

        self.mark_test_step("Verify none of the `enforced_db` documents are in `denied_copy`")
        denied = {row.id for row in (await consumer.get_all_documents("denied_copy")).rows}
        leaked = sorted(enforced_ids & denied)
        assert not leaked, f"syncer ({{}}) pulled {leaked} from enforced_db"
