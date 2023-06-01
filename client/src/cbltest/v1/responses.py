from enum import Enum
from typing import Final, List, cast
from cbltest.responses import ErrorResponseBody, TestServerResponse

# Like the requests file, this file also follows the convention that all of the 
# received responses are classes that end in 'Response'.  However, unlike the
# requests, there is no need to have a separate body class since the response
# bodies are immutable.  Their properties are just added to the class itself.
# However, since request factory returns the base class, the convention is that
# the Response for a given request is just that class name with the 'Request'
# replaced with 'Response'.  For example, PostResetRequest will have a response
# type of PostResetResponse.

class PostResetResponse(TestServerResponse):
    """
    A POST /reset response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """
    def __init__(self, request_id: int, status_code: int, uuid:str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "reset")
    
class PostGetAllDocumentIDsResponse(TestServerResponse):
    """
    A POST /getAllDocumentIDs response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "catalog.cloths": [
                "c001",
                "c002"
            ],
            "catalog.shoes": [
                "s001",
                "s002",
                "s003"
            ]
        }
    """

    @property
    def collection_keys(self) -> List[str]:
        """Gets all the collections that are specified in the response"""
        return self.__payload.keys()
    
    def documents_for_collection(self, collection: str) -> List[str]:
        """
        Gets the document IDs contained in the specified collection

        :param collection: The collection to return document IDs from
        """
        return self.__payload.get(collection)
    
    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "getAllDocumentIDs")
        self.__payload = body

class PostUpdateDatabaseResponse(TestServerResponse):
    """
    A POST /updateDatabase response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """
    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "updateDatabase")
    
class PostSnapshotDocumentsResponse(TestServerResponse):
    """
    A POST /snapshotDocuments response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "id": "123e0000-e89b-12d3-a456-426614174000"
        }
    """

    __id_key: Final[str] = "id"

    @property
    def snapshot_id(self) -> str:
        """Gets the ID of the snapshot that was created"""
        return self.__snapshot_id

    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "snapshotDocuments")
        self.__snapshot_id = cast(str, body.get(self.__id_key))
    
class PostVerifyDocumentsResponse(TestServerResponse):
    """
    A POST /verifyDocuments response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "result": true
        }
    """
    __result_key: Final[str] = "result"

    @property
    def result(self) -> bool:
        "Gets the result of the verification"
        return self.__result
    
    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "verifyDocuments")
        self.__result = cast(bool, body.get(self.__result_key))
    
class PostStartReplicatorResponse(TestServerResponse):
    """
    A POST /startReplicator response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "id": "123e0000-e89b-12d3-a456-426614174000"
        }
    """

    __id_key: Final[str] = "id"
    
    @property
    def replicator_id(self) -> str:
        """Gets the ID of the replicator that was started"""
        return self.__replicator_id

    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "startReplicator")
        self.__replicator_id = cast(str, body.get(self.__id_key))

class ReplicatorActivityLevel(Enum):
    """An enum representing the activity level of a replicator"""

    STOPPED = "STOPPED"
    """The replicator is stopped and will no longer perform any action"""

    OFFLINE = "OFFLINE"
    """The replicator is unable to connect to the remote endpoint and will try
    again later"""

    CONNECTING = "CONNECTING"
    """The replicator is establishing a connection to the remote endpoint"""

    IDLE = "IDLE"
    """The replicator is idle and waiting for more information"""

    BUSY = "BUSY"
    """The replicator is actively processing information"""

    def __str__(self) -> str:
        return self.value

class ReplicatorProgress:
    """A class representing the progress of a replicator in terms of units and documents complete"""

    __complete_key: Final[str] = "complete"
    __document_count_key: Final[str] = "documentCount"

    @property
    def complete(self) -> int:
        """Gets the number of units completed so far"""
        return self.__complete
    
    @property
    def document_count(self) -> int:
        """Gets the number of documents processed so far"""
        return self.__document_count
    
    def __init__(self, body: dict) -> None:
        assert(isinstance(body, dict))
        self.__complete = cast(int, body.get(self.__complete_key))
        self.__document_count = cast(int, body.get(self.__document_count_key))
        assert(isinstance(self.__complete, int))
        assert(isinstance(self.__document_count, int))

class ReplicatorDocumentEntry:
    """A class representing the status of a replicated document"""

    __collection_key: Final[str] = "collection"
    __document_id_key: Final[str] = "documentID"
    __is_push_key: Final[str] = "isPush"
    __flags_key: Final[str] = "flags"
    __error_key: Final[str] = "error"

    @property
    def collection(self) -> str:
        """Gets the collection that the document belongs to"""
        return self.__collection
    
    @property
    def document_id(self) -> str:
        """Gets the ID of the document"""
        return self.__document_id
    
    @property
    def is_push(self) -> bool:
        """Gets whether the document was pushed or pulled"""
        return self.__is_push
    
    @property
    def flags(self) -> int:
        """Gets the flags that were set on the document when it was replicated"""
        return self.__flags
    
    @property
    def error(self) -> ErrorResponseBody:
        """Gets the error that prevented the document from being replicated, if any"""
        return self.__error

    def __init__(self, body: dict) -> None:
        assert(isinstance(body, dict))
        self.__collection = cast(str, body.get(self.__collection_key))
        assert(self.__collection is not None)
        self.__document_id = cast(str, body.get(self.__document_id_key))
        assert(self.__document_id is not None)
        self.__is_push = cast(bool, body.get(self.__is_push_key))
        self.__flags = cast(int, body.get(self.__flags_key))
        self.__error = ErrorResponseBody.create(body.get(self.__error_key))


class PostGetReplicatorStatusResponse(TestServerResponse):
    """
    A POST /getReplicatorStatus response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "activity": "STOPPED",
            "progress": {
                "complete": 0,
                "documentCount": 0
            },
            "documents": [
                {
                    "collection": "store.cloths",
                    "documentID": "doc1",
                    "isPush": true,
                    "flags": 2,
                    "error": {
                        "domain": 1,
                        "code": 1,
                        "message": "This is an error"
                    }
                }
            ],
            "error": {
                "domain": 1,
                "code": 1,
                "message": "This is an error"
            }
        }
    """

    __activity_key: Final[str] = "activity"
    __progress_key: Final[str] = "progress"
    __replicator_error_key: Final[str] = "error"
    __documents_key: Final[str] = "documents"

    @property
    def activity(self) -> ReplicatorActivityLevel:
        """Gets the activity level of the replicator"""
        return self.__activity
    
    @property
    def progress(self) -> ReplicatorProgress:
        """Gets the current progress of the replicator"""
        return self.__progress
    
    @property
    def replicator_error(self) -> ErrorResponseBody:
        """Gets the error that occurred during replication, if any"""
        return self.__replicator_error
    
    @property
    def documents(self) -> List[ReplicatorDocumentEntry]:
        """Gets the unseen list of documents replicated previously.  Note
        that once viewed it will be cleared"""
        return self.__documents

    def __init__(self, request_id: int, status_code: int, uuid: str, body: dict):
        super().__init__(request_id, status_code, uuid, 1, body, "getReplicatorStatus")
        self.__activity = ReplicatorActivityLevel[cast(str, body.get(self.__activity_key)).upper()]
        self.__progress = ReplicatorProgress(cast(dict, body.get(self.__progress_key)))
        self.__replicator_error = ErrorResponseBody.create(body.get(self.__replicator_error_key))
        self.__documents = [ReplicatorDocumentEntry(d) for d in body.get(self.__documents_key)]
