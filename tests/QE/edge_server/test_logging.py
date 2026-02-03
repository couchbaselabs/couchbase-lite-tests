import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload

SCRIPT_DIR = str(Path(__file__).parent)

AUDIT_ASSERTIONS: dict[str, list[tuple[str, bool, str]]] = {
    "default": [
        ("57344", True, "server started"),
        ("57345", False, "server stopped"),
        ("57346", False, "public HTTP request"),
        ("57355", True, "inter-server replication start"),
        ("57356", False, "inter-server replication stop"),
        ("57358", False, "create document"),
        ("57359", False, "read document"),
        ("57360", False, "update document"),
        ("57361", False, "delete document"),
    ],
    "disabled": [
        ("57344", False, "server started"),
        ("57345", False, "server stopped"),
        ("57346", False, "public HTTP request"),
        ("57355", False, "inter-server replication start"),
        ("57356", False, "inter-server replication stop"),
    ],
    "enabled": [
        ("57344", True, "server started"),
        ("57345", False, "server stopped"),
        ("57346", True, "public HTTP request"),
        ("57355", True, "inter-server replication start"),
        ("57356", False, "inter-server replication stop"),
        ("57358", False, "create document"),
        ("57359", False, "read document"),
        ("57360", False, "update document"),
        ("57361", False, "delete document"),
    ],
}

AUDIT_CRUD_ASSERTIONS: list[tuple[str, bool, str]] = [
    ("57358", True, "create document"),
    ("57359", True, "read document"),
    ("57360", True, "update document"),
    ("57361", True, "delete document"),
]


def _apply_audit_config_default(config: dict) -> None:
    pass


def _apply_audit_config_disabled(config: dict) -> None:
    config["logging"]["audit"]["disable"] = "*"
    config["logging"]["audit"].pop("enable", None)


def _apply_audit_config_enabled(config: dict) -> None:
    config["logging"]["audit"]["enable"] = "*"
    config["logging"]["audit"].pop("disable", None)


AUDIT_CONFIG_APPLIERS: dict[str, Callable[[dict], None]] = {
    "default": _apply_audit_config_default,
    "disabled": _apply_audit_config_disabled,
    "enabled": _apply_audit_config_enabled,
}


class TestLogging(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("audit_mode", ["default", "disabled", "enabled"])
    async def test_audit_logging(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        audit_mode: str,
    ) -> None:
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket on server.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 5 documents to bucket.")
        for i in range(1, 6):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)

        self.mark_test_step("Creating a database on Sync Gateway.")
        sg_db_name = "db-1"
        sg_config = {
            "bucket": "bucket-1",
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {"sync": "function(doc){channel(doc.channels);}"}
                    }
                }
            },
            "num_index_replicas": 0,
        }
        payload = PutDatabasePayload(sg_config)
        await sync_gateway.put_database(sg_db_name, payload)

        self.mark_test_step("Adding role and user to Sync Gateway.")
        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        self.mark_test_step("Creating a database on Edge Server with audit config.")
        step_descriptions = {
            "default": "Creating a database on Edge Server with default audit config.",
            "disabled": "Creating a database on Edge Server with audit disabled.",
            "enabled": "Creating a database on Edge Server with audit enabled.",
        }
        self.mark_test_step(step_descriptions[audit_mode])
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_audit.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        AUDIT_CONFIG_APPLIERS[audit_mode](config)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        self.mark_test_step("Checking that Sync Gateway has 5 documents.")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )

        response = await edge_server.get_all_documents(es_db_name)
        self.mark_test_step("Checking that Edge Server has 5 documents.")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )

        for event_id, expected_non_empty, step_name in AUDIT_ASSERTIONS[audit_mode]:
            self.mark_test_step(f"Checking audit logs for {step_name}.")
            log = await edge_server.check_log(event_id)
            if expected_non_empty:
                assert len(log) > 0, f"Audit log for {step_name} event not found"
            else:
                assert log == [], f"Audit log for {step_name} event found"

        if audit_mode == "enabled":
            self.mark_test_step(
                "Making CRUD requests to verify audit logs are generated for CRUD operations."
            )
            doc_id = "doc_6"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
            assert response is not None, (
                f"Failed to create document {doc_id} via Edge Server."
            )
            remote_doc = await edge_server.get_document(es_db_name, doc_id)
            assert remote_doc is not None, (
                f"Failed to read document {doc_id} via Edge Server."
            )
            rev_id = remote_doc.revid
            updated_doc_body = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes",
            }
            updated_doc = await edge_server.put_document_with_id(
                updated_doc_body, doc_id, es_db_name, rev=rev_id
            )
            assert updated_doc is not None, (
                f"Failed to update document {doc_id} via Edge Server"
            )
            rev_id = updated_doc.revid
            delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
            assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
                f"Failed to delete document {doc_id} via Edge Server."
            )

            self.mark_test_step(
                "Verifying that audit logs are generated for CRUD operations."
            )
            for event_id, expected_non_empty, step_name in AUDIT_CRUD_ASSERTIONS:
                self.mark_test_step(f"Checking audit log for {step_name} after CRUD.")
                log = await edge_server.check_log(event_id)
                assert expected_non_empty and len(log) > 0, (
                    f"Audit log for {step_name} event not found"
                )

        self.mark_test_step("Audit logging test completed.")
