import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import BulkDocOperation, EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import get_basic_auth_headers

SCRIPT_DIR = Path(__file__).parent
CONFIG = SCRIPT_DIR / "config" / "test_public_api_authorization.json"
USERS_FILE = "/home/ec2-user/user/public_api_authorization_users.json"
DB = "names"

PASSWORD = "pass"
PASSWORD_HASH = "$2b$05$IcP5FQp9n229unPK9VLwAOrSmNO8dFT1EcUlMFc4h4l76YXefElwu"  # bcrypt of PASSWORD

# Access control is on for names, so a user reaches its documents only through a role or an access entry.
USERS = {
    "qe_admin": {"password": PASSWORD_HASH, "roles": ["admin"]},
    "replicator": {"password": PASSWORD_HASH, "roles": ["replicate"]},
    "writer": {"password": PASSWORD_HASH, "access": {DB: ["read", "write"]}},
    "reader": {"password": PASSWORD_HASH, "access": {DB: ["read"]}},
    "write_only": {"password": PASSWORD_HASH, "access": {DB: ["write"]}},
    "no_access": {"password": PASSWORD_HASH, "access": {}},
}
ANONYMOUS = "anonymous"
WRONG_PASSWORD = "wrong_password"  # reader, with a password that does not match

# A port that nothing listens on, on the Edge Server host, so the replication stays listed.
UNREACHABLE_TARGET = "ws://127.0.0.1:1/names"

OK = "ok"  # any 2xx

# Who may do what. Anyone else gets a 403, except that a request without valid credentials gets a 401 when
# the operation needs a role, or when its credentials are wrong.
EVERYONE = {"qe_admin", "replicator", "writer", "reader", "write_only", "no_access", ANONYMOUS}
READ = {"qe_admin", "replicator", "writer", "reader"}
WRITE = {"qe_admin", "replicator", "writer"}
DROP_BOX = WRITE | {"write_only"}  # write-only users may only create documents with generated IDs
SESSION = READ | {"write_only"}


@dataclass
class Context:
    """The revisions and replication task, read as the admin before any request."""

    revs: dict[str, str]
    task_id: int


@dataclass
class Operation:
    name: str
    allowed: set[str]
    anonymous: int  # the status an anonymous request gets when it is not allowed
    call: Callable[[EdgeServer, str, Context], Awaitable[Any]]


# Each write uses its own document, so that no write changes another's revision. The replication stop is
# last, because it ends the task that the reads before it use.
OPERATIONS = [
    Operation("GET /", EVERYONE, 401, lambda c, who, ctx: c.get_version()),
    Operation("GET /_all_dbs", EVERYONE, 401, lambda c, who, ctx: c.get_all_dbs()),
    Operation("GET /_active_tasks", {"qe_admin"}, 401, lambda c, who, ctx: c.get_active_tasks()),
    Operation("GET /_replicate", {"qe_admin", "replicator"}, 401, lambda c, who, ctx: c.all_replication_status()),
    Operation(
        "GET /_replicate/{taskid}",
        {"qe_admin", "replicator"},
        401,
        lambda c, who, ctx: c.replication_status(ctx.task_id),
    ),
    Operation("GET /{keyspace}", READ, 403, lambda c, who, ctx: c.get_db_info(DB)),
    Operation("GET /{keyspace}/_all_docs", READ, 403, lambda c, who, ctx: c.get_all_documents(DB)),
    Operation("GET /{keyspace}/{docid}", READ, 403, lambda c, who, ctx: c.get_document(DB, "name_1")),
    Operation(
        "GET /{keyspace}/{docid}/{key}", READ, 403, lambda c, who, ctx: c.get_sub_document("name_1", "contact", DB)
    ),
    Operation("GET /{keyspace}/_changes", READ, 403, lambda c, who, ctx: c.changes_feed(DB, limit=1)),
    Operation(
        "POST /{keyspace}/_query",
        READ,
        403,
        lambda c, who, ctx: c.adhoc_query(DB, query="SELECT meta().id FROM _default LIMIT 1"),
    ),
    Operation("GET /{keyspace}/_query/{name}", READ, 403, lambda c, who, ctx: c.named_query(DB, name="female_ids")),
    Operation("POST /{db}/_session", SESSION, 401, lambda c, who, ctx: c.create_session(DB)),
    Operation(
        "POST /{keyspace}",
        DROP_BOX,
        403,
        lambda c, who, ctx: c.add_document_auto_id({"by": who}, DB),
    ),
    Operation(
        "POST /{keyspace}/_bulk_docs, generated _id",
        DROP_BOX,
        403,
        lambda c, who, ctx: c.bulk_doc_op([BulkDocOperation({"by": who})], DB),
    ),
    Operation(
        "POST /{keyspace}/_bulk_docs, new _id",
        WRITE,
        403,
        lambda c, who, ctx: c.bulk_doc_op([BulkDocOperation({"by": who}, _id=f"bulk_{who}")], DB),
    ),
    Operation(
        "POST /{keyspace}/_bulk_docs, update",
        WRITE,
        403,
        lambda c, who, ctx: c.bulk_doc_op(
            [BulkDocOperation({"by": who}, _id="name_4", rev=ctx.revs["name_4"], optype="update")], DB
        ),
    ),
    Operation(
        "PUT /{keyspace}/{docid}",
        WRITE,
        403,
        lambda c, who, ctx: c.put_document_with_id({"by": who}, f"put_{who}", DB),
    ),
    Operation(
        "DELETE /{keyspace}/{docid}",
        WRITE,
        403,
        lambda c, who, ctx: c.delete_document("name_5", ctx.revs["name_5"], DB),
    ),
    Operation(
        "PUT /{keyspace}/{docid}/{key}",
        WRITE,
        403,
        lambda c, who, ctx: c.put_sub_document("name_2", ctx.revs["name_2"], "contact", DB, value={"by": who}),
    ),
    Operation(
        "DELETE /{keyspace}/{docid}/{key}",
        WRITE,
        403,
        lambda c, who, ctx: c.delete_sub_document("name_3", ctx.revs["name_3"], "gender", DB),
    ),
    Operation(
        "DELETE /_replicate/{taskid}",
        {"qe_admin", "replicator"},
        401,
        lambda c, who, ctx: c.stop_replication(ctx.task_id),
    ),
]

