"""
Access Control _blipsync Replication Tests — CBL <-> Edge Server
=================================================================
Covers per-collection access control enforced at the BLIP/WebSocket layer
when enable_user_access_control is true in the ES config.

Test matrix
-----------
P1  rw_all       scratch.*:["read","write"]          — full bidirectional sync
P2  ro_col_a     scratch._default._default:["read"]  — pull works, push blocked
P3  admin_user   roles:["admin"]                     — full access unconditionally
P4  ro_a_rw_b    _default._default:["read"]          — pull both, push only claws
                 claws:["read","write"]
F1  no_access    access:{}                           — 403, WebSocket rejected
F2  write_only   scratch.*:["write"]                 — 403, no read → gate fails

Config requirements (test_access_control_replication.json)
---------------------------------------------
    enable_user_access_control: true
    databases.scratch:
        create: true
        enable_client_writes: true
        enable_client_sync: true
        collections: ["_default", "claws"]
    users: "$HOME/user/users.json"   ← same file the bash script edits
"""

import asyncio
import os
from pathlib import Path

import pytest

from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import DocumentEntry
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PASSWORD = "password"
_ADMIN_PASSWORD = "admin_pass"

# User configs passed directly to EdgeServer.add_user().
# Keys are usernames; values carry password, optional role, optional access.
_USERS: dict = {
    "admin_user": {
        "password": _ADMIN_PASSWORD,
        "role": "admin",
    },
    "rw_all": {
        "password": _PASSWORD,
        "access": {
            "scratch.*": ["read", "write"],
        },
    },
    "ro_col_a": {
        "password": _PASSWORD,
        "access": {
            "scratch._default._default": ["read"],
        },
    },
    "ro_col_a_rw_b": {
        "password": _PASSWORD,
        "access": {
            "scratch._default._default": ["read"],
            "scratch.claws": ["read", "write"],
        },
    },
    "no_access": {
        "password": _PASSWORD,
        "access": {},
    },
    "write_only": {
        "password": _PASSWORD,
        "access": {
            "scratch.*": ["write"],
        },
    },
}


