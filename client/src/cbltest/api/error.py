from cbltest.responses import TestServerResponse


class CblTestError(Exception):
    """An error occurred in the test framework or test server"""

    def __init__(self, *args):
        super().__init__(args)


class CblTestServerBadResponseError(Exception):
    """A bad HTTP code was returned from the test server"""

    @property
    def code(self) -> int:
        """Gets the code that the test server returned"""
        return self.__code

    @property
    def response(self) -> TestServerResponse:
        """Gets the body of the response that had the bad status"""
        return self.__response

    def __init__(self, code: int, response: TestServerResponse, message: str):
        self.__code = code
        self.__response = response
        self.__message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.__message


class CblTimeoutError(Exception):
    """A timeout occurred while waiting for an event"""

    def __init__(self, *args):
        super().__init__(args)


class CblSyncGatewayBadResponseError(Exception):
    """A bad HTTP code was returned from Sync Gateway"""

    @property
    def code(self) -> int:
        """Gets the code that Sync Gateway returned"""
        return self.__code

    def __init__(self, code: int, *args):
        self.__code = code
        super().__init__(args)


class CblEdgeServerBadResponseError(Exception):
    """A bad HTTP code was returned from Edge Server"""

    @property
    def code(self) -> int:
        return self.__code

    def __init__(self, code: int, *args):
        self.__code = code
        super().__init__(args)