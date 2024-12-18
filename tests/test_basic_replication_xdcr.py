import subprocess
from pathlib import Path

import pytest
import time

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
    async def setup_replication_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path, dataset: str, bucket_name: str):
        """
        Setup XDCR replication by configuring datasets, setting up XDCR, and retrieving the load balancer IP.
        :param cblpytest: Pytest fixture for Couchbase Lite tests
        :param dataset_path: Path to the dataset
        :param dataset: Dataset name
        :param bucket_name: Couchbase bucket name
        """
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

        # Retrieve the load balancer IP
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
        # return cloud1, cloud2, load_balancer_ip

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path):
        dataset = "names"
        bucket_name = "names"

        # Setup XDCR:
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator: 
            * endpoint: `/names`
            * collections : `_default._default`
            * type: push
            * continuous: false
            ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PUSH,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        print("Replicator is not IDLE")

        self.mark_test_step("Check that all docs are replicated correctly to SG1.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "names",
                                       ["_default._default"])

        time.sleep(5);

        self.mark_test_step("Check that all docs are replicated correctly to SG2.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[1], ReplicatorType.PUSH, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()
