from __future__ import annotations
from abc import ABC, abstractmethod
from json import loads
from logging import warning
from typing import cast
from uuid import UUID, uuid4
from requests import Request, Response, Session
from importlib import import_module

from .responses import GetRootResponse, TestServerResponse

def available_api_version(version: int) -> int:
    if version < 2:
        return version
    
    raise NotImplementedError(f"API version {version} does not exist!")

class TestServerRequestBody(ABC):
    @property
    def version(self) -> int:
        return self.__version

    def __init__(self, version: int):
        self.__version = available_api_version(version)

    @abstractmethod
    def serialize(self) -> str:
        pass

class TestServerRequest(ABC):
    def __init__(self, version: int, uuid: UUID, payload: TestServerRequestBody = None):
        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload

    @abstractmethod
    def _create_request(self, url: str) -> Request:
        return None
    
    @abstractmethod
    def _create_response(self, r: Response, version: int) -> TestServerResponse:
        return None
    
    def send(self, url: str, session: Session = None) -> TestServerResponse:
        r = self._create_request(url)
        r.headers["Accept"] = "application/json"
        if self.__version > 0:
            r.headers["CBLTest-API-Version"] = str(self.__version)
            r.headers["CBLTest-Client-ID"] = str(self.__uuid)
        
        if self.__payload is not None:
            r.data = self.__payload.serialize()

        r.prepare()
        if session is not None:
            resp = session.send(r.prepare())
        else:
            with Session() as s:
                resp = s.send(r.prepare())

        resp_version = int(resp.headers["CBLTest-API-Version"])
        if resp_version != self.__version:
            warning(f"Response version {resp_version} does not match request version {self.__version}!")

        return self._create_response(resp, resp_version)

# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    def __init__(self, uuid: UUID):
        super().__init__(0, uuid)

    def _create_request(self, url: str) -> Request:
        return Request("get", url)
    
    def _create_response(self, r: Response, version: int) -> TestServerResponse:
        return GetRootResponse(loads(r.content))


class RequestFactory:
    def __init__(self, version: int):
        self.__version = available_api_version(version)
        self.__uuid = uuid4()

    def _create_request(self, name: str, payload: TestServerRequestBody = None) -> TestServerRequest:
        if self.__version != payload.version:
            raise ValueError(f"Request factory version {self.__version} does not match payload version {payload.version}!")
        
        module = import_module(f"cbltest.v{self.__version}.requests")
        request_class = getattr(module, name)
        if payload is None:
            return cast(TestServerRequest, request_class(self.__uuid))
        
        return cast(TestServerRequest, request_class(self.__uuid, payload))

    def create_get_root(self) -> TestServerRequest:
        return GetRootRequest(self.__uuid)
    
    def create_post_reset(self, payload: TestServerRequestBody) -> TestServerRequest:
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostResetRequest", payload)
    
    
