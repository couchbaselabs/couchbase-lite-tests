from enum import Flag, auto
from typing import cast

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


class ServerVariant(Flag):
    ANDROID = auto()
    C = auto()
    DOTNET = auto()
    IOS = auto()
    JAVA = auto()

    def __str__(self) -> str:
        return "|".join([member.name for member in ServerVariant if member in self])


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
        self.__variant = None

    async def get_variant(self) -> ServerVariant:
        if self.__variant is None:
            self.__variant = self.__extract_variant(await self.get_info())

        return self.__variant

    async def get_info(self) -> GetRootResponse:
        """
        Retrieves the information about the running test server
        """
        with self.__tracer.start_as_current_span("get_info"):
            request = self.__request_factory.create_request(TestServerRequestType.ROOT)
            resp = await self.__request_factory.send_request(self.__index, request)
            ret_val = cast(GetRootResponse, resp)
            self.__variant = self.__extract_variant(ret_val)
            return ret_val

    async def create_and_reset_db(
        self,
        db_names: list[str],
        dataset: str | None = None,
        collections: list[str] | None = None,
    ) -> list[Database]:
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
            ret_val: list[Database] = []
            for db_name in db_names:
                ret_val.append(Database(self.__request_factory, self.__index, db_name))

            return ret_val

    async def new_session(
        self, id: str, dataset_version: str, url: str | None, tag: str | None
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

    def __extract_variant(self, info: GetRootResponse) -> ServerVariant:
        """
        Extracts the test server variant from the given info object.

        Args:
            info (GetRootResponse): The information object containing test server details.

        Returns:
            TestServerVariant: The extracted test server variant.
        """
        if info.cbl == "couchbase-lite-android":
            return ServerVariant.ANDROID
        elif info.cbl == "couchbase-lite-c":
            return ServerVariant.C
        elif info.cbl == "couchbase-lite-net":
            return ServerVariant.DOTNET
        elif info.cbl == "couchbase-lite-ios":
            return ServerVariant.IOS
        elif info.cbl == "couchbase-lite-java":
            return ServerVariant.JAVA
        else:
            raise ValueError(f"Unknown test server variant: {info.cbl}")
