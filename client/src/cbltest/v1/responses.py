from typing import Any, Dict, Final, List, Optional, cast

from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorDocumentEntry,
    ReplicatorProgress,
)
from cbltest.jsonhelper import _assert_string_entry, _get_typed, _get_typed_required
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

    def __init__(self, status_code: int, uuid: str, body: dict):
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
        assert isinstance(body, dict), (
            "Invalid PostGetAllDocumentsEntry received (not an object)"
        )
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

    def documents_for_collection(
        self, collection: str
    ) -> List[PostGetAllDocumentsEntry]:
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


class ValueOrMissing:
    def __init__(self, value: Optional[Any] = None, exists: bool = False):
        self.value = value
        self.exists = exists if value is None else True


class PostVerifyDocumentsResponse(TestServerResponse):
    """
    A POST /verifyDocuments response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "result": true,
            "description": "What went wrong if false"
        }
    """

    __result_key: Final[str] = "result"
    __description_key: Final[str] = "description"
    __expected_key: Final[str] = "expected"
    __actual_key: Final[str] = "actual"
    __document_key: Final[str] = "document"

    @property
    def result(self) -> bool:
        """Gets the result of the verification"""
        return self.__result

    @property
    def description(self) -> Optional[str]:
        """Gets the description of what went wrong if result is false"""
        return self.__description

    @property
    def expected(self) -> ValueOrMissing:
        """Gets the expected value of the faulty keypath, if applicable"""
        return self.__expected

    @property
    def actual(self) -> ValueOrMissing:
        """Gets the actual value of the faulty keypath, if applicable"""
        return self.__actual

    @property
    def document(self) -> Optional[Dict[str, Any]]:
        """Gets the document body of the document with the faulty keypath, if applicable"""
        return self.__document

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "verifyDocuments")
        if self.__result_key not in body:
            return

        self.__result = _get_typed_required(body, self.__result_key, bool)
        self.__description = _get_typed(body, self.__description_key, str)
        if self.__expected_key not in body:
            self.__expected = ValueOrMissing()
        else:
            self.__expected = ValueOrMissing(body.get(self.__expected_key), True)

        if self.__actual_key not in body:
            self.__actual = ValueOrMissing()
        else:
            self.__actual = ValueOrMissing(body.get(self.__actual_key), True)

        self.__document = _get_typed(body, self.__document_key, Dict[str, Any])


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
                    "flags": ["REMOVED"],
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
        if self.__activity_key not in body:
            return

        self.__activity = ReplicatorActivityLevel[
            cast(str, body.get(self.__activity_key)).upper()
        ]
        self.__progress = ReplicatorProgress(cast(dict, body.get(self.__progress_key)))
        self.__replicator_error = ErrorResponseBody.create(
            body.get(self.__replicator_error_key)
        )
        docs = _get_typed(body, self.__documents_key, list)
        self.__documents = (
            [ReplicatorDocumentEntry(d) for d in docs] if docs is not None else []
        )


class PostPerformMaintenanceResponse(TestServerResponse):
    """
    A POST /performMaintenance response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "performMaintenance")


class PostNewSessionResponse(TestServerResponse):
    """
    A POST /newSession response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "newSession")


class PostRunQueryResponse(TestServerResponse):
    """
    A POST /runQuery response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "results": [
                {...},
                {...},
            ]
        }
    """

    __results_key: Final[str] = "results"

    @property
    def results(self) -> List[Dict]:
        return self.__results

    def __init__(self, status_code: int, uuid: str, body: Dict):
        super().__init__(status_code, uuid, 1, body, "runQuery")
        if self.__results_key not in body:
            return

        results = _get_typed_required(body, self.__results_key, list)
        self.__results = [dict(e) for e in results] if results is not None else []


class PostGetDocumentResponse(TestServerResponse):
    """
    A POST /getDocument response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)

    Example Body::

        {
            "_id": "doc1",
            "_revs": "17f4ed7b51a50000@MlAW1NbbT8KcTRO8oPnpgw, 17f4ed7b42a70000@ScJAVJf3TdOUanAcByIcXg",
            "foo": "bar
        }
    """

    @property
    def raw_body(self) -> Dict:
        """The raw return value from the server (containing id, revs, and body)"""
        return self.__body

    def __init__(self, status_code: int, uuid: str, body: Dict):
        super().__init__(status_code, uuid, 1, body, "getDocument")
        self.__body = body


class PostLogResponse(TestServerResponse):
    """
    A POST /log response as specified in version 1 of the
    [spec](https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml)
    """

    def __init__(self, status_code: int, uuid: str, body: dict):
        super().__init__(status_code, uuid, 1, body, "log")
