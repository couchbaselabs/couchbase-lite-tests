"""
Simple JWT token replication test.

Verifies that Edge Server can replicate with Sync Gateway using a JWT token
provided inline in the config. Uses the same token throughout (no rotation).
reconnect_on_token_change is set to false (only relevant for file-path form).

Valid openid_token config formats (per ES config schema oneOf):
  - Inline string:  "openid_token": "eyJhbG..."
  - File path:      "openid_token": {"path": "/path/to/jwt.txt"}
"""

import asyncio
from pathlib import Path

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload
from cbltest.asyncfile import read_json_file, write_json_file
from jwt_helper import generate_jwt, generate_rsa_keypair, public_key_to_jwk

SCRIPT_DIR = str(Path(__file__).parent)
JWT_FILE_PATH = "/home/ec2-user/cert/jwt.txt"


class TestJWTSimple(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_jwt_replication_reconnect_false(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """ES replicates with SGW using a static JWT token (reconnect_on_token_change=false)."""
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        # =====================================================================
        # STEP 0: Cleanup stale resources from previous test runs.
        # This ensures a fresh state even if a prior run crashed mid-test.
        # The @pytest.mark.sgw marker triggers auto-cleanup AFTER the test too.
        # =====================================================================
        try:
            await sync_gateway.delete_database("travel")
        except Exception:
            pass  # Database may not exist

        try:
            server.drop_bucket("travel")
            await server.wait_for_bucket_deleted("travel")
        except Exception:
            pass  # Bucket may not exist

        # =====================================================================
        # STEP 1: Generate RSA key pair and JWT token.
        # - Private key signs the JWT token
        # - Public key (as JWK) goes into SGW's local_jwt config for validation
        # - JWT claims: sub=user1, iss=test-issuer, aud=edge-server
        # =====================================================================
        self.mark_test_step("Generating RSA key pair and JWT token.")
        private_key, public_key = generate_rsa_keypair()
        jwt_token = generate_jwt(private_key, subject="user1", expires_in=3600)
        jwk = public_key_to_jwk(public_key)

        # =====================================================================
        # STEP 2: Create CBS bucket with scope and collection.
        # SGW maps to this bucket. Documents go into travel.airlines collection.
        # =====================================================================
        self.mark_test_step("Creating travel bucket on Couchbase Server.")
        bucket_name = "travel"
        server.create_bucket(bucket_name)
        server.create_collections(bucket_name, "travel", ["airlines"])

        # =====================================================================
        # STEP 3: Create SGW database with local_jwt provider.
        # - "local_jwt" tells SGW to validate JWTs locally (no external OIDC)
        # - "keys" contains the JWK public key for signature verification
        # - "register": true means SGW auto-creates users on first JWT auth
        # - "client_id" must match the JWT "aud" claim
        # - "issuer" must match the JWT "iss" claim
        # =====================================================================
        self.mark_test_step("Creating SGW database with local_jwt provider.")
        sg_db_name = "travel"
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
        payload = PutDatabasePayload(sg_config)
        await sync_gateway.put_database(sg_db_name, payload)

        # =====================================================================
        # STEP 4: Pre-create JWT user with channel access.
        # SGW auto-registers users on first JWT auth (register=true), but the
        # auto-created user has no channel access. We pre-create with
        # admin_channels=["*"] so it can pull all documents.
        # Username format: "<provider>_<sub>" = "test-provider_user1"
        # =====================================================================
        self.mark_test_step("Adding JWT user with channel access.")
        input_data = {"travel.airlines": ["*"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_user(
            sg_db_name, "test-provider_user1", "pass", access_dict
        )

        # =====================================================================
        # STEP 5: Insert test documents into CBS.
        # These docs will be imported by SGW and then pulled by ES.
        # Using unique IDs to avoid collision with pre-loaded travel dataset.
        # The "channels" field is used by the sync function to assign channels.
        # =====================================================================
        self.mark_test_step("Adding 5 documents to CBS bucket.")
        for i in range(1, 6):
            doc_id = f"jwt_test_airline_{i}"
            doc = {
                "id": doc_id,
                "channels": ["*"],
                "type": "airline",
                "name": f"JWT Test Airline {i}",
            }
            server.upsert_document(
                bucket_name, doc_id, doc, scope="travel", collection="airlines"
            )

        # =====================================================================
        # STEP 6: Wait for SGW to import docs from CBS.
        # CBS→SGW import is async. We poll SGW's _all_docs endpoint until our
        # documents appear (max 30s). This prevents the race condition where
        # ES starts replicating before SGW has the docs in its feed.
        # =====================================================================
        self.mark_test_step("Waiting for SGW to import documents from CBS.")
        max_wait = 30
        poll_interval = 2
        elapsed = 0
        docs_ready = False
        while elapsed < max_wait:
            sgw_docs = await sync_gateway.get_all_documents(
                sg_db_name, scope="travel", collection="airlines"
            )
            sgw_doc_ids = [row.id for row in sgw_docs.rows]
            if all(f"jwt_test_airline_{i}" in sgw_doc_ids for i in range(1, 6)):
                docs_ready = True
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        assert docs_ready, (
            f"SGW did not import all 5 docs within {max_wait}s. "
            f"Found: {[d for d in sgw_doc_ids if 'jwt_test' in d]}"
        )

        # =====================================================================
        # STEP 7: Verify JWT token works against SGW REST API.
        # Sanity check: send Bearer token via HTTP to SGW public port.
        # If this fails, the JWT/key configuration is wrong.
        # =====================================================================
        self.mark_test_step("Verifying JWT token against SGW REST API.")
        sgw_public_url = f"https://{sync_gateway.hostname}:4984/{sg_db_name}/"
        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session,
            session.get(
                sgw_public_url,
                headers={"Authorization": f"Bearer {jwt_token}"},
            ) as resp,
        ):
            status_code = resp.status
            resp_text = await resp.text()
        assert status_code == 200, (
            f"JWT verification against SGW failed: {status_code} {resp_text}"
        )

        # =====================================================================
        # STEP 8: Configure and start Edge Server with inline JWT token.
        #
        # Config structure for JWT auth (inline string format):
        #   "auth": {
        #       "openid_token": "eyJhbGciOiJSUzI1NiI...",
        #       "reconnect_on_token_change": false
        #   }
        #
        # openid_token supports oneOf: plain string OR {"path": "/file"}.
        # reconnect_on_token_change is only effective with the file-path
        # form but is harmless (and valid) with inline strings.
        #
        # configure_dataset() does:
        #   1. kill_server() — stop any running ES process
        #   2. reset-db — restore travel.cblite2 from zip (clean local DB)
        #   3. start_server(config) — write config and start ES binary
        # =====================================================================
        self.mark_test_step("Configuring Edge Server with JWT auth (inline token).")
        config_path = f"{SCRIPT_DIR}/config/test_jwt_simple.json"
        config = await read_json_file(config_path)

        # Set the real SGW replication URL (wss://hostname:4984/travel)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)

        # Set auth to inline JWT token string (oneOf: string form).
        # reconnect_on_token_change=false since we use a static inline token.
        config["replications"][0]["auth"] = {
            "openid_token": jwt_token,
            "reconnect_on_token_change": False,
        }

        await write_json_file(config_path, config)

        es_manager = cblpytest.edge_servers[0]
        edge_server = await es_manager.configure_dataset(
            db_name="travel", config_file=config_path
        )

        # =====================================================================
        # STEP 9: Wait for replication to complete.
        # First verify the replicator was actually created (not silently
        # dropped due to invalid config). Then wait for idle status.
        # =====================================================================
        self.mark_test_step("Waiting for replication to Edge Server to be idle.")

        # Give ES a moment to parse config and start the replicator
        await asyncio.sleep(1)

        # Verify replicator exists — if /_replicate returns [], the config was
        # rejected (e.g. invalid openid_token format) and no replication started
        repl_status = await edge_server.all_replication_status()
        assert len(repl_status) > 0, (
            "No replicators found on Edge Server — the replication config "
            "was likely rejected. Check openid_token format."
        )

        await edge_server.wait_for_idle(timeout=15)

        # =====================================================================
        # STEP 10: Verify replication is working by checking doc count.
        # The pre-loaded travel.cblite2 has 150 airline docs. After
        # bidirectional replication with JWT auth, ES should have at least
        # those 150 + our 5 new docs = 155 total. We poll until we see >= 155.
        # =====================================================================
        self.mark_test_step("Verifying that Edge Server has replicated documents.")
        max_wait = 30
        poll_interval = 3
        elapsed = 0
        expected_min = 150  # Pre-loaded travel dataset from zip
        final_count = 0
        while elapsed < max_wait:
            response = await edge_server.get_all_documents(
                "travel", collection="travel.airlines"
            )
            final_count = len(response.rows)
            if final_count >= expected_min:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        assert final_count >= expected_min, (
            f"Expected >= {expected_min} docs on ES, got {final_count}. "
            f"JWT auth replication may not have pulled new docs from SGW."
        )

        # =====================================================================
        # STEP 11: Verify a document can be fetched from ES.
        # This confirms the database is accessible and replication populated it.
        # =====================================================================
        self.mark_test_step("Verifying document accessible on Edge Server.")
        response = await edge_server.get_all_documents(
            "travel", collection="travel.airlines"
        )
        assert len(response.rows) > 0, "No documents found on Edge Server."
        first_doc_id = response.rows[0].id
        edge_doc = await edge_server.get_document(
            "travel", collection="travel.airlines", doc_id=first_doc_id
        )
        assert edge_doc is not None, (
            f"Document {first_doc_id} not retrievable from Edge Server."
        )
        assert "name" in edge_doc.body, (
            f"Document missing 'name' field: {edge_doc.body}"
        )
