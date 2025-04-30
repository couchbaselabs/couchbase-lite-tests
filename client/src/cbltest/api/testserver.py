from typing import List, Optional, cast
from urllib.parse import urljoin

from opentelemetry.trace import get_tracer

from cbltest.api.database import Database
from cbltest.globals import CBLPyTestGlobal
from cbltest.requests import RequestFactory, TestServerRequestType
from cbltest.responses import GetRootResponse
from cbltest.v1.requests import (
    PostLogRequestBody,
    PostNewSessionRequestBody,
    PostResetRequestBody,
)
from cbltest.version import VERSION
from client.src.cbltest import _assert_not_null
# For my project I had to configure the source to be `~/couchbase-lite-tests` manually,
# so all the imports now for my pycharm source are relative to that.
# By default, it was configured to be `~/couchbase-lite-tests/client/src/`
# Should I keep the imports sourced relative to the `src/` dir?


class TestServer:
    """
    A class for interacting with a Couchbase Lite test server
    """

    @property
    def url(self) -> str:
        """Gets the URL of the test server being communicated with"""
        return self.__url

    def __init__(self, request_factory: RequestFactory, index: int, url: str):
        assert request_factory.version == 1, (
            "This version of the CBLTest API requires request API v1"
        )
        self.__index = index
        self.__url = url
        self.__request_factory = request_factory
        self.__tracer = get_tracer(__name__, VERSION)

    async def get_info(self) -> GetRootResponse:
        """
        Retrieves the information about the running test server
        """
        with self.__tracer.start_as_current_span("get_info"):
            request = self.__request_factory.create_request(TestServerRequestType.ROOT)
            resp = await self.__request_factory.send_request(self.__index, request)
            return cast(GetRootResponse, resp)

    async def create_and_reset_db(
        self,
        db_names: List[str],
        dataset: Optional[str] = None,
        collections: Optional[List[str]] = None,
    ) -> List[Database]:
        """
        Creates and returns a set of Databases based on the given dataset

        :param db_names: A list of database names, each of which will become a database based on
                         the other two args
        :param dataset: The name of the dataset to use for creating the databases (if not specified
                        an empty database will be created).  Cannot be combined with collections.
        :param collections: The name of the collections to add after creating the database.  Cannot
                            be combined with dataset.
        """
        assert collections is None or dataset is None, (
            "dataset and collections cannot both be specified"
        )

        with self.__tracer.start_as_current_span("create_and_reset_db"):
            payload = PostResetRequestBody(CBLPyTestGlobal.running_test_name)
            if dataset is not None:
                payload.add_dataset(dataset, db_names)
            else:
                payload.add_empty(db_names, collections)

            request = self.__request_factory.create_request(
                TestServerRequestType.RESET, payload
            )
            await self.__request_factory.send_request(self.__index, request)
            ret_val: List[Database] = []
            for db_name in db_names:
                ret_val.append(Database(self.__request_factory, self.__index, db_name))

            return ret_val

    async def new_session(
        self, id: str, dataset_version: str, url: Optional[str], tag: Optional[str]
    ):
        """
        Instructs this test server to log to the given LogSlurp instance

        :param url: The URL of the LogSlurp server
        :param id: The ID of the log to log to
        :param tag: The tag to use for this test server
        """
        with self.__tracer.start_as_current_span("new_session"):
            payload = PostNewSessionRequestBody(id, dataset_version, url, tag)
            request = self.__request_factory.create_request(
                TestServerRequestType.NEW_SESSION, payload
            )
            await self.__request_factory.send_request(self.__index, request)

    async def cleanup(self) -> None:
        """
        Resets the test server
        """
        with self.__tracer.start_as_current_span("create_and_reset_db"):
            request = self.__request_factory.create_request(
                TestServerRequestType.RESET, PostResetRequestBody()
            )
            await self.__request_factory.send_request(self.__index, request)

    async def log(self, msg: str) -> None:
        """
        Sends a message to be logged on the server side.  Useful for debugging.
        """

        # I'll exclude this from telemetry since it's not really related to any testing
        payload = PostLogRequestBody(msg)
        request = self.__request_factory.create_request(
            TestServerRequestType.LOG, payload
        )
        await self.__request_factory.send_request(self.__index, request)

    def replication_url(self, db_name: str, port: int):
        """
        Returns the URL of the replication endpoint for this test server
        """
        ws_scheme = "ws://"  # For now not using secure

        _assert_not_null(db_name, "db_name")
        replication_url = f"{ws_scheme}{self.url}:{port}"
        return urljoin(replication_url, db_name)

