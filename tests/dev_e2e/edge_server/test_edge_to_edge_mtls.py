import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.x509_certificate import create_ca_certificate, create_leaf_certificate
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)
CERT_DIR = "/home/ec2-user/cert"


@pytest.mark.min_edge_servers(2)
class TestEdgeToEdgeMTLS(CBLTestClass):
    """Edge-to-edge replication over mTLS. See spec/tests/dev_e2e/015-edge-to-edge-mtls.md."""

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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_mtls_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("test_edge_to_edge_mtls_replication")
        source = cblpytest.edge_servers[0]
        target = cblpytest.edge_servers[1]
        target_host = str(target)

        self.mark_test_step("Generate CA, target server cert (SAN=target host), and client cert")
        ca = create_ca_certificate("Edge Test CA")
        server = create_leaf_certificate(target_host, issuer_data=ca, sans=[target_host])
        client = create_leaf_certificate("edge-client", issuer_data=ca)
        ca_pem = ca.pem_bytes().decode()
        server_cert_pem = server.pem_bytes().decode()
        server_key_pem = server.key_pem_bytes().decode()
        client_cert_pem = client.pem_bytes().decode()
        client_key_pem = client.key_pem_bytes().decode()

        # Trust our generated CA locally so the framework can reach the mTLS target; restored in finally.
        cert_dir = Path.home() / ".cbl_certs"
        cert_dir.mkdir(mode=0o700, exist_ok=True)
        cert_names = ("ca_cert.pem", "client_cert.pem", "client_key.pem")
        provisioned = {n: (cert_dir / n).read_bytes() for n in cert_names if (cert_dir / n).exists()}

        try:
            (cert_dir / "ca_cert.pem").write_bytes(ca_pem.encode())
            (cert_dir / "client_cert.pem").write_bytes(client_cert_pem.encode())
            (cert_dir / "client_key.pem").write_bytes(client_key_pem.encode())
            (cert_dir / "client_key.pem").chmod(0o600)

            self.mark_test_step("Push server cert/key + CA to the target host and start it with mTLS")
            await target.write_file(f"{CERT_DIR}/ca.crt", ca_pem)
            await target.write_file(f"{CERT_DIR}/server.crt", server_cert_pem)
            await target.write_file(f"{CERT_DIR}/server.key", server_key_pem)
            await target.configure_dataset(
                db_name="db", config_file=f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_target.json"
            )

            self.mark_test_step("Push client cert/key + CA to the source host")
            await source.write_file(f"{CERT_DIR}/client.crt", client_cert_pem)
            await source.write_file(f"{CERT_DIR}/client.key", client_key_pem)
            await source.write_file(f"{CERT_DIR}/ca.crt", ca_pem)

            self.mark_test_step("Configure the source with a config-file mTLS replication to the target")
            config = await read_json_file(f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_source.json")
            config["replications"][0]["target"] = f"wss://{target_host}:59840/db"
            # Write the run-specific target into a temp file so the checked-in fixture stays clean.
            config_path = str(tmp_path / "mtls_source_config.json")
            await write_json_file(config_path, config)
            source_es = await source.configure_dataset(db_name="db", config_file=config_path)

            self.mark_test_step("Verify the mTLS handshake succeeds and replication reaches Idle/Busy")
            status = await self._wait_for_status(source_es, {"Idle", "Busy"})
            assert status.get("status") in {"Idle", "Busy"}, f"edge-to-edge mTLS replication did not start: {status}"
            assert not status.get("error"), f"replication reported an error: {status.get('error')}"
        finally:
            for name, data in provisioned.items():
                (cert_dir / name).write_bytes(data)
            if (cert_dir / "client_key.pem").exists():
                (cert_dir / "client_key.pem").chmod(0o600)
