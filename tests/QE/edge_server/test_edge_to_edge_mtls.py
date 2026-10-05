import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import aiohttp
import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.x509_certificate import CertKeyPair, create_ca_certificate, create_leaf_certificate
from cbltest.asyncfile import read_json_file, write_json_file
from cbltest.utils import async_retry_assert

SCRIPT_DIR = str(Path(__file__).parent)
TARGET_TEMPLATE = f"{SCRIPT_DIR}/config/test_e2e_mtls_target.json"
SOURCE_TEMPLATE = f"{SCRIPT_DIR}/config/test_e2e_mtls_source.json"

# A directory of its own: files written to an ES host survive the per-test reset, so writing
# over the provisioned certificates would break every later TLS test on that host.
REMOTE_CERT_DIR = "/home/ec2-user/cert/qe_e2e_mtls"
ES_PORT = 59840
DB = "db"
# How long an empty /_replicate list must last before it counts as the replicator giving up.
_REJECTION_GRACE_SECONDS = 20

Format = Literal["pem", "der"]


@dataclass(frozen=True)
class MtlsFormats:
    """The encoding of each piece of TLS material a test writes to the Edge Server hosts."""

    server_cert: Format = "pem"
    server_key: Format = "pem"
    client_ca: Format = "pem"
    client_cert: Format = "pem"
    client_key: Format = "pem"


@dataclass(frozen=True)
class Pki:
    """The material every test mints for itself."""

    ca: CertKeyPair
    server: CertKeyPair
    framework_client: CertKeyPair


def _cert_bytes(pair: CertKeyPair, fmt: Format) -> bytes:
    """`pair`'s certificate encoded as `fmt`."""
    return pair.der_bytes() if fmt == "der" else pair.pem_bytes()


def _key_bytes(pair: CertKeyPair, fmt: Format) -> bytes:
    """`pair`'s private key encoded as unencrypted PKCS#8 `fmt`."""
    return pair.key_der_bytes() if fmt == "der" else pair.key_pem_bytes()


def _mint_pki(target_host: str) -> Pki:
    """Mint a CA, a target server certificate for `target_host`, and a framework client certificate."""
    ca = create_ca_certificate("QE E2E mTLS CA")
    return Pki(
        ca=ca,
        server=create_leaf_certificate(target_host, issuer_data=ca, sans=[target_host]),
        framework_client=create_leaf_certificate("qe-framework", issuer_data=ca),
    )


@contextmanager
def _framework_identity(pki: Pki) -> Iterator[None]:
    """
    Make the harness trust `pki`'s CA and present its framework certificate, which is what
    `EdgeServer` reads from ~/.cbl_certs to reach an mTLS Edge Server, restoring whatever was
    provisioned there on exit.
    """
    cert_dir = Path.home() / ".cbl_certs"
    cert_dir.mkdir(mode=0o700, exist_ok=True)
    files = {
        "ca_cert.pem": pki.ca.pem_bytes(),
        "client_cert.pem": pki.framework_client.pem_bytes(),
        "client_key.pem": pki.framework_client.key_pem_bytes(),
    }
    provisioned = {name: (cert_dir / name).read_bytes() for name in files if (cert_dir / name).exists()}
    try:
        for name, data in files.items():
            (cert_dir / name).write_bytes(data)
        (cert_dir / "client_key.pem").chmod(0o600)
        yield
    finally:
        for name in files:
            if name in provisioned:
                (cert_dir / name).write_bytes(provisioned[name])
            else:
                (cert_dir / name).unlink(missing_ok=True)
        if (cert_dir / "client_key.pem").exists():
            (cert_dir / "client_key.pem").chmod(0o600)


