from typing import List

from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import RequestFactory, TestServerRequestType
from cbltest.v1.requests import PostResetRequestBody
from cbltest.api.error import CblTestError
from cbltest.api.database import Database

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


    async def create_and_reset_db(self, dataset: str, db_names: List[str]) -> List[Database]:
        """
        Creates and returns a set of Databases based on the given dataset

        :param dataset: The name of the dataset to use for creating the databases
        :param db_names: A list of database names, each of which will become a database with the dataset data
        """
        payload = PostResetRequestBody()
        payload.add_dataset(dataset, db_names)
        request = self.__request_factory.create_request(TestServerRequestType.RESET, payload)
        resp = await self.__request_factory.send_request(self.__index, request)
        if not resp:
            raise CblTestError("Failed to send reset DB message, see http log")
        if resp.error:
            cbl_error("Failed to reset DB, see trace log for details")
            cbl_trace(resp.error.message)
            return None
        
        ret_val: List[Database] = []
        for db_name in db_names:
            ret_val.append(Database(self.__request_factory, self.__index, db_name))

        return ret_val