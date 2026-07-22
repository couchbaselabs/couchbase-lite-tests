"""
Access Control Tests — Edge Server 1.1.0

Priority 1: Flag behaviour (Scenario 3)
Priority 2: Admin role override (Scenario 4)
"""

from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)

user_config={
    "admin": {
        "password": "adminpass",
        "roles": ["admin"]
    },
    "AppUser1": {
        "password": "user1pass",
        "access": {
            "travel.*": ["read"],
            "scratch": ["read", "write"]
        }
    },
    "AppUser2": {
        "password": "user2pass",
        "access": {
            "travel.*": ["read"]
        }
    },
    "NoAccessUser": {
        "password": "noaccesspass",
        "access": {}
    }
}


class TestAccessControlFlagBehaviour(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_flag_absent_grants_full_access(
        self, cblpytest: CBLPyTest
    ) -> None:
        self.mark_test_step(
            "Start ES with enable_user_access_control absent. "
            "All users should have full read/write access."
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch",
            config_file=f"{SCRIPT_DIR}/config/test_no_access_control.json",
        )

        # Pre-create sessions for both app users
        user1_session = edge_server.create_user_session(*_APP_USER1)
        user2_session = edge_server.create_user_session(*_APP_USER2)

        self.mark_test_step(
            "AppUser1 writes a document to scratch — must succeed (200/201)"
        )
        doc = {"_id": "flag_absent_doc1", "test": "access_control_flag"}
        await edge_server._send_request(
            "put",
            "/scratch/flag_absent_doc1",
            payload=_dict_payload(doc),
            session=user1_session,
        )

        self.mark_test_step("AppUser1 reads the document back — must succeed")
        result = await edge_server._send_request(
            "get", "/scratch/flag_absent_doc1", session=user1_session
        )
        assert result.get("_id") == "flag_absent_doc1", (
            "Document read back did not match written document"
        )

        self.mark_test_step(
            "AppUser2 reads from travel.inventory.hotels — must succeed (no 403)"
        )
        # Any read on the travel db should work when flag is absent
        await edge_server._send_request(
            "get", "/travel/_all_docs", session=user2_session
        )

        self.mark_test_step(
            "GET /_all_dbs as AppUser1 — must return both travel and scratch, no 403"
        )
        all_dbs = await edge_server._send_request(
            "get", "/_all_dbs", session=user1_session
        )
        assert isinstance(all_dbs, list), "/_all_dbs did not return a list"
        assert "travel" in all_dbs, "travel missing from /_all_dbs when flag absent"
        assert "scratch" in all_dbs, "scratch missing from /_all_dbs when flag absent"

        self.mark_test_step(
            "NoAccessUser (no access property) writes a document — must succeed "
            "because flag is absent"
        )
        no_access_session = edge_server.create_user_session(*_NO_ACCESS)
        doc2 = {"_id": "flag_absent_doc2", "test": "no_access_user_write"}
        await edge_server._send_request(
            "put",
            "/scratch/flag_absent_doc2",
            payload=_dict_payload(doc2),
            session=no_access_session,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_flag_true_no_access_property_blocks_all(
        self, cblpytest: CBLPyTest
    ) -> None:
        self.mark_test_step(
            "Start ES with enable_user_access_control: true. "
            "NoAccessUser has no access property — every request must 403."
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch",
            config_file=f"{SCRIPT_DIR}/config/test_access_control.json",
        )
        no_access_session = edge_server.create_user_session(*_NO_ACCESS)

        self.mark_test_step("NoAccessUser GET /scratch/_all_docs — expect 403")
        _assert_403(await _try_request(
            edge_server, "get", "/scratch/_all_docs", session=no_access_session
        ))

        self.mark_test_step(
            "NoAccessUser PUT /scratch/some_doc — expect 403"
        )
        _assert_403(await _try_request(
            edge_server,
            "put",
            "/scratch/some_doc",
            payload=_dict_payload({"_id": "some_doc"}),
            session=no_access_session,
        ))

        self.mark_test_step(
            "NoAccessUser GET /_all_dbs — expect empty list or 403 "
            "(user must not see any database)"
        )
        result = await _try_request(
            edge_server, "get", "/_all_dbs", session=no_access_session
        )
        # ES either returns 403 or an empty list — both are acceptable;
        # what is NOT acceptable is returning the real database list.
        if isinstance(result, list):
            assert result == [], (
                f"NoAccessUser must not see any database in /_all_dbs, got: {result}"
            )
        else:
            _assert_403(result)

        self.mark_test_step(
            "NoAccessUser GET /travel/_all_docs — expect 403"
        )
        _assert_403(await _try_request(
            edge_server, "get", "/travel/_all_docs", session=no_access_session
        ))


class TestAdminRoleOverride(CBLTestClass):
    """
    Scenario 4 — admin role always has full access regardless of access property.

    Admin must be able to read/write every collection across all databases,
    access /_replicate and /_active_tasks, and any access property
    accidentally defined on the admin user must be completely ignored.
    """

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_has_full_access_across_databases(
        self, cblpytest: CBLPyTest
    ) -> None:
        self.mark_test_step(
            "Start ES with enable_user_access_control: true. "
            "Admin user has no access property — must still have full RW access."
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch",
            config_file=f"{SCRIPT_DIR}/config/test_access_control.json",
        )
        admin_session = edge_server.create_user_session(*_ADMIN)

        self.mark_test_step("Admin reads from travel via /_all_docs — must succeed")
        await edge_server._send_request(
            "get", "/travel/_all_docs", session=admin_session
        )

        self.mark_test_step("Admin writes a document to scratch — must succeed")
        doc = {"_id": "admin_write_doc", "written_by": "admin"}
        await edge_server._send_request(
            "put",
            "/scratch/admin_write_doc",
            payload=_dict_payload(doc),
            session=admin_session,
        )

        self.mark_test_step("Admin reads back the document from scratch — must succeed")
        result = await edge_server._send_request(
            "get", "/scratch/admin_write_doc", session=admin_session
        )
        assert result.get("written_by") == "admin"

        self.mark_test_step("Admin GET /_all_dbs — must see travel and scratch")
        all_dbs = await edge_server._send_request(
            "get", "/_all_dbs", session=admin_session
        )
        assert "travel" in all_dbs, "Admin must see travel in /_all_dbs"
        assert "scratch" in all_dbs, "Admin must see scratch in /_all_dbs"

        self.mark_test_step("Admin GET /_active_tasks — must succeed (not 403)")
        tasks = await edge_server._send_request(
            "get", "/_active_tasks", session=admin_session
        )
        assert isinstance(tasks, list), "/_active_tasks must return a list for admin"

        self.mark_test_step(
            "Admin GET /_replicate — must succeed (replicate endpoint requires admin role)"
        )
        replications = await edge_server._send_request(
            "get", "/_replicate", session=admin_session
        )
        assert isinstance(replications, list), (
            "/_replicate must return a list for admin"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_access_property_is_ignored(
        self, cblpytest: CBLPyTest
    ) -> None:
        self.mark_test_step(
            "Admin user with an access property defined must behave identically "
            "to admin without one — the access block must be silently ignored."
        )
        # This test uses a separate config where the admin user has a restrictive
        # access block to prove it is ignored.
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="scratch",
            config_file=f"{SCRIPT_DIR}/config/test_access_control_admin_with_access.json",
        )
        admin_session = edge_server.create_user_session(*_ADMIN)

        self.mark_test_step(
            "Admin writes to scratch even though access block restricts to travel only"
        )
        doc = {"_id": "admin_override_doc", "check": "access_ignored"}
        await edge_server._send_request(
            "put",
            "/scratch/admin_override_doc",
            payload=_dict_payload(doc),
            session=admin_session,
        )

        self.mark_test_step(
            "Admin reads from travel even though access block has no travel entry"
        )
        await edge_server._send_request(
            "get", "/travel/_all_docs", session=admin_session
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

class _dict_payload:
    """Minimal JSONSerializable wrapper for inline dicts."""
    def __init__(self, d: dict):
        self._d = d
    def serialize(self) -> str:
        import json
        return json.dumps(self._d)


async def _try_request(edge_server, method, path, payload=None, session=None):
    """
    Execute a request and return either the response dict/list on success,
    or a dict {"__status": status_code} on HTTP error — never raises.
    """
    try:
        return await edge_server._send_request(
            method, path, payload=payload, session=session
        )
    except CblEdgeServerBadResponseError as e:
        return {"__status": e.status}


def _assert_403(result):
    assert isinstance(result, dict) and result.get("__status") == 403, (
        f"Expected 403 but got: {result}"
    )