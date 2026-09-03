from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)

_HOST_CERT_DIR = "/home/ec2-user/cert"
_PEER_CA = f"{_HOST_CERT_DIR}/peer_ca_cert.pem"
_PEER_CLIENT_CERT = f"{_HOST_CERT_DIR}/peer_client_cert.pem"
_PEER_CLIENT_KEY = f"{_HOST_CERT_DIR}/peer_client_key.pem"


@pytest.mark.min_edge_servers(2)
class TestEdgeToEdgeMutualTLS(CBLTestClass):
    @staticmethod
    async def _install_peer_credentials(target: EdgeServer) -> None:
        cert_dir = Path.home() / ".cbl_certs"
        for src, dest in (
            (cert_dir / "ca_cert.pem", _PEER_CA),
            (cert_dir / "client_cert.pem", _PEER_CLIENT_CERT),
            (cert_dir / "client_key.pem", _PEER_CLIENT_KEY),
        ):
            assert src.exists(), (
                f"{src} is missing. It is written by "
                "environment/aws/es_setup/setup_edge_servers.py, so this topology was "
                "probably not provisioned from this machine."
            )
            await target.write_file(dest, src.read_text())

    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_replication_with_mtls(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        source_config = f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_source.json"
        target_config = f"{SCRIPT_DIR}/config/test_edge_to_edge_mtls_target.json"

        self.mark_test_step("Configure the source Edge Server with an mTLS listener")
        source = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=source_config)

        self.mark_test_step("Push the peer CA and client certificate onto the target host")
        await self._install_peer_credentials(cblpytest.edge_servers[1])

        self.mark_test_step("Point the target's replication at the source over wss")
        config = await read_json_file(target_config)
        config["replications"][0]["source"] = source.replication_url("travel")
        await write_json_file(target_config, config)

        self.mark_test_step("Configure the target Edge Server to replicate using a client certificate")
        target = await cblpytest.edge_servers[1].configure_dataset(db_name="travel", config_file=target_config)

        self.mark_test_step("Wait for the replication to become idle")
        await target.wait_for_idle()

        self.mark_test_step("Verify document parity across every replicated collection")
        for collection in (
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ):
            source_docs = await source.get_all_documents("travel", collection=collection)
            target_docs = await target.get_all_documents("travel", collection=collection)
            assert len(source_docs.rows) == len(target_docs.rows), (
                f"{collection}: source has {len(source_docs.rows)} docs, target has {len(target_docs.rows)}"
            )
            assert len(source_docs.rows) > 0, (
                f"{collection} is empty on both servers -- the mTLS handshake may have "
                "succeeded without replicating anything"
            )

        self.mark_test_step("Write a document on the target and check it reaches the source")
        await target.put_document_with_id(
            {"type": "airline", "name": "mTLS Airline", "data": "MTLS"},
            "airline_mtls_1",
            "travel",
            collection="travel.airlines",
        )
        await target.wait_for_idle()

        propagated = await source.get_document(
            db_name="travel", scope="travel", collection="airlines", doc_id="airline_mtls_1"
        )
        assert propagated is not None, "Document written on the target did not reach the source"
        assert propagated.body["name"] == "mTLS Airline", (
            f"Document reached the source with unexpected content: {propagated.body}"
        )