from typing import Any

from cbltest.responses import TestServerResponse


class CblTestError(Exception):
    """An error occurred in the test framework or test server"""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)


class CblHttpError(CblTestError):
    """A bad HTTP code was returned by an HTTP endpoint the framework called"""

    @property
    def code(self) -> int:
        """Gets the code that the endpoint returned"""
        return self.__code

    @property
    def body(self) -> str:
        """Gets the response body that the endpoint returned"""
        return self.__body

    def __init__(self, code: int, *args: Any, body: str) -> None:
        self.__code = code
        self.__body = body
        super().__init__(*args)


class CblTestServerBadResponseError(CblHttpError):
    """A bad HTTP code was returned from the test server"""

    @property
    def response(self) -> TestServerResponse:
        """Gets the body of the response that had the bad status"""
        return self.__response

    def __init__(self, code: int, response: TestServerResponse, message: str) -> None:
        self.__response = response
        super().__init__(code, message, body=response.serialize())


class CblTimeoutError(Exception):
    """A timeout occurred while waiting for an event"""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)


class CblSyncGatewayBadResponseError(CblHttpError):
    """A bad HTTP code was returned from Sync Gateway"""


class CblEdgeServerBadResponseError(CblHttpError):
    """A bad HTTP code was returned from Edge Server"""
