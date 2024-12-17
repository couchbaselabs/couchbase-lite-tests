import subprocess
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.test_functions import compare_local_and_remote


class TestBasicReplicationXDCR(CBLTestClass):

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path):
        dataset = "names"
        bucket_name = "names"
        self.mark_test_step(f"Reset SG and load `{dataset}` dataset in cbs1.")
        cloud1 = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud1.configure_dataset(dataset_path, dataset)

        session_token = await cblpytest.sync_gateways[0].get_session_token(dataset, "user1")
        print(f"{session_token=}")

        cloud2 = CouchbaseCloud(
            cblpytest.sync_gateways[1], cblpytest.couchbase_servers[1]
        )
        await cloud2.configure_dataset(dataset_path, dataset)

        self.mark_test_step("Setup XDCR cbs1->cbs2.")
        cloud1.start_xdcr(cloud2, bucket_name, bucket_name)
        self.mark_test_step("Setup XDCR cbs2->cbs1.")
        cloud2.start_xdcr(cloud1, bucket_name, bucket_name)

        load_balancer_ip = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "environment-cbl-test-nginx-1",
            ],
            stdout=subprocess.PIPE,
            check=True,
            text=True,
        ).stdout.strip()
        self.mark_test_step(f"Load balancer IP: {load_balancer_ip}")

        self.mark_test_step(
            """
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.routes", "travel.landmarks", "travel.hotels"]
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert (
            status.error is None
        ), f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.routes", "travel.landmarks", "travel.hotels"],
        )

        await cblpytest.test_servers[0].cleanup()
