from importlib import import_module
from json import dumps, loads
from typing import Dict, List, cast
from uuid import UUID
from requests import Request

from ..logging import cbl_warning
from ..requests import TestServerRequest, TestServerRequestBody
from urllib.parse import urljoin

class PostResetRequestBody(TestServerRequestBody):
    @property
    def datasets(self) -> Dict[str, List[str]]:
        return self.__datasets
    
    def __init__(self):
        super().__init__(1)
        self.__datasets = {}

    def add_dataset(self, name: str, result_db_names: List[str]):
        self.__datasets[name] = result_db_names

    def serialize(self) -> str:
        return f'{{"datasets": {dumps(self.__datasets)}}}'


class PostResetRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        assert(isinstance(payload, PostResetRequestBody))
        super().__init__(1, uuid, payload)

    def _create_request(self, url: str) -> Request:
        full_url = urljoin(url, "reset")
        return Request("post", full_url)
    
    def _http_name(self) -> str:
        return "v1 POST /reset"
    
class PostGetAllDocumentIDsRequestBody(TestServerRequestBody):
    @property
    def collections(self) -> List[str]:
        return self.__collections
    
    def __init__(self, database: str = None, collections: List[str] = None):
        super().__init__(1)
        self.database = database
        self.__collections = collections if collections is not None else []

    def serialize(self) -> str:
        raw = {"database": self.database, "collections": self.__collections}
        return dumps(raw)
    
class PostGetAllDocumentIDsRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        assert(isinstance(payload, PostGetAllDocumentIDsRequestBody))
        super().__init__(1, uuid, payload)

    def _create_request(self, url: str) -> Request:
        full_url = urljoin(url, "getAllDocumentIDs")
        return Request("post", full_url)
    
    def _http_name(self) -> str:
        return "v1 POST /getAllDocumentIDs"
    
class SnapshotDocumentEntry:
    def __init__(self, collection: str, id: str):
        self.collection = collection
        self.id = id
    
class PostSnapshotDocumentsRequestBody(TestServerRequestBody):
    def entries(self) -> List[SnapshotDocumentEntry]:
        return self.__entries
    
    def __init__(self, entries: List[SnapshotDocumentEntry] = None):
        super().__init__(1)
        self.__entries = entries if entries is not None else []

    def serialize(self) -> str:
        raw = []
        for e in self.__entries:
            raw.append({"collection": e.collection, "id": e.id})
        
        return dumps(raw)
    
class PostSnapshotDocumentsRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        assert(isinstance(payload, PostSnapshotDocumentsRequestBody))
        super().__init__(1, uuid, payload)

    def _create_request(self, url: str) -> Request:
        full_url = urljoin(url, "snapshotDocuments")
        return Request("post", full_url)
    
    def _http_name(self) -> str:
        return "v1 POST /snapshotDocuments"