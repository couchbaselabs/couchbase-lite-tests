from ..requests import TestServerResponse

class PostResetResponse(TestServerResponse):
    def __init__(self, version: int, body: dict):
        super().__init__(version, body)