@pytest.mark.min_edge_servers(2)
class TestEdgeToEdgeMtls(CBLTestClass):
    async def _start_target(self, cblpytest: CBLPyTest, tmp_path: Path, pki: Pki, formats: MtlsFormats) -> EdgeServer:
        """Write the target's TLS material in `formats` and start it serving mTLS."""
        target = cblpytest.edge_servers[1]
        cert_path = f"{REMOTE_CERT_DIR}/server_cert.{formats.server_cert}"
        key_path = f"{REMOTE_CERT_DIR}/server_key.{formats.server_key}"
        client_ca_path = f"{REMOTE_CERT_DIR}/client_ca.{formats.client_ca}"
        await target.write_file(cert_path, _cert_bytes(pki.server, formats.server_cert))
        await target.write_file(key_path, _key_bytes(pki.server, formats.server_key))
        await target.write_file(client_ca_path, _cert_bytes(pki.ca, formats.client_ca))

        config = await read_json_file(TARGET_TEMPLATE)
        config["https"] = {"tls_cert_path": cert_path, "tls_key_path": key_path, "client_cert_path": client_ca_path}
        config_path = str(tmp_path / "mtls_target.json")
        await write_json_file(config_path, config)
        return await target.configure_dataset(db_name=DB, config_file=config_path)

    async def _start_source(
        self,
        cblpytest: CBLPyTest,
        tmp_path: Path,
        ca: CertKeyPair,
        client: CertKeyPair | None,
        formats: MtlsFormats | None = None,
    ) -> EdgeServer:
        """
        Start the source replicating to the target, trusting `ca`, presenting `client` in `formats`.

        :param client: The client identity, or None for a replication with no `auth` block
        :param formats: The client certificate and key formats, or None for PEM
        """
        formats = formats or MtlsFormats()
        source = cblpytest.edge_servers[0]
        target_host = str(cblpytest.edge_servers[1])
        trusted_roots_path = f"{REMOTE_CERT_DIR}/trusted_roots.pem"
        await source.write_file(trusted_roots_path, ca.pem_bytes())

        config = await read_json_file(SOURCE_TEMPLATE)
        replication = config["replications"][0]
        replication["target"] = f"wss://{target_host}:{ES_PORT}/{DB}"
        replication["trusted_root_certs"] = trusted_roots_path
        if client is None:
            replication.pop("auth", None)
        else:
            cert_path = f"{REMOTE_CERT_DIR}/client_cert.{formats.client_cert}"
            key_path = f"{REMOTE_CERT_DIR}/client_key.{formats.client_key}"
            await source.write_file(cert_path, _cert_bytes(client, formats.client_cert))
            await source.write_file(key_path, _key_bytes(client, formats.client_key))
            replication["auth"] = {"tls_client_cert": cert_path, "tls_client_cert_key": key_path}

        config_path = str(tmp_path / "mtls_source.json")
        await write_json_file(config_path, config)
        return await source.configure_dataset(db_name=DB, config_file=config_path)

    async def _tls_probe(self, host: str, ca: CertKeyPair, client: CertKeyPair | None, tmp_path: Path) -> int:
        """
        GET / on `host` over TLS, trusting `ca` and presenting `client` (or no certificate).

        :return: The HTTP status, which any answer at all means the handshake was accepted
        :raises aiohttp.ClientError: If the connection fails, including a refused handshake
        """
        context = ssl.create_default_context(cadata=ca.pem_bytes().decode())
        context.check_hostname = False
        if client is not None:
            cert_file = tmp_path / "probe_cert.pem"
            key_file = tmp_path / "probe_key.pem"
            cert_file.write_bytes(client.pem_bytes())
            key_file.write_bytes(client.key_pem_bytes())
            key_file.chmod(0o600)
            context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))

        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context)) as session,
            session.get(f"https://{host}:{ES_PORT}/", timeout=aiohttp.ClientTimeout(total=15)) as resp,
        ):
            return resp.status

    async def _assert_target_enforces_mtls(self, cblpytest: CBLPyTest, pki: Pki, tmp_path: Path) -> None:
        """
        Prove the target asks for, and checks, a client certificate.  The probe with a valid
        certificate comes first, so the refusal cannot be a trust mistake in the probe itself.
        """
        target_host = str(cblpytest.edge_servers[1])
        status = await self._tls_probe(target_host, pki.ca, pki.framework_client, tmp_path)
        assert status < 500, f"Target answered {status} to a TLS client with a valid certificate"

        try:
            status = await self._tls_probe(target_host, pki.ca, None, tmp_path)
        except aiohttp.ClientConnectorCertificateError as e:
            pytest.fail(f"Probe could not verify the target's certificate, so it proves nothing: {e}")
        except (aiohttp.ClientError, ssl.SSLError, ConnectionError):
            return

        pytest.fail(
            f"Target answered HTTP {status} to a TLS client with no certificate: it is not enforcing "
            "mTLS, so replication succeeding would not prove the client certificate was checked"
        )

    async def _wait_for_replicator_idle(self, edge_server: EdgeServer) -> None:
        """
        Wait until the replicator exists, reports no error, and is Idle.  Unlike
        `EdgeServer.wait_for_idle`, an empty /_replicate list fails the wait, because Edge
        Server drops a replicator that hit a permanent error.
        """

        async def _poll() -> None:
            tasks = await edge_server.all_replication_status()
            assert tasks, "Source has no replicator: it hit a permanent error or its config was refused"
            assert "error" not in tasks[0], f"Replicator reported an error: {tasks[0]}"
            assert tasks[0].get("status") == "Idle", f"Replicator is not idle: {tasks[0]}"

        await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(90))

    async def _wait_for_replicator_rejected(self, edge_server: EdgeServer) -> list:
        """
        Wait until the replicator gives up: removed, Stopped/Offline, or reporting an error.

        :return: The final /_replicate list, for the test log
        """

        started = time.monotonic()

        async def _poll() -> list:
            tasks = await edge_server.all_replication_status()
            if not tasks:
                # Edge Server drops a replicator after a permanent error, but the list is
                # also empty before the replicator registers, so only trust it after a grace.
                assert time.monotonic() - started >= _REJECTION_GRACE_SECONDS, "Replicator not started yet"
                return tasks
            task = tasks[0]
            assert task.get("status") in ("Stopped", "Offline") or "error" in task, (
                f"Replicator is still running: {task}"
            )
            return tasks

        return await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(60))

    async def _wait_for_doc(self, edge_server: EdgeServer, doc_id: str) -> None:
        """Wait until `doc_id` is in `edge_server`'s default collection."""

        async def _poll() -> None:
            ids = {row.id for row in (await edge_server.get_all_documents(DB)).rows}
            assert doc_id in ids, f"{doc_id} not on {edge_server.hostname}"

        await async_retry_assert(_poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(60))

    @pytest.mark.parametrize(
        "formats",
        [
            pytest.param(MtlsFormats(client_cert="der", client_key="der"), id="client_cert_der_key_der"),
            pytest.param(MtlsFormats(client_key="der"), id="client_cert_pem_key_der"),
            pytest.param(MtlsFormats(client_cert="der"), id="client_cert_der_key_pem"),
            pytest.param(MtlsFormats(server_cert="der", server_key="der"), id="server_der"),
            pytest.param(
                MtlsFormats(server_cert="der", server_key="der", client_ca="der", client_cert="der", client_key="der"),
                id="all_der",
            ),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_mtls_formats(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        tmp_path: Path,
        formats: MtlsFormats,
        request: pytest.FixtureRequest,
    ) -> None:
        case = request.node.callspec.id

        self.mark_test_step("Generate the CA, target server, source client and framework client certificates")
        pki = _mint_pki(str(cblpytest.edge_servers[1]))
        source_client = create_leaf_certificate("es-source", issuer_data=pki.ca)

        self.mark_test_step("Install the CA and framework certificate as the harness's `~/.cbl_certs` identity")
        with _framework_identity(pki):
            self.mark_test_step(
                f"Write the target's cert ({formats.server_cert}), key ({formats.server_key}) and client CA "
                f"({formats.client_ca}), and start the target with mTLS"
            )
            target = await self._start_target(cblpytest, tmp_path, pki, formats)

            self.mark_test_step("Verify the target accepts the framework certificate and refuses no certificate")
            await self._assert_target_enforces_mtls(cblpytest, pki, tmp_path)

            self.mark_test_step(f"Write `{case}_target_seed` to the target")
            seed_id = f"{case}_target_seed"
            await target.put_document_with_id({"type": "seed", "from": "target"}, seed_id, DB)

            self.mark_test_step(
                f"Write the source's client cert ({formats.client_cert}) and key ({formats.client_key}) "
                "and the CA as PEM, and start the source replicating to the target"
            )
            source = await self._start_source(cblpytest, tmp_path, pki.ca, source_client, formats)

            self.mark_test_step("Wait for the source's replicator to exist, report no error, and be `Idle`")
            await self._wait_for_replicator_idle(source)

            self.mark_test_step(f"Verify `{seed_id}` is on the source")
            await self._wait_for_doc(source, seed_id)

            self.mark_test_step(f"Write `{case}_source_write` to the source and wait for it to reach the target")
            push_id = f"{case}_source_write"
            await source.put_document_with_id({"type": "push", "from": "source"}, push_id, DB)
            await self._wait_for_doc(target, push_id)

    @pytest.mark.parametrize("rejected_client", ["no_client_cert", "untrusted_ca", "expired_client_cert"])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_mtls_rejects_client(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, rejected_client: str
    ) -> None:
        self.mark_test_step("Generate the CA, target server and framework client certificates, and the client identity")
        pki = _mint_pki(str(cblpytest.edge_servers[1]))
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
                    issuer_data=pki.ca,
                    not_valid_before=now - timedelta(days=2),
                    not_valid_after=now - timedelta(days=1),
                )
            case _:
                raise ValueError(f"Unknown rejected client: {rejected_client}")

        self.mark_test_step("Install the CA and framework certificate as the harness's `~/.cbl_certs` identity")
        with _framework_identity(pki):
            self.mark_test_step("Write the target's cert, key and client CA as PEM, and start the target with mTLS")
            target = await self._start_target(cblpytest, tmp_path, pki, MtlsFormats())

            self.mark_test_step("Verify the target accepts the framework certificate and refuses no certificate")
            await self._assert_target_enforces_mtls(cblpytest, pki, tmp_path)

            self.mark_test_step(f"Write `{rejected_client}_target_seed` to the target")
            seed_id = f"{rejected_client}_target_seed"
            await target.put_document_with_id({"type": "seed", "from": "target"}, seed_id, DB)

            self.mark_test_step(f"Start the source replicating to the target with `{rejected_client}`")
            source = await self._start_source(cblpytest, tmp_path, pki.ca, client)

            self.mark_test_step("Wait for the source's replicator to give up")
            tasks = await self._wait_for_replicator_rejected(source)
            self.mark_test_step(f"Source replicator state: {tasks or 'removed'}")

            self.mark_test_step(f"Verify `{seed_id}` is not on the source")
            source_ids = {row.id for row in (await source.get_all_documents(DB)).rows}
            assert seed_id not in source_ids, f"{seed_id} replicated to a source presenting `{rejected_client}`"

            self.mark_test_step("Verify the target still serves requests")
            target_ids = {row.id for row in (await target.get_all_documents(DB)).rows}
            assert seed_id in target_ids, "Target lost its seeded document after refusing the source"
