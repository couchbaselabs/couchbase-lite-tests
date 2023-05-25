from importlib import import_module
from json import dumps, loads
from typing import Dict, List, cast
from uuid import UUID
from requests import Request, Response

from cbltest.requests import TestServerResponse
from ..requests import TestServerRequest, TestServerRequestBody
from urllib.parse import urljoin

class PostResetRequestBody(TestServerRequestBody):
    @property
    def datasets(self) -> Dict[str, List[str]]:
        return self.__datasets
    
    def __init__(self):
        super().__init__(1)
        self.__datasets = {}

    def add_dataset(self, name: str, result_db_names: List[str]):
        self.__datasets[name] = result_db_names

    def serialize(self) -> str:
        return dumps(self.__datasets)


class PostResetRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        assert(isinstance(payload, PostResetRequestBody))
        super().__init__(1, uuid, payload)

    def _create_request(self, url: str) -> Request:
        full_url = urljoin(url, "reset")
        return Request("post", full_url)
    
    def _create_response(self, r: Response, version: int) -> TestServerResponse:
        module = import_module(f"cbltest.v{version}.responses")
        request_class = getattr(module, "PostResetResponse")
        content = loads(r.content)
        return cast(TestServerResponse, request_class(content))