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
    
    def __init__(self, code: int, response: TestServerResponse, *args):
        self.__code = code
        self.__response = response
        super().__init__(args)

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