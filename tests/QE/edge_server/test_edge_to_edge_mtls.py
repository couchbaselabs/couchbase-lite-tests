import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.x509_certificate import CertKeyPair, create_ca_certificate, create_leaf_certificate
from cbltest.asyncfile import read_json_file, write_json_file
from cbltest.utils import async_retry_assert

SCRIPT_DIR = str(Path(__file__).parent)

REMOTE_CERT_DIR = "/home/ec2-user/cert/qe_e2e_mtls"
"""Kept apart from the provisioned certificates, because files on an ES host survive the per-test reset."""

ES_PORT = 59840

REJECTION_GRACE = 20
"""Seconds an empty /_replicate list must last before it counts as the replicator giving up."""


def _cert_bytes(pair: CertKeyPair, fmt: str) -> bytes:
    return pair.der_bytes() if fmt == "der" else pair.pem_bytes()


def _key_bytes(pair: CertKeyPair, fmt: str) -> bytes:
    return pair.key_der_bytes() if fmt == "der" else pair.key_pem_bytes()


def _create_certificates(target_host: str) -> tuple[CertKeyPair, CertKeyPair, CertKeyPair]:
    """Return a CA, a target server certificate, and a framework client certificate."""
    ca = create_ca_certificate("QE E2E mTLS CA")
    server = create_leaf_certificate(target_host, issuer_data=ca, sans=[target_host])
    framework_client = create_leaf_certificate("qe-framework", issuer_data=ca)
    return ca, server, framework_client


@contextmanager
def _framework_identity(ca: CertKeyPair, client: CertKeyPair) -> Iterator[None]:
    """Put `ca` and `client` in ~/.cbl_certs so the harness can reach an mTLS Edge Server, then restore."""
    cert_dir = Path.home() / ".cbl_certs"
    cert_dir.mkdir(mode=0o700, exist_ok=True)
    files = {
        "ca_cert.pem": ca.pem_bytes(),
        "client_cert.pem": client.pem_bytes(),
        "client_key.pem": client.key_pem_bytes(),
    }
    saved = {name: (cert_dir / name).read_bytes() for name in files if (cert_dir / name).exists()}
    try:
        for name, data in files.items():
            (cert_dir / name).write_bytes(data)
        (cert_dir / "client_key.pem").chmod(0o600)
        yield
    finally:
        for name in files:
            if name in saved:
                (cert_dir / name).write_bytes(saved[name])
            else:
                (cert_dir / name).unlink(missing_ok=True)


async def _start_target(
    cblpytest: CBLPyTest, tmp_path: Path, ca: CertKeyPair, server: CertKeyPair, fmt: str
) -> EdgeServer:
    target = cblpytest.edge_servers[1]
    cert_path = f"{REMOTE_CERT_DIR}/server_cert.{fmt}"
    key_path = f"{REMOTE_CERT_DIR}/server_key.{fmt}"
    client_ca_path = f"{REMOTE_CERT_DIR}/client_ca.{fmt}"
    await target.write_file(cert_path, _cert_bytes(server, fmt))
    await target.write_file(key_path, _key_bytes(server, fmt))
    await target.write_file(client_ca_path, _cert_bytes(ca, fmt))

    config = await read_json_file(f"{SCRIPT_DIR}/config/test_e2e_mtls_target.json")
    config["https"] = {"tls_cert_path": cert_path, "tls_key_path": key_path, "client_cert_path": client_ca_path}
    config_path = str(tmp_path / "target_config.json")
    await write_json_file(config_path, config)
    return await target.configure_dataset(db_name="db", config_file=config_path)


async def _start_source(
    cblpytest: CBLPyTest, tmp_path: Path, ca: CertKeyPair, client: CertKeyPair | None, fmt: str = "pem"
) -> EdgeServer:
    """Start the source replicating to the target, presenting `client` (None for no `auth` block)."""
    source = cblpytest.edge_servers[0]
    trusted_roots_path = f"{REMOTE_CERT_DIR}/trusted_roots.pem"
    await source.write_file(trusted_roots_path, ca.pem_bytes())

    config = await read_json_file(f"{SCRIPT_DIR}/config/test_e2e_mtls_source.json")
    replication = config["replications"][0]
    replication["target"] = f"wss://{cblpytest.edge_servers[1]}:{ES_PORT}/db"
    replication["trusted_root_certs"] = trusted_roots_path
    if client is None:
        replication.pop("auth", None)
    else:
        cert_path = f"{REMOTE_CERT_DIR}/client_cert.{fmt}"
        key_path = f"{REMOTE_CERT_DIR}/client_key.{fmt}"
        await source.write_file(cert_path, _cert_bytes(client, fmt))
        await source.write_file(key_path, _key_bytes(client, fmt))
        replication["auth"] = {"tls_client_cert": cert_path, "tls_client_cert_key": key_path}

    config_path = str(tmp_path / "source_config.json")
    await write_json_file(config_path, config)
    return await source.configure_dataset(db_name="db", config_file=config_path)