# Requests that Edge Server allows although it must not, with what it answers instead of the expected status.
KNOWN_BUGS = {
    # Bug: _bulk_docs and the {key} handler skip the check that write-only users only create new documents (CBL-9289).
    ("write_only", "POST /{keyspace}/_bulk_docs, new _id"): OK,
    ("write_only", "POST /{keyspace}/_bulk_docs, update"): OK,
    ("write_only", "PUT /{keyspace}/{docid}/{key}"): OK,
    ("write_only", "DELETE /{keyspace}/{docid}/{key}"): OK,
}


def expected_status(who: str, op: Operation) -> str | int:
    if who == WRONG_PASSWORD:
        return 401
    if who in op.allowed:
        return OK
    return op.anonymous if who == ANONYMOUS else 403


async def actual_status(request: Awaitable[Any]) -> str | int:
    try:
        await request
        return OK
    except CblEdgeServerBadResponseError as e:
        return e.code


@pytest.mark.openapi
@pytest.mark.min_edge_servers(1)
class TestPublicApiAuthorization(CBLTestClass):
    @pytest.mark.parametrize("who", [*USERS, ANONYMOUS, WRONG_PASSWORD])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_public_api_authorization(self, cblpytest: CBLPyTest, who: str) -> None:
        self.mark_test_step("Write the users file, and start Edge Server with access control on the names dataset")
        manager = cblpytest.edge_servers[0]
        await manager.write_file(USERS_FILE, json.dumps(USERS, indent=2))
        await manager.configure_dataset(db_name=DB, config_file=str(CONFIG))

        self.mark_test_step("As the admin, read the revisions of the documents to change, and start a replication")
        async with manager.get_user_client(get_basic_auth_headers("qe_admin", PASSWORD)) as admin:
            revs = {
                doc_id: (await admin.get_document(DB, doc_id)).revid
                for doc_id in ("name_2", "name_3", "name_4", "name_5")
            }
            task_id = await admin.start_replication(
                DB, UNREACHABLE_TARGET, user=None, password=None, bidirectional=False, continuous=True
            )
        context = Context(revs, task_id)

        self.mark_test_step(f"Send one valid request per operation as {who}, and record each status")
        if who == ANONYMOUS:
            client_context = manager.get_anonymous_client()
        else:
            password = "wrong" if who == WRONG_PASSWORD else PASSWORD
            client_context = manager.get_user_client(
                get_basic_auth_headers("reader" if who == WRONG_PASSWORD else who, password)
            )
        async with client_context as client:
            statuses = {op.name: await actual_status(op.call(client, who, context)) for op in OPERATIONS}

        self.mark_test_step("Check each status against the expected access and the known bugs")
        mismatches = []
        for op in OPERATIONS:
            expected = expected_status(who, op)
            allowed_actual = KNOWN_BUGS.get((who, op.name), expected)
            if statuses[op.name] != allowed_actual:
                note = f", known bug {allowed_actual!r}" if (who, op.name) in KNOWN_BUGS else ""
                mismatches.append(f"{op.name}: expected {expected!r}{note}, got {statuses[op.name]!r}")
        assert not mismatches, f"{who}:\n" + "\n".join(mismatches)
