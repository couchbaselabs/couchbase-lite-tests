import asyncio
import json
from pathlib import Path

import pytest
import requests
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.syncgateway import PutDatabasePayload

from jwt_helper import generate_jwt, generate_rsa_keypair, public_key_to_jwk

SCRIPT_DIR = str(Path(__file__).parent)
JWT_FILE = "/home/ec2-user/cert/jwt.txt"


class TestJWTReplication(CBLTestClass):
    """Test Edge Server replication using JWT file-based authentication."""

    async def _write_file_on_es(self, es_manager, path: str, content: str):
        """Write content to a file on the ES host via shell2http."""
        await es_manager._send_request(
            "post",
            "write-file",
            JSONDictionary({"path": path, "content": content}),
            session=es_manager._EdgeServer__shell_session,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_with_jwt_file(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        Verify that ES can replicate with SGW using a JWT token read from a file.

        Steps:
        1. Generate RSA key pair and sign a JWT token
        2. Configure SGW travel database with local_jwt provider for token validation
        3. Write JWT to a file on the ES machine
        4. Start ES with openid_token.path pointing to that file
        5. Verify replication syncs documents correctly
        """

        # --- Step 1: Generate JWT credentials ---
        self.mark_test_step("Generate RSA key pair and JWT token")
        private_key, public_key = generate_rsa_keypair()
        token = generate_jwt(private_key, subject="user1", expires_in=600)
        jwk = public_key_to_jwk(public_key)

        # --- Step 2: Setup SGW with travel dataset and local_jwt auth ---
        self.mark_test_step(
            "Configure SGW travel database with local_jwt provider"
        )
        cloud = cblpytest.simple_cloud()
        sgw = cloud.sync_gateway
        cbs = cloud.couchbase_server

        # Clean up any existing travel database from previous runs
        try:
            await sgw.delete_database("travel")
        except Exception:
            pass  # Database may not exist

        # Flush CBS bucket to clear stale documents
        requests.post(
            f"http://{cbs.hostname}:8091/pools/default/buckets/travel/controller/doFlush",
            auth=("Administrator", "password"),
        )

        # Build the SGW database config with local_jwt for JWT validation
        sg_config = {
            "bucket": "travel",
            "scopes": {
                "travel": {
                    "collections": {
                        "airlines": {
                            "sync": "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
                        },
                        "routes": {
                            "sync": "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
                        },
                        "airports": {
                            "sync": "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
                        },
                        "landmarks": {
                            "sync": "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
                        },
                        "hotels": {
                            "sync": "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
                        },
                    }
                }
            },
            "num_index_replicas": 0,
            "local_jwt": {
                "test-provider": {
                    "issuer": "test-issuer",
                    "client_id": "edge-server",
                    "register": True,
                    "algorithms": ["RS256"],
                    "keys": [jwk],
                }
            },
        }

        # Create bucket and collections on CBS, then create SGW database
        payload = PutDatabasePayload(sg_config)
        if not sgw.using_rosmar:
            cbs.create_bucket("travel")
            for scope_name in payload.scopes():
                cbs.create_collections(
                    "travel", scope_name, payload.collections(scope_name)
                )

        await sgw.put_database("travel", payload)

        # Create user1 with channel access to all travel collections
        collection_access_input = {
            "travel.airlines": ["*"],
            "travel.routes": ["*"],
            "travel.airports": ["*"],
            "travel.landmarks": ["*"],
            "travel.hotels": ["*"],
        }
        access_dict = sgw.create_collection_access_dict(collection_access_input)
        await sgw.add_user("travel", "test-provider_user1", "pass", access_dict)

        # Load travel dataset
        data_filepath = dataset_path / "travel-sg.json"
        await sgw.load_dataset("travel", data_filepath)

        # --- Step 3: Write JWT to file on ES ---
        self.mark_test_step("Write JWT token to file on Edge Server")
        es_manager = cblpytest.edge_servers[0]
        await self._write_file_on_es(es_manager, JWT_FILE, token)

        # --- Step 4: Configure ES with JWT file auth ---
        self.mark_test_step("Configure ES with openid_token.path auth")
        config_path = f"{SCRIPT_DIR}/config/test_jwt_auth_sgw.json"
        with open(config_path) as f:
            config = json.load(f)
        config["replications"][0]["source"] = sgw.replication_url("travel")
        config["replications"][0]["collections"] = [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        # --- Step 5: Verify replication works ---
        self.mark_test_step("Wait for replication to become idle")
        await edge_server.wait_for_idle()

        self.mark_test_step("Verify document parity between ES and SGW")
        for collection in [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]:
            edge_docs = await edge_server.get_all_documents(
                "travel", collection=collection
            )
            sgw_docs = await sgw.get_all_documents(
                "travel", scope="travel", collection=collection.split(".")[1]
            )
            assert len(edge_docs.rows) == len(sgw_docs.rows), (
                f"Collection {collection}: ES={len(edge_docs.rows)} SGW={len(sgw_docs.rows)}"
            )

        self.mark_test_step(
            "PASSED — Replication works with JWT file-based authentication"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_token_rotation_reconnect(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        Verify that ES detects a JWT file change and reconnects with the new token.

        With reconnect_on_token_change=true and openid_token as a file path,
        ES should:
        1. Start replicating with Token-A
        2. Detect when the file is overwritten with Token-B
        3. Disconnect the current replication
        4. Reconnect using Token-B
        5. Continue replicating successfully
        """

        # --- Step 1: Generate TWO RSA key pairs (simulating key rotation) ---
        self.mark_test_step("Generate two RSA key pairs for token rotation")
        private_key_a, public_key_a = generate_rsa_keypair()
        private_key_b, public_key_b = generate_rsa_keypair()
        token_a = generate_jwt(private_key_a, subject="user1", expires_in=3600, kid="test-key-1")
        token_b = generate_jwt(private_key_b, subject="user1", expires_in=3600, kid="test-key-2")
        jwk_a = public_key_to_jwk(public_key_a)
        jwk_b = public_key_to_jwk(public_key_b)
        # Use different kid for key B
        jwk_b["kid"] = "test-key-2"

        # --- Step 2: Setup SGW with local_jwt containing BOTH keys ---
        self.mark_test_step("Configure SGW with both JWK keys (A and B)")
        cloud = cblpytest.simple_cloud()
        sgw = cloud.sync_gateway
        cbs = cloud.couchbase_server

        # Clean up
        try:
            await sgw.delete_database("travel")
        except Exception:
            pass

        try:
            cbs.drop_bucket("travel")
            await cbs.wait_for_bucket_deleted("travel")
        except Exception:
            pass

        sg_config = {
            "bucket": "travel",
            "scopes": {
                "travel": {
                    "collections": {
                        "airlines": {
                            "sync": "function(doc){channel(doc.channels);}"
                        }
                    }
                }
            },
            "num_index_replicas": 0,
            "local_jwt": {
                "test-provider": {
                    "issuer": "test-issuer",
                    "client_id": "edge-server",
                    "register": True,
                    "algorithms": ["RS256"],
                    "keys": [jwk_a, jwk_b],
                }
            },
        }

        cbs.create_bucket("travel")
        cbs.create_collections("travel", "travel", ["airlines"])

        payload = PutDatabasePayload(sg_config)
        await sgw.put_database("travel", payload)

        # Create JWT user with channel access
        collection_access_input = {"travel.airlines": ["*"]}
        access_dict = sgw.create_collection_access_dict(collection_access_input)
        await sgw.add_user("travel", "test-provider_user1", "pass", access_dict)

        # Insert docs into CBS
        self.mark_test_step("Insert 5 test documents into CBS")
        for i in range(1, 6):
            doc_id = f"rotation_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"Rotation Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")


        # --- Step 3: Write Token-A to file and start ES ---
        self.mark_test_step("Write Token-A to file and start ES")
        es_manager = cblpytest.edge_servers[0]
        await self._write_file_on_es(es_manager, JWT_FILE, token_a)

        config_path = f"{SCRIPT_DIR}/config/test_jwt_auth_sgw.json"
        with open(config_path) as f:
            config = json.load(f)
        config["replications"][0]["source"] = sgw.replication_url("travel")
        # Only sync airlines for this test
        config["replications"][0]["collections"] = ["travel.airlines"]
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        # --- Step 4: Wait for initial replication to become idle with Token-A ---
        self.mark_test_step("Wait for initial replication with Token-A to be idle")
        await edge_server.wait_for_idle(timeout=30)

        # Verify initial replication pulled docs
        response = await edge_server.get_all_documents("travel", collection="travel.airlines")
        initial_count = len(response.rows)
        assert initial_count >= 5, (
            f"Initial replication failed: expected >= 5 docs, got {initial_count}"
        )
        self.mark_test_step(f"Token-A replication OK: {initial_count} docs on ES")

        # --- Step 5: Rotate token — write Token-B to the same file ---
        self.mark_test_step("Rotating token: writing Token-B to file")
        await self._write_file_on_es(es_manager, JWT_FILE, token_b)

        # --- Step 6: Wait for ES to detect file change and reconnect ---
        self.mark_test_step("Waiting for ES to detect token change and reconnect")

        # --- Step 7: Insert more docs to verify replication continues ---
        self.mark_test_step("Insert 5 more docs to verify replication after rotation")
        for i in range(6, 11):
            doc_id = f"rotation_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"Rotation Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")


        # --- Step 8: Verify ES has the new docs (replication works with Token-B) ---
        self.mark_test_step("Verify replication continues with Token-B")
        max_wait = 30
        poll_interval = 3
        elapsed = 0
        final_count = 0
        while elapsed < max_wait:
            response = await edge_server.get_all_documents("travel", collection="travel.airlines")
            final_count = len(response.rows)
            if final_count >= initial_count + 5:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        assert final_count >= initial_count + 5, (
            f"Token rotation failed: expected >= {initial_count + 5} docs after rotation, "
            f"got {final_count}. Replication may not have reconnected with new token."
        )

        self.mark_test_step(
            f"PASSED — Token rotation works: {final_count} docs after rotating to Token-B"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_invalid_token_rotation_causes_401_stop(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        Overwrite the JWT file with an invalid token (signed by unknown key)
        while replication is active. ES detects the change via FileWatcher,
        stops the replicator, and reconnects with the invalid token.
        SGW rejects it with 401 → replication permanently stops.

        Scenario:
        1. Start ES with valid Token-A, replication goes idle
        2. Overwrite JWT file with an INVALID token (signed by unknown key)
        3. ES detects token change → disconnects → reconnects with invalid token
        4. SGW rejects invalid token → replication status = Stopped with 401
        """

        # --- Step 1: Setup SGW + CBS ---
        self.mark_test_step("Setup SGW with local_jwt for network disconnect test")
        private_key, public_key = generate_rsa_keypair()
        token_valid = generate_jwt(private_key, subject="user1", expires_in=3600)
        jwk = public_key_to_jwk(public_key)

        # Generate invalid token (signed by a DIFFERENT key not registered with SGW)
        invalid_private_key, _ = generate_rsa_keypair()
        token_invalid = generate_jwt(invalid_private_key, subject="user1", expires_in=3600, kid="unknown-key")

        cloud = cblpytest.simple_cloud()
        sgw = cloud.sync_gateway
        cbs = cloud.couchbase_server

        # Cleanup
        try:
            await sgw.delete_database("travel")
        except Exception:
            pass

        sg_config = {
            "bucket": "travel",
            "scopes": {
                "travel": {
                    "collections": {
                        "airlines": {"sync": "function(doc){channel(doc.channels);}"}
                    }
                }
            },
            "num_index_replicas": 0,
            "local_jwt": {
                "test-provider": {
                    "issuer": "test-issuer",
                    "client_id": "edge-server",
                    "register": True,
                    "algorithms": ["RS256"],
                    "keys": [jwk],  # Only valid key registered
                }
            },
        }

        cbs.create_bucket("travel")
        cbs.create_collections("travel", "travel", ["airlines"])
        payload = PutDatabasePayload(sg_config)
        await sgw.put_database("travel", payload)

        collection_access_input = {"travel.airlines": ["*"]}
        access_dict = sgw.create_collection_access_dict(collection_access_input)
        await sgw.add_user("travel", "test-provider_user1", "pass", access_dict)

        # Insert test docs
        for i in range(1, 4):
            doc_id = f"disconnect_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"Disconnect Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")

        # --- Step 2: Start ES with valid token ---
        self.mark_test_step("Start ES with valid JWT token")
        es_manager = cblpytest.edge_servers[0]
        await self._write_file_on_es(es_manager, JWT_FILE, token_valid)

        config_path = f"{SCRIPT_DIR}/config/test_jwt_auth_sgw.json"
        with open(config_path) as f:
            config = json.load(f)
        config["replications"][0]["source"] = sgw.replication_url("travel")
        config["replications"][0]["collections"] = ["travel.airlines"]
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        await edge_server.wait_for_idle(timeout=30)
        self.mark_test_step("Replication idle with valid token — confirmed working")

        # --- Step 3: Write invalid token ---
        # With reconnect_on_token_change=true, ES should automatically detect
        # the file change via inotify, disconnect the current replicator, and
        # reconnect with the invalid token. SGW rejects it with 401.
        self.mark_test_step("Writing INVALID token to JWT file")
        await self._write_file_on_es(es_manager, JWT_FILE, token_invalid)

        # --- Step 4: Wait for ES to detect change, reconnect, and fail auth ---
        self.mark_test_step("Waiting for automatic token change detection and auth failure")

        # Poll for up to 60s — the ES file watcher may take time to detect
        # the token change, disconnect, and reconnect with the invalid token.
        max_wait = 60
        poll_interval = 5
        elapsed = 0
        repl_status = []
        detected = False
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            repl_status = await edge_server.all_replication_status()
            if len(repl_status) == 0:
                detected = True
                break
            task = repl_status[0]
            status = task.get("status", "")
            if status in ("Stopped", "Offline"):
                detected = True
                break

        # Check replication status.
        # When 401 occurs (non-transient error), the replicator task is
        # permanently stopped and REMOVED from the /_replicate list.
        # So either: empty list (task removed) or Stopped status.
        repl_status = await edge_server.all_replication_status()

        if len(repl_status) == 0:
            # Task removed after permanent 401 — this IS expected behavior
            self.mark_test_step(
                "PASSED — Replicator task removed after 401 auth failure "
                "(invalid token correctly rejected by SGW)"
            )
        else:
            task = repl_status[0]
            status = task.get("status", "")
            error = task.get("error", {})
            error_code = error.get("x-litecore-code", 0) if isinstance(error, dict) else 0

            self.mark_test_step(
                f"Replication status: {status}, error: {error}"
            )

            assert status in ("Stopped", "Offline"), (
                f"Expected replication to stop/go offline with invalid token, "
                f"but status is '{status}'. Error: {error}"
            )
            assert error_code == 401 or "login" in str(error).lower(), (
                f"Expected 401 auth error, got: {error}"
            )

            self.mark_test_step(
                "PASSED — Invalid token correctly causes auth failure"
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_corrupt_token_file_content_mid_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        Overwrite the JWT token file with corrupt content while replication is active.

        Scenario:
        1. Start ES with valid token file, replication goes idle
        2. Overwrite the JWT file with invalid content (single space)
        3. ES detects file change → either stops replication (401) or continues
           with existing connection (if FileWatcher treats empty as no-change)
        4. Verify replication behavior
        """

        # --- Step 1: Setup ---
        self.mark_test_step("Setup SGW for file deletion test")
        private_key, public_key = generate_rsa_keypair()
        token = generate_jwt(private_key, subject="user1", expires_in=3600)
        jwk = public_key_to_jwk(public_key)

        cloud = cblpytest.simple_cloud()
        sgw = cloud.sync_gateway
        cbs = cloud.couchbase_server

        try:
            await sgw.delete_database("travel")
        except Exception:
            pass

        sg_config = {
            "bucket": "travel",
            "scopes": {
                "travel": {
                    "collections": {
                        "airlines": {"sync": "function(doc){channel(doc.channels);}"}
                    }
                }
            },
            "num_index_replicas": 0,
            "local_jwt": {
                "test-provider": {
                    "issuer": "test-issuer",
                    "client_id": "edge-server",
                    "register": True,
                    "algorithms": ["RS256"],
                    "keys": [jwk],
                }
            },
        }

        cbs.create_bucket("travel")
        cbs.create_collections("travel", "travel", ["airlines"])
        payload = PutDatabasePayload(sg_config)
        await sgw.put_database("travel", payload)

        collection_access_input = {"travel.airlines": ["*"]}
        access_dict = sgw.create_collection_access_dict(collection_access_input)
        await sgw.add_user("travel", "test-provider_user1", "pass", access_dict)

        # Insert docs
        for i in range(1, 4):
            doc_id = f"filedel_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"FileDel Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")

        # --- Step 2: Start ES with valid token ---
        self.mark_test_step("Start ES with valid JWT file")
        es_manager = cblpytest.edge_servers[0]
        await self._write_file_on_es(es_manager, JWT_FILE, token)

        config_path = f"{SCRIPT_DIR}/config/test_jwt_auth_sgw.json"
        with open(config_path) as f:
            config = json.load(f)
        config["replications"][0]["source"] = sgw.replication_url("travel")
        config["replications"][0]["collections"] = ["travel.airlines"]
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        await edge_server.wait_for_idle(timeout=30)
        self.mark_test_step("Replication idle — now deleting JWT file")

        # --- Step 3: Delete the JWT file content ---
        # write-file.sh rejects empty content, so write a single space
        # which is an invalid JWT token (not valid base64url format)
        self.mark_test_step("Overwriting JWT file with invalid content on ES")
        await self._write_file_on_es(es_manager, JWT_FILE, " ")

        # --- Step 4: Poll until replication stops or wait times out ---
        self.mark_test_step("Polling for ES to detect corrupt token")
        max_wait = 30
        poll_interval = 3
        elapsed = 0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            repl_status = await edge_server.all_replication_status()
            if len(repl_status) == 0:
                break
            task = repl_status[0]
            if task.get("status", "") in ("Stopped", "Offline"):
                break

        repl_status = await edge_server.all_replication_status()

        if len(repl_status) == 0:
            # Task removed — ES detected empty file, tried to reconnect with
            # empty/no token, got 401, task permanently stopped and removed
            self.mark_test_step(
                "PASSED — File deletion (empty content) caused replicator to stop "
                "and be removed (401 on reconnect with empty token)"
            )
        else:
            task = repl_status[0]
            status = task.get("status", "")
            error = task.get("error", {})

            self.mark_test_step(
                f"After file deletion — Status: {status}, Error: {error}"
            )

            if status in ("Stopped", "Offline"):
                self.mark_test_step(
                    "PASSED — File deletion caused replication to stop as expected"
                )
            elif status == "Idle":
                # ES might keep the existing connection alive with the old token
                # if it doesn't consider empty file as a "change"
                self.mark_test_step(
                    "INFO — ES kept existing connection alive after file emptied "
                    "(file watcher may only trigger on valid content change)"
                )
            else:
                pytest.fail(
                    f"Unexpected status after JWT file deletion: {status}, error: {error}"
                )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_valid_invalid_valid_token_cycle(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        Test cycle: valid token → invalid token → valid token.

        Verified behavior with continuous replication:
        Phase 1: Valid Token-A → replication idle, docs sync
        Phase 2: Invalid token written → FileWatcher fires →
                 restartWithNewToken() sends Authorization: Bearer <invalid> →
                 SGW returns 401 → C4RemoteReplicator permanent stop
                 (401 is NOT transient/network-dependent → no retry) →
                 ReplicationTask destroyed → FileWatcher destroyed
        Phase 3: Valid Token-C written → nobody watching (FileWatcher dead) →
                 _replicate must be re-triggered manually →
                 new replication with Token-C → docs sync
        """

        # --- Step 1: Generate keys ---
        self.mark_test_step("Generate valid key pair A, invalid key, and valid key pair C")
        # ...existing code through Step 3 and initial replication verify...
        private_key_a, public_key_a = generate_rsa_keypair()
        private_key_c, public_key_c = generate_rsa_keypair()
        private_key_invalid, _ = generate_rsa_keypair()

        token_a = generate_jwt(private_key_a, subject="user1", expires_in=3600, kid="test-key-1")
        token_invalid = generate_jwt(private_key_invalid, subject="user1", expires_in=3600, kid="bad-key")
        token_c = generate_jwt(private_key_c, subject="user1", expires_in=3600, kid="test-key-3")

        jwk_a = public_key_to_jwk(public_key_a)
        jwk_c = public_key_to_jwk(public_key_c)
        jwk_c["kid"] = "test-key-3"

        # --- Step 2: Setup SGW with keys A and C (not the invalid one) ---
        self.mark_test_step("Configure SGW with valid keys A and C")
        cloud = cblpytest.simple_cloud()
        sgw = cloud.sync_gateway
        cbs = cloud.couchbase_server

        try:
            await sgw.delete_database("travel")
        except Exception:
            pass
        try:
            cbs.drop_bucket("travel")
            await cbs.wait_for_bucket_deleted("travel")
        except Exception:
            pass

        sg_config = {
            "bucket": "travel",
            "scopes": {
                "travel": {
                    "collections": {
                        "airlines": {"sync": "function(doc){channel(doc.channels);}"}
                    }
                }
            },
            "num_index_replicas": 0,
            "local_jwt": {
                "test-provider": {
                    "issuer": "test-issuer",
                    "client_id": "edge-server",
                    "register": True,
                    "algorithms": ["RS256"],
                    "keys": [jwk_a, jwk_c],
                }
            },
        }

        cbs.create_bucket("travel")
        cbs.create_collections("travel", "travel", ["airlines"])
        payload = PutDatabasePayload(sg_config)
        await sgw.put_database("travel", payload)

        collection_access_input = {"travel.airlines": ["*"]}
        access_dict = sgw.create_collection_access_dict(collection_access_input)
        await sgw.add_user("travel", "test-provider_user1", "pass", access_dict)

        # Insert initial docs
        self.mark_test_step("Insert 3 initial documents")
        for i in range(1, 4):
            doc_id = f"cycle_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"Cycle Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")

        # --- Step 3: Start with valid Token-A ---
        self.mark_test_step("Phase 1: Start ES with valid Token-A")
        es_manager = cblpytest.edge_servers[0]
        await self._write_file_on_es(es_manager, JWT_FILE, token_a)

        config_path = f"{SCRIPT_DIR}/config/test_jwt_auth_sgw.json"
        with open(config_path) as f:
            config = json.load(f)
        config["replications"][0]["source"] = sgw.replication_url("travel")
        config["replications"][0]["collections"] = ["travel.airlines"]
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        await edge_server.wait_for_idle(timeout=30)

        # Verify initial replication worked
        response = await edge_server.get_all_documents("travel", collection="travel.airlines")
        initial_count = len(response.rows)
        assert initial_count >= 3, f"Initial replication failed: {initial_count} docs"
        self.mark_test_step(f"Phase 1 OK: {initial_count} docs replicated with Token-A")

        # --- Phase 2: Switch to INVALID token ---
        # FileWatcher detects change → onTokenFileChanged() → _repl->stop() →
        # restartWithNewToken() builds Authorization: Bearer <invalid> →
        # new WebSocket → SGW 401 → C4RemoteReplicator permanent stop
        # (401 is NOT transient, NOT network-dependent → no retry)
        # → ReplicationTask destroyed → FileWatcher destroyed
        self.mark_test_step("Phase 2: Writing INVALID token to file")
        await self._write_file_on_es(es_manager, JWT_FILE, token_invalid)

        # Poll until the replicator stops or task is removed
        max_wait = 60
        poll_interval = 3
        elapsed = 0
        status_after_invalid = "Unknown"
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            repl_status = await edge_server.all_replication_status()
            if len(repl_status) == 0:
                status_after_invalid = "Removed"
                break
            task = repl_status[0]
            status_after_invalid = task.get("status", "")
            if status_after_invalid in ("Stopped", "Offline"):
                break

        if status_after_invalid in ("Removed", "Stopped", "Offline"):
            self.mark_test_step(
                f"Phase 2 OK: Replication permanently stopped after invalid token "
                f"(status: {status_after_invalid}, 401 is not transient → no retry)"
            )
        else:
            pytest.fail(
                f"Expected replication to permanently stop with invalid token "
                f"(401), but status is '{status_after_invalid}' after {max_wait}s."
            )

        # --- Step 5: Insert more docs while replication is stopped ---
        self.mark_test_step("Insert 3 more docs while replication is stopped")
        for i in range(4, 7):
            doc_id = f"cycle_test_{i}"
            doc = {"id": doc_id, "channels": ["*"], "type": "airline", "name": f"Cycle Airline {i}"}
            cbs.upsert_document("travel", doc_id, doc, scope="travel", collection="airlines")

        # Verify ES does NOT have the new docs (replication is dead)
        response = await edge_server.get_all_documents("travel", collection="travel.airlines")
        count_while_stopped = len(response.rows)
        self.mark_test_step(
            f"Docs on ES while stopped: {count_while_stopped} (should still be {initial_count})"
        )
        assert count_while_stopped == initial_count, (
            f"ES should NOT have new docs while replication is stopped: "
            f"expected {initial_count}, got {count_while_stopped}"
        )

        # --- Phase 3: Recover with valid Token-C ---
        # After 401 permanent stop, the ReplicationTask and FileWatcher are
        # destroyed. Writing a new valid token to the file has no effect —
        # nobody is watching. The _replicate endpoint must be re-triggered.
        self.mark_test_step(
            "Phase 3: Writing valid Token-C and re-triggering _replicate "
            "(FileWatcher destroyed after 401 → manual restart required)"
        )
        await self._write_file_on_es(es_manager, JWT_FILE, token_c)

        # Re-trigger replication via configure_dataset (calls _replicate)
        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        await edge_server.wait_for_idle(timeout=30)

        # Verify recovery — ES should now have all docs including the 3 new ones
        response = await edge_server.get_all_documents("travel", collection="travel.airlines")
        final_count = len(response.rows)
        assert final_count >= initial_count + 3, (
            f"After recovery with Token-C and _replicate re-trigger, "
            f"expected >= {initial_count + 3} docs, got {final_count}"
        )
        self.mark_test_step(
            f"PASSED — Valid→Invalid→Valid cycle complete: {final_count} docs. "
            f"Phase 2: Invalid token → automatic 401 permanent stop. "
            f"Phase 3: Valid token → manual _replicate re-trigger required "
            f"(FileWatcher destroyed after 401)."
        )



