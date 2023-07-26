from typing import Dict, Final, List, cast, Optional
from cbltest.responses import ErrorResponseBody, TestServerResponse
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorDocumentEntry, ReplicatorProgress

from cbltest.jsonhelper import _assert_string_entry

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
    def __init__(self, status_code: int, uuid:str, body: dict):
        super().__init__(status_code, uuid, 1, body, "reset")

class PostGetAllDocumentsEntry:
    __id_key: Final[str] = "id"
    __rev_key: Final[str] = "rev"

    @property
    def id(self) -> str:
        return self.__id
    
    @property
    def rev(self) -> str:
        return self.__rev

    def __init__(self, body: dict):
        assert isinstance(body, dict), "Invalid PostGetAllDocumentsEntry received (not an object)"
        self.__id = _assert_string_entry(body, self.__id_key)
        self.__rev = _assert_string_entry(body, self.__rev_key)
    
class PostGetAllDocumentsResponse(TestServerResponse):
    """
    A POST /getAllDocuments response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "catalog.cloths": [
                {
                    "id": "c1",
                    "rev": "1-abc"
                },
                {
                    "id": "c2",
                    "rev": "1-9ef"
                }
            ],
                "catalog.shoes": [
                {
                    "id": "s1",
                    "rev": "1-ff0"
                },
                {
                    "id": "s2",
                    "rev": "1-e0f"
                }
            ]
        }
    """

    @property
    def collection_keys(self) -> List[str]:
        """Gets all the collections that are specified in the response"""
        return list(self.__payload.keys())
    
    def documents_for_collection(self, collection: str) -> List[PostGetAllDocumentsEntry]:
        """
        Gets the documents contained in the specified collection

        :param collection: The collection to return documents from
        """
        return cast(List[PostGetAllDocumentsEntry], self.__payload.get(collection))
    
    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "getAllDocuments")
        self.__payload: Dict[str, List[PostGetAllDocumentsEntry]] = {}
        for k in body:
            v = body[k]
            self.__payload[k] = []
            for entry in v:
                self.__payload[k].append(PostGetAllDocumentsEntry(entry))

class PostUpdateDatabaseResponse(TestServerResponse):
    """
    A POST /updateDatabase response as specified in version 1 of the 
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """
    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "updateDatabase")
    
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

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "snapshotDocuments")
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
    
    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "verifyDocuments")
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

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "startReplicator")
        self.__replicator_id = cast(str, body.get(self.__id_key))

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
    def replicator_error(self) -> Optional[ErrorResponseBody]:
        """Gets the error that occurred during replication, if any"""
        return self.__replicator_error
    
    @property
    def documents(self) -> List[ReplicatorDocumentEntry]:
        """Gets the unseen list of documents replicated previously.  Note
        that once viewed it will be cleared"""
        return self.__documents

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "getReplicatorStatus")
        if not self.__activity_key in body:
            return
        
        self.__activity = ReplicatorActivityLevel[cast(str, body.get(self.__activity_key)).upper()]
        self.__progress = ReplicatorProgress(cast(dict, body.get(self.__progress_key)))
        self.__replicator_error = ErrorResponseBody.create(body.get(self.__replicator_error_key))
        if self.__documents_key in body:
            docs = body.get(self.__documents_key)
            assert isinstance(docs, dict)
            self.__documents = [ReplicatorDocumentEntry(d) for d in cast(dict, docs)]
