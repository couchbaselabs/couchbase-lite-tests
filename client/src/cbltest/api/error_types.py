from __future__ import annotations
from typing import Final, Optional

class ErrorDomain:
    """An enum representing the domain of an error returned by the server"""

    TESTSERVER: Final[str] = "TESTSERVER"
    """The test server itself encountered an error (not a library bug)"""

    CBL: Final[str] = "CBL"
    """High level Couchbase Lite error"""

    POSIX: Final[str] = "POSIX"
    """Low level OS error"""

    SQLITE: Final[str] = "SQLITE"
    """Error returned from SQLite"""

    FLEECE: Final[str] = "FLEECE"
    """Error returned from Fleece"""

    @classmethod
    def equal(cls, val: str, expected: str) -> bool:
        return val.upper() == expected

class ErrorResponseBody:
    """A class representing an error condition returned from the server"""

    __error_domain_key: Final[str] = "domain"
    __error_code_key: Final[str] = "code"
    __error_msg_key: Final[str] = "message"

    @property
    def domain(self) -> str:
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
    def create(c, body: Optional[dict]) -> Optional[ErrorResponseBody]:
        """
        Creates an :class:`ErrorResponseBody` if the provided body contains the appropriate
        content, or returns `None` otherwise
        
        :param body: A dict potentially containing error keys
        """
        if body is not None and c.__error_domain_key in body and c.__error_code_key in body \
            and c.__error_msg_key in body:
            return ErrorResponseBody(body[c.__error_domain_key], body[c.__error_code_key], body[c.__error_msg_key])
        
        return None

    def __init__(self, domain: str, code: int, message: str):
        self.__domain = domain
        self.__code = code
        self.__message = message