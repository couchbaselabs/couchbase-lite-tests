class CblTestError(Exception):
    """An error occurred in the test framework or test server"""
    def __init__(self, *args):
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