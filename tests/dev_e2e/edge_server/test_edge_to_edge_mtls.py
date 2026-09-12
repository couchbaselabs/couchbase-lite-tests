# xfail: ES 1.1.0 misreads the PEM replication client key (set_identity size vs size + 1) -> "PK - Invalid key tag or value".
import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.asyncfile import read_json_file, write_json_file
from cert_helper import cert_pem, generate_ca, generate_signed_cert, key_pem

SCRIPT_DIR = str(Path(__file__).parent)
CERT_DIR = "/home/ec2-user/cert"


@pytest.mark.min_edge_servers(2)
class TestEdgeToEdgeMTLS(CBLTestClass):
    """Edge-to-edge replication authenticated with a TLS client certificate (mTLS).

    A source Edge Server replicates to a target Edge Server over mutual TLS: the
    source presents a client certificate (auth.tls_client_cert /
    tls_client_cert_key) while the target verifies incoming clients against a CA
    (https.client_cert_path). The client cert/key are given as file paths in a
    config-file replications block, matching the customer's setup.
    """

    async def _write_file_on_es(self, es_manager: EdgeServer, path: str, content: str) -> None:
        """Write content to a file on the ES host via shell2http."""
        await es_manager._send_request(
            "post",
            "write-file",
            JSONDictionary({"path": path, "content": content}),
            session=es_manager._EdgeServer__shell_session,  # ty: ignore[unresolved-attribute]
        )

    async def _wait_for_status(self, es: EdgeServer, wanted: set[str], timeout: int = 90) -> dict:
        """Poll the replication task list until the first task's status is in `wanted`.

        Returns the task dict, or {} if the task list stays empty for the whole
        timeout (which itself signals a replication that never started).
        """
        elapsed = 0
        task: dict = {}
        while elapsed < timeout:
            try:
                tasks = await es.all_replication_status()
                if tasks:
                    task = tasks[0]
                    if task.get("status") in wanted:
                        return task
            except Exception:
                task = {}
            await asyncio.sleep(3)
            elapsed += 3
        return task

    @pytest.mark.xfail(
        reason="ES 1.1.0 misreads the PEM replication client key (set_identity size vs size + 1), "
        "so it fails with 'PK - Invalid key tag or value'. Remove xfail once fixed.",
        strict=False,
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_mtls_replication(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_edge_to_edge_mtls_replication")
        source = cblpytest.edge_servers[0]  # replication client (presents the cert)
        target = cblpytest.edge_servers[1]  # passive mTLS server (verifies the cert)

        self.mark_test_step("Generate CA, target server cert (SAN=target host), and client cert")
        ca_cert, ca_key = generate_ca()
        server_cert, server_key = generate_signed_cert(
            ca_cert, ca_key, target.hostname, sans=[target.hostname], client=False
        )
        client_cert, client_key = generate_signed_cert(ca_cert, ca_key, "edge-client", client=True)
        ca_pem = cert_pem(ca_cert)

        self.mark_test_step("Push server cert/key + CA to the target host and start it with mTLS")
        await self._write_file_on_es(target, f"{CERT_DIR}/ca.crt", ca_pem)
        await self._write_file_on_es(target, f"{CERT_DIR}/server.crt", cert_pem(server_cert))
        await self._write_file_on_es(target, f"{CERT_DIR}/server.key", key_pem(server_key))
        await target.configure_dataset(
            db_name="db", config_file=f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_target.json"
        )

        self.mark_test_step("Push client cert/key + CA to the source host")
        await self._write_file_on_es(source, f"{CERT_DIR}/client.crt", cert_pem(client_cert))
        # A plain, unencrypted PEM key -- still hits the bug (only the PEM encoding matters).
        await self._write_file_on_es(source, f"{CERT_DIR}/client.key", key_pem(client_key))
        await self._write_file_on_es(source, f"{CERT_DIR}/ca.crt", ca_pem)

        self.mark_test_step("Configure the source with a config-file mTLS replication to the target")
        config_path = f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_source.json"
        config = await read_json_file(config_path)
        config["replications"][0]["target"] = f"wss://{target.hostname}:59840/db"
        await write_json_file(config_path, config)
        source_es = await source.configure_dataset(db_name="db", config_file=config_path)

        self.mark_test_step("Verify the mTLS handshake succeeds and replication reaches Idle/Busy")
        status = await self._wait_for_status(source_es, {"Idle", "Busy"})
        assert status.get("status") in {"Idle", "Busy"}, f"edge-to-edge mTLS replication did not start: {status}"
        assert not status.get("error"), f"replication reported an error: {status.get('error')}"
