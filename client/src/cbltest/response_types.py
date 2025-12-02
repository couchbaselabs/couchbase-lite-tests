from abc import ABC, abstractmethod
from typing import Any, Final, cast

from cbltest.api.error_types import ErrorResponseBody
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorDocumentEntry,
    ReplicatorProgress,
)
from cbltest.jsonhelper import _assert_string_entry, _get_typed


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


class PostGetAllDocumentsResponseMethods(ABC):
    @property
    @abstractmethod
    def collection_keys(self) -> list[str]:
        """Gets all the collections that are specified in the response"""
        pass

    @abstractmethod
    def documents_for_collection(
        self, collection: str
    ) -> list[PostGetAllDocumentsEntry]:
        """
        Gets the documents contained in the specified collection

        :param collection: The collection to return documents from
        """
        pass


class PostSnapshotDocumentsResponseMethods(ABC):
    @property
    @abstractmethod
    def snapshot_id(self) -> str:
        """Gets the ID of the snapshot that was created"""
        pass


class ValueOrMissing:
    def __init__(self, value: Any | None = None, exists: bool = False):
        self.value = value
        self.exists = exists if value is None else True


class PostVerifyDocumentsResponseMethods(ABC):
    @property
    @abstractmethod
    def result(self) -> bool:
        """Gets the result of the verification"""
        pass

    @property
    @abstractmethod
    def description(self) -> str | None:
        """Gets the description of what went wrong if result is false"""
        pass

    @property
    @abstractmethod
    def expected(self) -> ValueOrMissing:
        """Gets the expected value of the faulty keypath, if applicable"""
        pass

    @property
    @abstractmethod
    def actual(self) -> ValueOrMissing:
        """Gets the actual value of the faulty keypath, if applicable"""
        pass

    @property
    @abstractmethod
    def document(self) -> dict[str, Any] | None:
        """Gets the document body of the document with the faulty keypath, if applicable"""
        pass


class PostStartReplicatorResponseMethods(ABC):
    @property
    @abstractmethod
    def replicator_id(self) -> str:
        """Gets the ID of the started replicator"""
        pass


class ReplicatorStatusBody:
    """
    A class representing the body of a replicator status response.
    This is used to encapsulate the common properties of a replicator status.
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
    def replicator_error(self) -> ErrorResponseBody | None:
        """Gets the error that occurred during replication, if any"""
        return self.__replicator_error

    @property
    def documents(self) -> list[ReplicatorDocumentEntry]:
        """Gets the unseen list of documents replicated previously.  Note
        that once viewed it will be cleared"""
        return self.__documents

    def __init__(self, body: dict):
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


class PostGetReplicatorStatusResponseMethods(ABC):
    @property
    @abstractmethod
    def activity(self) -> ReplicatorActivityLevel:
        """Gets the activity level of the replicator"""
        pass

    @property
    @abstractmethod
    def progress(self) -> ReplicatorProgress:
        """Gets the current progress of the replicator"""
        pass

    @property
    @abstractmethod
    def replicator_error(self) -> ErrorResponseBody | None:
        """Gets the error that occurred during replication, if any"""
        pass

    @property
    @abstractmethod
    def documents(self) -> list[ReplicatorDocumentEntry]:
        """Gets the unseen list of documents replicated previously.  Note
        that once viewed it will be cleared"""
        pass


class PostRunQueryResponseMethods(ABC):
    @property
    @abstractmethod
    def results(self) -> list[dict]:
        """Gets the results of the query"""
        pass


class PostGetDocumentResponseMethods(ABC):
    @property
    @abstractmethod
    def raw_body(self) -> dict:
        """The raw return value from the server (containing id, revs, and body)"""
        pass


class PostStartListenerResponseMethods(ABC):
    @property
    @abstractmethod
    def listener_id(self) -> str:
        """Gets the ID of the listener that was started"""
        pass

    @property
    @abstractmethod
    def port(self) -> int:
        """Gets the port of the listener that was started"""
        pass


class PostStartMultipeerReplicatorResponseMethods(ABC):
    @property
    @abstractmethod
    def replicator_id(self) -> str:
        """Gets the ID of the multipeer replicator that was started"""
        pass


class MultipeerReplicatorStatusEntry:
    """
    A class representing a single entry in the multipeer replicator status response.
    """

    __peer_id_key: Final[str] = "peerID"
    __status_key: Final[str] = "status"

    @property
    def peer_id(self) -> str:
        """Gets the peer ID of the replicator"""
        return self.__peer_id

    @property
    def status(self) -> ReplicatorStatusBody:
        """Gets the status of the replicator"""
        return self.__status

    def __init__(self, body: dict):
        assert isinstance(body, dict), (
            "Invalid MultipeerReplicatorStatusEntry received (not an object)"
        )

        self.__peer_id = _assert_string_entry(body, self.__peer_id_key)
        self.__status = ReplicatorStatusBody(body.get(self.__status_key, {}))


class PostGetMultipeerReplicatorStatusResponseMethods(ABC):
    @property
    @abstractmethod
    def replicators(self) -> list[MultipeerReplicatorStatusEntry]:
        """Gets the list of multipeer replicator status entries"""
        pass