async def _wait_for_replicator_idle(edge_server: EdgeServer) -> None:
    """Unlike `wait_for_idle`, a missing replicator fails: Edge Server drops one after a permanent error."""

    async def _poll() -> None:
        tasks = await edge_server.all_replication_status()
        assert tasks, "Replicator is missing: it hit a permanent error or its config was refused"
        assert "error" not in tasks[0], f"Replicator reported an error: {tasks[0]}"
        assert tasks[0].get("status") == "Idle", f"Replicator is not idle: {tasks[0]}"

    await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(90))


async def _wait_for_replicator_rejected(edge_server: EdgeServer) -> list:
    """Wait for the replicator to be removed, Stopped/Offline, or reporting an error."""
    started = time.monotonic()

    async def _poll() -> list:
        tasks = await edge_server.all_replication_status()
        if not tasks:
            # Also empty before the replicator registers, so only trust it after a grace period
            assert time.monotonic() - started >= REJECTION_GRACE, "Replicator not started yet"
            return tasks
        assert tasks[0].get("status") in ("Stopped", "Offline") or "error" in tasks[0], (
            f"Replicator is still running: {tasks[0]}"
        )
        return tasks

    return await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(60))


async def _wait_for_doc(edge_server: EdgeServer, doc_id: str) -> None:
    async def _poll() -> None:
        ids = {row.id for row in (await edge_server.get_all_documents("db")).rows}
        assert doc_id in ids, f"{doc_id} not on {edge_server.hostname}"

    await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(60))


@pytest.mark.min_edge_servers(2)
class TestEdgeToEdgeMtls(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "server_format, client_format",
        [("pem", "pem"), ("der", "der"), ("pem", "der")],
    )
    async def test_edge_to_edge_mtls_formats(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        tmp_path: Path,
        server_format: str,
        client_format: str,
    ) -> None:
        self.mark_test_step("test_edge_to_edge_mtls_formats")
        seed_id = f"seed_{server_format}_{client_format}"
        push_id = f"push_{server_format}_{client_format}"

        self.mark_test_step("Create the CA, target server, source client and framework client certificates")
        ca, server, framework_client = _create_certificates(str(cblpytest.edge_servers[1]))
        source_client = create_leaf_certificate("es-source", issuer_data=ca)

        with _framework_identity(ca, framework_client):
            self.mark_test_step(f"Start the target with mTLS, server cert, key and client CA as {server_format}")
            target = await _start_target(cblpytest, tmp_path, ca, server, server_format)

            self.mark_test_step(f"Create document {seed_id} on the target")
            await target.put_document_with_id({"type": "seed"}, seed_id, "db")

            self.mark_test_step(f"Start the source replicating to the target, client cert and key as {client_format}")
            source = await _start_source(cblpytest, tmp_path, ca, source_client, client_format)

            self.mark_test_step("Wait for the source replicator to become idle")
            await _wait_for_replicator_idle(source)

            self.mark_test_step(f"Verify {seed_id} replicated to the source")
            await _wait_for_doc(source, seed_id)

            self.mark_test_step(f"Create document {push_id} on the source and verify it replicates to the target")
            await source.put_document_with_id({"type": "push"}, push_id, "db")
            await _wait_for_doc(target, push_id)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("rejected_client", ["no_client_cert", "untrusted_ca", "expired_client_cert"])
    async def test_edge_to_edge_mtls_rejects_client(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, rejected_client: str
    ) -> None:
        self.mark_test_step("test_edge_to_edge_mtls_rejects_client")
        seed_id = f"seed_{rejected_client}"

        self.mark_test_step(f"Create the CA, target server and framework client certificates, and {rejected_client}")
        ca, server, framework_client = _create_certificates(str(cblpytest.edge_servers[1]))
        client: CertKeyPair | None
        match rejected_client:
            case "no_client_cert":
                client = None
            case "untrusted_ca":
                rogue_ca = create_ca_certificate("QE E2E mTLS rogue CA")
                client = create_leaf_certificate("es-source", issuer_data=rogue_ca)
            case "expired_client_cert":
                now = datetime.now(UTC)
                client = create_leaf_certificate(
                    "es-source",
                    issuer_data=ca,
                    not_valid_before=now - timedelta(days=2),
                    not_valid_after=now - timedelta(days=1),
                )
            case _:
                raise ValueError(f"Unknown rejected client: {rejected_client}")

        with _framework_identity(ca, framework_client):
            self.mark_test_step("Start the target with mTLS, server cert, key and client CA as pem")
            target = await _start_target(cblpytest, tmp_path, ca, server, "pem")

            self.mark_test_step(f"Create document {seed_id} on the target")
            await target.put_document_with_id({"type": "seed"}, seed_id, "db")

            self.mark_test_step(f"Start the source replicating to the target with {rejected_client}")
            source = await _start_source(cblpytest, tmp_path, ca, client)

            self.mark_test_step("Wait for the source replicator to give up")
            tasks = await _wait_for_replicator_rejected(source)
            self.mark_test_step(f"Source replicator state: {tasks or 'removed'}")

            self.mark_test_step(f"Verify {seed_id} did not replicate to the source")
            source_docs = await source.get_all_documents("db")
            assert seed_id not in {row.id for row in source_docs.rows}, f"{seed_id} replicated with {rejected_client}"

            self.mark_test_step(f"Verify {seed_id} is still on the target")
            target_docs = await target.get_all_documents("db")
            assert seed_id in {row.id for row in target_docs.rows}, "Target lost its document after refusing the source"
