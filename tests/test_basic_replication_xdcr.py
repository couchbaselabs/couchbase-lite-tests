from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import List

import pytest, pytest_asyncio
import subprocess
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
from cbltest.api.replicator_types import ReplicatorSessionAuthenticator
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.utils import assert_not_null

class ServiceAction(Enum):
    START = "start"
    STOP = "stop"

class SGService(Enum):
    SG1 = "cbl-test-sg1"
    SG2 = "cbl-test-sg2"
class DatasetBucket(Enum):
    NONE = 0
    SG1 = 1
    SG2 = 2

class TestBasicReplicationXDCR(CBLTestClass):
    def manage_sync_gateway(self, action: ServiceAction, name: SGService) -> None:
        """
        Manages a Sync Gateway service using Docker Compose (start or stop).
        :param name: Name of the Sync Gateway service.
        :param action: Action to perform, either ServiceAction.START or ServiceAction.STOP.
        """
        if action not in ServiceAction:
            raise ValueError(f"Invalid action: {action}")

        script_dir = Path(__file__).resolve().parent
        config_file = script_dir / "../environment/docker-compose-xdcr.yml"

        if not config_file.exists():
            raise FileNotFoundError(f"Docker Compose config file not found: {config_file}")

        try:
            subprocess.run(
                ["docker", "compose", "-f", str(config_file), action.value, name.value],
                check=True,
                text=True
            )

            if action == ServiceAction.START:
                print("Waiting for 20 seconds for SG to start ...")
                time.sleep(20)

            print(f"Successfully performed '{action.value}' on {name.value} using config: {config_file}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to {action.value} {name.value}: {e}")

    def is_sync_gateway_running(self, name: SGService) -> bool:
        script_dir = Path(__file__).resolve().parent
        config_file = script_dir / "../environment/docker-compose-xdcr.yml"

        if not config_file.exists():
            raise FileNotFoundError(f"Docker Compose config file not found: {config_file}")

        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(config_file), "ps", "--services", "--filter", "status=running"],
                stdout=subprocess.PIPE,
                check=True,
                text=True
            )
            running_services = result.stdout.splitlines()
            return name.value in running_services
        except subprocess.CalledProcessError as e:
            print(f"Error checking sync gateway status: {e}")
            return False

    async def setup_replication_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path, dataset: str, bucket_name: str,
                                     dataset_bucket: DatasetBucket = DatasetBucket.SG1):
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
        await cloud1.configure_dataset(dataset_path, dataset, loadDataset=(dataset_bucket == DatasetBucket.SG1))

        cloud2 = CouchbaseCloud(
            cblpytest.sync_gateways[1], cblpytest.couchbase_servers[1]
        )
        await cloud2.configure_dataset(dataset_path, dataset, loadDataset=(dataset_bucket == DatasetBucket.SG2))

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

    @pytest_asyncio.fixture(autouse=True)
    async def setup_test(self, cblpytest: CBLPyTest, dataset_path: Path):
        if not self.is_sync_gateway_running(SGService.SG1):
            self.mark_test_step("SG1 is down, start SG1")
            self.manage_sync_gateway(ServiceAction.START, SGService.SG1)
        if not self.is_sync_gateway_running(SGService.SG2):
            self.mark_test_step("SG2 is down, start SG2")
            self.manage_sync_gateway(ServiceAction.START, SGService.SG2)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path):
        '''
        Summary:
            1. Push 100 names docs from a local database to a Sync Gateway via a load balancer.
            2. Wait until the replicator is idle.
            3. Check that all docs are pushed from the local database to both Sync Gateways
        '''
        dataset = "names"
        bucket_name = "names"

        self.mark_test_step("Setup SG and XDCR.")
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator: 
            * endpoint: `/names`
            * collections : `_default._default`
            * type: push
            * continuous: true
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

        self.mark_test_step("Check that all docs are pushed correctly to SG1.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "names",
                                       ["_default._default"])

        self.mark_test_step("Wait 5 secs to ensure that the docs are sync between two SGs.")
        time.sleep(5);

        self.mark_test_step("Check that all docs are pushed correctly to SG2.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[1], ReplicatorType.PUSH, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path):
        '''
        Summary:
            1. Pull 100 names docs from a Sync Gateway via a load balancer to a local database.
            2. Wait until the replicator is idle.
            3. Check that all docs are pulled from Sync Gateway by comparing with both Sync Gateways.
        '''
        dataset = "names"
        bucket_name = "names"

        self.mark_test_step("Setup SG and XDCR.")
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name, dataset_bucket=DatasetBucket.SG2)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("Wait 5 secs to ensure that the docs are sync between two SGs.")
        time.sleep(5);

        self.mark_test_step('''
            Start a replicator: 
            * endpoint: `/names`
            * collections : `_default._default`
            * type: pull
            * continuous: true
            ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PULL,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are pulled correctly from SG1.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "names",
                                       ["_default._default"])

        self.mark_test_step("Check that all docs are pulled correctly from SG2.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[1], ReplicatorType.PULL, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_and_pull_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path):
        '''
        Summary:
            1. Push and pull 100 names docs from a Sync Gateway via a load balancer to a local database.
            2. Wait until the replicator is idle.
            3. Check that all docs are replicated correctly.
            4. Add, update, and delete docs from the local database.
            5. Add, update, and delete docs from Sync Gateway via a load balancer.
            6. Wait until the replicator is idle.
            7. Check that all docs are replicated correctly.
        '''
        dataset = "names"
        bucket_name = "names"

        self.mark_test_step("Setup SG and XDCR.")
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator to SG1 via load balancer: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
            ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])
        await compare_local_and_remote(db, cblpytest.sync_gateways[1], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        self.mark_test_step('''
            Update documents in the local database.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_201", [{"name.last": "Spring"}])
            b.upsert_document("_default._default", "name_202", [{"name.last": "Summer"}])
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.upsert_document("_default._default", "name_2", [{"name.last": "Fall"}])
            b.delete_document("_default._default", "name_3")
            b.delete_document("_default._default", "name_4")

        self.mark_test_step('''
            Update documents on SG 2.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        # Add 2 docs to SG
        sg_news: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"}),
            DocumentUpdateEntry("name_302", None, body={"name.last": "Rain"})]
        await cblpytest.sync_gateways[1].update_documents("names", sg_news, "_default", "_default")

        # Update 2 docs in SG
        sg_updates: List[DocumentUpdateEntry] = []
        names_all_docs = await cblpytest.sync_gateways[1].get_all_documents("names", "_default", "_default")
        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"}))
            elif doc.id == "name_102":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Sky"}))
        await cblpytest.sync_gateways[1].update_documents("names", sg_updates, "_default", "_default")

        # Remove 2 docs from SG
        hotels_all_docs = await cblpytest.sync_gateways[1].get_all_documents("names", "_default", "_default")
        for doc in hotels_all_docs.rows:
            if doc.id == "name_103" or doc.id == "name_104":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[1].delete_document(doc.id, revid, "names", "_default", "_default")

        self.mark_test_step("Wait 5 secs to ensure that the docs are sync between two SGs.")
        time.sleep(5);

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])
        await compare_local_and_remote(db, cblpytest.sync_gateways[1], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_fail_over_with_basic_auth(self, cblpytest: CBLPyTest, dataset_path: Path):
        '''
        Summary:
            1. Push and pull 100 names docs from a Sync Gateway via a load balancer to a local database.
            2. Wait until the replicator is IDLE.
            3. Check that all docs are replicated correctly.
            4. Stop SG1
            5. Wait until the replicator is OFFLINE.
            6. Wait until the replicator is IDLE, after reconnecting to SG2 via load balancer.
            7. Add 2 docs (name_201, name_202), update 2 docs (name_1, name_2), and delete 2 docs (name_3, name_4) in the local database.
            8. Add 2 docs (name_301, name_302), update 2 docs (name_101, name_102), and delete 2 docs (name_103, name_104) in SG2.
            9. Wait until the replicator is IDLE.
            10. Check that all docs are replicated correctly.
        '''
        dataset = "names"
        bucket_name = "names"

        self.mark_test_step("Setup SG and XDCR.")
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator to SG1 via load balancer: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
            ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        self.mark_test_step('''Stop SG1''')
        self.manage_sync_gateway(ServiceAction.STOP, SGService.SG1)

        self.mark_test_step('''Wait for replicator to become OFFLINE''')
        await replicator.wait_for(ReplicatorActivityLevel.OFFLINE)

        self.mark_test_step('''Wait for replicator to become IDLE again after reconnect to SG2''')
        await replicator.wait_for(ReplicatorActivityLevel.IDLE, timeout=timedelta(seconds=60))

        self.mark_test_step('''
            Update documents in the local database.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_201", [{"name.last": "Spring"}])
            b.upsert_document("_default._default", "name_202", [{"name.last": "Summer"}])
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.upsert_document("_default._default", "name_2", [{"name.last": "Fall"}])
            b.delete_document("_default._default", "name_3")
            b.delete_document("_default._default", "name_4")

        self.mark_test_step('''
            Update documents on SG via load balancer.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        # Add 2 docs to SG
        sg_news: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"}),
            DocumentUpdateEntry("name_302", None, body={"name.last": "Rain"})]
        await cblpytest.sync_gateways[2].update_documents("names", sg_news, "_default", "_default")

        # Update 2 docs in SG
        sg_updates: List[DocumentUpdateEntry] = []
        names_all_docs = await cblpytest.sync_gateways[2].get_all_documents("names", "_default", "_default")
        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"}))
            elif doc.id == "name_102":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Sky"}))
        await cblpytest.sync_gateways[2].update_documents("names", sg_updates, "_default", "_default")

        # Remove 2 docs from SG
        hotels_all_docs = await cblpytest.sync_gateways[2].get_all_documents("names", "_default", "_default")
        for doc in hotels_all_docs.rows:
            if doc.id == "name_103" or doc.id == "name_104":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[2].delete_document(doc.id, revid, "names", "_default", "_default")

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[2], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_fail_over_with_session_auth(self, cblpytest: CBLPyTest, dataset_path: Path):
        '''
        Summary:
            1. Get a session token from SG and start a push-pull replicator.
            2. Push and pull 100 names docs from a Sync Gateway via a load balancer to a local database.
            3. Wait until the replicator is IDLE.
            4. Check that all docs are replicated correctly.
            5. Stop SG1
            6. Wait until the replicator is OFFLINE.
            7. Wait until the replicator is STOPPED after reconnecting to SG2 with the old session via the load balancer.
            8. Get a new session token from SG2 and start a push-pull replicator via the load balancer.
            9. Wait until the replicator is IDLE.
            10. Add 2 docs (name_201, name_202), update 2 docs (name_1, name_2), and delete 2 docs (name_3, name_4) in the local database.
            11. Add 2 docs (name_301, name_302), update 2 docs (name_101, name_102), and delete 2 docs (name_103, name_104) in SG2.
            12. Wait until the replicator is IDLE.
            13. Check that all docs are replicated correctly.
        '''
        dataset = "names"
        bucket_name = "names"

        self.mark_test_step("Setup SG and XDCR.")
        await self.setup_replication_xdcr(cblpytest, dataset_path, dataset, bucket_name)

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("Get a session token from SG.")
        session = await cblpytest.sync_gateways[2].get_session_token(dataset, "user1")

        self.mark_test_step('''
            Start a replicator to SG1 via load balancer: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
            ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorSessionAuthenticator(session["session_id"], session["cookie_name"]))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        self.mark_test_step('''Stop SG1''')
        self.manage_sync_gateway(ServiceAction.STOP, SGService.SG1)

        self.mark_test_step('''Wait for replicator to become OFFLINE''')
        await replicator.wait_for(ReplicatorActivityLevel.OFFLINE)

        self.mark_test_step('''Wait for replicator to become STOPPED after reconnect to SG2''')
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED, timeout=timedelta(seconds=60))
        assert status.error is not None, "Expected an error, but none occurred."
        assert status.error.code == 10401, f"Expected error code 10401, but got {status.error.code}"
        print(f">>> STATUS : {status}")

        self.mark_test_step("Get a new session token from SG.")
        session = await cblpytest.sync_gateways[2].get_session_token(dataset, "user1")

        self.mark_test_step('''
            Start a replicator to SG2 via load balancer with a new session: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
                ''')
        replicator = Replicator(db, cblpytest.sync_gateways[2].replication_url("names"),
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                continuous=True,
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                authenticator=ReplicatorSessionAuthenticator(session["session_id"], session["cookie_name"]))
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step('''
            Update documents in the local database.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_201", [{"name.last": "Spring"}])
            b.upsert_document("_default._default", "name_202", [{"name.last": "Summer"}])
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.upsert_document("_default._default", "name_2", [{"name.last": "Fall"}])
            b.delete_document("_default._default", "name_3")
            b.delete_document("_default._default", "name_4")

        self.mark_test_step('''
            Update documents on SG via load balancer.
                * Add 2 docs in default collection.
                * Update 2 docs in default collection.
                * Remove 2 docs in default collection.
            ''')
        # Add 2 docs to SG
        sg_news: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"}),
            DocumentUpdateEntry("name_302", None, body={"name.last": "Rain"})]
        await cblpytest.sync_gateways[2].update_documents("names", sg_news, "_default", "_default")

        # Update 2 docs in SG
        sg_updates: List[DocumentUpdateEntry] = []
        names_all_docs = await cblpytest.sync_gateways[2].get_all_documents("names", "_default", "_default")
        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"}))
            elif doc.id == "name_102":
                sg_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Sky"}))
        await cblpytest.sync_gateways[2].update_documents("names", sg_updates, "_default", "_default")

        # Remove 2 docs from SG
        hotels_all_docs = await cblpytest.sync_gateways[2].get_all_documents("names", "_default", "_default")
        for doc in hotels_all_docs.rows:
            if doc.id == "name_103" or doc.id == "name_104":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[2].delete_document(doc.id, revid, "names", "_default", "_default")

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly")
        await compare_local_and_remote(db, cblpytest.sync_gateways[2], ReplicatorType.PUSH_AND_PULL, "names",
                                       ["_default._default"])

        await cblpytest.test_servers[0].cleanup()
