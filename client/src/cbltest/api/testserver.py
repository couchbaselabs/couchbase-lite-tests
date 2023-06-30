from typing import List

from ..logging import cbl_error, cbl_trace
from ..requests import RequestFactory, TestServerRequestType
from ..v1.requests import PostResetRequestBody
from .error import CblTestError
from .database import Database

class TestServer:
    @property
    def url(self) -> str:
        return self.__url
    
    def __init__(self, request_factory: RequestFactory, index: int, url: str):
        assert(request_factory.version == 1)
        self.__index = index
        self.__url = url
        self.__request_factory = request_factory


    async def create_and_reset_db(self, dataset: str, db_names: List[str]) -> List[Database]:
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