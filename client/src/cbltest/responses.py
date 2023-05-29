from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from json import dumps
from typing import Dict, Final, cast

from . import available_api_version
    
class ErrorDomain(Enum):
    TESTSERVER = 0
    CBL = 1
    POSIX = 2
    SQLITE = 3
    FLEECE = 4
    NETWORK = 5
    WEBSOCKET = 6

class ErrorResponseBody:
    ERROR_DOMAIN_KEY: Final[str] = "domain"
    ERROR_CODE_KEY: Final[str] = "code"
    ERROR_MSG_KEY: Final[str] = "message"

    @property
    def domain(self) -> ErrorDomain:
        return self.__domain
    
    @property
    def code(self) -> int:
        return self.__code
    
    @property
    def message(self) -> str:
        return self.__message
    
    @classmethod
    def create(c, body: dict) -> ErrorResponseBody:
        if c.ERROR_DOMAIN_KEY in body and c.ERROR_CODE_KEY in body \
            and c.ERROR_MSG_KEY in body:
            return ErrorResponseBody(body[c.ERROR_DOMAIN_KEY], body[c.ERROR_CODE_KEY], body[c.ERROR_MSG_KEY])
        
        return None

    def __init__(self, domain: ErrorDomain, code: int, message: str):
        self.__domain = domain
        self.__code = code
        self.__message = message

class TestServerResponse:
    @property
    def version(self) -> int:
        return self.__version
    
    @property
    def number(self) -> int:
        return self.__id
    
    @property
    def error(self) -> ErrorResponseBody:
        return self.__error

    def __init__(self, request_id: int, status_code: int, version: int, body: dict, 
                 http_name: str, http_method: str = "post"):
        self.__id = request_id
        self.__version = available_api_version(version)
        self.__status_code = status_code
        self.__error = ErrorResponseBody.create(body)
        self.__payload = body
        self.__http_name = http_name
        self.__http_method = http_method

    def serialize_payload(self) -> str:
        return dumps(self.__payload)

    def __str__(self) -> str:
        return f"<- v{self.__version} {self.__http_method.upper()} /{self.__http_name} #{self.__id} {self.__status_code}"

class GetRootResponse(TestServerResponse):
    __version_key: Final[str] = "version"
    __api_version_key: Final[str] = "apiVersion"
    __cbl_key: Final[str] = "cbl"
    __device_key: Final[str] = "device"

    @property
    def version(self) -> int:
        return self.__api_version

    @property
    def library_version(self) -> str:
        return self.__lib_version
    
    @property
    def cbl(self) -> str:
        return self.__cbl
    
    @property
    def device(self) -> Dict[str, any]:
        return self.__device
    
    def __init__(self, request_id: int, status_code: int, json: dict):
        self.__lib_version = cast(str, json.get(self.__version_key))
        self.__api_version = cast(int, json.get(self.__api_version_key))
        self.__cbl = cast(str, json.get(self.__cbl_key))
        self.__device = cast(Dict[str, any], json.get(self.__device_key))
        super().__init__(request_id, status_code, self.__api_version, json, "", "get")