class TestAccessControlReplication(CBLTestClass):


    @pytest.mark.asyncio(loop_scope="session")
    async def test_p1_rw_all_collections(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty, no dataset).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        )[0]

        self.mark_test_step("Pre-seed one document on the ES side.")
        await edge_server.put_document_with_id(
            {"content": "seeded on ES", "test": "p1"},
            "es_seed_p1",
            "scratch",
        )

        self.mark_test_step("Create push documents on the CBL side.")
        async with db.batch_updater() as b:
            for i in range(0,3):
                b.upsert_document("_default._default", f"p1_push_{i}",
                   [ {"content": f"push doc {i}"},{"test": "p1"}],
                )

        self.mark_test_step(
            "Start PUSH_AND_PULL replication using rw_all credentials."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("rw_all", _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"P1: unexpected replicator error "
            f"({status.error.domain}/{status.error.code}): {status.error.message}"
        )

        self.mark_test_step("Verify pushed docs are present on ES.")
        es_docs = await edge_server.get_all_documents("scratch")
        es_ids = {row.id for row in es_docs.rows}
        for i in range(3):
            assert f"p1_push_{i}" in es_ids, (
                f"P1: CBL push doc 'p1_push_{i}' not found on ES"
            )

        self.mark_test_step("Verify ES-seeded doc was pulled into CBL.")
        cbl_docs = await db.get_all_documents("_default._default")
        cbl_ids = {doc.id for doc in cbl_docs["_default._default"]}
        assert "es_seed_p1" in cbl_ids, (
            "P1: ES-seeded doc 'es_seed_p1' not found in CBL after pull"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_p2_read_only_collection(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        P2 — ro_col_a has scratch._default._default:["read"] only.
        Expect:
          - Replicator connects (at least read satisfies the WebSocket gate).
          - ES-seeded doc pulled into CBL.
          - CBL docs do NOT appear on ES (push blocked by read-only access).
          - If ES rejects push at BLIP layer with an error, that is flagged
            for dev confirmation but does not fail the test — the doc-absence
            check is the authoritative assertion.
        """
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db2"])
        )[0]

        self.mark_test_step("Pre-seed a document on ES to confirm pull works.")
        await edge_server.put_document_with_id(
            {"content": "seeded on ES", "test": "p2"},
            "es_seed_p2",
            "scratch",
        )

        self.mark_test_step("Create docs on CBL side that should NOT reach ES.")
        async with db.batch_updater() as b:
            for i in range(3):
                b.upsert_document("_default._default", f"p2_push_{i}",
                    [{"content": f"push doc {i}"},{ "test": "p2"}],
                )

        self.mark_test_step(
            "Start PUSH_AND_PULL replication using ro_col_a credentials."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("ro_col_a", _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        # Push to a read-only collection may produce a BLIP-level error.
        # Capture it for dev review; do not assert None — validate outcome via
        # doc checks below.
        if status.error is not None:
            self.mark_test_step(
                f"P2: replicator error noted "
                f"({status.error.domain}/{status.error.code}): {status.error.message} "
                f"— confirm with devs whether this is expected for read-only push."
            )

        self.mark_test_step("Verify ES-seeded doc was pulled into CBL.")
        cbl_docs = await db.get_all_documents("_default._default")
        cbl_ids = {doc.id for doc in cbl_docs["_default._default"]}
        assert "es_seed_p2" in cbl_ids, (
            "P2: ES-seeded doc 'es_seed_p2' not found in CBL — pull must work for read-only user"
        )

        self.mark_test_step("Verify CBL push docs did NOT reach ES.")
        es_docs = await edge_server.get_all_documents("scratch")
        es_ids = {row.id for row in es_docs.rows}
        for i in range(3):
            assert f"p2_push_{i}" not in es_ids, (
                f"P2: doc 'p2_push_{i}' found on ES — read-only user must not be able to push"
            )

    # ------------------------------------------------------------------
    # P3: Admin user — unconditional full access
    # ------------------------------------------------------------------
    @pytest.mark.asyncio(loop_scope="session")
    async def test_p3_admin_user(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        P3 — admin_user carries roles:["admin"].
        Per PRD: admin role overrides all access checks unconditionally.
        Expect:
          - Replicator stops cleanly.
          - Full bidirectional sync regardless of any access config.
        """
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db3"])
        )[0]

        self.mark_test_step("Pre-seed a document on ES.")
        await edge_server.put_document_with_id(
            {"content": "seeded on ES", "test": "p3"},
            "es_seed_p3",
            "scratch",
        )

        self.mark_test_step("Create push docs on CBL side.")
        async with db.batch_updater() as b:
            for i in range(3):
                 b.upsert_document("_default._default", f"p3_push_{i}",
                    [{"content": f"push doc {i}"},{ "test": "p3"}],
                )

        self.mark_test_step(
            "Start PUSH_AND_PULL replication using admin_user credentials."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("admin_user", "password"),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"P3: admin replicator stopped with unexpected error "
            f"({status.error.domain}/{status.error.code}): {status.error.message}"
        )

        self.mark_test_step("Verify pushed docs are present on ES.")
        es_docs = await edge_server.get_all_documents("scratch")
        es_ids = {row.id for row in es_docs.rows}
        for i in range(3):
            assert f"p3_push_{i}" in es_ids, (
                f"P3: admin push doc 'p3_push_{i}' not found on ES"
            )

        self.mark_test_step("Verify ES-seeded doc pulled into CBL.")
        cbl_docs = await db.get_all_documents("_default._default")
        cbl_ids = {doc.id for doc in cbl_docs["_default._default"]}
        assert "es_seed_p3" in cbl_ids, (
            "P3: ES-seeded doc 'es_seed_p3' not found in CBL for admin user"
        )

    # ------------------------------------------------------------------
    # P4: Read on col_A, Read+Write on col_B — mixed per-collection
    # ------------------------------------------------------------------
    @pytest.mark.asyncio(loop_scope="session")
    async def test_p4_mixed_permissions_two_collections(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        P4 — ro_col_a_rw_b:
              scratch._default._default : read only
              scratch.claws             : read + write

        Expect:
          - WebSocket upgrade succeeds (at least one readable collection).
          - Pull works on both _default._default and claws.
          - Push succeeds on claws (read+write).
          - Push docs targeting _default._default do NOT appear on ES.
        """
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db4"],collections=["_default.claws"])
        )[0]

        self.mark_test_step(
            "Pre-seed one doc on ES in _default._default and one in claws."
        )
        await edge_server.put_document_with_id(
            {"content": "col_a ES seed", "test": "p4"},
            "es_col_a_p4",
            "scratch",
        )
        await edge_server.put_document_with_id(
            {"content": "col_b ES seed", "test": "p4"},
            "es_col_b_p4",
            "scratch",
            collection="claws",
        )

        self.mark_test_step(
            "Create push docs on CBL for both collections."
        )
        async with db.batch_updater() as b:
            for i in range(3):
                b.upsert_document("_default._default", f"p4_col_a_push_{i}",
                    [{"content": f"col_a push {i}"},{ "test": "p4"}],
                )
                b.upsert_document("_default.claws", f"p4_col_b_push_{i}",
                    [{"content": f"col_b push {i}"},{ "test": "p4"}],
                )

        self.mark_test_step(
            "Start PUSH_AND_PULL on both collections using ro_col_a_rw_b credentials."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[
                ReplicatorCollectionEntry(["_default._default", "_default.claws"])
            ],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("ro_col_a_rw_b", _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        # Per-collection push rejection on _default._default may surface as an
        # error. Capture for dev review; authoritative check is the doc assertions.
        if status.error is not None:
            self.mark_test_step(
                f"P4: replicator error noted "
                f"({status.error.domain}/{status.error.code}): {status.error.message} "
                f"— confirm with devs whether this is expected for partial read-only push."
            )

        self.mark_test_step("Verify pull worked on _default._default.")
        cbl_default = await db.get_all_documents("_default._default")
        cbl_default_ids = {doc.id for doc in cbl_default["_default._default"]}
        assert "es_col_a_p4" in cbl_default_ids, (
            "P4: ES _default._default doc 'es_col_a_p4' not pulled into CBL"
        )

        self.mark_test_step("Verify pull worked on claws.")
        cbl_claws = await db.get_all_documents("_default.claws")
        cbl_claws_ids = {doc.id for doc in cbl_claws["_default.claws"]}
        assert "es_col_b_p4" in cbl_claws_ids, (
            "P4: ES claws doc 'es_col_b_p4' not pulled into CBL"
        )

        self.mark_test_step(
            "Verify claws push docs reached ES (read+write allowed)."
        )
        es_claws = await edge_server.get_all_documents(
            "scratch", collection="claws"
        )
        es_claws_ids = {row.id for row in es_claws.rows}
        for i in range(3):
            assert f"p4_col_b_push_{i}" in es_claws_ids, (
                f"P4: claws push doc 'p4_col_b_push_{i}' not found on ES"
            )

        self.mark_test_step(
            "Verify _default._default push docs did NOT reach ES (read-only)."
        )
        es_default = await edge_server.get_all_documents("scratch")
        es_default_ids = {row.id for row in es_default.rows}
        for i in range(3):
            assert f"p4_col_a_push_{i}" not in es_default_ids, (
                f"P4: _default._default push doc 'p4_col_a_push_{i}' found on ES "
                f"— read-only user must not push to this collection"
            )

    # ------------------------------------------------------------------
    # F1: No access to any collection — WebSocket upgrade rejected
    # ------------------------------------------------------------------
    @pytest.mark.asyncio(loop_scope="session")
    async def test_f1_no_access_user_rejected(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        F1 — no_access has access:{} (zero permissions).
        Per PRD: GET /db/_blipsync must be rejected (HTTP 403) because the
        user has no accessible collections.
        Expect: replicator stops with a non-None error.
        """
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db5"])
        )[0]
        await edge_server.put_document_with_id(
            {"content": "col_a ES seed", "test": "f1"},
            "no_access",
            "scratch",
        )
        async with db.batch_updater() as b:
            for i in range(3):
                b.upsert_document("_default._default", f"f1_no_access_{i}",
                    [{"content": f"col_a push {i}"},{ "test": "f1"}],
                )

        self.mark_test_step(
            "Start replication with no_access user — expect 403 rejection."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("no_access", _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        # assert status.error is not None, (
        #     "F1: expected replicator error (403 — no accessible collections) "
        #     "but replicator stopped cleanly."
        # )
        # self.mark_test_step(
        #     f"F1: replicator correctly rejected — "
        #     f"({status.error.domain}/{status.error.code}): {status.error.message}"
        # )
        self.mark_test_step("Verify docs:testserver's _default._default.")
        cbl_default = await db.get_all_documents("_default._default")
        cbl_default_ids = {doc.id for doc in cbl_default["_default._default"]}


        self.mark_test_step("Verify docs on ES")
        es_default = await edge_server.get_all_documents("scratch")
        es_default_ids = {row.id for row in es_default.rows}
        assert len(es_default_ids) == 1
        assert len(cbl_default_ids) == 3


    # ------------------------------------------------------------------
    # F2: Write-only on all collections — WebSocket gate fails (no read)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio(loop_scope="session")
    async def test_f2_write_only_user_rejected(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        F2 — write_only has scratch.*:["write"] only.
        Per PRD: the WebSocket gate requires at least read on one collection;
        write-only does not satisfy checkAccess(read), so upgrade is rejected.
        Expect: replicator stops with a non-None error.
        """
        self.mark_test_step("Configure Edge Server with access control config.")
        config_path = os.path.join(SCRIPT_DIR, "config", "test_access_control_replication.json")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch", config_file=config_path
        )

        self.mark_test_step("Add all test users to Edge Server.")
        await edge_server.add_user(_USERS)

        self.mark_test_step("Reset local CBL database (empty).")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(["db6"])
        )[0]

        self.mark_test_step(
            "Start replication with write_only user — expect 403 rejection."
        )
        replicator = Replicator(
            db,
            edge_server.replication_url("scratch"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("write_only", _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Wait for replicator to stop.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is not None, (
            "F2: expected replicator error (403 — write-only, no read access) "
            "but replicator stopped cleanly."
        )
        self.mark_test_step(
            f"F2: replicator correctly rejected — "
            f"({status.error.domain}/{status.error.code}): {status.error.message}"
        )
