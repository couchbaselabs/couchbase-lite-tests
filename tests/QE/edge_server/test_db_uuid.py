from datetime import timedelta, datetime
from pathlib import Path
from random import randint
from typing import List
import random
import pytest
import time
import os
import json
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblEdgeServerBadResponseError, CblSyncGatewayBadResponseError
from cbltest.api.edgeserver import EdgeServer, BulkDocOperation
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, \
    WaitForDocumentEventEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload, SyncGateway
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null

from conftest import cblpytest

from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
import logging

logger = logging.getLogger(__name__)

class TestDbUUID(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_db_uuid_cli(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to check the database UUID reset functionality")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        self.mark_test_step("Get initial UUID")
        response = await edge_server.get_db_info(es_db_name)
        initial_uuid = response["db_uuid"]
        logger.info(f"Initial UUID: {initial_uuid}")
        # print(response)

        self.mark_test_step("Reset the database UUID")
        await edge_server.reset_db_uuid(es_db_name)

        self.mark_test_step("Get the UUID after reset")
        response = await edge_server.get_db_info(es_db_name)
        reset_uuid = response["db_uuid"]
        logger.info(f"Reset UUID: {reset_uuid}")
        # print(response)

        self.mark_test_step("Check if the UUID is different after reset")
        assert initial_uuid != reset_uuid, "UUID should be different after reset"

        logger.info("Database UUID reset through CLI test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_db_uuid_config(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to check the database UUID reset functionality")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        self.mark_test_step("Get initial UUID")
        response = await edge_server.get_db_info(es_db_name)
        initial_uuid = response["db_uuid"]
        logger.info(f"Initial UUID: {initial_uuid}")
        print(response)

        self.mark_test_step("Reset the database UUID")

        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        config_path =f"{file_path}/environment/edge_server/config/config_reset_uuid.json"
        with open(config_path, "r") as file:
            config = json.load(file)

        # Update the source dynamically
        config["databases"]["db"]["placeholder_uuid"] = initial_uuid

        # Save the updated config
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)

        await edge_server.set_config(config_path, "/opt/couchbase-edge-server/etc/config.json")

        self.mark_test_step("Get the UUID after reset")
        response = await edge_server.get_db_info(es_db_name)
        reset_uuid = response["db_uuid"]
        logger.info(f"Reset UUID: {reset_uuid}")
        print(response)

        self.mark_test_step("Check if the UUID is different after reset")
        assert initial_uuid != reset_uuid, "UUID should be different after reset"

        logger.info("Database UUID reset through config file test passed.")
