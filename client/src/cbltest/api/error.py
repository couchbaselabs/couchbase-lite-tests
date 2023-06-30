class CblTestError(Exception):
    def __init__(self, *args):
        super().__init__(args)

class CblTimeoutError(Exception): 
    def __init__(self, *args):
        super().__init__(args)

class CblSyncGatewayBadResponseError(Exception):
    @property 
    def code(self) -> int:
        return self.__code
    
    def __init__(self, code: int, *args):
        self.__code = code
        super().__init__(args)