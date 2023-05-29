from enum import Enum
from json import dumps
from typing import Final, List, cast
from ..responses import ErrorResponseBody, TestServerResponse

class PostResetResponse(TestServerResponse):
    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "reset")
    
class PostGetAllDocumentIDsResponse(TestServerResponse):
    @property
    def collection_keys(self) -> List[str]:
        return self.__payload.keys()
    
    def documents_for_collection(self, collection: str) -> List[str]:
        return self.__payload.get(collection)
    
    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "getAllDocumentIDs")
        self.__payload = body

class PostUpdateDatabaseResponse(TestServerResponse):
    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "updateDatabase")
    
class PostSnapshotDocumentsResponse(TestServerResponse):
    __id_key: Final[str] = "id"

    @property
    def snapshot_id(self) -> str:
        return self.__snapshot_id

    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "snapshotDocuments")
        self.__snapshot_id = cast(str, body.get(PostSnapshotDocumentsResponse.__id_key))
    
class PostVerifyDocumentsResponse(TestServerResponse):
    __result_key: Final[str] = "result"

    @property
    def result(self) -> str:
        return self.__result
    
    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "verifyDocuments")
        self.__result = cast(str, body.get(PostVerifyDocumentsResponse.__result_key))
    
class PostStartReplicatorResponse(TestServerResponse):
    __id_key: Final[str] = "id"
    
    @property
    def replicator_id(self) -> str:
        return self.__replicator_id

    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "startReplicator")
        self.__replicator_id = cast(str, body.get(PostStartReplicatorResponse.__id_key))

class ReplicatorActivityLevel(Enum):
    STOPPED = "STOPPED"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    IDLE = "IDLE"
    BUSY = "BUSY"

    def __str__(self) -> str:
        return self.value

class ReplicatorProgress:
    __complete_key: Final[str] = "complete"
    __document_count_key: Final[str] = "documentCount"

    @property
    def complete(self) -> int:
        return self.__complete
    
    @property
    def document_count(self) -> int:
        return self.__document_count
    
    def __init__(self, body: dict) -> None:
        assert(isinstance(body, dict))
        self.__complete = cast(int, body.get(ReplicatorProgress.__complete_key))
        self.__document_count = cast(int, body.get(ReplicatorProgress.__document_count_key))
        assert(isinstance(self.__complete, int))
        assert(isinstance(self.__document_count, int))

class PostGetReplicatorStatusResponse(TestServerResponse):
    __activity_key: Final[str] = "activity"
    __progress_key: Final[str] = "progress"
    __replicator_error_key: Final[str] = "error"

    @property
    def activity(self) -> ReplicatorActivityLevel:
        return self.__activity
    
    @property
    def progress(self) -> ReplicatorProgress:
        return self.__progress
    
    @property
    def replicator_error(self) -> ErrorResponseBody:
        return self.__replicator_error

    def __init__(self, request_id: int, status_code: int, body: dict):
        super().__init__(request_id, status_code, 1, body, "getReplicatorStatus")
        self.__activity = ReplicatorActivityLevel[cast(str, body.get(PostGetReplicatorStatusResponse.__activity_key)).upper()]
        self.__progress = ReplicatorProgress(cast(dict, body.get(PostGetReplicatorStatusResponse.__progress_key)))
        self.__replicator_error = ErrorResponseBody.create(body.get(PostGetReplicatorStatusResponse.__replicator_error_key))
        