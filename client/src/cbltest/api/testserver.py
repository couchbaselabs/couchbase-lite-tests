from typing import List, cast

from opentelemetry.trace import get_tracer

from cbltest.api.database import Database
from cbltest.globals import CBLPyTestGlobal
from cbltest.requests import RequestFactory, TestServerRequestType
from cbltest.responses import GetRootResponse
from cbltest.v1.requests import PostResetRequestBody
from cbltest.version import VERSION


class TestServer:
    """
    A class for interacting with a Couchbase Lite test server
    """

    @property
    def url(self) -> str:
        """Gets the URL of the test server being communicated with"""
        return self.__url

    def __init__(self, request_factory: RequestFactory, index: int, url: str):
        assert request_factory.version == 1, "This version of the CBLTest API requires request API v1"
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

    async def create_and_reset_db(self, dataset: str, db_names: List[str]) -> List[Database]:
        """
        Creates and returns a set of Databases based on the given dataset

        :param dataset: The name of the dataset to use for creating the databases
        :param db_names: A list of database names, each of which will become a database with the dataset data
        """
        with self.__tracer.start_as_current_span("create_and_reset_db"):
            payload = PostResetRequestBody(CBLPyTestGlobal.running_test_name)
            payload.add_dataset(dataset, db_names)
            request = self.__request_factory.create_request(TestServerRequestType.RESET, payload)
            await self.__request_factory.send_request(self.__index, request)
            ret_val: List[Database] = []
            for db_name in db_names:
                ret_val.append(Database(self.__request_factory, self.__index, db_name))

            return ret_val

    async def cleanup(self) -> None:
        """
        Resets the test server
       """
        with self.__tracer.start_as_current_span("create_and_reset_db"):
            request = self.__request_factory.create_request(TestServerRequestType.RESET, PostResetRequestBody())
            await self.__request_factory.send_request(self.__index, request)
