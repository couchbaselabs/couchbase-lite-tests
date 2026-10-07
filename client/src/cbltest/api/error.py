from typing import Any

from cbltest.responses import TestServerResponse


class CblTestError(Exception):
    """An error occurred in the test framework or test server"""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)


class CblTimeoutError(TimeoutError):
    """A timeout occurred while waiting for an event"""

    # One message only, since OSError reads two arguments as (errno, strerror).
    def __init__(self, message: str) -> None:
        super().__init__(message)


class CblRemoteBadResponseError(Exception):
    """A bad response was returned from a remote service"""

    @property
    def code(self) -> int:
        """Gets the code that the remote service returned"""
        return self.__code

    @property
    def body(self) -> str:
        """Gets the response body that the remote service returned"""
        return self.__body

    def __init__(self, code: int, *args: Any, body: str) -> None:
        self.__code = code
        self.__body = body
        super().__init__(*args)


class CblTestServerBadResponseError(CblRemoteBadResponseError):
    """A bad HTTP code was returned from the test server"""

    @property
    def response(self) -> TestServerResponse:
        """Gets the body of the response that had the bad status"""
        return self.__response

    def __init__(self, code: int, response: TestServerResponse, message: str) -> None:
        if response.error is not None:
            message = f"{message}: ({response.error.domain} / {response.error.code}) {response.error.message}"

        self.__response = response
        super().__init__(code, message, body=response.serialize())


class CblSyncGatewayBadResponseError(CblRemoteBadResponseError):
    """A bad HTTP code was returned from Sync Gateway"""


class CblEdgeServerBadResponseError(CblRemoteBadResponseError):
    """A bad HTTP code was returned from Edge Server"""
