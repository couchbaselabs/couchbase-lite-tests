from __future__ import annotations
from abc import ABC
from enum import Enum
from json import dumps, loads
from typing import Dict, Final, cast

from .requests import available_api_version
    
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
        if c.ERROR_DOMAIN_KEY in dict and c.ERROR_CODE_KEY in dict \
            and c.ERROR_MSG_KEY in dict:
            return ErrorResponseBody(body[c.ERROR_DOMAIN_KEY], body[c.ERROR_CODE_KEY], body[c.ERROR_MSG_KEY])
        
        return None

    def __init__(self, domain: ErrorDomain, code: int, message: str):
        self.__domain = domain
        self.__code = code
        self.__message = message

class TestServerResponse(ABC):
    @property
    def version(self) -> int:
        return self.__version
    
    @property
    def error(self) -> ErrorResponseBody:
        return self.__error

    def __init__(self, version: int, body: dict):
        self.__version = available_api_version(version)
        self.__error = ErrorResponseBody.create(body)

class GetRootResponse(TestServerResponse):
    __version_key: Final[str] = "version"
    __api_version_key: Final[str] = "apiVersion"
    __cbl_key: Final[str] = "cbl"
    __device_key: Final[str] = "device"

    @property
    def version(self) -> str:
        return self.__version
    
    @property
    def api_version(self) -> int:
        return self.__api_version
    
    @property
    def cbl(self) -> str:
        return self.__cbl
    
    @property
    def device(self) -> Dict[str, any]:
        return self.__device
    
    def __init__(self, json: dict):
        self.__version = cast(str, json.get(self.__version_key))
        self.__api_version = cast(int, json.get(self.__api_version_key))
        self.__cbl = cast(str, json.get(self.__cbl_key))
        self.__device = cast(Dict[str, any], json.get(self.__device_key))

    def __str__(self):
        return f"Version: {self.__version}\nAPI Version: {self.__api_version}\nCBL Variant: {self.__cbl}\nDevice: {dumps(self.__device)}"