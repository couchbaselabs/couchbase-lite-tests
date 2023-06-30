from __future__ import annotations
from enum import Enum
from json import dumps
from typing import Dict, Final, cast

from .version import available_api_version
from .api.jsonserializable import JSONSerializable
    
class ErrorDomain(Enum):
    """An enum representing the domain of an error returned by the server"""

    TESTSERVER = 0
    """The test server itself encountered an error (not a library bug)"""

    CBL = 1
    """High level Couchbase Lite error"""

    POSIX = 2
    """Low level OS error"""

    SQLITE = 3
    """Error returned from SQLite"""

    FLEECE = 4
    """Error returned from Fleece"""

    NETWORK = 5
    """Error in network connection"""

    WEBSOCKET = 6
    """Web socket protocol error"""

class ErrorResponseBody:
    """A class representing an error condition returned from the server"""

    __error_domain_key: Final[str] = "domain"
    __error_code_key: Final[str] = "code"
    __error_msg_key: Final[str] = "message"

    @property
    def domain(self) -> ErrorDomain:
        """Gets the domain of the returned error"""
        return self.__domain
    
    @property
    def code(self) -> int:
        """Gets the code of the returned error"""
        return self.__code
    
    @property
    def message(self) -> str:
        """Gets the message of the returned error"""
        return self.__message
    
    @classmethod
    def create(c, body: dict) -> ErrorResponseBody:
        """
        Creates an :class:`ErrorResponseBody` if the provided body contains the appropriate
        content, or returns `None` otherwise
        
        :param body: A dict potentially containing error keys
        """
        if body is not None and c.__error_domain_key in body and c.__error_code_key in body \
            and c.__error_msg_key in body:
            return ErrorResponseBody(body[c.__error_domain_key], body[c.__error_code_key], body[c.__error_msg_key])
        
        return None

    def __init__(self, domain: ErrorDomain, code: int, message: str):
        self.__domain = domain
        self.__code = code
        self.__message = message

class TestServerResponse(JSONSerializable):
    @property
    def version(self) -> int:
        """Gets the API version of the response, as specified by the remote server"""
        return self.__version
    
    @property
    def uuid(self) -> str:
        """Gets the UUID of the remote server that sent this response"""
        return self.__uuid
    
    @property
    def error(self) -> ErrorResponseBody:
        """Gets the error sent by the remote server, if any"""
        return self.__error

    def __init__(self, status_code: int, uuid: str, version: int, body: dict, 
                 http_name: str, http_method: str = "post"):
        self.__version = available_api_version(version)
        self.__status_code = status_code
        self.__uuid = uuid
        self.__error = ErrorResponseBody.create(body)
        self.__payload = body
        self.__http_name = http_name
        self.__http_method = http_method

    def to_json(self) -> any:
        """Serializes the body of the response to a JSON string"""
        return self.__payload

    def __str__(self) -> str:
        return f"<- {self.__uuid} v{self.__version} {self.__http_method.upper()} /{self.__http_name} {self.__status_code}"

class GetRootResponse(TestServerResponse):
    """
    The response to a GET / request.  It is not versioned like others, and in fact
    itself contains the API version to use.
    """
    __version_key: Final[str] = "version"
    __api_version_key: Final[str] = "apiVersion"
    __cbl_key: Final[str] = "cbl"
    __device_key: Final[str] = "device"

    @property
    def version(self) -> int:
        """Gets the API version specified by the remote server"""
        return self.__api_version

    @property
    def library_version(self) -> str:
        """Gets the version of Couchbase Lite that the remote server is using"""
        return self.__lib_version
    
    @property
    def cbl(self) -> str:
        """Gets the variant of Couchbase Lite (e.g. C) that the remote server is using"""
        return self.__cbl
    
    @property
    def device(self) -> Dict[str, any]:
        """Gets details about the device that the remote server is running on"""
        return self.__device
    
    def __init__(self, request_id: int, status_code: int, uuid: str, json: dict):
        self.__lib_version = cast(str, json.get(self.__version_key))
        self.__api_version = cast(int, json.get(self.__api_version_key))
        self.__cbl = cast(str, json.get(self.__cbl_key))
        self.__device = cast(Dict[str, any], json.get(self.__device_key))
        super().__init__(request_id, status_code, uuid, self.__api_version, json, "", "get")