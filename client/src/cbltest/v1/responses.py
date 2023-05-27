from json import dumps
from typing import Final, List, cast
from ..responses import TestServerResponse

class PostResetResponse(TestServerResponse):
    def __init__(self, request_id: int, status_code: int, version: int, body: dict):
        super().__init__(request_id, status_code, version, body)

    def _http_name(self) -> str:
        return "v1 POST /reset"
    
class PostGetAllDocumentIDsResponse(TestServerResponse):
    @property
    def collection_keys(self) -> List[str]:
        return self.__payload.keys()
    
    def documents_for_collection(self, collection: str) -> List[str]:
        return self.__payload.get(collection)
    
    def __init__(self, request_id: int, status_code: int, version: int, body: dict):
        super().__init__(request_id, status_code, version, body)
        self.__payload = body

    def _http_name(self) -> str:
        return "v1 POST /getAllDocumentIDs"
    
class PostSnapshotDocumentsResponse(TestServerResponse):
    __id_key: Final[str] = "id"

    @property
    def snapshot_id(self) -> str:
        return self.__snapshot_id

    def __init__(self, request_id: int, status_code: int, version: int, body: dict):
        super().__init__(request_id, status_code, version, body)
        self.__snapshot_id = cast(str, body.get(PostSnapshotDocumentsResponse.__id_key))

    def _http_name(self) -> str:
        return "v1 POST /snapshotDocuments"

    
